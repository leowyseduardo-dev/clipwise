from __future__ import annotations

import logging
import math
import subprocess
from pathlib import Path
from typing import Iterator

import numpy as np

from .config import settings
from .utils import MediaError, NO_WINDOW

logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000
FRAME_SECONDS = 0.5
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_SECONDS)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _to_db(value: float) -> float:
    return 20.0 * math.log10(max(1e-8, value))


def _rolling_median(values: np.ndarray, window: int) -> np.ndarray:
    if values.size == 0:
        return values
    window = max(1, min(window, values.size if values.size % 2 else values.size - 1))
    if window <= 1:
        return values.copy()
    pad = window // 2
    padded = np.pad(values, (pad, pad), mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(padded, window)
    return np.median(view, axis=1)


def _mask_clusters(mask: np.ndarray, times: np.ndarray, gap_frames: int = 2) -> list[tuple[int, int]]:
    clusters: list[tuple[int, int]] = []
    start: int | None = None
    last_true = -10_000
    for index, active in enumerate(mask):
        if not active:
            continue
        if start is None:
            start = index
        elif index - last_true > gap_frames:
            clusters.append((start, last_true))
            start = index
        last_true = index
    if start is not None:
        clusters.append((start, last_true))
    return clusters


def _count_bursts(envelope: np.ndarray) -> int:
    if envelope.size < 3:
        return 0
    mean = float(np.mean(envelope))
    spread = float(np.std(envelope))
    threshold = mean + 0.35 * spread
    count = 0
    for index in range(1, len(envelope) - 1):
        if envelope[index] < threshold:
            continue
        # Strict on the left so a flat sustained tone is one plateau, not one
        # "burst" per 50 ms frame.
        if envelope[index] > envelope[index - 1] and envelope[index] >= envelope[index + 1]:
            count += 1
    return count


def _envelope_burst_count(
    samples: np.ndarray,
    sample_rate: int,
    start: float,
    end: float,
) -> int:
    """Count amplitude peaks inside an event with a 50 ms envelope.

    The main timeline uses 0.5 s frames, which is right for loudness and
    silence but blurs the 4-8 bursts that make laughter read as laughter
    instead of as one long scream.
    """
    if sample_rate <= 0 or end <= start:
        return 0
    first = max(0, int(start * sample_rate))
    last = min(samples.size, int(end * sample_rate))
    if last - first < sample_rate // 10:
        return 0
    segment = samples[first:last].astype(np.float32, copy=False)
    hop = max(8, int(sample_rate * 0.05))
    frame_count = segment.size // hop
    if frame_count < 3:
        return 0
    frames = segment[: frame_count * hop].reshape(frame_count, hop)
    envelope = np.sqrt(np.mean(np.square(frames), axis=1, dtype=np.float64))
    bursts = _count_bursts(envelope)
    if bursts < 4:
        return 0
    # A sustained tone also has tiny ripples that can look like peaks. Real
    # laughter rises and falls enough that its 50 ms envelope has a high
    # coefficient of variation.
    mean = float(np.mean(envelope))
    if mean <= 1e-9 or float(np.std(envelope)) / mean < 0.70:
        return 0
    return bursts


def build_audio_features(
    samples: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
    *,
    duration: float | None = None,
) -> dict[str, object]:
    """Analyze mono float samples without touching the filesystem.

    Keeping this pure makes the detector testable with synthetic signals and
    keeps the ffmpeg decoding concern in :func:`analyze_audio`.
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        return {
            "available": False,
            "times": [],
            "rms_db": [],
            "peak_db": [],
            "zcr": [],
            "centroid": [],
            "high_ratio": [],
            "flatness": [],
            "flux": [],
            "events": [],
            "baseline_db": -60.0,
            "noise_floor_db": -60.0,
            "rms_median": -60.0,
            "rms_p90": -60.0,
            "hop": FRAME_SECONDS,
        }

    frame_samples = max(128, int(round(sample_rate * FRAME_SECONDS)))
    frame_count = max(1, int(math.ceil(samples.size / frame_samples)))
    padded = np.zeros(frame_count * frame_samples, dtype=np.float32)
    padded[: samples.size] = samples

    rms_values: list[float] = []
    peak_values: list[float] = []
    zcr_values: list[float] = []
    centroid_values: list[float] = []
    high_ratio_values: list[float] = []
    flatness_values: list[float] = []
    flux_values: list[float] = []
    times: list[float] = []
    prev_mag: np.ndarray | None = None
    window = np.hanning(frame_samples).astype(np.float32)
    freqs = np.fft.rfftfreq(frame_samples, 1.0 / float(sample_rate))
    high_mask = freqs >= min(1800.0, sample_rate * 0.24)

    for index in range(frame_count):
        frame = padded[index * frame_samples : (index + 1) * frame_samples]
        rms = float(np.sqrt(np.mean(np.square(frame), dtype=np.float64)))
        peak = float(np.max(np.abs(frame)))
        rms_values.append(_to_db(rms))
        peak_values.append(_to_db(peak))
        signs = np.signbit(frame)
        zcr_values.append(float(np.mean(signs[1:] != signs[:-1])) if frame.size > 1 else 0.0)
        magnitude = np.abs(np.fft.rfft(frame * window))
        total = float(np.sum(magnitude)) + 1e-12
        centroid = float(np.sum(freqs * magnitude) / total)
        centroid_values.append(centroid)
        energy = np.square(magnitude)
        total_energy = float(np.sum(energy)) + 1e-12
        high_ratio_values.append(float(np.sum(energy[high_mask]) / total_energy))
        flatness_values.append(
            float(np.exp(np.mean(np.log(magnitude + 1e-10))) / (np.mean(magnitude) + 1e-10))
        )
        if prev_mag is None:
            flux_values.append(0.0)
        else:
            positive = np.maximum(0.0, magnitude - prev_mag)
            flux_values.append(float(np.sum(positive) / total))
        prev_mag = magnitude
        times.append(round(index * FRAME_SECONDS, 3))

    rms = np.asarray(rms_values, dtype=np.float64)
    peak = np.asarray(peak_values, dtype=np.float64)
    zcr = np.asarray(zcr_values, dtype=np.float64)
    centroid = np.asarray(centroid_values, dtype=np.float64)
    high_ratio = np.asarray(high_ratio_values, dtype=np.float64)
    flatness = np.asarray(flatness_values, dtype=np.float64)
    flux = np.asarray(flux_values, dtype=np.float64)

    # A short median window removes the normal syllable envelope while keeping
    # a genuine shout or a laugh burst visible.  Baseline is local, not global,
    # so a stream that is loud for ten minutes does not become "all peaks".
    smoothed = np.convolve(rms, np.ones(3, dtype=np.float64) / 3.0, mode="same")
    baseline = _rolling_median(smoothed, 11)
    noise_floor = float(np.percentile(rms, 10))
    rms_median = float(np.median(rms))
    rms_p90 = float(np.percentile(rms, 90))
    delta = smoothed - baseline

    high_mask = (
        (delta >= 4.2)
        & (smoothed >= noise_floor + 4.0)
        & (smoothed > -55.0)
    )
    events: list[dict[str, object]] = []
    for start_index, end_index in _mask_clusters(high_mask, np.asarray(times), gap_frames=2):
        left = max(0, start_index - 1)
        right = min(frame_count - 1, end_index + 1)
        peak_index = int(np.argmax(smoothed[left : right + 1]) + left)
        length = max(0.25, (right - left + 1) * FRAME_SECONDS)
        peak_delta = float(peak[peak_index] - baseline[peak_index])
        centroid_mean = float(np.mean(centroid[left : right + 1]))
        zcr_mean = float(np.mean(zcr[left : right + 1]))
        high_mean = float(np.mean(high_ratio[left : right + 1]))
        flux_mean = float(np.mean(flux[left : right + 1]))
        bursts = _envelope_burst_count(
            samples,
            sample_rate,
            float(times[left]),
            float(times[right]) + FRAME_SECONDS,
        )
        scream = (
            peak_delta >= 9.0
            and length <= 5.0
            and (zcr_mean >= 0.11 or centroid_mean >= 1500.0 or high_mean >= 0.45)
        )
        laughter = (
            1.2 <= length <= 8.5
            and bursts >= 4
            and (zcr_mean >= 0.08 or high_mean >= 0.28)
            and peak_delta >= 3.0
        )
        # Repeated amplitude peaks are laughter; a sustained high-energy
        # scream is one event. Check laughter first so a 2-4 second laugh is
        # not swallowed by the scream condition.
        if laughter:
            kind = "laughter"
        elif scream:
            kind = "scream"
        else:
            kind = "volume_peak"
        score = _clamp(
            48.0
            + peak_delta * 3.1
            + (12.0 if scream else 0.0)
            + (8.0 if laughter else 0.0)
            + min(10.0, flux_mean * 100.0)
        )
        events.append(
            {
                "kind": kind,
                "source": "audio",
                "start": round(float(times[left]), 3),
                "end": round(float(times[right]) + FRAME_SECONDS, 3),
                "score": round(score, 1),
                "confidence": round(_clamp(score, 0.0, 100.0) / 100.0, 3),
                "peak_db": round(float(peak[peak_index]), 2),
                "baseline_db": round(float(baseline[peak_index]), 2),
                "delta_db": round(peak_delta, 2),
                "zcr": round(zcr_mean, 4),
                "centroid": round(centroid_mean, 1),
                "high_ratio": round(high_mean, 3),
                "flux": round(flux_mean, 4),
                "bursts": bursts,
            }
        )

    # A loud reaction followed by a sudden drop is often the real punchline:
    # the streamer stops, stares at the screen, or the lobby goes quiet.
    # Compare against the previous five seconds, not a centred median, so the
    # drop itself does not drag the baseline down with it.
    prior = np.empty_like(smoothed)
    for index in range(smoothed.size):
        window = smoothed[max(0, index - 10) : index]
        prior[index] = float(np.max(window)) if window.size else smoothed[index]
    quiet = (smoothed < prior - 8.0) & (smoothed < rms_median - 6.0)
    for start_index, end_index in _mask_clusters(quiet, np.asarray(times), gap_frames=2):
        length = (end_index - start_index + 1) * FRAME_SECONDS
        if length < 1.5:
            continue
        before = smoothed[max(0, start_index - 10) : start_index]
        quiet_peak = float(np.max(smoothed[start_index : end_index + 1]))
        if before.size == 0 or float(np.max(before)) < quiet_peak + 8.0:
            continue
        events.append(
            {
                "kind": "sudden_silence",
                "source": "audio",
                "start": round(float(times[start_index]), 3),
                "end": round(float(times[end_index]) + FRAME_SECONDS, 3),
                "score": 48.0,
                "confidence": 0.5,
                "peak_db": round(float(peak[start_index]), 2),
                "baseline_db": round(float(baseline[start_index]), 2),
                "delta_db": round(float(smoothed[start_index] - baseline[start_index]), 2),
            }
        )

    events.sort(key=lambda item: float(item["start"]))
    return {
        "available": True,
        "sample_rate": sample_rate,
        "hop": FRAME_SECONDS,
        "times": times,
        "rms_db": [round(float(value), 2) for value in rms],
        "peak_db": [round(float(value), 2) for value in peak],
        "zcr": [round(float(value), 4) for value in zcr],
        "centroid": [round(float(value), 1) for value in centroid],
        "high_ratio": [round(float(value), 4) for value in high_ratio],
        "flatness": [round(float(value), 4) for value in flatness],
        "flux": [round(float(value), 4) for value in flux],
        "baseline_db": round(float(np.median(baseline)), 2),
        "noise_floor_db": round(noise_floor, 2),
        "rms_median": round(rms_median, 2),
        "rms_p90": round(rms_p90, 2),
        "events": events,
    }


def _iter_audio_frames(path: Path, sample_rate: int) -> Iterator[np.ndarray]:
    frame_samples = max(128, int(round(sample_rate * FRAME_SECONDS)))
    frame_bytes = frame_samples * 4
    command = [
        settings.ffmpeg,
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
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
    pending = b""
    try:
        while True:
            chunk = process.stdout.read(frame_bytes * 32)
            if not chunk:
                break
            pending += chunk
            while len(pending) >= frame_bytes:
                raw = pending[:frame_bytes]
                pending = pending[frame_bytes:]
                yield np.frombuffer(raw, dtype="<f4").astype(np.float32, copy=False)
        if pending:
            samples = np.frombuffer(pending, dtype="<f4").astype(np.float32, copy=False)
            if samples.size:
                padded = np.zeros(frame_samples, dtype=np.float32)
                padded[: min(frame_samples, samples.size)] = samples
                yield padded
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)


def analyze_audio(path: Path, *, duration: float | None = None) -> dict[str, object]:
    """Decode audio to mono float samples and extract reaction events."""
    chunks = list(_iter_audio_frames(path, SAMPLE_RATE))
    if not chunks:
        return build_audio_features(np.asarray([], dtype=np.float32), duration=duration)
    samples = np.concatenate(chunks).astype(np.float32, copy=False)
    features = build_audio_features(samples, SAMPLE_RATE, duration=duration)
    if duration is not None:
        features["duration"] = round(float(duration), 3)
    logger.info(
        "Analisis de audio: %d eventos, baseline %.1f dB.",
        len(features.get("events") or []),
        float(features.get("baseline_db") or -60.0),
    )
    return features
