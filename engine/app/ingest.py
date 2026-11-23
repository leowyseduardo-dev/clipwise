from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .config import settings
from .sources import PLATFORM_LABELS, source_platform
from .context import source_meta_from_info
from .utils import MediaError, probe_media, run_ffmpeg

logger = logging.getLogger(__name__)

_ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


class IngestError(RuntimeError):
    """Raised when a source video cannot be imported."""


def validate_youtube_url(url: str) -> str:
    candidate = (url or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise IngestError("El enlace debe comenzar por http:// o https://.")
    try:
        platform = source_platform(candidate)
    except ValueError as exc:
        raise IngestError(str(exc)) from exc
    host = parsed.hostname or ""
    if platform != "youtube":
        raise IngestError("El enlace no es de YouTube.")
    if host not in _ALLOWED_HOSTS:
        raise IngestError("Solo se admiten enlaces de YouTube. Para otras fuentes, sube el archivo.")
    path = parsed.path or ""
    if host.endswith("youtu.be"):
        if not path.strip("/"):
            raise IngestError("El enlace de YouTube no contiene un video.")
    else:
        query = parse_qs(parsed.query)
        valid = (
            (path == "/watch" and bool(query.get("v")))
            or path.startswith("/shorts/")
            or path.startswith("/embed/")
            or path.startswith("/live/")
        )
        if not valid:
            raise IngestError("El enlace no apunta a un video de YouTube.")
    return candidate


def validate_source_url(url: str) -> str:
    """Accept individual videos/clips; channels belong in the live panel."""
    candidate = (url or "").strip()
    try:
        platform = source_platform(candidate)
    except ValueError as exc:
        raise IngestError(str(exc)) from exc
    if platform == "youtube":
        return validate_youtube_url(candidate)
    # Reuse the installed extractor's URL grammar, so validation stays aligned
    # with the downloader (VODs, share links, embedded clips and legacy links).
    from yt_dlp.extractor.kick import KickVODIE, KickClipIE
    from yt_dlp.extractor.twitch import TwitchVodIE, TwitchClipsIE
    extractors = (KickVODIE, KickClipIE) if platform == "kick" else (TwitchVodIE, TwitchClipsIE)
    if any(extractor.suitable(candidate) for extractor in extractors):
        return candidate
    raise IngestError(
        f"Pega el enlace de una repetición o clip de {PLATFORM_LABELS[platform]}. "
        "Para un canal que está emitiendo, usa la pestaña Directos."
    )


_BOT_CHECK_MARKERS = (
    "sign in to confirm you're not a bot",
    "confirm you're not a bot",
    "use --cookies-from-browser",
    "use --cookies for the authentication",
)
_AUTO_BROWSERS = ("edge", "chrome", "firefox", "brave", "vivaldi", "opera")


def _is_bot_check(message: str) -> bool:
    low = message.lower()
    return any(marker in low for marker in _BOT_CHECK_MARKERS)


_TRANSIENT_ERROR_MARKERS = (
    "failed to resolve",
    "getaddrinfo failed",
    "temporary failure in name resolution",
    "name or service not known",
    "nodename nor servname provided",
    "network is unreachable",
    "no route to host",
    "connection reset",
    "connection aborted",
    "connection refused",
    "timed out",
    "timeout",
    "transport error",
    "eof occurred",
    "remote end closed connection",
    "unable to download api page",
)
_TRANSIENT_ATTEMPTS = 6
_TRANSIENT_MAX_DELAY = 30.0


def _is_transient_error(message: str) -> bool:
    low = message.lower()
    return any(marker in low for marker in _TRANSIENT_ERROR_MARKERS)


def _retry_delay(attempt: int, *, transient: bool) -> float:
    if transient:
        return min(_TRANSIENT_MAX_DELAY, 2.0 * (2**attempt))
    return 1.5 * (attempt + 1)


def _friendly_ytdlp_error(message: str) -> str:
    low = message.lower()
    if "confirm you're not a bot" in low or "sign in to confirm" in low:
        return (
            "YouTube bloqueo temporalmente la descarga anonima (verificacion anti-bot). "
            "Clipwise reintenta automaticamente; si vuelve a fallar, inicia sesion en "
            "YouTube desde tu navegador y reintenta el trabajo, o sube el archivo directamente."
        )
    if "subscriber" in low or "subscription" in low or "sub-only" in low:
        return "Este video requiere una suscripción. Usa una sesión con acceso configurada o sube el archivo."
    if "403" in low or "forbidden" in low:
        return "La plataforma rechazó el acceso al video (403). Reintenta o sube el archivo si dispones de él."
    if "404" in low or "does not exist" in low or "not found" in low:
        return "No se encontró el video. Comprueba el enlace; la repetición o el clip puede haber caducado."
    if "private video" in low:
        return "El video es privado. Solo se admiten videos accesibles publicamente."
    if "sign in" in low or "confirm your age" in low or "login required" in low:
        return (
            "La plataforma pide iniciar sesión o verificar la edad para este video. "
            "Inicia sesion en tu navegador y reintenta, o sube el archivo directamente."
        )
    if "drm" in low:
        return "El video esta protegido con DRM y no se puede procesar."
    if "unavailable" in low or "not available" in low or "removed" in low:
        return "El video no está disponible en la plataforma."
    if "live event" in low or "is live" in low:
        return "Para una emisión en directo, usa la pestaña Directos."
    if "requested format is not available" in low:
        return "La plataforma no ofreció un formato compatible. Reintenta el trabajo o sube el archivo."
    if "cookie" in low:
        return (
            "No se pudieron leer las cookies del navegador. Cierra el navegador y "
            "reintenta, o sube el archivo directamente."
        )
    return f"No se pudo descargar el video: {message[:280]}"


def _browser_cookie_option(value: str) -> dict[str, Any] | None:
    raw = (value or "").strip()
    if not raw:
        return None
    browser, _, profile = raw.partition(":")
    browser = browser.strip().lower()
    if browser not in _AUTO_BROWSERS:
        logger.warning("Navegador no soportado en YTDLP_COOKIES_FROM_BROWSER: %s", browser)
        return None
    return {"cookiesfrombrowser": (browser, profile.strip() or None, None, None)}


def _cookie_option_sets() -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    seen: set[str] = set()

    if settings.ytdlp_cookies:
        path = Path(settings.ytdlp_cookies)
        if path.is_file():
            options.append({"cookiefile": str(path)})
        else:
            logger.warning("YTDLP_COOKIES no existe: %s", path)

    configured = _browser_cookie_option(settings.ytdlp_cookies_from_browser)
    if configured:
        browser = str(configured["cookiesfrombrowser"][0])
        seen.add(browser)
        options.append(configured)

    if settings.ytdlp_auto_cookies:
        for browser in _AUTO_BROWSERS:
            if browser in seen:
                continue
            options.append({"cookiesfrombrowser": (browser, None, None, None)})

    return options


def _auth_label(auth: dict[str, Any]) -> str:
    if "cookiefile" in auth:
        return "archivo de cookies"
    browser = auth.get("cookiesfrombrowser")
    if browser:
        return f"cookies de {browser[0]}"
    return "sin cookies"


def _extract_info(
    yt_dlp: Any,
    url: str,
    opts: dict[str, Any],
    attempts: int = 3,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(max(1, attempts, _TRANSIENT_ATTEMPTS)):
        try:
            with yt_dlp.YoutubeDL({**opts, "skip_download": True}) as ydl:
                return ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            last_error = exc
            transient = _is_transient_error(str(exc))
            retryable = _is_bot_check(str(exc)) or transient
            limit = max(attempts, _TRANSIENT_ATTEMPTS) if transient else max(1, attempts)
            if not retryable or attempt + 1 >= limit:
                raise
            delay = _retry_delay(attempt, transient=transient)
            logger.info(
                "YouTube no respondio%s; reintentando en %.1f s (%d/%d).",
                " (red)" if transient else " (verificacion)",
                delay,
                attempt + 1,
                limit - 1,
            )
            time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise IngestError("No se pudo consultar YouTube.")


def _download_video(
    yt_dlp: Any,
    url: str,
    opts: dict[str, Any],
    attempts: int = 3,
) -> None:
    last_error: Exception | None = None
    for attempt in range(max(1, attempts, _TRANSIENT_ATTEMPTS)):
        try:
            with yt_dlp.YoutubeDL({**opts, "skip_download": False}) as ydl:
                ydl.download([url])
            return
        except yt_dlp.utils.DownloadError as exc:
            last_error = exc
            transient = _is_transient_error(str(exc))
            retryable = _is_bot_check(str(exc)) or transient
            limit = max(attempts, _TRANSIENT_ATTEMPTS) if transient else max(1, attempts)
            if not retryable or attempt + 1 >= limit:
                raise
            delay = _retry_delay(attempt, transient=transient)
            logger.info(
                "YouTube no respondio al descargar%s; reintentando en %.1f s (%d/%d).",
                " (red)" if transient else " (verificacion)",
                delay,
                attempt + 1,
                limit - 1,
            )
            time.sleep(delay)
    if last_error is not None:
        raise last_error


def _ffmpeg_location() -> str | None:
    path = Path(settings.ffmpeg)
    if path.parent == Path("."):
        return None
    return str(path.parent)


def _load_ytdlp() -> Any:
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - dependency is expected
        raise IngestError("yt-dlp no esta instalado en el servidor.") from exc
    return yt_dlp


def _base_options() -> dict[str, Any]:
    base_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
    }
    ffmpeg_location = _ffmpeg_location()
    if ffmpeg_location:
        base_opts["ffmpeg_location"] = ffmpeg_location
    return base_opts


def _download_format(duration: float, *, audio_only: bool = False) -> str:
    if audio_only:
        return "bestaudio[ext=m4a]/bestaudio/best"
    max_height = (
        settings.long_source_height
        if duration >= settings.long_source_seconds
        else 1080
    )
    return (
        f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]"
        f"/bestvideo[height<={max_height}]+bestaudio"
        f"/best[height<={max_height}]/best"
    )


