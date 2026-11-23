"""TikTok grabber: download a TikTok video clean (no watermark) and
optionally publish it straight to YouTube.

Primary path is TikTok's own mobile feed API, which serves the unwatermarked
render for standard videos. If that fails, yt-dlp downloads the watermarked
file and a delogo pass scrubs the known watermark corners.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from .config import settings
from .publishing import _access_token
from .utils import MediaError, probe_media, run_ffmpeg

logger = logging.getLogger(__name__)

AWEME_FEED_URL = "https://api16-normal-c-useast1a.tiktokv.com/aweme/v1/feed/"
AWEME_PARAMS = {
    "iid": "7318518857994389254",
    "device_id": "7318517321748022790",
    "channel": "googleplay",
    "app_name": "musical_ly",
    "version_code": "300904",
    "device_platform": "android",
    "device_type": "ASUS_Z01QD",
    "os_version": "9",
    "aid": "1180",
}
REQUEST_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

GRAB_STEP_WEIGHTS = {"downloading": (5, 60), "cleaning": (60, 80), "publishing": (80, 99)}


class TikTokGrabError(RuntimeError):
    pass


def _grabs_dir() -> Path:
    path = settings.data_dir / "grabs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_aweme_id(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.path.startswith("/video/"):
        match = re.search(r"/video/(\d+)", parsed.path)
        if match:
            return match.group(1)
    for value in parse_qs(parsed.query).get("item_id", []):
        if value.isdigit():
            return value
    match = re.search(r"/(?:video|photo)/(\d+)", url)
    if match:
        return match.group(1)
    raise TikTokGrabError(
        "No se pudo extraer el ID del video de esa URL de TikTok."
    )


def _fetch_aweme(aweme_id: str) -> dict[str, Any]:
    headers = {
        "User-Agent": (
            "TikTok 26.2.0 rv:262018 (ASUS_Z01QD; Android 9; es_US) "
            "musical_ly_2022602040"
        ),
        "Accept": "application/json",
    }
    last_error: Exception | None = None
    for attempt, delay in enumerate((0, 4, 10)):
        if delay:
            time.sleep(delay)
        try:
            response = requests.get(
                AWEME_FEED_URL,
                params={**AWEME_PARAMS, "aweme_id": aweme_id},
                headers=headers,
                timeout=30,
            )
            if response.status_code == 429:
                # Rate limited: back off and retry before giving up.
                last_error = TikTokGrabError(
                    "TikTok limito las peticiones temporalmente (429)."
                )
                continue
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            last_error = TikTokGrabError(f"TikTok no respondio: {exc}")
            continue
        except ValueError as exc:
            raise TikTokGrabError("TikTok devolvio una respuesta no valida.") from exc

        aweme_list = payload.get("aweme_list") or []
        if aweme_list:
            return aweme_list[0]
        last_error = TikTokGrabError(
            "TikTok no devolvio datos para ese video (puede ser privado o haberse borrado)."
        )
    raise last_error or TikTokGrabError("TikTok no respondio.")


def _aweme_meta(aweme: dict[str, Any]) -> dict[str, Any]:
    author = aweme.get("author") or {}
    music = aweme.get("music") or {}
    return {
        "title": str(aweme.get("desc") or "").strip(),
        "author": str(author.get("nickname") or author.get("unique_id") or "").strip(),
        "duration_ms": int((aweme.get("video") or {}).get("duration") or 0),
        "music": str(music.get("title") or "").strip(),
        "cover": str(((aweme.get("video") or {}).get("cover") or {}).get("url_list", [""])[0]),
    }


def _download_clean(aweme: dict[str, Any], destination: Path) -> None:
    video = aweme.get("video") or {}
    urls: list[str] = []
    for key in ("play_addr", "download_addr"):
        addr = video.get(key) or {}
        urls.extend(addr.get("url_list") or [])
    urls = [u for u in urls if u]
    if not urls:
        raise TikTokGrabError("TikTok no expuso ninguna URL de video para ese enlace.")
    last_error: Exception | None = None
    for url in urls:
        try:
            with requests.get(
                url,
                headers={"User-Agent": REQUEST_UA},
                stream=True,
                timeout=120,
            ) as response:
                response.raise_for_status()
                with destination.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 16):
                        if chunk:
                            handle.write(chunk)
            if destination.stat().st_size > 0:
                return
        except requests.RequestException as exc:
            last_error = exc
    raise TikTokGrabError(f"No se pudo descargar el video: {last_error}")


def _download_ytdlp(url: str, destination: Path) -> dict[str, Any]:
    import yt_dlp

    opts = {
        "outtmpl": str(destination.with_suffix(".%(ext)s")),
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "overwrites": True,
        "noprogress": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
    }
    info: dict[str, Any] = {}
    last_error: Exception | None = None
    for attempt, delay in enumerate((0, 5, 15)):
        if delay:
            time.sleep(delay)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True) or {}
            last_error = None
            break
        except yt_dlp.utils.DownloadError as exc:
            last_error = exc
            info = {}
            if attempt < 2:
                logger.warning(
                    "yt-dlp fallo (intento %d/3); reintentando en %d s.",
                    attempt + 1,
                    (5, 15, 0)[attempt],
                )
    if last_error is not None:
        raise TikTokGrabError(f"La descarga alternativa fallo: {last_error}") from last_error
    if not destination.exists() or destination.stat().st_size == 0:
        # yt-dlp may have written a different extension next to the target.
        for candidate in destination.parent.glob(destination.stem + ".*"):
            if candidate.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov"):
                candidate.replace(destination)
                break
    if not destination.exists() or destination.stat().st_size == 0:
        raise TikTokGrabError("La descarga alternativa no genero ningun archivo.")
    return info


def _meta_from_ytdlp(info: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    """Fill grab metadata from yt-dlp when the TikTok API gave us nothing."""
    meta = dict(fallback)
    if not meta.get("title"):
        desc = info.get("description") or info.get("title") or ""
        meta["title"] = re.sub(r"\s+", " ", str(desc)).strip()
    if not meta.get("author"):
        author = str(info.get("uploader") or info.get("channel") or "").strip()
        meta["author"] = author.lstrip("@")
    return meta


def _delogo_watermark(source: Path, destination: Path) -> bool:
    """Scrub the moving TikTok watermark from both corners it jumps between.

    The watermark rests top-left or bottom-right and swaps position every
    ~2.5 seconds, so two static boxes cover both resting spots. delogo takes
    integer coordinates only, so the boxes are computed from the real
    dimensions with ffprobe instead of expressions like iw-224.
    """
    try:
        media = probe_media(source)
        width, height = media["width"], media["height"]
        if width <= 0 or height <= 0:
            return False
        box_w, box_h = min(220, width // 4), 64
        tl_x, tl_y = 24, 64
        br_x = max(0, width - box_w - 24)
        br_y = max(0, height - box_h - 32)
        vf = (
            f"delogo=x={tl_x}:y={tl_y}:w={box_w}:h={box_h}:show=0,"
            f"delogo=x={br_x}:y={br_y}:w={box_w}:h={box_h}:show=0"
        )
        run_ffmpeg(
            [
                "-y",
                "-i",
                str(source),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "copy",
                str(destination),
            ],
            timeout=1800,
        )
    except MediaError:
        return False
    return destination.exists() and destination.stat().st_size > 0


def _grab_out(grab: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": grab["id"],
        "url": grab["url"],
        "status": grab["status"],
        "stage": grab["stage"],
        "progress": grab["progress"],
        "error": grab["error"],
        "title": grab.get("title") or "",
        "author": grab.get("author") or "",
        "clean": grab.get("clean", False),
        "file": grab.get("file"),
        "youtube_url": grab.get("youtube_url"),
        "auto_publish": grab.get("auto_publish", False),
        "created_at": grab.get("created_at"),
    }


def load_grab(grab_id: str) -> dict[str, Any] | None:
    path = _grabs_dir() / f"{grab_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_grabs() -> list[dict[str, Any]]:
    grabs = []
    for path in sorted(_grabs_dir().glob("*.json"), reverse=True):
        try:
            grabs.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return [_grab_out(grab) for grab in grabs]


def _save(grab: dict[str, Any]) -> None:
    path = _grabs_dir() / f"{grab['id']}.json"
    # Write next to the target and swap atomically: a full disk during a
    # plain write_text leaves a zero-byte JSON and the grab disappears.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(grab, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def reset_stale_grabs() -> int:
    """Mark grabs interrupted by an app stop as failed so they can be retried."""
    stale = 0
    for path in _grabs_dir().glob("*.json"):
        try:
            grab = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if grab.get("status") not in ("queued", "processing", "publishing"):
            continue
        grab.update(
            status="failed",
            stage="",
            error="La descarga se interrumpio al cerrar la aplicacion. Reintenta.",
        )
        _save(grab)
        stale += 1
    return stale


def _update(grab_id: str, **fields: Any) -> dict[str, Any]:
    grab = load_grab(grab_id) or {"id": grab_id}
    grab.setdefault("id", grab_id)
    grab.update(fields)
    _save(grab)
    return grab


def _split_hashtags(desc: str) -> tuple[str, list[str]]:
    """Split a TikTok description into clean text and its #hashtags."""
    hashtags = re.findall(r"#\w+", desc)
    clean = re.sub(r"#\w+", "", desc)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean, hashtags


