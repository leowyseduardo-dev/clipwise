from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
IS_FROZEN = bool(getattr(sys, "frozen", False))
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR)) if IS_FROZEN else BASE_DIR

if os.getenv("CLIPFORGE_TEAM_ENGINE") != "1":
    load_dotenv(BASE_DIR / ".env")
if os.getenv("DATA_DIR") and os.getenv("CLIPFORGE_TEAM_ENGINE") != "1":
    load_dotenv(Path(os.environ["DATA_DIR"]) / ".env")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        if IS_FROZEN and not os.getenv("DATA_DIR"):
            local = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            data_default = Path(local) / "Clipwise"
        else:
            data_default = BASE_DIR / "data"
        self.data_dir = Path(os.getenv("DATA_DIR", str(data_default))).resolve()
        self.jobs_dir = self.data_dir / "jobs"
        self.tmp_dir = self.data_dir / "tmp"
        self.db_path = self.data_dir / "Clipwise.db"
        web_default = (
            RESOURCE_DIR / "web" / "dist"
            if IS_FROZEN
            else BASE_DIR.parent / "web" / "dist"
        )
        self.web_dist = Path(os.getenv("WEB_DIST", str(web_default))).resolve()

        bundled_ffmpeg = RESOURCE_DIR / "bin" / "ffmpeg.exe"
        bundled_ffprobe = RESOURCE_DIR / "bin" / "ffprobe.exe"
        self.ffmpeg = (
            os.getenv("FFMPEG_BIN")
            or (str(bundled_ffmpeg) if bundled_ffmpeg.exists() else None)
            or shutil.which("ffmpeg")
            or "ffmpeg"
        )
        self.ffprobe = (
            os.getenv("FFPROBE_BIN")
            or (str(bundled_ffprobe) if bundled_ffprobe.exists() else None)
            or shutil.which("ffprobe")
            or "ffprobe"
        )

        bundled_model = RESOURCE_DIR / "models" / "tiny"
        model_default = str(bundled_model) if bundled_model.exists() else "small"
        self.whisper_model = os.getenv("WHISPER_MODEL", model_default)
        self.whisper_device = os.getenv("WHISPER_DEVICE", "auto")
        self.whisper_compute = os.getenv("WHISPER_COMPUTE", "int8")

        self.llm_base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.llm_api_key = os.getenv("LLM_API_KEY", "").strip()
        self.llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.llm_timeout = _env_int("LLM_TIMEOUT_SECONDS", 90)

        self.max_upload_bytes = _env_int("MAX_UPLOAD_MB", 16384) * 1024 * 1024
        self.max_source_seconds = _env_int("MAX_SOURCE_MINUTES", 720) * 60

        # Sources above this length use the audio-first path: only the audio is
        # downloaded for transcription, then each clip downloads its own
        # section. This keeps multi-hour streams from filling the disk.
        self.long_source_seconds = _env_int("LONG_SOURCE_MINUTES", 90) * 60
        self.long_source_height = _env_int("LONG_SOURCE_HEIGHT", 720)
        self.split_face_band = _env_int("SPLIT_FACE_BAND", 640)
        self.overlay_context_seconds = 5.5
        # Shorts do not need 60 fps. Capping the render rate halves both decode
        # work and x264 time on 60 fps streams without a visible loss.
        self.max_output_fps = max(15, _env_int("MAX_OUTPUT_FPS", 30))

        self.target_w = 1080
        self.target_h = 1920
        self.clip_min_seconds = 12.0
        self.clip_max_seconds = 60.0
        self.min_clips = 5
        self.default_max_clips = 15
        self.audio_analysis = _env_bool("AUDIO_ANALYSIS", True)
        self.visual_analysis = _env_bool("VISUAL_ANALYSIS", True)

        self.subtitle_font = os.getenv("SUBTITLE_FONT", "Arial")
        self.default_subtitle_style = os.getenv("SUBTITLE_STYLE", "shorts")
        self.face_model = Path(
            os.getenv(
                "FACE_MODEL",
                str(RESOURCE_DIR / "models" / "face_detection_yunet_2023mar.onnx"),
            )
        ).resolve()
        try:
            self.music_volume = float(os.getenv("MUSIC_VOLUME", "0.14"))
        except ValueError:
            self.music_volume = 0.14

        self.ytdlp_cookies = os.getenv("YTDLP_COOKIES", "").strip()
        self.ytdlp_cookies_from_browser = os.getenv(
            "YTDLP_COOKIES_FROM_BROWSER", ""
        ).strip()
        self.ytdlp_auto_cookies = _env_bool("YTDLP_AUTO_COOKIES", True)
        self.keep_working_copy = _env_bool("KEEP_WORKING_COPY", False)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.jobs_dir, self.tmp_dir):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()


def _prepend_binary_dir(binary: str | None) -> None:
    """Make a bundled ffmpeg visible to libraries that ignore our settings.

    yt-dlp's partial-download path checks PATH directly instead of honoring
    ffmpeg_location, so a bundled binary must be on PATH too.
    """
    if not binary:
        return
    directory = Path(binary).parent
    if directory == Path("."):
        return
    current = os.environ.get("PATH", "")
    entries = current.split(os.pathsep) if current else []
    if str(directory) in entries:
        return
    os.environ["PATH"] = str(directory) + (os.pathsep + current if current else "")


_prepend_binary_dir(settings.ffmpeg)
_prepend_binary_dir(settings.ffprobe)
settings.ensure_dirs()
