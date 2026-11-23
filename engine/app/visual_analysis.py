from __future__ import annotations

import logging
import math
import subprocess
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np

from .audio_analysis import _clamp
from .config import settings
from .utils import MediaError, NO_WINDOW

logger = logging.getLogger(__name__)

_MAX_ANALYSIS_SECONDS = 90 * 60


def _decode_frames(path: Path, *, duration: float) -> Iterator[tuple[float, np.ndarray]]:
    """Yield RGB frames from ffmpeg's MJPEG pipe at a bounded sampling rate."""
    if duration <= 20 * 60:
        sample_rate = 2.0
    else:
        sample_rate = 1.0
    command = [
        settings.ffmpeg,
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-vf",
        f"fps={sample_rate},scale=320:-2",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "-q:v",
        "4",
        "-",
    ]
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise MediaError(f"No se encontro ffmpeg: {settings.ffmpeg}") from exc
    assert process.stdout is not None
    buffer = b""
    index = 0
    try:
        while True:
            chunk = process.stdout.read(64 * 1024)
            if not chunk:
                break
            buffer += chunk
            while True:
                start = buffer.find(b"\xff\xd8")
                end = buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                if start < 0 or end < 0:
                    break
                payload = buffer[start : end + 2]
                buffer = buffer[end + 2 :]
                frame = cv2.imdecode(
                    np.frombuffer(payload, dtype=np.uint8),
                    cv2.IMREAD_COLOR,
                )
                if frame is None or frame.size == 0:
                    continue
                timestamp = index / float(sample_rate)
                index += 1
                yield round(timestamp, 3), frame
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)


def _hist_difference(current: np.ndarray, previous: np.ndarray | None) -> float:
    if previous is None:
        return 0.0
    current_hist = cv2.calcHist([current], [0], None, [32], [0, 256])
    previous_hist = cv2.calcHist([previous], [0], None, [32], [0, 256])
    cv2.normalize(current_hist, current_hist)
    cv2.normalize(previous_hist, previous_hist)
    return float(np.sum(np.abs(current_hist - previous_hist)) / 2.0)


def _face_crop(frame: np.ndarray, box: tuple[float, float, float, float, float], *, lower: bool) -> np.ndarray | None:
    height, width = frame.shape[:2]
    cx, cy, face_w, face_h, _ = box
    left = max(0, int(cx - face_w / 2.0))
    right = min(width, int(cx + face_w / 2.0))
    if lower:
        top = max(0, int(cy - face_h * 0.05))
        bottom = min(height, int(cy + face_h / 2.0))
    else:
        top = max(0, int(cy - face_h / 2.0))
        bottom = min(height, int(cy + face_h / 2.0))
    if right - left < 8 or bottom - top < 8:
        return None
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return None
    return cv2.resize(crop, (64, 64), interpolation=cv2.INTER_AREA)


def _clusters(mask: list[bool], times: list[float], *, gap: float = 2.0) -> list[tuple[int, int]]:
    clusters: list[tuple[int, int]] = []
    start: int | None = None
    last = -1
    for index, active in enumerate(mask):
        if not active:
            continue
        if start is None:
            start = index
        elif times[index] - times[last] > gap:
            clusters.append((start, last))
            start = index
        last = index
    if start is not None:
        clusters.append((start, last))
    return clusters


