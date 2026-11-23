from __future__ import annotations

from app.signals import summarize_visual
from app.visual_analysis import build_visual_features


def flat_samples(seconds: int = 24, step: float = 0.5) -> list[dict[str, float]]:
    count = int(seconds / step)
    return [
        {
            "t": round(index * step, 3),
            "motion": 0.004,
            "center_motion": 0.003,
            "face_motion": 0.002,
            "mouth_motion": 0.002,
            "face_present": 1.0,
            "hist_diff": 0.01,
        }
        for index in range(count)
    ]


def test_empty_visual_timeline_is_unavailable() -> None:
    features = build_visual_features([])

    assert features["available"] is False
    assert features["events"] == []
    assert features["face_present_ratio"] == 0.0


def test_sampled_scene_boundaries_require_full_coverage_and_joint_evidence():
    samples = flat_samples()
    samples[8].update(hist_diff=0.8, motion=0.15)
    samples[9].update(hist_diff=0.5, motion=0.13)
    samples[18].update(motion=0.8)
    result = build_visual_features(samples, duration=24)
    assert result["scenes"] == [{"start": 0, "end": 4}, {"start": 4, "end": 24}]
    assert build_visual_features(samples[:10], duration=24)["scenes"] is None
    assert build_visual_features(flat_samples(), duration=24)["scenes"] == []


def test_face_reaction_and_motion_create_visual_events() -> None:
    samples = flat_samples()
    for index, sample in enumerate(samples):
        if 10.0 <= sample["t"] <= 12.5:
            sample["motion"] = 0.06
            sample["center_motion"] = 0.07
            sample["face_motion"] = 0.08
            sample["mouth_motion"] = 0.10
            sample["hist_diff"] = 0.03

    features = build_visual_features(samples)
    kinds = {event["kind"] for event in features["events"]}

    assert features["available"] is True
    assert features["face_present_ratio"] == 1.0
    assert "face_reaction" in kinds
    assert "visual_reaction" in kinds
    assert "motion_burst" in kinds
    summary = summarize_visual(features, 9.5, 13.0)
    assert summary["reaction"] is True
    assert summary["intensity"] > 50.0


def test_scene_changes_are_tracked_but_are_not_reactions() -> None:
    samples = flat_samples(seconds=12)
    for sample in samples:
        if 4.0 <= sample["t"] <= 4.5:
            sample["hist_diff"] = 0.45

    features = build_visual_features(samples)
    summary = summarize_visual(features, 3.5, 5.0)

    assert summary["scene_cuts"] >= 1.0
    assert summary["reaction"] is False


def test_talking_head_motion_is_not_a_facial_reaction() -> None:
    samples = flat_samples(seconds=12)
    for sample in samples:
        sample["head_motion"] = 0.0008
        sample["face_crop_motion"] = 0.03
        sample["face_motion"] = 0.03
        sample["mouth_motion"] = 0.035
    for sample in samples:
        if 5.0 <= sample["t"] <= 7.0:
            sample["head_motion"] = 0.001
            sample["face_crop_motion"] = 0.032
            sample["face_motion"] = 0.032
            sample["mouth_motion"] = 0.036

    features = build_visual_features(samples)
    kinds = {event["kind"] for event in features["events"]}
    summary = summarize_visual(features, 4.5, 7.5)

    assert "face_reaction" not in kinds
    assert "face_expression" not in kinds
    assert "visual_reaction" not in kinds
    assert summary["reaction"] is False


def test_head_turn_is_a_face_reaction() -> None:
    samples = flat_samples(seconds=12)
    for sample in samples:
        sample["head_motion"] = 0.0005
        sample["face_crop_motion"] = 0.006
        sample["face_motion"] = 0.006
        sample["mouth_motion"] = 0.004
    for sample in samples:
        if 5.0 <= sample["t"] <= 6.5:
            sample["head_motion"] = 0.04
            sample["face_motion"] = 0.04

    features = build_visual_features(samples)
    summary = summarize_visual(features, 4.5, 7.0)

    assert any(event["kind"] == "face_reaction" for event in features["events"])
    assert summary["reaction"] is True