def _progress_hook(
    on_progress: Callable[[float], None] | None,
) -> Callable[[dict[str, Any]], None]:
    def hook(data: dict[str, Any]) -> None:
        if on_progress and data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            if total:
                on_progress(min(99.0, done / total * 100.0))

    return hook


def _validate_source_info(info: dict[str, Any]) -> None:
    if info.get("is_live"):
        raise IngestError("Para una emisión en directo, usa la pestaña Directos.")
    duration = float(info.get("duration") or 0)
    if duration <= 0:
        raise IngestError("No se pudo determinar la duración del video.")
    if duration > settings.max_source_seconds:
        raise IngestError(
            f"El video dura {duration / 60:.0f} minutos; el limite es "
            f"{settings.max_source_seconds / 60:.0f} minutos."
        )


def fetch_source_info(url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read video metadata and return the cookie profile that worked."""
    url = validate_source_url(url)
    yt_dlp = _load_ytdlp()
    base_opts = _base_options()
    auth_options: list[dict[str, Any]] = [{}] + _cookie_option_sets()
    used_auth: dict[str, Any] = {}
    info: dict[str, Any] | None = None
    last_error: Exception | None = None
    bot_check_seen = False

    for auth in auth_options:
        opts = {**base_opts, **auth}
        try:
            candidate = _extract_info(
                yt_dlp,
                url,
                opts,
                attempts=3 if not auth else 2,
            )
        except yt_dlp.utils.DownloadError as exc:
            last_error = exc
            if not _is_bot_check(str(exc)):
                if auth:
                    logger.warning(
                        "No se pudieron usar %s: %s",
                        _auth_label(auth),
                        str(exc)[:300],
                    )
                    continue
                logger.warning("yt-dlp metadata error: %s", exc)
                raise IngestError(_friendly_ytdlp_error(str(exc))) from exc
            bot_check_seen = True
            logger.warning(
                "La plataforma rechazó la extraccion con %s: %s",
                _auth_label(auth),
                str(exc)[:300],
            )
            continue
        except Exception as exc:
            last_error = exc
            if auth:
                logger.warning(
                    "No se pudieron usar %s: %s",
                    _auth_label(auth),
                    str(exc)[:300],
                )
                continue
            raise IngestError(f"No se pudo consultar el video: {exc}") from exc

        if isinstance(candidate, dict):
            info = candidate
            used_auth = auth
            if auth:
                logger.info("La plataforma aceptó %s.", _auth_label(auth))
            break
        last_error = IngestError("La plataforma no devolvió informacion del video.")

    if info is None:
        message = str(last_error) if last_error else "La plataforma no devolvió informacion."
        if bot_check_seen:
            message = (
                "Sign in to confirm you're not a bot. "
                "Use --cookies-from-browser or --cookies for the authentication."
            )
        logger.warning("yt-dlp metadata error: %s", message)
        raise IngestError(_friendly_ytdlp_error(message))

    _validate_source_info(info)
    return info, used_auth


def _run_download(
    yt_dlp: Any,
    url: str,
    opts: dict[str, Any],
    *,
    used_auth: dict[str, Any],
    label: str,
) -> None:
    auth_options: list[dict[str, Any]] = [{}] + _cookie_option_sets()
    download_sets = [used_auth] + [
        auth for auth in auth_options if auth != used_auth
    ]
    last_error: Exception | None = None
    bot_check_seen = False
    for auth in download_sets:
        try:
            _download_video(yt_dlp, url, {**opts, **auth}, attempts=3)
            return
        except yt_dlp.utils.DownloadError as exc:
            last_error = exc
            if not _is_bot_check(str(exc)):
                logger.warning("yt-dlp %s error: %s", label, exc)
                raise IngestError(_friendly_ytdlp_error(str(exc))) from exc
            bot_check_seen = True
            logger.warning(
                "La plataforma rechazó la %s con %s: %s",
                label,
                _auth_label(auth),
                str(exc)[:300],
            )
            continue
        except Exception as exc:
            last_error = exc
            if auth:
                logger.warning(
                    "No se pudo completar la %s con %s: %s",
                    label,
                    _auth_label(auth),
                    str(exc)[:300],
                )
                continue
            raise IngestError(f"La {label} fallo: {exc}") from exc

    message = str(last_error) if last_error else f"La {label} fallo sin detalle."
    if bot_check_seen:
        message = (
            "Sign in to confirm you're not a bot. "
            "Use --cookies-from-browser or --cookies for the authentication."
        )
    logger.warning("yt-dlp %s error: %s", label, message)
    raise IngestError(_friendly_ytdlp_error(message))


def _find_media_file(workdir: Path, stem: str) -> Path | None:
    exact = workdir / f"{stem}.mp4"
    if exact.is_file() and exact.stat().st_size > 0:
        return exact
    candidates = [
        path
        for path in workdir.glob(f"{stem}.*")
        if path.is_file()
        and path.name.startswith(f"{stem}.")
        and path.suffix.lower() not in {".part", ".ytdl", ".temp"}
        # Unmerged format fragments (source.f616.mp4 + source.f140.m4a) are
        # inputs to the merge, never the finished download.
        and not re.search(r"\.f\d+\.", path.name)
        and path.stat().st_size > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_size)


def _remux_to(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(source),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(destination),
        ],
        timeout=1800,
    )
    return destination


def _probe_duration(path: Path) -> float:
    try:
        return float(probe_media(path).get("duration") or 0.0)
    except (MediaError, OSError):
        return 0.0


def find_existing_source(workdir: Path, expected_duration: float) -> Path | None:
    """Return the finished download in workdir when it already covers the
    expected duration, so retries skip both the download and its free-space
    gate."""
    existing = _find_media_file(workdir, "source")
    if (
        existing is not None
        and expected_duration > 0
        and _probe_duration(existing) >= expected_duration - 2.0
    ):
        return existing
    return None


def _download_source_media(
    url: str,
    workdir: Path,
    info: dict[str, Any],
    used_auth: dict[str, Any],
    *,
    audio_only: bool,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    yt_dlp = _load_ytdlp()
    stem = "source_audio" if audio_only else "source"
    duration = float(info.get("duration") or 0)
    # A previous run that died mid-merge leaves source.temp.* / .part debris
    # behind; it is dead weight (GBs for a long stream) and poisons the
    # next attempt's free-space math.
    for stale in workdir.glob(f"{stem}.temp.*"):
        stale.unlink(missing_ok=True)
    for stale in workdir.glob(f"{stem}.*.part"):
        stale.unlink(missing_ok=True)
    for stale in workdir.glob(f"{stem}*.ytdl"):
        stale.unlink(missing_ok=True)
    existing = _find_media_file(workdir, stem)
    if (
        existing is not None
        and duration > 0
        and _probe_duration(existing) >= duration - 2.0
    ):
        logger.info("La fuente ya esta descargada en %s; se reutiliza.", existing.name)
        if audio_only or existing.suffix.lower() == ".mp4":
            return existing
    download_opts: dict[str, Any] = {
        **_base_options(),
        "format": _download_format(duration, audio_only=audio_only),
        "outtmpl": str(workdir / f"{stem}.%(ext)s"),
        "overwrites": True,
        "progress_hooks": [_progress_hook(on_progress)],
        "concurrent_fragment_downloads": 4,
    }
    if audio_only:
        download_opts["noprogress"] = True
    else:
        download_opts["merge_output_format"] = "mp4"

    _run_download(
        yt_dlp,
        url,
        download_opts,
        used_auth=used_auth,
        label="descarga de audio" if audio_only else "descarga del video",
    )

    source = _find_media_file(workdir, stem)
    if source is None:
        kind = "audio" if audio_only else "video"
        raise IngestError(f"La descarga no genero ningun archivo de {kind}.")
    if audio_only or source.suffix.lower() == ".mp4":
        return source

    remuxed = workdir / "source_fixed.mp4"
    try:
        return _remux_to(source, remuxed)
    except MediaError:
        logger.warning("No se pudo remuxear el archivo descargado; se usara el original.")
        return source


def download_source_video(
    url: str,
    workdir: Path,
    info: dict[str, Any],
    used_auth: dict[str, Any],
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    return _download_source_media(
        url,
        workdir,
        info,
        used_auth,
        audio_only=False,
        on_progress=on_progress,
    )


def fetch_source(
    url: str,
    workdir: Path,
    on_progress: Callable[[float], None] | None = None,
) -> tuple[Path, str, dict[str, Any], dict[str, Any]]:
    """Download a supported video the user has the right to process."""
    info, used_auth = fetch_source_info(url)
    source = download_source_video(url, workdir, info, used_auth, on_progress=on_progress)
    title = (info.get("title") or "Video importado").strip()[:200]
    return source, title, source_meta_from_info(info), used_auth


def fetch_source_audio(
    url: str,
    workdir: Path,
    on_progress: Callable[[float], None] | None = None,
    *,
    info: dict[str, Any] | None = None,
    used_auth: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """Download only the audio track for long sources."""
    if info is None or used_auth is None:
        info, used_auth = fetch_source_info(url)
    source = _download_source_media(
        url,
        workdir,
        info,
        used_auth,
        audio_only=True,
        on_progress=on_progress,
    )
    return source, info, used_auth


def download_source_section(
    url: str,
    workdir: Path,
    info: dict[str, Any],
    used_auth: dict[str, Any],
    start: float,
    end: float,
    destination: Path,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Download one clip window without pulling the full source video."""
    url = validate_source_url(url)
    duration = float(info.get("duration") or 0)
    start = max(0.0, float(start))
    end = max(start + 0.5, float(end))
    if duration > 0:
        start = min(start, duration)
        end = min(end, duration)
    if end - start < 0.5:
        raise IngestError("La seccion del clip es demasiado corta para descargarla.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 1024:
        try:
            probe_media(destination)
            return destination
        except MediaError:
            destination.unlink(missing_ok=True)

    stem = destination.stem
    yt_dlp = _load_ytdlp()
    range_start = start
    range_end = end

    def _range(info_dict: dict[str, Any], ydl: Any) -> list[dict[str, Any]]:
        del info_dict, ydl
        return [{"start_time": range_start, "end_time": range_end}]

    download_opts: dict[str, Any] = {
        **_base_options(),
        "format": _download_format(duration, audio_only=False),
        "outtmpl": str(destination.with_name(f"{stem}.%(ext)s")),
        "merge_output_format": "mp4",
        "overwrites": True,
        "progress_hooks": [_progress_hook(on_progress)],
        "download_ranges": _range,
        "force_keyframes_at_cuts": True,
    }
    _run_download(
        yt_dlp,
        url,
        download_opts,
        used_auth=used_auth,
        label=f"descarga de la seccion {start:.1f}-{end:.1f}s",
    )

    source = _find_media_file(destination.parent, stem)
    if source is None:
        raise IngestError("La descarga de la seccion no genero ningun archivo de video.")
    if source.resolve() != destination.resolve():
        try:
            _remux_to(source, destination)
        except MediaError as exc:
            raise IngestError(
                "No se pudo preparar la seccion descargada para el render."
            ) from exc
        if source != destination:
            source.unlink(missing_ok=True)
    try:
        probe_media(destination)
    except MediaError as exc:
        destination.unlink(missing_ok=True)
        raise IngestError("La seccion descargada no se puede reproducir.") from exc
    return destination


def inspect_source(path: Path) -> dict[str, Any]:
    try:
        info = probe_media(path)
    except MediaError as exc:
        raise IngestError(str(exc)) from exc
    if info["duration"] > settings.max_source_seconds:
        raise IngestError(
            f"El video dura {info['duration'] / 60:.0f} minutos; el limite es "
            f"{settings.max_source_seconds / 60:.0f} minutos."
        )
    return info


def prepare_working_copy(
    source: Path,
    workdir: Path,
    info: dict[str, Any],
    on_progress: Callable[[float], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Return a video file OpenCV can decode reliably.

    Rotated phone videos and codecs that OpenCV wheels do not decode are
    transcoded to H.264 with the display rotation baked in.
    """
    working = workdir / "working.mp4"
    if working.exists() and working.stat().st_size > 0:
        try:
            return working, probe_media(working)
        except MediaError:
            working.unlink(missing_ok=True)

    has_video = (
        bool(info.get("video_codec"))
        and int(info.get("width") or 0) > 0
        and int(info.get("height") or 0) > 0
    )
    rotation = abs(int(info.get("rotation") or 0)) % 360
    codec = str(info.get("video_codec") or "").lower()
    needs_transcode = has_video and (
        rotation in (90, 270) or codec not in {"h264", "vp8", "vp9", "av1"}
    )
    if not needs_transcode:
        return source, info

    if on_progress:
        on_progress(0.0)
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(source),
            "-vf",
            "scale=w='min(1920,iw)':h='min(1920,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(working),
        ],
        timeout=6 * 3600,
    )
    if on_progress:
        on_progress(100.0)
    return working, probe_media(working)


# Compatibility for integrations using the original YouTube-only API names.
fetch_youtube_info = fetch_source_info
download_youtube_video = download_source_video
fetch_youtube_audio = fetch_source_audio
download_youtube_section = download_source_section
fetch_youtube = fetch_source
