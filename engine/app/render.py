from __future__ import annotations

import json
import logging
import math
import os
import re
import statistics
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from . import layouts
from .config import settings
from .subtitles import build_ass, cues_to_srt
from .utils import (
    CancelledError,
    MediaError,
    NO_WINDOW,
    clamp,
    fmt_seconds,
    probe_media,
    run_ffmpeg,
)

logger = logging.getLogger(__name__)

_SILENCE_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


class RenderError(RuntimeError):
    pass


def cleanup_old_outputs(clip_dir: Path, *, keep: set[Path]) -> None:
    """Remove previous renders without failing if Windows still has one open."""
    for pattern in ("video*.mp4", "thumb*.jpg"):
        for path in clip_dir.glob(pattern):
            if path in keep:
                continue
            try:
                path.unlink()
            except OSError:
                logger.debug("No se pudo borrar el archivo anterior %s", path)


def extract_clip_audio(
    source: Path,
    start: float,
    duration: float,
    destination: Path,
    *,
    has_audio: bool,
) -> Path:
    if has_audio:
        run_ffmpeg(
            [
                "-y",
                "-ss",
                fmt_seconds(start),
                "-t",
                fmt_seconds(duration),
                "-i",
                str(source),
                "-vn",
                "-ac",
                "2",
                "-ar",
                "44100",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ],
            timeout=1800,
        )
    else:
        run_ffmpeg(
            [
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-t",
                fmt_seconds(duration),
                "-c:a",
                "pcm_s16le",
                str(destination),
            ],
            timeout=600,
        )
    return destination