def _youtube_request(method: str, url: str, *, attempts: int = 4, **kwargs: Any) -> requests.Response:
    """HTTP call that survives DNS blips and dropped connections."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return requests.request(method, url, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(3 * (attempt + 1))
    raise TikTokGrabError(f"YouTube no respondio por red: {last}")


def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Direct resumable YouTube upload for grab files (no clip records)."""
    token = _access_token("youtube")
    size = video_path.stat().st_size
    snippet: dict[str, Any] = {
        "title": title[:100],
        "description": description[:4900],
        "categoryId": "24",
    }
    if tags:
        snippet["tags"] = tags[:40]
    body = {
        "snippet": snippet,
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    init = _youtube_request(
        "POST",
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        },
        timeout=60,
    )
    if init.status_code >= 400:
        raise TikTokGrabError(
            f"YouTube rechazo la creacion del video (HTTP {init.status_code})."
        )
    upload_url = init.headers.get("Location")
    if not upload_url:
        raise TikTokGrabError("YouTube no devolvio la URL de subida.")
    payload: dict[str, Any] | None = None
    with video_path.open("rb") as handle:
        offset = 0
        chunk_size = 4 << 20
        retries = 0
        while offset < size:
            handle.seek(offset)
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            response = _youtube_request(
                "PUT",
                upload_url,
                data=chunk,
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{offset + len(chunk) - 1}/{size}",
                },
                timeout=600,
            )
            if response.status_code in (200, 201):
                payload = response.json()
                break
            if response.status_code == 308:
                # Expected after every non-final chunk: continue from the
                # acknowledged offset taken from the Range header.
                next_offset = offset + len(chunk)
                rng = response.headers.get("Range")
                if rng and "-" in rng:
                    try:
                        next_offset = int(rng.rsplit("-", 1)[1]) + 1
                    except ValueError:
                        pass
                offset = max(next_offset, offset + len(chunk))
                retries = 0
                continue
            if response.status_code in (500, 502, 503, 504):
                retries += 1
                if retries > 4:
                    raise TikTokGrabError(
                        f"YouTube abandono la subida (HTTP {response.status_code})."
                    )
                time.sleep(2 * retries)
                continue
            raise TikTokGrabError(
                f"YouTube rechazo la subida (HTTP {response.status_code})."
            )
        if payload is None and offset >= size:
            # All bytes acknowledged via 308: finalize with an empty PUT so
            # YouTube returns the created video resource.
            response = _youtube_request(
                "PUT",
                upload_url,
                data=b"",
                headers={
                    "Content-Length": "0",
                    "Content-Range": f"bytes */{size}",
                },
                timeout=600,
            )
            if response.status_code in (200, 201):
                payload = response.json()
            else:
                raise TikTokGrabError(
                    f"YouTube no confirmo la subida final (HTTP {response.status_code})."
                )
    if not payload or not payload.get("id"):
        raise TikTokGrabError("YouTube no devolvio el ID del video subido.")
    return {
        "youtube_id": payload.get("id"),
        "youtube_url": f"https://www.youtube.com/watch?v={payload.get('id')}",
    }


