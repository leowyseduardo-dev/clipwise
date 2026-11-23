from __future__ import annotations

import numpy as np
import pytest

from app.config import settings
from app.render import (
    _build_audio_graph,
    _Camera,
    _choose_face,
    _clamp_center,
    _crop_fit_pad,
    _estimate_facecam_panel,
    _facecam_background,
    _gameplay_anchor,
    _inside,
    _manual_camera_panels,
    _needs_render_proxy,
    _plan_crop,
    _plan_crop_aspect,
    _select_facecam_boxes,
    cleanup_old_outputs,
    compress_silences,
    map_time,
)


def test_compress_silences_trims_edges_and_merges_close_ranges() -> None:
    removed = compress_silences([(1.0, 3.0), (2.5, 4.0)], 60.0)

    assert len(removed) == 1
    assert removed[0][0] == pytest.approx(1.22)
    assert removed[0][1] == pytest.approx(3.78)


def test_compress_silences_trims_single_range() -> None:
    removed = compress_silences([(10.0, 15.0)], 30.0)

    assert len(removed) == 1
    assert removed[0][0] == pytest.approx(10.22)
    assert removed[0][1] == pytest.approx(14.78)


def test_compress_silences_ignores_short_and_long_ranges() -> None:
    assert compress_silences([(1.0, 1.5)], 30.0) == []
    assert compress_silences([(0.0, 29.0)], 60.0) == []


def test_compress_silences_discards_too_many_cuts() -> None:
    raw = [(index * 4.0, index * 4.0 + 1.5) for index in range(61)]
    assert compress_silences(raw, 400.0) == []


def test_map_time_shifts_around_removed_intervals() -> None:
    removed = [(2.0, 4.0), (10.0, 12.0)]

    assert map_time(1.0, removed) == pytest.approx(1.0)
    assert map_time(3.0, removed) == pytest.approx(2.0)
    assert map_time(5.0, removed) == pytest.approx(3.0)
    assert map_time(10.0, removed) == pytest.approx(8.0)
    assert map_time(11.0, removed) == pytest.approx(8.0)
    assert map_time(13.0, removed) == pytest.approx(9.0)
    assert map_time(-5.0, removed) == 0.0
    assert map_time(5.0, []) == pytest.approx(5.0)


def test_inside_uses_half_open_intervals() -> None:
    removed = [(2.0, 4.0)]

    assert _inside(2.0, removed) is True
    assert _inside(3.9, removed) is True
    assert _inside(4.0, removed) is False
    assert _inside(1.9, removed) is False


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (1920, 1080),
        (1080, 1920),
        (1000, 1000),
        (4000, 1000),
        (1080, 3000),
    ],
)
def test_plan_crop_produces_vertical_frame_inside_source(width: int, height: int) -> None:
    crop_w, crop_h = _plan_crop(width, height)

    assert 0 < crop_w <= width
    assert 0 < crop_h <= height
    assert crop_w % 2 == 0
    assert crop_h % 2 == 0
    assert abs(crop_w / crop_h - settings.target_w / settings.target_h) < 0.01


def test_plan_crop_full_vertical_source_is_unchanged() -> None:
    assert _plan_crop(1080, 1920) == (1080, 1920)


def test_plan_crop_aspect_uses_the_split_game_area() -> None:
    width, height = 1920, 1080
    game_height = settings.target_h - settings.split_face_band
    crop_w, crop_h = _plan_crop_aspect(
        width,
        height,
        settings.target_w / game_height,
    )

    assert 0 < crop_w <= width
    assert 0 < crop_h <= height
    assert abs(crop_w / crop_h - settings.target_w / game_height) < 0.01


def test_estimate_facecam_panel_finds_a_stable_square_region() -> None:
    boxes = [(275.0, 616.0, 270.0, 377.0, 0.9) for _ in range(10)]

    panel = _estimate_facecam_panel(boxes, 1920, 1080)

    assert panel is not None
    x, y, panel_w, panel_h = panel
    assert 0 <= x <= 1920 - panel_w
    assert 0 <= y <= 1080 - panel_h
    assert panel_w == panel_h
    assert panel_w >= 270 * 2
    assert x <= 275 <= x + panel_w
    assert y <= 616 <= y + panel_h


def test_estimate_facecam_panel_rejects_scattered_faces() -> None:
    boxes = [
        (100.0 + index * 170.0, 100.0 + index * 70.0, 150.0, 150.0, 0.9)
        for index in range(10)
    ]

    assert _estimate_facecam_panel(boxes, 1920, 1080) is None


