from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from .config import settings


class MediaError(RuntimeError):
    """Raised when ffmpeg/ffprobe cannot process a file."""


class CancelledError(RuntimeError):
    """Raised when a running job is cancelled between processing stages."""


# Keep child processes (ffmpeg/ffprobe/yt-dlp) from flashing console windows.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def has_render_headroom() -> bool:
    """Check both free RAM and commit space before starting another encoder."""
    if os.name != "nt":
        return True
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_uint32), ("load", ctypes.c_uint32),
            *((name, ctypes.c_uint64) for name in (
                "total_phys", "avail_phys", "total_commit", "avail_commit",
                "total_virtual", "avail_virtual", "avail_extended",
            )),
        ]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return True
    return min(status.avail_phys, status.avail_commit) >= 1536 * 1024**2


def run(args: Sequence[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise MediaError(f"Executable not found: {args[0]}") from exc


def run_ffmpeg(args: Sequence[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    proc = run([settings.ffmpeg, "-hide_banner", "-nostdin", *args], timeout=timeout)
    if proc.returncode != 0:
        tail = " | ".join((proc.stderr or "").strip().splitlines()[-6:])
        raise MediaError(f"ffmpeg failed: {tail or 'unknown error'}")
    return proc


def _parse_fraction(value: Any) -> float | None:
    if not value:
        return None
    try:
        text = str(value)
        if "/" in text:
            num, den = text.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else None
        return float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def probe_media(path: Path | str) -> dict[str, Any]:
    proc = run(
        [
            settings.ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout=120,
    )
    if proc.returncode != 0:
        tail = " | ".join((proc.stderr or "").strip().splitlines()[-4:])
        raise MediaError(f"ffprobe failed: {tail or 'unknown error'}")
    try:
        data = json.loads(proc.stdout or "{}")
    except ValueError as exc:
        raise MediaError("ffprobe returned invalid JSON") from exc

    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise MediaError("El archivo no contiene una pista de video.")

    duration = 0.0
    for candidate in (data.get("format", {}).get("duration"), video.get("duration")):
        try:
            duration = float(candidate)
        except (TypeError, ValueError):
            duration = 0.0
        if duration > 0:
            break
    if duration <= 0:
        raise MediaError("No se pudo determinar la duracion del video.")

    rotation = 0
    for side_data in video.get("side_data_list") or []:
        if "rotation" in side_data:
            try:
                rotation = int(float(side_data["rotation"]))
            except (TypeError, ValueError):
                rotation = 0
    if not rotation:
        try:
            rotation = int(float((video.get("tags") or {}).get("rotate", 0)))
        except (TypeError, ValueError):
            rotation = 0

    fps = _parse_fraction(video.get("avg_frame_rate")) or _parse_fraction(video.get("r_frame_rate")) or 30.0

    return {
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": round(fps, 3),
        "video_codec": str(video.get("codec_name") or ""),
        "audio_codec": str(audio.get("codec_name") or "") if audio else None,
        "has_audio": audio is not None,
        "rotation": rotation,
        "container": Path(path).suffix.lower().lstrip("."),
    }


def extract_audio(source: Path | str, destination: Path | str, *, sample_rate: int = 16000) -> Path:
    destination = Path(destination)
    codec = "flac" if destination.suffix.lower() == ".flac" else "pcm_s16le"
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            codec,
            str(destination),
        ],
        timeout=6 * 3600,
    )
    return destination


def fmt_seconds(seconds: float) -> str:
    return f"{max(0.0, seconds):.3f}"


def fmt_ass_time(seconds: float) -> str:
    total = max(0, int(round(seconds * 100)))
    hours, rem = divmod(total, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, centis = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def fmt_srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def binary_status(*, fast: bool = False) -> dict[str, Any]:
    status: dict[str, Any] = {}
    for name, path in (("ffmpeg", settings.ffmpeg), ("ffprobe", settings.ffprobe)):
        if fast:
            candidate = Path(path)
            available = candidate.is_file() if candidate.is_absolute() else bool(shutil.which(path))
            status[name] = {"available": available, "version": None, "path": path}
            continue
        try:
            proc = subprocess.run(
                [path, "-version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
                creationflags=NO_WINDOW,
            )
            line = (proc.stdout or "").splitlines()
            status[name] = {
                "available": proc.returncode == 0,
                "version": line[0] if proc.returncode == 0 and line else None,
                "path": path,
            }
        except (OSError, subprocess.SubprocessError):
            status[name] = {"available": False, "version": None, "path": path}
    return status
