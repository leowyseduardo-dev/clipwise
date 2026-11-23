"""Live clipping for Kick, YouTube and Twitch broadcasts.

A live session resolves the stream URL with yt-dlp, then ffmpeg records it
continuously into short MPEG-TS segments inside a rolling buffer. "Clip now"
concatenates the last segments and trims the tail, so a clip exists seconds
after the moment happened instead of hours later.

The buffer is pruned to ``BUFFER_MINUTES`` of footage, which bounds disk usage
per session at roughly (bitrate x minutes).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import settings
from .sources import source_platform
from .ingest import _cookie_option_sets, _is_bot_check
from .utils import NO_WINDOW, MediaError, run_ffmpeg

logger = logging.getLogger(__name__)

# The auth set (cookies) that worked last time; retried first on reconnects.
_auth_preference: dict[str, Any] | None = None

BUFFER_MINUTES = 6
SEGMENT_SECONDS = 4
MAX_SESSIONS = 3
CLIP_MIN_SECONDS = 5
CLIP_MAX_SECONDS = 120
# Newly written segments may still be growing; never read the newest ones.
SAFE_TAIL_SEGMENTS = 2

PLATFORMS = {
    "kick.com": "kick",
    "www.kick.com": "kick",
    "youtube.com": "youtube",
    "www.youtube.com": "youtube",
    "m.youtube.com": "youtube",
    "youtu.be": "youtube",
    "twitch.tv": "twitch",
    "www.twitch.tv": "twitch",
    "m.twitch.tv": "twitch",
}

PLATFORM_LABEL = {"kick": "Kick", "youtube": "YouTube", "twitch": "Twitch"}


class LiveError(RuntimeError):
    pass


_sessions: dict[str, dict[str, Any]] = {}
_threads: dict[str, threading.Thread] = {}
_stop_events: dict[str, threading.Event] = {}
_procs: dict[str, subprocess.Popen[bytes]] = {}
_lock = threading.Lock()


def _live_root() -> Path:
    path = settings.data_dir / "live"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_dir(session_id: str) -> Path:
    path = _live_root() / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _buffer_dir(session_id: str) -> Path:
    path = _session_dir(session_id) / "buffer"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _clips_dir(session_id: str) -> Path:
    path = _session_dir(session_id) / "clips"
    path.mkdir(parents=True, exist_ok=True)
    return path


def platform_for(url: str) -> str:
    try:
        return source_platform(url)
    except ValueError as exc:
        raise LiveError(str(exc)) from exc



def _session_path(session_id: str) -> Path:
    return _session_dir(session_id) / "session.json"


def _save(session: dict[str, Any]) -> None:
    _session_path(session["id"]).write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _update(session_id: str, **fields: Any) -> dict[str, Any]:
    with _lock:
        session = _sessions.get(session_id) or {}
        session.update(fields)
        _sessions[session_id] = session
    _save(session)
    return session


def load_session(session_id: str) -> dict[str, Any] | None:
    with _lock:
        session = _sessions.get(session_id)
    if session:
        return session
    path = _session_path(session_id)
    if not path.is_file():
        return None
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    with _lock:
        _sessions[session_id] = session
    return session


def _segments(session_id: str) -> list[Path]:
    return sorted(_buffer_dir(session_id).glob("seg_*.ts"))


def _buffer_seconds(session_id: str) -> int:
    count = max(0, len(_segments(session_id)) - SAFE_TAIL_SEGMENTS)
    return count * SEGMENT_SECONDS


def _clips(session_id: str) -> list[dict[str, Any]]:
    clips = []
    for path in sorted(_clips_dir(session_id).glob("*.json"), reverse=True):
        try:
            clips.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    clips.sort(key=lambda clip: clip.get("created_at") or "", reverse=True)
    return clips


def _clip_out(clip: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": clip["id"],
        "session_id": clip["session_id"],
        "title": clip.get("title") or "Clip en vivo",
        "platform": clip.get("platform") or "",
        "author": clip.get("author") or "",
        "seconds": clip.get("seconds") or 0,
        "created_at": clip.get("created_at"),
        "file": clip.get("file"),
    }


def _session_out(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": session["id"],
        "url": session["url"],
        "platform": session.get("platform") or "",
        "title": session.get("title") or "",
        "author": session.get("author") or "",
        "status": session.get("status") or "connecting",
        "error": session.get("error"),
        "started_at": session.get("started_at"),
        "buffer_seconds": _buffer_seconds(session["id"]),
        "buffer_minutes": BUFFER_MINUTES,
        "clips": [_clip_out(clip) for clip in _clips(session["id"])],
    }


def list_sessions() -> list[dict[str, Any]]:
    sessions = []
    for path in sorted(_live_root().glob("*/session.json"), reverse=True):
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sessions.append(_session_out(session))
    return sessions


def _pick_streams(info: dict[str, Any]) -> tuple[str, str | None]:
    """Return ``(video_url, audio_url)`` for a live stream.

    YouTube live exposes split HLS renditions (video-only and audio-only), so
    the recorder needs a second input for sound. Kick and Twitch normally ship a
    muxed HLS playlist and return ``audio_url=None``.
    """
    formats = [fmt for fmt in (info.get("formats") or []) if fmt.get("url")]

    def height(fmt: dict[str, Any]) -> int:
        return int(fmt.get("height") or 0)

    def bitrate(fmt: dict[str, Any]) -> float:
        return float(fmt.get("abr") or fmt.get("tbr") or 0)

    def has_video(fmt: dict[str, Any]) -> bool:
        return (fmt.get("vcodec") or "none") != "none"

    def has_audio(fmt: dict[str, Any]) -> bool:
        return (fmt.get("acodec") or "none") != "none"

    muxed = [fmt for fmt in formats if has_video(fmt) and has_audio(fmt)]
    if muxed:
        return max(muxed, key=height)["url"], None

    videos = [fmt for fmt in formats if has_video(fmt)]
    if videos:
        audio = max((fmt for fmt in formats if not has_video(fmt)), key=bitrate, default=None)
        return max(videos, key=height)["url"], audio["url"] if audio else None

    if formats:
        return formats[-1]["url"], None
    raise LiveError("No se encontro la URL del directo.")


def _resolve(url: str) -> dict[str, Any]:
    """Ask yt-dlp for metadata and the direct stream URL."""
    global _auth_preference
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        "nocheckcertificate": True,
    }
    auth_sets: list[dict[str, Any]] = []
    if _auth_preference:
        auth_sets.append(_auth_preference)
    auth_sets.append({})
    for candidate in _cookie_option_sets():
        if candidate not in auth_sets:
            auth_sets.append(candidate)

    info: dict[str, Any] | None = None
    last_error: Exception | None = None
    for auth in auth_sets:
        try:
            with yt_dlp.YoutubeDL({**opts, **auth}) as ydl:
                info = ydl.extract_info(url, download=False) or {}
            _auth_preference = auth
            break
        except Exception as exc:  # noqa: BLE001 - yt-dlp raises many types
            last_error = exc
            if auth:
                logger.warning(
                    "No se pudieron usar cookies (%s): %s", auth, str(exc)[:300]
                )
                continue
            if _is_bot_check(str(exc)):
                continue
            raise LiveError(f"No se pudo leer la emision: {str(exc)[:220]}") from exc
    if info is None:
        raise LiveError(
            "YouTube pidio verificar la sesion para este directo. Inicia sesion en "
            "el navegador y vuelve a intentar."
        ) from last_error

    if info.get("is_live") is not True:
        raise LiveError("Ese canal no esta en directo ahora mismo.")
    stream_url, audio_url = _pick_streams(info)
    return {
        "stream_url": stream_url,
        "audio_url": audio_url,
        "title": str(info.get("title") or "").strip(),
        "author": str(info.get("uploader") or info.get("channel") or "").strip(),
    }


def _record_loop(session_id: str, url: str, stop: threading.Event) -> None:
    """Keep ffmpeg writing segments while the stream is live."""
    failures = 0
    resolve_failures = 0
    while not stop.is_set():
        try:
            meta = _resolve(url)
            resolve_failures = 0
        except LiveError as exc:
            message = str(exc)
            if "no esta en directo" in message:
                _update(session_id, status="offline", error=message[:300])
                return
            resolve_failures += 1
            if resolve_failures >= 4:
                _update(session_id, status="error", error=message[:300])
                return
            _update(
                session_id,
                status="connecting",
                error=f"Sin conexion, reintentando: {message[:190]}",
            )
            if stop.wait(min(20, 4 * resolve_failures)):
                break
            continue
        _update(
            session_id,
            status="recording",
            title=meta["title"] or None,
            author=meta["author"] or None,
            error=None,
        )
        buffer_dir = _buffer_dir(session_id)
        for stale in _segments(session_id):
            stale.unlink(missing_ok=True)
        args = [
            settings.ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            meta["stream_url"],
        ]
        if meta.get("audio_url"):
            args += ["-i", meta["audio_url"], "-map", "0:v:0", "-map", "1:a:0?"]
        else:
            args += ["-map", "0:v:0", "-map", "0:a:0?"]
        args += [
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(SEGMENT_SECONDS),
            "-segment_format",
            "mpegts",
            "-reset_timestamps",
            "1",
            "-max_muxing_queue_size",
            "1024",
            str(buffer_dir / "seg_%06d.ts"),
        ]
        try:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=NO_WINDOW,
            )
        except OSError as exc:
            _update(session_id, status="error", error=f"ffmpeg no arranco: {exc}")
            return
        with _lock:
            _procs[session_id] = proc
        started = time.monotonic()
        while not stop.is_set():
            if proc.poll() is not None:
                break
            _prune(session_id)
            time.sleep(2)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        with _lock:
            _procs.pop(session_id, None)
        if stop.is_set():
            break
        survived = time.monotonic() - started
        failures = 0 if survived > 60 else failures + 1
        if failures >= 3:
            _update(
                session_id,
                status="error",
                error="El directo se corto y no se pudo reconectar. Pulsa Reanudar.",
            )
            return
        time.sleep(3)
    _update(session_id, status="stopped")


def _prune(session_id: str) -> None:
    segments = _segments(session_id)
    keep = int(BUFFER_MINUTES * 60 / SEGMENT_SECONDS) + SAFE_TAIL_SEGMENTS
    for stale in segments[:-keep] if len(segments) > keep else []:
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            pass


def start_session(url: str) -> dict[str, Any]:
    platform = platform_for(url)
    active = [s for s in list_sessions() if s["status"] in ("connecting", "recording")]
    if len(active) >= MAX_SESSIONS:
        raise LiveError(
            f"Ya hay {MAX_SESSIONS} emisiones grabando. Deten una antes de abrir otra."
        )
    session_id = uuid.uuid4().hex
    session = {
        "id": session_id,
        "url": url,
        "platform": platform,
        "title": "",
        "author": "",
        "status": "connecting",
        "error": None,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with _lock:
        _sessions[session_id] = session
    _save(session)
    _session_dir(session_id)
    _buffer_dir(session_id)
    _clips_dir(session_id)
    stop = threading.Event()
    thread = threading.Thread(
        target=_record_loop,
        args=(session_id, url, stop),
        name=f"live-{platform}-{session_id}",
        daemon=True,
    )
    with _lock:
        _stop_events[session_id] = stop
        _threads[session_id] = thread
    thread.start()
    return _session_out(session)


def resume_session(session_id: str) -> dict[str, Any]:
    session = load_session(session_id)
    if not session:
        raise LiveError("Esa emision no existe.")
    with _lock:
        existing = _threads.get(session_id)
    if existing and existing.is_alive():
        return _session_out(session)
    stop = threading.Event()
    thread = threading.Thread(
        target=_record_loop,
        args=(session_id, session["url"], stop),
        name=f"live-{session.get('platform')}-{session_id}",
        daemon=True,
    )
    with _lock:
        _stop_events[session_id] = stop
        _threads[session_id] = thread
    _update(session_id, status="connecting", error=None)
    thread.start()
    return _session_out(load_session(session_id) or session)


def stop_session(session_id: str) -> dict[str, Any]:
    session = load_session(session_id)
    if not session:
        raise LiveError("Esa emision no existe.")
    with _lock:
        stop = _stop_events.pop(session_id, None)
        proc = _procs.get(session_id)
    if stop:
        stop.set()
    if proc and proc.poll() is None:
        proc.terminate()
    _update(session_id, status="stopped", error=None)
    with _lock:
        thread = _threads.get(session_id)
    if thread:
        thread.join(timeout=15)
        with _lock:
            _threads.pop(session_id, None)
    return _session_out(load_session(session_id) or session)


def delete_session(session_id: str) -> None:
    try:
        stop_session(session_id)
    except LiveError:
        pass
    shutil.rmtree(_session_dir(session_id), ignore_errors=True)
    with _lock:
        _sessions.pop(session_id, None)
        _stop_events.pop(session_id, None)
        _procs.pop(session_id, None)


def _select_segments(segments: list[Path], seconds: int) -> list[Path]:
    """Pick enough closed segments to cover ``seconds`` of footage."""
    usable = segments[:-SAFE_TAIL_SEGMENTS] if len(segments) > SAFE_TAIL_SEGMENTS else []
    needed = int(seconds / SEGMENT_SECONDS) + 2
    if len(usable) < min(needed, 2):
        return []
    return usable[-needed:]


def make_clip(session_id: str, seconds: int) -> dict[str, Any]:
    session = load_session(session_id)
    if not session:
        raise LiveError("Esa emision no existe.")
    if session.get("status") != "recording":
        raise LiveError("La emision no esta grabando ahora mismo.")
    seconds = max(CLIP_MIN_SECONDS, min(CLIP_MAX_SECONDS, int(seconds)))
    selected = _select_segments(_segments(session_id), seconds)
    if not selected:
        raise LiveError(
            "Todavia no hay buffer suficiente. Espera unos segundos y vuelve a intentar."
        )
    clip_id = uuid.uuid4().hex
    work_dir = _session_dir(session_id) / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    list_file = work_dir / f"{clip_id}.txt"
    list_file.write_text(
        "".join(f"file '{segment.as_posix()}'\n" for segment in selected),
        encoding="utf-8",
    )
    joined = work_dir / f"{clip_id}.ts"
    out_path = _clips_dir(session_id) / f"{clip_id}.mp4"
    try:
        run_ffmpeg(
            [
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                str(joined),
            ],
            timeout=180,
        )
        run_ffmpeg(
            [
                "-y",
                "-sseof",
                f"-{seconds}",
                "-i",
                str(joined),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(out_path),
            ],
            timeout=180,
        )
    except MediaError as exc:
        raise LiveError(f"No se pudo cortar el clip: {str(exc)[:200]}") from exc
    finally:
        list_file.unlink(missing_ok=True)
        joined.unlink(missing_ok=True)
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise LiveError("El clip salio vacio. Intenta de nuevo.")
    started = time.strftime("%H:%M:%S", time.localtime())
    title = f"{session.get('title') or PLATFORM_LABEL.get(session.get('platform'), 'Vivo')} · {started}"
    clip = {
        "id": clip_id,
        "session_id": session_id,
        "title": title[:100],
        "platform": session.get("platform") or "",
        "author": session.get("author") or "",
        "seconds": seconds,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "file": str(out_path),
    }
    (_clips_dir(session_id) / f"{clip_id}.json").write_text(
        json.dumps(clip, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return _clip_out(clip)


def load_clip(clip_id: str) -> dict[str, Any] | None:
    for path in _live_root().glob(f"*/clips/{clip_id}.json"):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def stop_all() -> None:
    for session_id in list(_sessions):
        try:
            stop_session(session_id)
        except Exception:  # noqa: BLE001 - shutdown must not raise
            pass


def recover_stale_sessions() -> None:
    """Mark sessions left 'recording' by a previous run as stopped."""
    for path in _live_root().glob("*/session.json"):
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if session.get("status") in ("recording", "connecting"):
            session["status"] = "stopped"
            session["error"] = "La app se reinicio; pulsa Reanudar para seguir grabando."
            path.write_text(
                json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
            )
