from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from app.audio_analysis import build_audio_features
from app.moments import _event_candidates, _finalize, _select, generate_moments
from app.visual_analysis import build_visual_features

SAMPLE_RATE = 8000


def multimodal_features(seconds: int = 60) -> tuple[dict, dict]:
    rng = np.random.default_rng(7)
    samples = rng.normal(0, 0.004, seconds * SAMPLE_RATE).astype(np.float32)
    t = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    samples[25 * SAMPLE_RATE : 26 * SAMPLE_RATE] = (
        0.5 * np.sin(2 * np.pi * 900 * t)
    ).astype(np.float32)
    audio = build_audio_features(samples, SAMPLE_RATE)

    visual_samples = []
    for index in range(seconds * 2):
        timestamp = index / 2.0
        active = 25.0 <= timestamp <= 28.0
        visual_samples.append(
            {
                "t": timestamp,
                "motion": 0.08 if active else 0.005,
                "center_motion": 0.10 if active else 0.004,
                "face_motion": 0.09 if active else 0.002,
                "mouth_motion": 0.12 if active else 0.001,
                "face_present": 1.0,
                "hist_diff": 0.20 if timestamp in {25.0, 26.0} else 0.01,
            }
        )
    visual = build_visual_features(visual_samples)
    return audio, visual


def candidate(
    start: float,
    end: float,
    score: int,
    *,
    category: str = "funny",
    text: str = "",
) -> dict:
    return {
        "start": start,
        "end": end,
        "duration": end - start,
        "score": score,
        "category": category,
        "text": text,
        "event_kinds": [],
    }


def test_event_can_become_a_no_speech_clip() -> None:
    audio, visual = multimodal_features()

    clips = generate_moments(
        [],
        [],
        duration=60.0,
        options=SimpleNamespace(subtitle_style="bold"),
        requested=1,
        language="es",
        meta={},
        audio_features=audio,
        visual_features=visual,
    )

    assert len(clips) == 1
    clip = clips[0]
    assert clip["category"] == "crazy_reactions"
    assert clip["score"] >= 55
    assert clip["subtitles"]["cues"] == []
    assert clip["title"] != "Momento destacado"
    assert clip["title"] == "La reacción lo dice todo"
    assert clip["start"] <= 24.5
    assert clip["end"] >= 29.0
    assert 15.0 <= clip["duration"] <= 60.0
    assert set(clip["score_breakdown"]) >= {
        "intensity",
        "surprise",
        "humor",
        "originality",
        "importance",
        "conversation",
        "entertainment",
        "context",
        "category_confidence",
    }


def test_select_suppresses_overlapping_candidates() -> None:
    first = candidate(10.0, 35.0, 90)
    overlapping = candidate(12.0, 37.0, 80)
    separate = candidate(80.0, 105.0, 70, category="angry")

    chosen = _select([first, overlapping, separate], 3)

    assert [item["start"] for item in chosen] == [10.0, 80.0]


def test_select_suppresses_near_duplicate_transcripts() -> None:
    text = "no puede ser lo que acaba de pasar en esta partida ahora mismo"
    first = candidate(10.0, 30.0, 90, text=text)
    duplicate = candidate(70.0, 90.0, 85, text=text)

    chosen = _select([first, duplicate], 2)

    assert chosen == [first]


def test_select_keeps_distinct_categories_in_the_same_window() -> None:
    first = candidate(10.0, 30.0, 90, category="funny")
    second = candidate(70.0, 90.0, 85, category="angry")

    chosen = _select([first, second], 2)

    assert {item["category"] for item in chosen} == {"funny", "angry"}


def test_silence_alone_does_not_become_an_event_clip() -> None:
    audio = {
        "events": [
            {
                "kind": "sudden_silence",
                "source": "audio",
                "start": 10.0,
                "end": 12.5,
                "score": 48.0,
                "confidence": 0.5,
            }
        ]
    }

    candidates = _event_candidates(
        audio,
        None,
        [],
        [],
        total_duration=30.0,
    )

    assert candidates == []


def test_event_window_is_preserved_after_finalization() -> None:
    audio, visual = multimodal_features()
    event = candidate(24.0, 29.0, 62, category="crazy_reactions")
    event["source"] = "event"
    event["event_kinds"] = ["face_reaction", "scream"]
    event["score_breakdown"] = {
        "hook": 60,
        "clarity": 36,
        "interest": 20,
        "pacing": 40,
        "retention": 60,
        "intensity": 70,
        "surprise": 50,
        "humor": 10,
        "originality": 50,
        "importance": 60,
        "conversation": 18,
        "entertainment": 60,
        "context": 60,
        "category_confidence": 70,
        "total": 62,
    }

    clips = _finalize(
        [event],
        scenes=[],
        segments=[],
        style="clean",
        total_duration=60.0,
        language="es",
        meta={},
        audio_features=audio,
        visual_features=visual,
    )

    assert len(clips) == 1
    clip = clips[0]
    assert clip["start"] <= 24.0
    assert clip["end"] >= 29.0

def test_nonverbal_reaction_is_in_the_first_second_of_the_export():
    event = {"kind": "face_reaction", "start": 28.0, "end": 30.0, "score": 92.0}
    visual = {"events": [event]}
    clips = generate_moments([], [], duration=75.0, options=SimpleNamespace(),
                             requested=None, language="es", visual_features=visual)
    assert len(clips) == 1
    assert 0 <= event["start"] - clips[0]["start"] < 1.0
    assert clips[0]["end"] >= event["end"]


def test_chatter_and_scene_cuts_do_not_join_two_reactions():
    from app.moments import build_sentences

    words = [
        {"w": token, "start": t, "end": t + 0.3}
        for token, t in [("Hola", 15.0), ("chat.", 15.5), ("Probando", 20.0),
                         ("audio.", 20.4), ("¿Quién?", 49.0), ("¡Yo!", 52.0)]
    ]
    segments = [{"words": words}]
    events = [
        {"kind": "face_reaction", "start": t, "end": t + 1, "score": 90}
        for t in [25.0, 51.0]
    ]
    events += [
        {"kind": "scene_cut", "start": t, "end": t + 0.5, "score": 65}
        for t in range(26, 52, 3)
    ]
    visual = {"events": events}
    candidates = _event_candidates(None, visual, build_sentences(segments), segments, total_duration=90)
    clips = _finalize(candidates, scenes=[], segments=segments, style="bold",
                      total_duration=90, visual_features=visual)
    assert len(clips) == 2
    assert 0 <= 25 - clips[0]["start"] < 1
    assert 0 <= 49 - clips[1]["start"] < 1
    assert clips[1]["end"] >= 52.3