def test_estimate_facecam_panel_requires_enough_samples() -> None:
    assert _estimate_facecam_panel([(1500.0, 300.0, 160.0, 160.0, 0.9)], 1920, 1080) is None


def test_crop_fit_pad_keeps_a_square_facecam_inside_the_band() -> None:
    frame = np.zeros((1080, 1920, 3), dtype="uint8")
    panel = (0.0, 279.0, 702.0, 702.0)

    result = _crop_fit_pad(frame, panel, (1080, 640))

    assert result.shape == (640, 1080, 3)


def test_crop_fit_pad_can_reuse_a_static_background() -> None:
    frame = np.zeros((1080, 1920, 3), dtype="uint8")
    panel = (0.0, 279.0, 702.0, 702.0)
    background = _facecam_background(frame, panel, (1080, 640))
    original = background.copy()

    result = _crop_fit_pad(frame, panel, (1080, 640), background=background)

    assert result.shape == (640, 1080, 3)
    assert np.array_equal(background, original)


def test_select_facecam_boxes_prefers_the_stable_corner_face() -> None:
    boxes: list[tuple[float, float, float, float, float, int]] = []
    for sample in range(10):
        boxes.append((280.0, 700.0, 240.0, 320.0, 0.9, sample))
        if sample < 5:
            boxes.append((1100.0, 420.0, 300.0, 380.0, 0.9, sample))

    selected = _select_facecam_boxes(boxes, 1920, 1080, 10)

    assert len(selected) == 10
    assert max(box[0] for box in selected) < 500


def test_render_proxy_only_for_slow_or_oversized_sources() -> None:
    assert _needs_render_proxy(
        {"video_codec": "h264", "width": 1920, "height": 1080, "fps": 60}
    ) is False
    assert _needs_render_proxy(
        {"video_codec": "av1", "width": 1920, "height": 1080, "fps": 30}
    ) is False
    assert _needs_render_proxy(
        {"video_codec": "h264", "width": 3840, "height": 2160, "fps": 30}
    ) is True
    assert _needs_render_proxy(
        {"video_codec": "hevc", "width": 1920, "height": 1080, "fps": 30}
    ) is True


def test_gameplay_anchor_moves_away_from_a_left_facecam() -> None:
    panel = (0.0, 279.0, 702.0, 702.0)

    anchor_x, anchor_y = _gameplay_anchor(1920, 1080, 911, panel)

    assert anchor_x > 1920 * 0.6
    assert anchor_y == 1080 / 2


def test_gameplay_anchor_stays_centered_for_a_centered_panel() -> None:
    panel = (609.0, 100.0, 702.0, 702.0)

    anchor_x, anchor_y = _gameplay_anchor(1920, 1080, 911, panel)

    assert anchor_x == 960
    assert anchor_y == 540


def test_cleanup_old_outputs_keeps_current_version(tmp_path) -> None:
    current_video = tmp_path / "video-new.mp4"
    current_thumb = tmp_path / "thumb-new.jpg"
    current_video.write_bytes(b"new-video")
    current_thumb.write_bytes(b"new-thumb")
    (tmp_path / "video.mp4").write_bytes(b"legacy")
    (tmp_path / "video-old.mp4").write_bytes(b"old")
    (tmp_path / "thumb_tmp.jpg").write_bytes(b"tmp")
    (tmp_path / "thumb-old.jpg").write_bytes(b"old")
    (tmp_path / "audio.wav").write_bytes(b"audio")
    (tmp_path / "subs.srt").write_text("1\n", encoding="utf-8")

    cleanup_old_outputs(tmp_path, keep={current_video, current_thumb})

    assert current_video.exists()
    assert current_thumb.exists()
    assert (tmp_path / "audio.wav").exists()
    assert (tmp_path / "subs.srt").exists()
    assert not (tmp_path / "video.mp4").exists()
    assert not (tmp_path / "video-old.mp4").exists()
    assert not (tmp_path / "thumb_tmp.jpg").exists()
    assert not (tmp_path / "thumb-old.jpg").exists()


def test_audio_graph_voice_only() -> None:
    graph = _build_audio_graph([], 10.0, has_music=False)

    assert graph.startswith("[1:a]highpass=f=75")
    assert graph.endswith("apad[a]")
    assert "amix" not in graph
    assert "dynaudnorm=f=250:g=6:p=0.90" in graph
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in graph
    assert "aresample=48000" in graph
    assert "alimiter=limit=0.97" in graph