MIN_FREE_MB = int(os.getenv("MIN_FREE_MB", "300"))


def _ensure_free_space() -> None:
    free_mb = shutil.disk_usage(settings.data_dir).free // (1024 * 1024)
    if free_mb < MIN_FREE_MB:
        raise TikTokGrabError(
            f"No hay espacio libre suficiente: quedan {free_mb} MB. "
            f"Libera al menos {MIN_FREE_MB} MB y reintenta."
        )


def _grab_worker(grab_id: str, url: str, title_override: str, auto_publish: bool) -> None:
    workdir = settings.tmp_dir / f"tiktok-{grab_id}"
    # A previous run that ran out of disk leaves a .part behind; start clean.
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)
    raw_path = workdir / "raw.mp4"
    final_dir = _grabs_dir() / grab_id
    final_dir.mkdir(parents=True, exist_ok=True)
    final_path: Path | None = None
    clean = False
    try:
        _update(grab_id, status="processing", stage="downloading", progress=5, error=None)
        _ensure_free_space()
        aweme_id = extract_aweme_id(url)
        meta = {"title": "", "author": "", "duration_ms": 0, "music": "", "cover": ""}
        aweme: dict[str, Any] | None = None
        try:
            aweme = _fetch_aweme(aweme_id)
            meta = _aweme_meta(aweme)
            _update(grab_id, title=meta["title"], author=meta["author"])
        except TikTokGrabError:
            logger.warning(
                "La API de TikTok no esta disponible para %s; se descarga por yt-dlp.",
                grab_id,
            )
        try:
            if aweme is not None:
                _download_clean(aweme, raw_path)
                clean = True
            else:
                meta = _meta_from_ytdlp(_download_ytdlp(url, raw_path), meta)
        except TikTokGrabError:
            logger.warning(
                "La via limpia fallo para %s; se descarga por yt-dlp.", grab_id
            )
            meta = _meta_from_ytdlp(_download_ytdlp(url, raw_path), meta)
        if meta.get("title") or meta.get("author"):
            _update(grab_id, title=meta.get("title") or "", author=meta.get("author") or "")

        raw_desc = re.sub(r"\s+", " ", meta["title"]).strip()
        if raw_desc.lower() == "video de tiktok":
            raw_desc = ""
        clean_desc, hashtags = _split_hashtags(raw_desc)
        if title_override.strip():
            title = title_override.strip()
        elif raw_desc:
            title = raw_desc[:100]
        else:
            vid = re.search(r"/video/(\d+)", url)
            tail = vid.group(1)[-6:] if vid else grab_id[:6]
            title = f"@{meta['author']} · {tail}" if meta.get("author") else f"TikTok · {tail}"
        _update(
            grab_id,
            status="processing",
            stage="cleaning",
            progress=60,
        )
        final_path = final_dir / "video.mp4"
        if clean:
            raw_path.replace(final_path)
        else:
            if _delogo_watermark(raw_path, final_path):
                _update(grab_id, watermark_removed=True)
            else:
                raise TikTokGrabError("No se pudo eliminar la marca de agua del video.")

        import datetime

        _update(
            grab_id,
            file=str(final_path),
            clean=clean,
            title=title,
            progress=80,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        if auto_publish:
            _update(grab_id, status="publishing", stage="publishing", progress=85)
            hashtags_line = " ".join(hashtags[:15]) if hashtags else "#tiktok #viral #shorts"
            desc_lines = [raw_desc] if raw_desc else []
            if meta["author"]:
                desc_lines.append(f"Video de @{meta['author']}")
            desc_lines.append(hashtags_line)
            description = "\n".join(desc_lines)
            tags = [tag.lstrip("#") for tag in hashtags[:15]]
            result = upload_to_youtube(final_path, title, description, tags)
            _update(
                grab_id,
                youtube_url=result["youtube_url"],
                progress=99,
            )
        _update(grab_id, status="ready", stage="", progress=100)
    except Exception as exc:
        logger.error("El grab de TikTok %s fallo: %s", grab_id, exc)
        _update(grab_id, status="failed", stage="", error=str(exc)[:300])
    finally:
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass


def start_grab(url: str, title: str, auto_publish: bool) -> dict[str, Any]:
    grab_id = uuid.uuid4().hex
    grab = {
        "id": grab_id,
        "url": url,
        "status": "queued",
        "stage": "",
        "progress": 0,
        "error": None,
        "auto_publish": auto_publish,
    }
    _save(grab)
    thread = threading.Thread(
        target=_grab_worker,
        args=(grab_id, url, title, auto_publish),
        name=f"tiktok-grab-{grab_id}",
        daemon=True,
    )
    thread.start()
    return _grab_out(grab)


def retry_grab(grab_id: str, auto_publish: bool | None = None) -> dict[str, Any]:
    grab = load_grab(grab_id)
    if not grab:
        raise TikTokGrabError("Ese grab no existe.")
    if auto_publish is not None:
        grab["auto_publish"] = auto_publish
    _save(grab)
    thread = threading.Thread(
        target=_grab_worker,
        args=(grab_id, grab["url"], grab.get("title") or "", grab["auto_publish"]),
        name=f"tiktok-grab-{grab_id}",
        daemon=True,
    )
    thread.start()
    return _grab_out(grab)