def _median_mad(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    array = np.asarray(values, dtype=np.float64)
    median = float(np.median(array))
    mad = float(np.median(np.abs(array - median)))
    return median, mad


def build_visual_features(
    samples: list[dict[str, Any]],
    *,
    scenes: list[dict[str, float]] | None = None,
    duration: float | None = None,
) -> dict[str, Any]:
    """Build motion and face-reaction events from sampled frame features."""
    if not samples:
        return {
            "available": False,
            "times": [],
            "motion": [],
            "center_motion": [],
            "face_motion": [],
            "head_motion": [],
            "face_crop_motion": [],
            "mouth_motion": [],
            "face_present": [],
            "hist_diff": [],
            "events": [],
            "motion_median": 0.0,
            "motion_mad": 0.0,
            "face_present_ratio": 0.0,
        }
    times = [float(sample["t"]) for sample in samples]
    motion = [float(sample.get("motion", 0.0)) for sample in samples]
    center_motion = [float(sample.get("center_motion", 0.0)) for sample in samples]
    face_motion = [float(sample.get("face_motion", 0.0)) for sample in samples]
    head_motion = [float(sample.get("head_motion", 0.0)) for sample in samples]
    face_crop_motion = [float(sample.get("face_crop_motion", 0.0)) for sample in samples]
    mouth_motion = [float(sample.get("mouth_motion", 0.0)) for sample in samples]
    face_present = [float(sample.get("face_present", 0.0)) for sample in samples]
    hist_diff = [float(sample.get("hist_diff", 0.0)) for sample in samples]
    # New samples split head movement from crop change.  Older/synthetic
    # samples only carry the combined face_motion field; keep that path working.
    split_face = any("head_motion" in sample or "face_crop_motion" in sample for sample in samples)

    motion_median, motion_mad = _median_mad(motion)
    face_median, face_mad = _median_mad(head_motion if split_face else face_motion)
    crop_median, crop_mad = _median_mad(face_crop_motion)
    mouth_median, mouth_mad = _median_mad(mouth_motion)
    hist_median, hist_mad = _median_mad(hist_diff)

    motion_threshold = motion_median + max(0.012, motion_mad * 3.2)
    face_threshold = face_median + max(0.012, face_mad * 3.0)
    crop_threshold = crop_median + max(0.055, crop_mad * 4.0)
    # Talking produces a steady mouth-crop change of roughly 0.02-0.04.
    # Require a much larger deformation before calling it a reaction.
    mouth_threshold = mouth_median + max(0.05, mouth_mad * 3.0)
    hist_threshold = hist_median + max(0.10, hist_mad * 4.0)

    # A dissolve can cross the threshold on successive frames. Keep its
    # strongest transition as the cut point in the sampled timeline.
    if scenes is None and duration and times[-1] >= duration - 1.5:
        cut_hist = hist_median + max(0.10, hist_mad)
        cut_motion = motion_median + max(0.035, 1.5 * motion_mad)
        transitions = _clusters(
            [h >= cut_hist and m >= cut_motion for h, m in zip(hist_diff, motion)],
            times, gap=0.55,
        )
        cuts = [times[max(range(a, b + 1), key=hist_diff.__getitem__)] for a, b in transitions]
        boundaries = [0.0, *(t for t in cuts if 0.7 <= t <= duration - 0.7), duration]
        scenes = [
            {"start": left, "end": right}
            for left, right in zip(boundaries, boundaries[1:])
        ] if len(boundaries) > 2 else []

    events: list[dict[str, Any]] = []

    def add_clusters(
        values: list[float],
        threshold: float,
        kind: str,
        *,
        score_bonus: float = 0.0,
        gap: float = 2.0,
    ) -> None:
        mask = [value >= threshold for value in values]
        for first, last in _clusters(mask, times, gap=gap):
            peak = max(values[first : last + 1]) if last >= first else 0.0
            relative = (peak - threshold) / max(0.01, motion_mad + 0.01)
            events.append(
                {
                    "kind": kind,
                    "source": "visual",
                    "start": round(max(0.0, times[first] - 0.6), 3),
                    "end": round(times[last] + 0.8, 3),
                    "score": round(_clamp(48.0 + relative * 7.0 + score_bonus), 1),
                    "confidence": round(_clamp(48.0 + relative * 7.0 + score_bonus) / 100.0, 3),
                    "peak": round(peak, 4),
                    "threshold": round(threshold, 4),
                }
            )

    add_clusters(motion, motion_threshold, "motion_burst", score_bonus=2.0)
    if split_face:
        add_clusters(head_motion, face_threshold, "face_reaction", score_bonus=7.0)
        add_clusters(face_crop_motion, crop_threshold, "face_expression", score_bonus=6.0)
    else:
        add_clusters(face_motion, face_threshold, "face_reaction", score_bonus=7.0)
    add_clusters(mouth_motion, mouth_threshold, "visual_reaction", score_bonus=4.0)
    add_clusters(hist_diff, hist_threshold, "scene_change", score_bonus=3.0, gap=1.0)

    for scene in scenes or []:
        start = float(scene.get("start", 0.0))
        if start > 0.5:
            events.append(
                {
                    "kind": "scene_cut",
                    "source": "visual",
                    "start": round(start, 3),
                    "end": round(start + 0.5, 3),
                    "score": 54.0,
                    "confidence": 0.55,
                    "peak": 1.0,
                    "threshold": 0.5,
                }
            )

    events.sort(key=lambda item: float(item["start"]))
    return {
        "available": True,
        "scenes": scenes,
        "times": times,
        "motion": motion,
        "center_motion": center_motion,
        "face_motion": face_motion,
        "head_motion": head_motion,
        "face_crop_motion": face_crop_motion,
        "mouth_motion": mouth_motion,
        "face_present": face_present,
        "hist_diff": hist_diff,
        "events": events,
        "motion_median": round(motion_median, 5),
        "motion_mad": round(motion_mad, 5),
        "face_present_ratio": round(sum(face_present) / max(1, len(face_present)), 3),
    }


def analyze_visual(
    path: Path,
    *,
    duration: float,
    scenes: list[dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Sample a video for motion, face reactions and scene changes.

    Long sources use the audio-first path and never reach this function.  The
    normal YouTube/upload path has the full file on disk, so visual evidence is
    available during moment selection.
    """
    if duration > _MAX_ANALYSIS_SECONDS:
        logger.info(
            "Video de %.0f s: se omite el analisis visual para no bloquear el trabajo.",
            duration,
        )
        return build_visual_features([])
    try:
        from .render import _FaceTracker

        tracker = _FaceTracker(settings.face_model)
    except Exception as exc:  # pragma: no cover - depends on OpenCV build
        logger.warning("Detector facial no disponible: %s", exc)
        tracker = None

    samples: list[dict[str, Any]] = []
    previous_gray: np.ndarray | None = None
    previous_face: tuple[float, float, float, float, float] | None = None
    previous_face_crop: np.ndarray | None = None
    previous_mouth_crop: np.ndarray | None = None
    try:
        for timestamp, frame in _decode_frames(path, duration=duration):
            height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small_width = 160
            small_height = max(90, int(round(height * small_width / max(1, width))))
            small = cv2.resize(gray, (small_width, small_height), interpolation=cv2.INTER_AREA)
            if previous_gray is None:
                motion = 0.0
                center_motion = 0.0
                hist_diff = 0.0
            else:
                difference = cv2.absdiff(small, previous_gray)
                motion = float(np.mean(difference) / 255.0)
                x0 = int(small_width * 0.20)
                x1 = int(small_width * 0.80)
                y0 = int(small_height * 0.20)
                y1 = int(small_height * 0.80)
                center_motion = float(np.mean(difference[y0:y1, x0:x1]) / 255.0)
                hist_diff = _hist_difference(small, previous_gray)
            previous_gray = small

            boxes = tracker.detect_boxes(frame) if tracker is not None else []
            box = None
            if boxes:
                box = max(boxes, key=lambda item: float(item[2]) * float(item[3]))
            face_present = 1.0 if box else 0.0
            head_motion = 0.0
            face_crop_motion = 0.0
            mouth_motion = 0.0
            face_area = 0.0
            face_cx = 0.0
            face_cy = 0.0
            if box is not None:
                face_cx = float(box[0]) / max(1.0, width)
                face_cy = float(box[1]) / max(1.0, height)
                face_area = float(box[2]) * float(box[3]) / max(1.0, width * height)
                if previous_face is not None:
                    previous_cx = previous_face[0] / max(1.0, width)
                    previous_cy = previous_face[1] / max(1.0, height)
                    head_motion = math.hypot(face_cx - previous_cx, face_cy - previous_cy)
                current_face_crop = _face_crop(frame, box, lower=False)
                current_mouth_crop = _face_crop(frame, box, lower=True)
                if (
                    current_face_crop is not None
                    and previous_face_crop is not None
                    and current_face_crop.shape == previous_face_crop.shape
                ):
                    face_crop_motion = float(
                        np.mean(cv2.absdiff(current_face_crop, previous_face_crop)) / 255.0
                    )
                if (
                    current_mouth_crop is not None
                    and previous_mouth_crop is not None
                    and current_mouth_crop.shape == previous_mouth_crop.shape
                ):
                    mouth_motion = float(
                        np.mean(cv2.absdiff(current_mouth_crop, previous_mouth_crop)) / 255.0
                    )
                previous_face_crop = current_face_crop
                previous_mouth_crop = current_mouth_crop
                previous_face = box
            else:
                previous_face = None
                previous_face_crop = None
                previous_mouth_crop = None

            samples.append(
                {
                    "t": timestamp,
                    "motion": motion,
                    "center_motion": center_motion,
                    "face_motion": max(head_motion, face_crop_motion),
                    "head_motion": head_motion,
                    "face_crop_motion": face_crop_motion,
                    "mouth_motion": mouth_motion,
                    "face_present": face_present,
                    "face_area": face_area,
                    "face_cx": face_cx,
                    "face_cy": face_cy,
                    "hist_diff": hist_diff,
                }
            )
    except Exception as exc:  # keep the job alive if a codec misbehaves
        logger.warning("Analisis visual fallido: %s", exc)
        return build_visual_features([])

    features = build_visual_features(samples, scenes=scenes, duration=duration)
    logger.info(
        "Analisis visual: %d muestras, %d eventos, cara presente %.0f%%.",
        len(samples),
        len(features.get("events") or []),
        float(features.get("face_present_ratio") or 0.0) * 100.0,
    )
    return features