def test_audio_graph_with_removed_silences_and_music() -> None:
    graph = _build_audio_graph([(2.0, 4.0)], 10.0, has_music=True)

    assert "aselect='not(between(t,2.000,4.000))'" in graph
    assert "asetpts=N/SR/TB" in graph
    assert "[2:a]" in graph
    assert "amix=inputs=2" in graph
    assert "normalize=0" in graph
    assert f"volume={settings.music_volume:.3f}" in graph
    assert "atrim=0:10.000" in graph
    assert "afade=t=out" in graph
    assert graph.endswith("alimiter=limit=0.97,apad[a]")


def test_clamp_center_keeps_crop_inside_frame() -> None:
    assert _clamp_center(0.0, 0.0, 600, 1000, 1920, 1080) == (300.0, 500.0)
    assert _clamp_center(1900.0, 900.0, 600, 1000, 1920, 1080) == (1620.0, 580.0)


def test_choose_face_prefers_the_tracked_face() -> None:
    candidates = [
        (400.0, 400.0, 100.0, 100.0, 0.9),
        (1000.0, 500.0, 300.0, 300.0, 0.9),
    ]

    chosen = _choose_face(candidates, 1920, 1080, previous=(405.0, 405.0))

    assert chosen is not None
    assert chosen[0] < 500


def test_camera_follows_face_smoothly_and_pushes_in() -> None:
    camera = _Camera(
        width=1920,
        height=1080,
        base_crop_w=608,
        base_crop_h=1080,
        duration=10.0,
        dynamic_zoom=True,
    )

    start_x, start_y, start_w, start_h = camera.sample(0.0, (400.0, 300.0), 1 / 30)
    next_x, next_y, _, _ = camera.sample(0.1, (440.0, 300.0), 1 / 30)
    _, _, end_w, end_h = camera.sample(10.0, (400.0, 300.0), 1 / 30)

    # Face target is blended with the frame center so reacted-to content
    # stays inside the vertical crop: 0.70 * 400 + 0.30 * 960 = 568.
    assert start_x == pytest.approx(568.0)
    assert start_y == pytest.approx(540.0)
    assert start_x < next_x < 596.0
    assert next_y == pytest.approx(540.0)
    assert end_w < start_w
    assert end_h < start_h


def test_camera_blend_keeps_face_and_center_content_in_frame() -> None:
    camera = _Camera(
        width=1920,
        height=1080,
        base_crop_w=608,
        base_crop_h=1080,
        duration=10.0,
        dynamic_zoom=False,
    )

    center_x, _, _, _ = camera.sample(0.0, (200.0, 400.0), 1 / 30)

    # An edge-locked face no longer drags the crop to the edge; the center
    # sits strictly between the face and the frame center.
    assert 200.0 < center_x < 960.0
    assert center_x == pytest.approx(0.70 * 200.0 + 0.30 * 960.0)

def test_manual_camera_panels_scales_and_sorts_boxes() -> None:
    panels = _manual_camera_panels(
        [
            {"x": 0.6, "y": 0.05, "w": 0.3, "h": 0.3},
            {"x": 0.05, "y": 0.05, "w": 0.3, "h": 0.3},
            {"x": 0.05, "y": 0.65, "w": 0.9, "h": 0.3},
        ],
        1920,
        1080,
    )

    assert len(panels) == 3
    assert panels[0][0] == pytest.approx(96.0)
    assert panels[1][0] == pytest.approx(1152.0)
    assert panels[2][1] == pytest.approx(702.0)
    assert panels[1][2] == pytest.approx(576.0)


def test_manual_camera_panels_clamps_bad_rects() -> None:
    panels = _manual_camera_panels(
        [
            {"x": 0.95, "y": 0.95, "w": 0.5, "h": 0.5},
            {"x": -1, "y": -1, "w": 0, "h": 0},
            {"x": "bad", "y": 0, "w": 0.2, "h": 0.2},
            {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
            {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.2},
        ],
        1000,
        1000,
    )

    # Four boxes max, invalid entries skipped, everything inside the frame.
    assert len(panels) == 4
    for x, y, w, h in panels:
        assert 0 <= x < 1000
        assert 0 <= y < 1000
        assert w > 0 and h > 0
        assert x + w <= 1000.001
        assert y + h <= 1000.001
