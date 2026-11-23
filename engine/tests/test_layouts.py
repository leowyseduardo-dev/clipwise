from __future__ import annotations

import pytest

from app import layouts


def _cams(count: int, size: tuple[int, int] = (1920, 1080)):
    width, height = size
    step = width / (count + 1)
    box_w = min(360.0, width * 0.24)
    box_h = min(320.0, height * 0.42)
    return [
        (step * (index + 1) - box_w / 2, height * 0.18, box_w, box_h)
        for index in range(count)
    ]


def test_choose_template_single_camera() -> None:
    assert layouts.choose_template(1, has_content=False) == "vertical"
    assert layouts.choose_template(1, has_content=True, small_cams=True) == "cam_juego"
    assert layouts.choose_template(1, has_content=True, small_cams=False) == "spotlight"


def test_choose_template_multi_camera() -> None:
    assert layouts.choose_template(2, has_content=False) == "dividido"
    assert layouts.choose_template(2, has_content=True) == "dos_cams_juego"
    assert layouts.choose_template(3, has_content=False) == "trio"
    assert layouts.choose_template(3, has_content=True) == "tres_cams_juego"
    assert layouts.choose_template(4, has_content=False) == "cuarteto"
    assert layouts.choose_template(5, has_content=True) == "horizontal"
    assert layouts.choose_template(0) == "vertical"


def test_normalize_template_accepts_split_alias() -> None:
    assert layouts.normalize_template("split") == "cam_juego"
    assert layouts.normalize_template("cam_juego") == "cam_juego"
    assert layouts.normalize_template("nonsense") == "auto"
    assert layouts.normalize_template(None) == "auto"


@pytest.mark.parametrize("name", [key for key in layouts.TEMPLATES if key != "vertical"])
def test_plan_slots_cover_canvas_without_overlap(name: str) -> None:
    count = 3 if name in {"trio", "tres_cams_juego", "trio_juego"} else 2
    plan = layouts.build_plan(name, _cams(count))
    assert plan.slots, name
    for slot in plan.slots:
        x, y, w, h = slot.rect
        assert 0 <= x < layouts.CANVAS_W, (name, slot)
        assert 0 <= y < layouts.CANVAS_H, (name, slot)
        assert x + w <= layouts.CANVAS_W, (name, slot)
        assert y + h <= layouts.CANVAS_H, (name, slot)
        assert w > 0 and h > 0, (name, slot)


def test_cam_slots_attach_boxes_in_order() -> None:
    plan = layouts.build_plan("dos_cams_juego", _cams(2))
    cams = [slot for slot in plan.slots if slot.kind == "cam"]
    assert len(cams) == 2
    assert cams[0].box is not None and cams[1].box is not None
    assert cams[0].box[0] < cams[1].box[0]
    assert plan.slots[-1].kind == "game"


def test_missing_panels_degrade_to_scene() -> None:
    plan = layouts.build_plan("cuarteto", _cams(1))
    kinds = [slot.kind for slot in plan.slots]
    assert kinds.count("cam") == 1
    assert kinds.count("game") == 3


def test_caption_anchor_for_cam_layouts() -> None:
    assert layouts.build_plan("cam_juego", _cams(1)).caption_anchor is not None
    assert layouts.build_plan("dos_cams_juego", _cams(2)).caption_anchor is not None
    assert layouts.build_plan("tres_cams_juego", _cams(3)).caption_anchor is not None
    anchor = layouts.build_plan("trio_juego", _cams(3)).caption_anchor
    assert anchor is not None and anchor < layouts.CANVAS_H - 300
    assert layouts.build_plan("vertical", []).caption_anchor is None
    assert layouts.build_plan("cuarteto", _cams(4)).caption_anchor is None