def detect_silences(audio_path: Path, duration: float) -> list[tuple[float, float]]:
    proc = subprocess.run(
        [
            settings.ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-i",
            str(audio_path),
            "-af",
            "silencedetect=noise=-38dB:d=1.1",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
        creationflags=NO_WINDOW,
    )
    stderr = proc.stderr or ""
    starts = [float(value) for value in _SILENCE_START.findall(stderr)]
    ends = [float(value) for value in _SILENCE_END.findall(stderr)]
    pairs: list[tuple[float, float]] = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else duration
        if end > start:
            pairs.append((max(0.0, start), min(duration, end)))
    return pairs


def compress_silences(
    raw: list[tuple[float, float]], duration: float
) -> list[tuple[float, float]]:
    removed: list[tuple[float, float]] = []
    for start, end in raw:
        start = max(0.0, start)
        end = min(duration, end)
        if end - start < 1.1:
            continue
        inner_start = start + 0.22
        inner_end = end - 0.22
        if inner_end - inner_start < 0.45:
            continue
        removed.append((inner_start, inner_end))
    removed.sort()
    merged: list[tuple[float, float]] = []
    for start, end in removed:
        if merged and start <= merged[-1][1] + 0.05:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    total = sum(end - start for start, end in merged)
    if len(merged) > 60 or total > duration * 0.4:
        logger.info("Se descarta la eliminacion de silencios (demasiados cortes).")
        return []
    return merged


def map_time(seconds: float, removed: list[tuple[float, float]]) -> float:
    shift = 0.0
    for start, end in removed:
        if seconds <= start:
            break
        shift += min(seconds, end) - start
    return max(0.0, seconds - shift)


def protect_speech(
    removed: list[tuple[float, float]], cues: list[dict[str, Any]]
) -> list[tuple[float, float]]:
    """Low-volume speech is not dead air. Preserve words and their breathing room.

    With no transcript we cannot distinguish silence from a visual payoff,
    so retain the original timing instead of deleting silent gameplay.
    """
    if not cues:
        return []
    protected = []
    for cue in cues:
        for word in cue.get("words") or [cue]:
            protected.append((max(0, float(word["start"]) - .12), float(word["end"]) + .18))
    result = []
    for start, end in removed:
        parts = [(start, end)]
        for left, right in protected:
            next_parts = []
            for a, b in parts:
                if right <= a or left >= b:
                    next_parts.append((a, b))
                else:
                    if left > a:
                        next_parts.append((a, left))
                    if right < b:
                        next_parts.append((right, b))
            parts = next_parts
        result.extend((a, b) for a, b in parts if b - a >= .45)
    return result


def _inside(seconds: float, removed: list[tuple[float, float]]) -> bool:
    return any(start <= seconds < end for start, end in removed)


def _needs_render_proxy(info: dict[str, Any]) -> bool:
    codec = str(info.get("video_codec") or "").lower()
    width = int(info.get("width") or 0)
    height = int(info.get("height") or 0)
    fps = float(info.get("fps") or 0)
    if max(width, height) > 1920:
        return True
    if fps > 60:
        return True
    # ffmpeg decodes 1080p AV1/VP9 faster than an extra full x264 pass, so
    # only transcode codecs that are consistently slow on Windows.
    return codec not in {"h264", "av1", "vp9", "vp8", ""}


def _build_render_proxy(
    source: Path,
    start: float,
    duration: float,
    destination: Path,
    info: dict[str, Any],
) -> Path | None:
    """Transcode one clip window to fast-decode H.264 before frame work.

    AV1 and 4K sources are expensive to decode frame by frame. A single ffmpeg
    pass produces a 1080p-class H.264 window that both the face tracker and the
    renderer can read quickly, and it keeps the original source untouched.
    """
    fps = max(1.0, min(float(info.get("fps") or 30.0), float(settings.max_output_fps)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_ffmpeg(
            [
                "-y",
                "-ss",
                fmt_seconds(start),
                "-t",
                fmt_seconds(duration),
                "-i",
                str(source),
                "-an",
                "-sn",
                "-dn",
                "-vf",
                (
                    "scale=w='min(1920,iw)':h='min(1920,ih)':"
                    f"force_original_aspect_ratio=decrease:force_divisible_by=2,"
                    f"fps={fps:.6f}"
                ),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(destination),
            ],
            timeout=1800,
        )
        probe_media(destination)
    except (MediaError, OSError) as exc:
        logger.warning("No se pudo preparar el proxy de render: %s", exc)
        destination.unlink(missing_ok=True)
        return None
    return destination


def _plan_crop_aspect(width: int, height: int, aspect: float) -> tuple[int, int]:
    if width / height > aspect:
        crop_h = height
        crop_w = int(round(height * aspect))
    else:
        crop_w = width
        crop_h = int(round(width / aspect))
    crop_w = max(2, min(width, crop_w // 2 * 2))
    crop_h = max(2, min(height, crop_h // 2 * 2))
    return crop_w, crop_h


def _plan_crop(width: int, height: int) -> tuple[int, int]:
    return _plan_crop_aspect(width, height, settings.target_w / settings.target_h)


def _build_audio_graph(
    removed: list[tuple[float, float]],
    out_duration: float,
    has_music: bool,
    music_level: float | None = None,
) -> str:
    filters: list[str] = []
    if removed:
        expression = "+".join(
            f"between(t,{start:.3f},{end:.3f})" for start, end in removed
        )
        filters.append(f"aselect='not({expression})'")
        filters.append("asetpts=N/SR/TB")
    filters.extend(
        [
            "highpass=f=75",
            "dynaudnorm=f=250:g=6:p=0.90",
            "loudnorm=I=-14:TP=-1.5:LRA=11",
            "aresample=48000",
            "alimiter=limit=0.97",
        ]
    )
    voice = "[1:a]" + ",".join(filters)
    if not has_music:
        # apad keeps the audio stream alive until the explicit -t cut, even if
        # silence removal leaves the audio a few milliseconds short.
        return f"{voice},apad[a]"
    music_filters = [
        f"volume={settings.music_volume if music_level is None else music_level:.3f}",
        f"atrim=0:{out_duration:.3f}",
        "afade=t=in:st=0:d=0.8",
        f"afade=t=out:st={max(0.0, out_duration - 1.2):.3f}:d=1.2",
    ]
    music = "[2:a]" + ",".join(music_filters)
    return (
        f"{voice}[voice];"
        f"{music}[music];"
        "[voice][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        "alimiter=limit=0.97,apad[a]"
    )


def _ffmpeg_frame(
    source: Path,
    at: float,
    width: int,
    height: int,
) -> np.ndarray | None:
    """Decode one frame with ffmpeg.

    OpenCV's random seek on long AV1 files can take seconds per frame. ffmpeg
    decodes the same frame in a fraction of that time and understands every
    container the engine accepts.
    """
    if width <= 0 or height <= 0:
        return None
    command = [
        settings.ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-ss",
        fmt_seconds(at),
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-an",
        "-sn",
        "-dn",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=120,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.debug("No se pudo decodificar un fotograma de muestra.", exc_info=True)
        return None
    expected = width * height * 3
    if proc.returncode != 0 or len(proc.stdout or b"") < expected:
        return None
    return (
        np.frombuffer(proc.stdout[:expected], dtype=np.uint8)
        .reshape((height, width, 3))
        .copy()
    )


class _FrameReader:
    """Stream clip-sized BGR frames from ffmpeg instead of seeking OpenCV."""

    def __init__(
        self,
        source: Path,
        start: float,
        duration: float,
        width: int,
        height: int,
        fps: float,
    ) -> None:
        self.width = width
        self.height = height
        self.frame_bytes = max(1, width * height * 3)
        command = [
            settings.ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-threads:v",
            "2",
            "-filter_threads",
            "1",
            "-ss",
            fmt_seconds(start),
            "-i",
            str(source),
            "-t",
            fmt_seconds(duration),
            "-an",
            "-sn",
            "-dn",
            "-vf",
            f"fps={fps:.6f}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{width}x{height}",
            "-threads:v",
            "1",
            "pipe:1",
        ]
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
        self._stdout = self._process.stdout

    def read(self) -> np.ndarray | None:
        if self._stdout is None:
            return None
        data = self._stdout.read(self.frame_bytes)
        if not data or len(data) < self.frame_bytes:
            return None
        return np.frombuffer(data, dtype=np.uint8).reshape(
            (self.height, self.width, 3)
        )

    def close(self) -> None:
        if self._stdout is not None:
            try:
                self._stdout.close()
            except OSError:
                pass
            self._stdout = None
        if self._process.poll() is None:
            try:
                self._process.kill()
            except OSError:
                pass
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass


def _clamp_center(
    x: float,
    y: float,
    crop_w: int,
    crop_h: int,
    width: int,
    height: int,
) -> tuple[float, float]:
    half_w = crop_w / 2.0
    half_h = crop_h / 2.0
    return (
        clamp(x, half_w, max(half_w, width - half_w)),
        clamp(y, half_h, max(half_h, height - half_h)),
    )


def _choose_face_box(
    candidates: list[tuple[float, float, float, float, float]],
    width: int,
    height: int,
    previous: tuple[float, float] | None,
) -> tuple[float, float, float, float, float] | None:
    if not candidates:
        return None
    diagonal = max(1.0, math.hypot(width, height))
    best: tuple[float, float, float, float, float] | None = None
    best_score = -1.0
    for face_x, face_y, face_w, face_h, confidence in candidates:
        area = (face_w * face_h) / float(max(1, width * height))
        center_bias = 1.0 - min(
            1.0,
            math.hypot(face_x - width / 2.0, face_y - height / 2.0)
            / max(1.0, math.hypot(width / 2.0, height / 2.0)),
        )
        score = area * 6.0 + confidence * 0.5 + center_bias * 0.25
        if previous is not None:
            distance = math.hypot(face_x - previous[0], face_y - previous[1]) / diagonal
            score += (1.0 - min(1.0, distance * 4.0)) * 0.85
        if score > best_score:
            best_score = score
            best = (face_x, face_y, face_w, face_h, confidence)
    return best


def _choose_face(
    candidates: list[tuple[float, float, float, float, float]],
    width: int,
    height: int,
    previous: tuple[float, float] | None,
) -> tuple[float, float] | None:
    box = _choose_face_box(candidates, width, height, previous)
    return (box[0], box[1]) if box else None


def _rank_facecam_clusters(
    boxes: list[tuple[float, float, float, float, float, int]],
    width: int,
    height: int,
    valid_samples: int,
) -> list[list[tuple[float, float, float, float, float, int]]]:
    """Cluster detected faces and return them best-first.

    Game scenes contain faces too. A facecam inset is the face that survives
    across the whole clip, usually near an edge, while a game character face
    appears only while the scene stays on that character. Multiple stable
    clusters mean multiple webcams.
    """
    if not boxes or valid_samples < 4:
        return []
    tolerance = max(30.0, width * 0.07)
    clusters: list[list[tuple[float, float, float, float, float, int]]] = []
    for box in boxes:
        best: list[tuple[float, float, float, float, float, int]] | None = None
        best_distance = tolerance
        for cluster in clusters:
            center_x = statistics.median(item[0] for item in cluster)
            center_y = statistics.median(item[1] for item in cluster)
            distance = math.hypot(box[0] - center_x, box[1] - center_y)
            if distance < best_distance:
                best_distance = distance
                best = cluster
        if best is None:
            clusters.append([box])
        else:
            best.append(box)
    if not clusters:
        return []

    minimum_coverage = max(4, int(math.ceil(valid_samples * 0.6)))
    scored: list[tuple[float, list[tuple[float, float, float, float, float, int]]]] = []
    for cluster in clusters:
        per_sample: dict[int, tuple[float, float, float, float, float, int]] = {}
        for item in cluster:
            sample = item[5]
            current = per_sample.get(sample)
            if current is None or item[2] * item[3] > current[2] * current[3]:
                per_sample[sample] = item
        if len(per_sample) < minimum_coverage:
            continue
        values = list(per_sample.values())
        face_w = statistics.median(item[2] for item in values)
        face_h = statistics.median(item[3] for item in values)
        if face_w < width * 0.025 or face_h < height * 0.03:
            continue
        center_x = statistics.median(item[0] for item in values)
        center_y = statistics.median(item[1] for item in values)
        edge_distance = min(
            center_x,
            width - center_x,
            center_y,
            height - center_y,
        )
        corner = 1.0 - min(
            1.0,
            edge_distance / max(1.0, min(width, height) * 0.45),
        )
        coverage = len(values) / float(valid_samples)
        size_score = min(1.0, face_w / max(1.0, width * 0.10))
        score = coverage * 4.0 + corner * 1.4 + size_score * 0.6
        scored.append((score, cluster))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [cluster for _, cluster in scored]


def _select_facecam_boxes(
    boxes: list[tuple[float, float, float, float, float, int]],
    width: int,
    height: int,
    valid_samples: int,
) -> list[tuple[float, float, float, float, float]]:
    """Pick the stable face cluster most likely to be the main facecam."""
    clusters = _rank_facecam_clusters(boxes, width, height, valid_samples)
    return _cluster_values(clusters[0]) if clusters else []


def _cluster_values(
    cluster: list[tuple[float, float, float, float, float, int]],
) -> list[tuple[float, float, float, float, float]]:
    per_sample: dict[int, tuple[float, float, float, float, float, int]] = {}
    for item in cluster:
        sample = item[5]
        current = per_sample.get(sample)
        if current is None or item[2] * item[3] > current[2] * current[3]:
            per_sample[sample] = item
    return [(item[0], item[1], item[2], item[3], item[4]) for item in per_sample.values()]


def _estimate_facecam_panel(
    boxes: list[tuple[float, float, float, float, float]],
    width: int,
    height: int,
) -> tuple[float, float, float, float] | None:
    """Return a stable square facecam crop, or None when no panel is present.

    A square crop works for the 16:9, 4:3, and vertical camera boxes streamers
    use in practice. The renderer letterboxes it into the top band instead of
    cutting the face off to force an exact 16:9 panel.
    """
    if len(boxes) < 4:
        return None
    median_x = statistics.median(box[0] for box in boxes)
    median_y = statistics.median(box[1] for box in boxes)
    tolerance = max(24.0, width * 0.06)
    stable = [
        box
        for box in boxes
        if math.hypot(box[0] - median_x, box[1] - median_y) <= tolerance
    ]
    if len(stable) < max(3, int(round(len(boxes) * 0.6))):
        return None

    face_w = statistics.median(box[2] for box in stable)
    face_h = statistics.median(box[3] for box in stable)
    if face_w < width * 0.025 or face_h < height * 0.03:
        return None
    if face_w > width * 0.38 or face_h > height * 0.55:
        return None

    side = max(face_w * 2.6, face_h * 1.65, height * 0.30)
    side = min(side, float(width), float(height))
    if side < max(face_w * 1.15, face_h * 1.05):
        return None
    if side * side > width * height * 0.60:
        return None
    side = max(2, int(round(side)) // 2 * 2)
    if side > width or side > height:
        return None

    center_x = statistics.median(box[0] for box in stable)
    center_y = statistics.median(box[1] for box in stable) + side * 0.02
    x = clamp(center_x - side / 2.0, 0.0, max(0.0, width - side))
    y = clamp(center_y - side / 2.0, 0.0, max(0.0, height - side))
    return (x, y, float(side), float(side))


class _FaceTracker:
    """YuNet when the bundled model is available, Haar as a fallback."""

    def __init__(self, model_path: Path | None) -> None:
        self._detector: Any | None = None
        self._cascade: Any | None = None
        if (
            model_path is not None
            and model_path.exists()
            and hasattr(cv2, "FaceDetectorYN")
        ):
            try:
                self._detector = cv2.FaceDetectorYN.create(
                    str(model_path),
                    "",
                    (640, 640),
                    0.6,
                    0.3,
                    5000,
                )
            except Exception as exc:  # pragma: no cover - depends on OpenCV build
                logger.warning("YuNet no disponible, se usa Haar: %s", exc)
        if self._detector is None:
            self._ensure_cascade()

    def _ensure_cascade(self) -> None:
        if self._cascade is None:
            self._cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )

    def detect_boxes(
        self,
        frame: np.ndarray,
    ) -> list[tuple[float, float, float, float, float]]:
        if self._detector is not None:
            try:
                return self._detect_yunet_boxes(frame)
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning("Fallo YuNet, se cambia a Haar: %s", exc)
                self._detector = None
                self._ensure_cascade()
        if self._cascade is not None:
            return self._detect_haar_boxes(frame)
        return []

    def detect_box(
        self,
        frame: np.ndarray,
        previous: tuple[float, float] | None,
    ) -> tuple[float, float, float, float, float] | None:
        height, width = frame.shape[:2]
        candidates = self.detect_boxes(frame)
        return _choose_face_box(candidates, width, height, previous)

    def detect(
        self,
        frame: np.ndarray,
        previous: tuple[float, float] | None,
    ) -> tuple[float, float] | None:
        box = self.detect_box(frame, previous)
        return (box[0], box[1]) if box else None

    def _detect_yunet_boxes(
        self,
        frame: np.ndarray,
    ) -> list[tuple[float, float, float, float, float]]:
        height, width = frame.shape[:2]
        scale = min(1.0, 720.0 / float(max(1, width)))
        if scale < 1.0:
            working = cv2.resize(
                frame,
                (max(2, int(round(width * scale))), max(2, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            working = frame
        self._detector.setInputSize((working.shape[1], working.shape[0]))
        _, faces = self._detector.detect(working)
        if faces is None:
            return []
        candidates: list[tuple[float, float, float, float, float]] = []
        for face in np.asarray(faces, dtype=np.float32).reshape(-1, 15):
            confidence = float(face[14])
            if confidence < 0.55:
                continue
            face_x = float(face[0]) / scale
            face_y = float(face[1]) / scale
            face_w = float(face[2]) / scale
            face_h = float(face[3]) / scale
            if face_w < width * 0.03 or face_h < height * 0.03:
                continue
            if face_w > width * 0.92 or face_h > height * 0.92:
                continue
            candidates.append(
                (face_x + face_w / 2.0, face_y + face_h / 2.0, face_w, face_h, confidence)
            )
        return candidates

    def _detect_haar_boxes(
        self,
        frame: np.ndarray,
    ) -> list[tuple[float, float, float, float, float]]:
        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        scale = min(1.0, 720.0 / float(max(1, width)))
        if scale < 1.0:
            working = cv2.resize(
                gray,
                (max(2, int(round(width * scale))), max(2, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            working = gray
        min_size = max(24, int(round(48 * scale)))
        faces = self._cascade.detectMultiScale(
            working,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(min_size, min_size),
        )
        candidates: list[tuple[float, float, float, float, float]] = []
        for face_x, face_y, face_w, face_h in faces:
            coordinates = (
                float(face_x) / scale,
                float(face_y) / scale,
                float(face_w) / scale,
                float(face_h) / scale,
            )
            candidates.append(
                (
                    coordinates[0] + coordinates[2] / 2.0,
                    coordinates[1] + coordinates[3] / 2.0,
                    coordinates[2],
                    coordinates[3],
                    1.0,
                )
            )
        return candidates


class _Camera:
    """Smooth subpixel crop with a very slow push-in."""

    def __init__(
        self,
        *,
        width: int,
        height: int,
        base_crop_w: int,
        base_crop_h: int,
        duration: float,
        dynamic_zoom: bool,
        anchor_x: float | None = None,
        anchor_y: float | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.base_crop_w = base_crop_w
        self.base_crop_h = base_crop_h
        self.duration = max(0.001, duration)
        self.dynamic_zoom = dynamic_zoom
        self.anchor_x = width / 2.0 if anchor_x is None else float(anchor_x)
        self.anchor_y = height / 2.0 if anchor_y is None else float(anchor_y)
        self.x = self.anchor_x
        self.y = self.anchor_y
        self.target_x = self.x
        self.target_y = self.y
        self.last_face_at = -10.0
        self.started = False

    def sample(
        self,
        t: float,
        face: tuple[float, float] | None,
        dt: float,
    ) -> tuple[float, float, int, int]:
        progress = clamp(t / self.duration, 0.0, 1.0)
        eased = progress * progress * (3.0 - 2.0 * progress)
        zoom = 1.0 + (0.045 * eased if self.dynamic_zoom else 0.0)
        crop_w = max(2, int(round(self.base_crop_w / zoom)) // 2 * 2)
        crop_h = max(2, int(round(self.base_crop_h / zoom)) // 2 * 2)
        crop_w = min(self.width, crop_w)
        crop_h = min(self.height, crop_h)

        if face is not None:
            self.last_face_at = t
            face_x = float(face[0])
            face_y = float(face[1]) + crop_h * 0.10
            # The face alone is not the subject: the clip usually reacts to
            # content near the frame center, so blend both into the crop
            # target instead of centering on the face and cutting the
            # content out of the 9:16 window.
            desired_x = face_x * 0.70 + self.anchor_x * 0.30
            desired_y = face_y * 0.70 + self.anchor_y * 0.30
            if (
                abs(desired_x - self.target_x) > 1.5
                or abs(desired_y - self.target_y) > 1.5
            ):
                self.target_x = desired_x
                self.target_y = desired_y
        elif t - self.last_face_at > 1.6:
            self.target_x = self.anchor_x
            self.target_y = self.anchor_y

        target_x, target_y = _clamp_center(
            self.target_x,
            self.target_y,
            crop_w,
            crop_h,
            self.width,
            self.height,
        )
        if not self.started:
            self.x, self.y = target_x, target_y
            self.started = True
        else:
            step = max(1.0 / 240.0, float(dt))
            alpha = 1.0 - math.exp(-step / 0.38)
            self.x += (target_x - self.x) * alpha
            self.y += (target_y - self.y) * alpha
        self.x, self.y = _clamp_center(
            self.x,
            self.y,
            crop_w,
            crop_h,
            self.width,
            self.height,
        )
        return self.x, self.y, crop_w, crop_h


def _crop_fit(
    frame: np.ndarray,
    rect: tuple[float, float, float, float],
    size: tuple[int, int],
) -> np.ndarray:
    height, width = frame.shape[:2]
    x, y, rect_w, rect_h = rect
    x1 = int(clamp(round(x), 0, max(0, width - 2)))
    y1 = int(clamp(round(y), 0, max(0, height - 2)))
    x2 = int(clamp(round(x + rect_w), x1 + 2, width))
    y2 = int(clamp(round(y + rect_h), y1 + 2, height))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        crop = frame
    crop_h, crop_w = crop.shape[:2]
    target_aspect = size[0] / float(size[1])
    if crop_w / float(max(1, crop_h)) > target_aspect:
        trimmed_w = max(2, int(round(crop_h * target_aspect)))
        offset = max(0, (crop_w - trimmed_w) // 2)
        crop = crop[:, offset : offset + trimmed_w]
    elif crop_w / float(max(1, crop_h)) < target_aspect:
        trimmed_h = max(2, int(round(crop_w / target_aspect)))
        offset = max(0, (crop_h - trimmed_h) // 2)
        crop = crop[offset : offset + trimmed_h, :]
    interpolation = (
        cv2.INTER_LANCZOS4
        if size[0] > crop.shape[1] * 1.05
        else cv2.INTER_AREA
    )
    return cv2.resize(crop, size, interpolation=interpolation)


def _facecam_background(
    frame: np.ndarray,
    rect: tuple[float, float, float, float],
    size: tuple[int, int],
) -> np.ndarray:
    height, width = frame.shape[:2]
    target_w, target_h = size
    x, y, rect_w, rect_h = rect
    x1 = int(clamp(round(x), 0, max(0, width - 2)))
    y1 = int(clamp(round(y), 0, max(0, height - 2)))
    x2 = int(clamp(round(x + rect_w), x1 + 2, width))
    y2 = int(clamp(round(y + rect_h), y1 + 2, height))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        crop = frame
    crop_h, crop_w = crop.shape[:2]
    cover = max(target_w / float(max(1, crop_w)), target_h / float(max(1, crop_h)))
    bg_w = max(target_w, int(round(crop_w * cover)))
    bg_h = max(target_h, int(round(crop_h * cover)))
    background = cv2.resize(crop, (bg_w, bg_h), interpolation=cv2.INTER_AREA)
    bg_x = max(0, (bg_w - target_w) // 2)
    bg_y = max(0, (bg_h - target_h) // 2)
    background = background[bg_y : bg_y + target_h, bg_x : bg_x + target_w]
    sigma = max(8.0, target_w * 0.03)
    background = cv2.GaussianBlur(background, (0, 0), sigmaX=sigma, sigmaY=sigma)
    return (background.astype(np.float32) * 0.55).clip(0, 255).astype(np.uint8)


def _crop_fit_pad(
    frame: np.ndarray,
    rect: tuple[float, float, float, float],
    size: tuple[int, int],
    background: np.ndarray | None = None,
) -> np.ndarray:
    """Fit a facecam crop into the band without cutting the face.

    The leftover sides are filled with a blurred, darkened copy of the same
    crop, which is standard Shorts framing for square or vertical facecams.
    The background is computed once per clip and reused for every frame.
    """
    height, width = frame.shape[:2]
    target_w, target_h = size
    x, y, rect_w, rect_h = rect
    x1 = int(clamp(round(x), 0, max(0, width - 2)))
    y1 = int(clamp(round(y), 0, max(0, height - 2)))
    x2 = int(clamp(round(x + rect_w), x1 + 2, width))
    y2 = int(clamp(round(y + rect_h), y1 + 2, height))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        crop = frame
    crop_h, crop_w = crop.shape[:2]

    scale = min(target_w / float(max(1, crop_w)), target_h / float(max(1, crop_h)))
    fit_w = max(2, int(round(crop_w * scale)))
    fit_h = max(2, int(round(crop_h * scale)))
    interpolation = (
        cv2.INTER_LANCZOS4
        if fit_w > crop_w * 1.05
        else cv2.INTER_AREA
    )
    resized = cv2.resize(crop, (fit_w, fit_h), interpolation=interpolation)

    if background is None or background.shape[:2] != (target_h, target_w):
        background = _facecam_background(frame, rect, size)
    else:
        background = background.copy()

    offset_x = max(0, (target_w - fit_w) // 2)
    offset_y = max(0, (target_h - fit_h) // 2)
    background[offset_y : offset_y + fit_h, offset_x : offset_x + fit_w] = resized
    return background


def _fit_cover(image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Scale to fill the target box, cropping the overflow (center weighted)."""
    target_w, target_h = size
    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        return np.zeros((max(2, target_h), max(2, target_w), 3), dtype=np.uint8)
    scale = max(target_w / float(width), target_h / float(height))
    resized_w = max(2, int(round(width * scale)))
    resized_h = max(2, int(round(height * scale)))
    interpolation = cv2.INTER_LANCZOS4 if scale > 1.05 else cv2.INTER_AREA
    resized = cv2.resize(image, (resized_w, resized_h), interpolation=interpolation)
    offset_x = max(0, (resized_w - target_w) // 2)
    offset_y = max(0, (resized_h - target_h) // 2)
    return resized[offset_y : offset_y + target_h, offset_x : offset_x + target_w]


def _fit_contain(image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Letterbox: the whole frame inside the box, black bars around it."""
    target_w, target_h = size
    height, width = image.shape[:2]
    canvas = np.zeros((max(2, target_h), max(2, target_w), 3), dtype=np.uint8)
    if width <= 0 or height <= 0:
        return canvas
    scale = min(target_w / float(width), target_h / float(height))
    fit_w = max(2, int(round(width * scale)))
    fit_h = max(2, int(round(height * scale)))
    interpolation = cv2.INTER_LANCZOS4 if scale > 1.05 else cv2.INTER_AREA
    resized = cv2.resize(image, (fit_w, fit_h), interpolation=interpolation)
    offset_x = max(0, (target_w - fit_w) // 2)
    offset_y = max(0, (target_h - fit_h) // 2)
    canvas[offset_y : offset_y + fit_h, offset_x : offset_x + fit_w] = resized
    return canvas


def _compose_slots(
    frame: np.ndarray,
    game_crop: np.ndarray,
    slots: list[Any],
    size: tuple[int, int],
    backgrounds: dict[int, np.ndarray],
) -> np.ndarray:
    """Draw every panel of a layout template onto the vertical canvas."""
    target_w, target_h = size
    canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    for index, slot in enumerate(slots):
        x, y, width, height = slot.rect
        width = min(width, target_w - x)
        height = min(height, target_h - y)
        if width <= 1 or height <= 1:
            continue
        target = (width, height)
        if slot.kind == "cam" and slot.box is not None:
            if slot.pad:
                background = backgrounds.get(index)
                if background is None or background.shape[:2] != (height, width):
                    background = _facecam_background(frame, slot.box, target)
                    backgrounds[index] = background
                patch = _crop_fit_pad(frame, slot.box, target, background=background)
            else:
                patch = _crop_fit(frame, slot.box, target)
        elif slot.kind == "full_blur":
            patch = _facecam_background(frame, (0.0, 0.0, float(frame.shape[1]), float(frame.shape[0])), target)
        elif slot.kind == "full":
            patch = _fit_contain(frame, target)
        else:
            patch = _fit_cover(game_crop, target)
        canvas[y : y + patch.shape[0], x : x + patch.shape[1]] = patch
    return canvas


def _gameplay_anchor(
    width: int,
    height: int,
    crop_w: int,
    panel: tuple[float, float, float, float] | None,
) -> tuple[float, float]:
    """Keep the gameplay crop away from a corner facecam."""
    center_x = width / 2.0
    center_y = height / 2.0
    if panel is None:
        return center_x, center_y
    panel_x, _, panel_w, _ = panel
    panel_center = panel_x + panel_w / 2.0
    if panel_center < width * 0.35:
        center_x = (panel_x + panel_w + width) / 2.0
    elif panel_center > width * 0.65:
        center_x = panel_x / 2.0
    half_w = crop_w / 2.0
    center_x = clamp(center_x, half_w, max(half_w, width - half_w))
    return center_x, center_y


def _panel_iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    union = aw * ah + bw * bh - intersection
    return intersection / max(1.0, union)


def _manual_camera_panels(
    boxes: list[Any],
    width: float,
    height: float,
) -> list[tuple[float, float, float, float]]:
    """Turn normalised editor boxes into source-pixel camera panels.

    Rectangles are clamped to the frame and a minimum size is enforced so a
    bad payload can never produce a zero-width crop.
    """
    width = max(1.0, float(width))
    height = max(1.0, float(height))
    panels: list[tuple[float, float, float, float]] = []
    for item in boxes or []:
        if len(panels) >= 4:
            break
        if not isinstance(item, dict):
            continue
        try:
            bx = float(item.get("x", 0.0))
            by = float(item.get("y", 0.0))
            bw = float(item.get("w", 0.0))
            bh = float(item.get("h", 0.0))
        except (TypeError, ValueError):
            continue
        bx = min(max(bx, 0.0), 0.98)
        by = min(max(by, 0.0), 0.98)
        bw = min(max(bw, 0.02), 1.0 - bx)
        bh = min(max(bh, 0.02), 1.0 - by)
        panels.append((bx * width, by * height, bw * width, bh * height))
    panels.sort(key=lambda panel: (round(panel[1] / height * 4), panel[0]))
    return panels


def _detect_facecam_panels(
    source: Path,
    start: float,
    duration: float,
    *,
    info: dict[str, Any] | None = None,
    samples: int = 10,
    max_panels: int = 4,
) -> list[tuple[float, float, float, float]]:
    """Return every stable facecam panel, best cluster first."""
    try:
        metadata = info or probe_media(source)
    except (MediaError, OSError):
        return []
    width = int(metadata.get("width") or 0)
    height = int(metadata.get("height") or 0)
    if width <= 0 or height <= 0:
        return []

    detect_w = min(640, width)
    detect_h = max(2, int(round(height * detect_w / float(width))) // 2 * 2)
    scale_x = width / float(detect_w)
    scale_y = height / float(detect_h)
    tracker = _FaceTracker(settings.face_model)
    boxes: list[tuple[float, float, float, float, float, int]] = []
    valid_samples = 0
    count = max(4, samples)
    for index in range(count):
        at = start + duration * (index + 0.5) / count
        frame = _ffmpeg_frame(source, at, detect_w, detect_h)
        if frame is None:
            continue
        valid_samples += 1
        for box in tracker.detect_boxes(frame):
            boxes.append(
                (
                    box[0] * scale_x,
                    box[1] * scale_y,
                    box[2] * scale_x,
                    box[3] * scale_y,
                    box[4],
                    index,
                )
            )

    clusters = _rank_facecam_clusters(boxes, width, height, valid_samples)
    panels: list[tuple[float, float, float, float]] = []
    for cluster in clusters:
        panel = _estimate_facecam_panel(_cluster_values(cluster), width, height)
        if panel is None:
            continue
        if any(_panel_iou(panel, other) > 0.45 for other in panels):
            continue
        panels.append(panel)
        if len(panels) >= max_panels:
            break
    if not panels:
        logger.info("No se encontro un panel de facecam estable; se usa crop vertical.")
    else:
        logger.info(
            "Paneles de facecam detectados: %s",
            ", ".join(
                f"{x:.0f},{y:.0f} ({w:.0f}x{h:.0f})" for x, y, w, h in panels
            ),
        )
    return panels


def _detect_facecam_panel(
    source: Path,
    start: float,
    duration: float,
    *,
    info: dict[str, Any] | None = None,
    samples: int = 10,
) -> tuple[float, float, float, float] | None:
    """Compatibility wrapper: the main facecam panel, or None."""
    panels = _detect_facecam_panels(
        source,
        start,
        duration,
        info=info,
        samples=samples,
        max_panels=1,
    )
    return panels[0] if panels else None


def _render_video(
    *,
    source: Path,
    clip_dir: Path,
    start: float,
    duration: float,
    removed: list[tuple[float, float]],
    out_duration: float,
    ass_name: str,
    has_subtitles: bool,
    audio_path: Path,
    music_path: Path | None,
    video_tmp: Path,
    thumb_tmp: Path,
    dynamic_zoom: bool,
    progress: Callable[[float], None] | None,
    is_cancelled: Callable[[], bool] | None,
    facecam_panel: tuple[float, float, float, float] | None = None,
    face_band: int = 0,
    slots: list[Any] | None = None,
    output_size: tuple[int, int] | None = None,
    music_level: float | None = None,
    saturation: float = 1.0,
    speech_intervals: list[tuple[float,float]] | None = None,
    transition: str = "cut",
    sound_accent: bool = False,
    logo_file: Path | None = None,
) -> None:
    info = probe_media(source)
    width = int(info["width"])
    height = int(info["height"])
    if width <= 0 or height <= 0:
        raise RenderError("El video no tiene dimensiones validas.")

    source_fps = float(info["fps"] or 30.0)
    out_fps = max(1.0, min(source_fps, float(settings.max_output_fps)))

    target_w, target_h = output_size or (settings.target_w, settings.target_h)
    use_slots = bool(slots)
    split_layout = facecam_panel is not None and face_band > 0 and not use_slots
    game_h = max(2, target_h - face_band) if split_layout else target_h
    base_crop_w, base_crop_h = (
        _plan_crop_aspect(width, height, target_w / target_h)
        if use_slots or not split_layout
        else _plan_crop_aspect(width, height, target_w / float(game_h))
    )
    expected_written = max(1, int(round(out_duration * out_fps)))
    target_frames = expected_written

    graph = _build_audio_graph(removed, out_duration, music_path is not None, music_level)
    if sound_accent:
        graph = graph[:-3] + "[program];sine=frequency=660:duration=0.13,volume=0.10,afade=t=out:st=0.02:d=0.11[cue];[program][cue]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.97[a]"
    filters = []
    if saturation != 1:
        filters.append(f"eq=saturation={saturation:.3f}")
    if transition == "fade":
        span = min(.22, out_duration / 4)
        filters.extend([f"fade=t=in:d={span:.3f}", f"fade=t=out:st={out_duration-span:.3f}:d={span:.3f}"])
    if has_subtitles:
        filters.append(f"subtitles={ass_name}")
    video_filter = "[0:v]" + ",".join([*filters, "format=yuv420p"]) + "[v]"
    filter_complex = f"{video_filter};{graph}"

    command = [
        settings.ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{target_w}x{target_h}",
        "-framerate",
        f"{out_fps:.5f}",
        "-i",
        "pipe:0",
        "-i",
        str(audio_path),
    ]
    if music_path is not None:
        command.extend(["-stream_loop", "-1", "-i", str(music_path)])
    command.extend(
        [
            "-filter_complex_threads",
            "2",
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-threads:v",
            "2",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-maxrate",
            "12M",
            "-bufsize",
            "24M",
            "-g",
            str(max(30, int(round(out_fps * 2.0)))),
            "-x264-params",
            "aq-mode=3:aq-strength=1.0:rc-lookahead=5",
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            "-t",
            f"{out_duration:.3f}",
            str(video_tmp),
        ]
    )

    log_path = clip_dir / "render.log"
    log_file = open(log_path, "wb")
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=log_file,
        cwd=str(clip_dir),
        creationflags=NO_WINDOW,
    )

    from .speakers import SpeakerFocus
    speaker_focus = SpeakerFocus()
    speech_windows = sorted(speech_intervals or [])
    speech_cursor = 0
    logo = cv2.imread(str(logo_file), cv2.IMREAD_UNCHANGED) if logo_file else None
    if logo is not None:
        scale = min(target_w * .16 / logo.shape[1], target_h * .09 / logo.shape[0])
        logo = cv2.resize(logo, (max(1,round(logo.shape[1]*scale)), max(1,round(logo.shape[0]*scale))))
        opacity = (logo[:,:,3:4].astype(np.float32)/255) if logo.shape[2]==4 else 1
    reader = _FrameReader(source, start, duration, width, height, out_fps)
    needs_crop = not slots or any(
        slot.kind == "game" or (slot.kind == "cam" and slot.box is None) for slot in slots
    )
    tracker = _FaceTracker(settings.face_model) if needs_crop and not split_layout else None
    anchor_x, anchor_y = width / 2.0, height / 2.0
    if split_layout and facecam_panel is not None:
        anchor_x, anchor_y = _gameplay_anchor(
            width,
            height,
            base_crop_w,
            facecam_panel,
        )
    camera = _Camera(
        width=width,
        height=height,
        base_crop_w=base_crop_w,
        base_crop_h=base_crop_h,
        duration=duration,
        dynamic_zoom=dynamic_zoom,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
    )
    detect_interval = max(1, int(round(out_fps / 6.0)))
    last_face: tuple[float, float] | None = None
    last_sample_t = -1.0
    written = 0
    frame_number = 0
    thumb_saved = False
    cancelled = False
    next_cancel_check = 0.0
    face_background: np.ndarray | None = None
    slot_backgrounds: dict[int, np.ndarray] = {}

    try:
        # -t already bounds the output; stop feeding the pipe at the same
        # frame count so rounding cannot cause a late BrokenPipeError.
        while written < target_frames:
            frame = reader.read()
            if frame is None:
                break
            if is_cancelled and time.monotonic() >= next_cancel_check:
                next_cancel_check = time.monotonic() + 0.25
                if is_cancelled():
                    cancelled = True
                    break
            current_index = frame_number
            frame_number += 1
            t = current_index / out_fps
            if _inside(t, removed):
                continue
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))

            cropped = frame
            if needs_crop:
                detected: tuple[float, float] | None = None
                if tracker is not None and current_index % detect_interval == 0:
                    while speech_cursor < len(speech_windows) and speech_windows[speech_cursor][1] < t:
                        speech_cursor += 1
                    speaking = speech_cursor < len(speech_windows) and speech_windows[speech_cursor][0] <= t
                    boxes = tracker.detect_boxes(frame)
                    detected = speaker_focus.choose(frame, boxes, speaking)
                    if detected is None:
                        candidate = _choose_face_box(boxes, width, height, last_face)
                        detected = candidate[:2] if candidate else None
                    if detected is not None:
                        last_face = detected
                dt = (
                    1.0 / out_fps
                    if last_sample_t < 0
                    else max(1.0 / out_fps, t - last_sample_t)
                )
                center_x, center_y, crop_w, crop_h = camera.sample(t, detected, dt)
                last_sample_t = t
                cropped = cv2.getRectSubPix(
                    frame,
                    (crop_w, crop_h),
                    (center_x, center_y),
                )
                if cropped is None or cropped.size == 0:
                    continue
            if use_slots:
                resized = _compose_slots(
                    frame,
                    cropped,
                    slots or [],
                    (target_w, target_h),
                    slot_backgrounds,
                )
            else:
                if target_w > crop_w * 1.05 or game_h > crop_h * 1.05:
                    interpolation = cv2.INTER_LANCZOS4
                else:
                    interpolation = cv2.INTER_AREA
                game_frame = cv2.resize(
                    cropped,
                    (target_w, game_h),
                    interpolation=interpolation,
                )
                if split_layout and facecam_panel is not None:
                    if face_background is None:
                        face_background = _facecam_background(
                            frame,
                            facecam_panel,
                            (target_w, face_band),
                        )
                    face_frame = _crop_fit_pad(
                        frame,
                        facecam_panel,
                        (target_w, face_band),
                        background=face_background,
                    )
                    canvas = np.empty((target_h, target_w, 3), dtype=np.uint8)
                    canvas[:face_band] = face_frame
                    canvas[face_band:] = game_frame
                    resized = canvas
                else:
                    resized = game_frame

            if logo is not None:
                ly,lx = round(target_h*.07),round(target_w*.05)
                region = resized[ly:ly+logo.shape[0],lx:lx+logo.shape[1]]
                region[:] = (logo[:,:,:3]*opacity + region*(1-opacity)).astype(np.uint8)
            if not thumb_saved and t >= min(max(0.5, duration * 0.12), 1.5):
                cv2.imwrite(
                    str(thumb_tmp),
                    resized,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 88],
                )
                thumb_saved = True
            try:
                assert process.stdin is not None
                process.stdin.write(memoryview(np.ascontiguousarray(resized)).cast("B"))
            except (BrokenPipeError, OSError):
                # ffmpeg may stop reading as soon as -t is reached. The wait
                # and output validation below decide whether this was normal.
                break
            written += 1
            if progress and written % 12 == 0:
                progress(min(96.0, written / expected_written * 96.0))
    finally:
        reader.close()
        try:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
        except OSError:
            pass

    if cancelled:
        process.kill()
        process.wait(timeout=30)
        log_file.close()
        video_tmp.unlink(missing_ok=True)
        thumb_tmp.unlink(missing_ok=True)
        raise CancelledError("Render cancelado.")

    try:
        return_code = process.wait(timeout=3600)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=30)
        return_code = -1
    log_file.close()

    if return_code != 0 or not video_tmp.exists() or video_tmp.stat().st_size == 0:
        tail = ""
        try:
            tail = " | ".join(log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:])
        except OSError:
            pass
        raise RenderError(f"El render fallo: {tail or 'sin detalles'}")
    if written < expected_written * 0.5:
        raise RenderError("Se leyeron muy pocos fotogramas del video de origen.")


def _extract_thumbnail(video: Path, destination: Path, duration: float) -> None:
    at = max(0.1, min(1.5, max(0.1, duration) * 0.15))
    try:
        run_ffmpeg(
            [
                "-y",
                "-ss",
                fmt_seconds(at),
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-an",
                "-vf",
                "scale=480:-2:flags=lanczos",
                "-q:v",
                "2",
                str(destination),
            ],
            timeout=120,
        )
    except (MediaError, OSError) as exc:
        logger.debug("No se pudo extraer la miniatura con ffmpeg: %s", exc)
    if destination.exists() and destination.stat().st_size > 0:
        return

    destination.unlink(missing_ok=True)
    capture = cv2.VideoCapture(str(video))
    try:
        capture.set(cv2.CAP_PROP_POS_MSEC, at * 1000.0)
        ok, frame = capture.read()
        if not ok or frame is None:
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = capture.read()
        if not ok or frame is None:
            raise MediaError("No se pudo leer un fotograma para la miniatura.")
        height, width = frame.shape[:2]
        thumb_w = 480
        thumb_h = max(2, int(round(height * thumb_w / float(max(1, width)))) // 2 * 2)
        resized = cv2.resize(
            frame,
            (thumb_w, thumb_h),
            interpolation=cv2.INTER_AREA,
        )
        if not cv2.imwrite(
            str(destination),
            resized,
            [int(cv2.IMWRITE_JPEG_QUALITY), 90],
        ):
            raise MediaError("OpenCV no pudo guardar la miniatura.")
    finally:
        capture.release()


def render_clip(
    *,
    source: Path,
    clip: dict[str, Any],
    options: dict[str, Any],
    music_path: Path | None,
    clip_dir: Path,
    progress: Callable[[float], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    clip_dir.mkdir(parents=True, exist_ok=True)
    start = float(clip["start"])
    duration = float(clip["end"]) - start
    if duration <= 0:
        raise RenderError("El clip tiene una duracion invalida.")

    info = probe_media(source)
    has_audio = bool(info.get("has_audio"))
    render_source = source
    render_start = start
    proxy_path: Path | None = None
    render_info = info
    if _needs_render_proxy(info):
        candidate = clip_dir / "render_source.mp4"
        if candidate.exists() and candidate.stat().st_size > 1024:
            try:
                probe_media(candidate)
                proxy_path = candidate
            except MediaError:
                candidate.unlink(missing_ok=True)
        if proxy_path is None:
            proxy_path = _build_render_proxy(
                source,
                start,
                duration,
                candidate,
                info,
            )
        if proxy_path is not None:
            render_source = proxy_path
            render_start = 0.0
            render_info = probe_media(proxy_path)

    overlay = clip.get("overlay") or {}
    # Older clips can still carry the former channel/game label and its
    # generic fallback. Neither should be burned into a new export.
    fallback_labels = {
        f"LO MEJOR DE {name}".upper()
        for name in (overlay.get("game"), overlay.get("streamer"))
        if name
    }
    if str(overlay.get("context") or "").strip().upper() in fallback_labels:
        overlay = {**overlay, "context": ""}
    layout_value = layouts.normalize_template(options.get("layout"))
    context_overlay = bool(options.get("context_overlay", True))
    landscape = render_info["width"] > render_info["height"]
    source_w = float(render_info["width"] or 1)
    source_h = float(render_info["height"] or 1)

    # Manual camera boxes come from the studio editor, normalised to the
    # source frame. They replace detection for the camera slots.
    manual_panels = _manual_camera_panels(
        options.get("manual_cams") or [],
        source_w,
        source_h,
    )

    panels: list[tuple[float, float, float, float]] = []
    if layout_value not in {"vertical", "horizontal", "centrado", "spotlight"}:
        if manual_panels:
            panels = manual_panels
        else:
            panels = _detect_facecam_panels(
                render_source,
                render_start,
                duration,
                info=render_info,
            )
            panels.sort(key=lambda panel: (round(panel[1] / source_h * 4), panel[0]))
    if layout_value == "auto":
        total_area = float(
            max(1, int(render_info["width"])) * max(1, int(render_info["height"]))
        )
        cam_area = sum(panel[2] * panel[3] for panel in panels)
        has_content = bool(panels) and cam_area / total_area < 0.55
        median_h = (
            statistics.median([panel[3] for panel in panels]) if panels else 0.0
        )
        small_cams = median_h < source_h * 0.35
        template = layouts.choose_template(
            len(panels),
            has_content=has_content,
            small_cams=small_cams,
        )
    else:
        template = layout_value
    plan = layouts.build_plan(template, panels)
    use_slots = template != "vertical" and bool(plan.slots)
    default_size = (settings.target_w, settings.target_h)
    output_size = {"1:1": (1080, 1080), "16:9": (1920, 1080)}.get(options.get("aspect"), default_size)
    slots = None
    if use_slots:
        from dataclasses import replace
        sx, sy = output_size[0] / layouts.CANVAS_W, output_size[1] / layouts.CANVAS_H
        slots = [replace(slot, rect=tuple(round(v * scale) for v, scale in
                 zip(slot.rect, (sx, sy, sx, sy)))) for slot in plan.slots]
    logger.info("Layout del clip: %s (%d paneles)", template, len(panels))
    # The legacy split path stays reachable through ``facecam_panel`` for
    # vertical renders, but template layouts go through the slot compositor.
    facecam_panel: tuple[float, float, float, float] | None = None
    face_band = 0

    audio_path = clip_dir / "audio.wav"
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        extract_clip_audio(source, start, duration, audio_path, has_audio=has_audio)

    removed: list[tuple[float, float]] = []
    silence_cache = clip_dir / "silences.json"
    if bool(options.get("remove_silences", True)) and has_audio:
        cache_valid = False
        if silence_cache.exists():
            try:
                cached = json.loads(silence_cache.read_text(encoding="utf-8"))
                if cached.get("version") == 2:
                    removed = [
                        (float(a), float(b)) for a, b in cached.get("intervals", [])
                    ]
                    cache_valid = True
                else:
                    removed = []
            except (ValueError, TypeError, OSError):
                removed = []
        if not cache_valid:
            raw = detect_silences(audio_path, duration)
            removed = compress_silences(raw, duration)
            try:
                silence_cache.write_text(
                    json.dumps({"version": 2, "intervals": removed}),
                    encoding="utf-8",
                )
            except OSError:
                pass

    # Apply on every render, including cached silence detection, because the
    # user may have corrected the subtitle timing since the preceding render.
    removed = protect_speech(removed, (clip.get("subtitles") or {}).get("cues") or [])
    out_duration = max(1.0, duration - sum(end - begin for begin, end in removed))

    def time_map(seconds: float) -> float:
        return map_time(seconds, removed)

    subtitles = clip.get("subtitles") or {}
    cues = subtitles.get("cues") or []
    style = str(clip.get("style") or settings.default_subtitle_style)
    title_card: dict[str, Any] | None = None
    card_text = str(options.get("title_card") or "").strip()
    if card_text:
        title_card = {
            "text": card_text,
            "seconds": options.get("title_card_seconds", 4.0),
            "position": options.get("title_card_position", "top"),
            "style": options.get("title_card_style", "impact"),
        }
    ass_name = "subs.ass"
    ass_text = build_ass(
        cues,
        style,
        time_map=time_map,
        duration=out_duration,
        overlay=overlay if context_overlay else None,
        top_offset=face_band,
        anchor_y=({"tiktok":1320,"shorts":1420,"instagram":1380,"facebook":1380}.get(options.get("platform")) or (plan.caption_anchor if use_slots else None)),
        title_card=title_card,
        font=options.get("caption_font"),
        colors=(options.get("caption_color"), options.get("accent_color")),
        script_width=round(1920 * output_size[0] / output_size[1]),
        brand_text=options.get("brand_text", ""),
    )
    (clip_dir / ass_name).write_text(ass_text, encoding="utf-8")
    srt_text = cues_to_srt(cues, time_map=time_map, duration=out_duration)
    (clip_dir / "subs.srt").write_text(srt_text, encoding="utf-8")
    has_subtitles = (
        bool(cues)
        or title_card is not None
        or bool(options.get("brand_text"))
        or bool(context_overlay and overlay.get("context"))
    )

    video_tmp = clip_dir / "render.mp4"
    thumb_tmp = clip_dir / "thumb_tmp.jpg"
    thumb_tmp.unlink(missing_ok=True)

    if progress:
        progress(1.0)
    logo_id = str(options.get("logo_id") or "")
    brand_logo = settings.data_dir / "brand" / (logo_id + ".png") if len(logo_id)==32 and all(c in "0123456789abcdef" for c in logo_id) else None
    _render_video(
        source=render_source,
        clip_dir=clip_dir,
        start=render_start,
        duration=duration,
        removed=removed,
        out_duration=out_duration,
        ass_name=ass_name,
        has_subtitles=has_subtitles,
        audio_path=audio_path,
        music_path=music_path,
        video_tmp=video_tmp,
        thumb_tmp=thumb_tmp,
        dynamic_zoom=bool(options.get("dynamic_zoom", True)),
        progress=progress,
        is_cancelled=is_cancelled,
        facecam_panel=facecam_panel,
        face_band=face_band,
        slots=slots,
        output_size=output_size,
        music_level=options.get("music_level"),
        saturation=float(options.get("saturation", 1)),
        speech_intervals=[(float(c["start"]), float(c["end"])) for c in cues],
        transition=options.get("transition","cut"),
        sound_accent=bool(options.get("sound_accent")),
        logo_file=brand_logo,
    )
    if proxy_path is not None:
        proxy_path.unlink(missing_ok=True)

    # Windows no permite reemplazar un archivo que el navegador todavía tiene
    # abierto. Cada render usa nombres nuevos; la URL del API no cambia y el
    # pipeline actualiza video_file/thumb_file en la base de datos.
    suffix = uuid.uuid4().hex[:12]
    video_path = clip_dir / f"video-{suffix}.mp4"
    thumb_path = clip_dir / f"thumb-{suffix}.jpg"
    os.replace(video_tmp, video_path)
    final_thumb = clip_dir / f"thumb-final-{suffix}.jpg"
    try:
        _extract_thumbnail(video_path, final_thumb, out_duration)
        os.replace(final_thumb, thumb_path)
        thumb_tmp.unlink(missing_ok=True)
    except (MediaError, OSError, cv2.error):
        logger.debug("Se usa la miniatura temprana para el clip %s", suffix)
        final_thumb.unlink(missing_ok=True)
        if thumb_tmp.exists():
            os.replace(thumb_tmp, thumb_path)
        elif not thumb_path.exists():
            raise RenderError("No se pudo generar la miniatura del clip.")

    if progress:
        progress(100.0)
    return {
        "video": video_path,
        "thumb": thumb_path,
        "ass": clip_dir / ass_name,
        "duration": round(out_duration, 3),
    }
