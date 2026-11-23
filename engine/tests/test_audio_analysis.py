from __future__ import annotations

import numpy as np

from app.audio_analysis import build_audio_features
from app.signals import summarize_audio

SAMPLE_RATE = 8000


def base_signal(seconds: int = 24, amplitude: float = 0.004) -> np.ndarray:
    rng = np.random.default_rng(17)
    return rng.normal(0, amplitude, seconds * SAMPLE_RATE).astype(np.float32)


def tone(seconds: float, frequency: float, amplitude: float) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def test_empty_audio_is_unavailable() -> None:
    features = build_audio_features(np.asarray([], dtype=np.float32), SAMPLE_RATE)

    assert features["available"] is False
    assert features["events"] == []


def test_sustained_high_tone_is_a_scream_not_laughter() -> None:
    samples = base_signal()
    samples[10 * SAMPLE_RATE : 11 * SAMPLE_RATE] = tone(1.0, 900.0, 0.5)

    features = build_audio_features(samples, SAMPLE_RATE)
    kinds = [event["kind"] for event in features["events"]]

    assert "scream" in kinds
    assert "laughter" not in kinds
    summary = summarize_audio(features, 9.0, 12.0)
    assert summary["scream"] is True
    assert summary["intensity"] > 55.0


def test_repeated_amplitude_bursts_are_laughter() -> None:
    samples = base_signal()
    burst = tone(0.24, 1200.0, 0.12)
    for index in range(5):
        start = int((9.6 + index * 0.42) * SAMPLE_RATE)
        samples[start : start + burst.size] += burst

    features = build_audio_features(samples, SAMPLE_RATE)
    laughs = [event for event in features["events"] if event["kind"] == "laughter"]

    assert laughs
    assert int(laughs[0]["bursts"]) >= 4
    summary = summarize_audio(features, 9.0, 12.5)
    assert summary["laughter"] is True


def test_loud_reaction_then_drop_is_sudden_silence() -> None:
    samples = base_signal(seconds=20, amplitude=0.006)
    samples[6 * SAMPLE_RATE : 9 * SAMPLE_RATE] = tone(3.0, 500.0, 0.25)
    samples[9 * SAMPLE_RATE : 14 * SAMPLE_RATE] *= 0.02

    features = build_audio_features(samples, SAMPLE_RATE)
    silences = [event for event in features["events"] if event["kind"] == "sudden_silence"]

    assert silences
    assert silences[0]["start"] >= 8.5
    assert silences[0]["end"] <= 14.5


def test_loudness_alone_is_not_an_emotional_event() -> None:
    samples = base_signal()
    samples[8 * SAMPLE_RATE : 12 * SAMPLE_RATE] = tone(4.0, 220.0, 0.08)

    features = build_audio_features(samples, SAMPLE_RATE)

    assert all(event["kind"] not in {"scream", "laughter"} for event in features["events"])
