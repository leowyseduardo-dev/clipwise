from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import CameraBox, ClipEditInput


def test_camera_box_accepts_normalised_rect() -> None:
    box = CameraBox(x=0.1, y=0.2, w=0.3, h=0.4)

    assert box.model_dump() == {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}


def test_camera_box_rejects_out_of_frame_values() -> None:
    with pytest.raises(ValidationError):
        CameraBox(x=1.5, y=0.0, w=0.2, h=0.2)
    with pytest.raises(ValidationError):
        CameraBox(x=0.0, y=0.0, w=0.0, h=0.2)
    with pytest.raises(ValidationError):
        CameraBox(x=0.0, y=0.0, w=1.2, h=0.2)


def test_clip_edit_input_defaults_to_automatic_cameras() -> None:
    payload = ClipEditInput()

    assert payload.manual_cams == []


def test_clip_edit_input_serialises_manual_cameras() -> None:
    payload = ClipEditInput(
        layout="cam_juego",
        manual_cams=[CameraBox(x=0.02, y=0.03, w=0.34, h=0.4)],
    )

    dumped = payload.model_dump(exclude={"subtitle_style"})

    assert dumped["manual_cams"] == [{"x": 0.02, "y": 0.03, "w": 0.34, "h": 0.4}]


def test_clip_edit_input_caps_manual_cameras_at_four() -> None:
    with pytest.raises(ValidationError):
        ClipEditInput(
            manual_cams=[CameraBox(x=0.1, y=0.1, w=0.2, h=0.2) for _ in range(5)]
        )
