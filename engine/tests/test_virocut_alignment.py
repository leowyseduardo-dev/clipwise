from app import pipeline


def test_virocut_overlay_keeps_resolved_render_in_the_editor():
    clip = {
        "hook": "Mira esto",
        "style": "shorts",
        "overlay": {"render_options": {"layout": "auto"}},
    }
    result = {"template": "cam_juego", "layout": "auto"}
    overlay = pipeline._virocut_overlay(
        clip, {"layout": "auto", "brand_text": ""}, result
    )
    saved = overlay["virocut"]
    assert saved["template"] == "cam_juego"
    assert saved["caption_style"] == "default"
    assert saved["hook"] == "Mira esto"
    assert saved["watermark"] == ""
    assert overlay["render_options"]["template"] == "cam_juego"
    assert overlay["render_options"]["captions_enabled"] is True


def test_virocut_overlay_maps_unsupported_template():
    clip = {"hook": "", "style": "neon", "overlay": {}}
    overlay = pipeline._virocut_overlay(
        clip, {"layout": "auto"}, {"template": "trio_juego"}
    )
    assert overlay["virocut"]["template"] == "trio"
    assert overlay["virocut"]["caption_style"] == "neon"
