import json
from pathlib import Path

import pytest

from app import main, tiktok  # noqa: F401


def test_extract_aweme_id_standard():
    assert (
        tiktok.extract_aweme_id("https://www.tiktok.com/@usuario/video/7301234567890123456")
        == "7301234567890123456"
    )


def test_extract_aweme_id_short():
    assert (
        tiktok.extract_aweme_id("https://vm.tiktok.com/ZMabcdefg/?item_id=7301234567890123456")
        == "7301234567890123456"
    )


def test_extract_aweme_id_invalid():
    import pytest

    with pytest.raises(tiktok.TikTokGrabError):
        tiktok.extract_aweme_id("https://www.youtube.com/watch?v=abc")


def test_grab_out_shape():
    grab = {
        "id": "x",
        "url": "u",
        "status": "queued",
        "stage": "",
        "progress": 0,
        "error": None,
    }
    out = tiktok._grab_out(grab)
    assert out["clean"] is False
    assert out["auto_publish"] is False
    assert out["youtube_url"] is None


def test_split_hashtags():
    clean, tags = tiktok._split_hashtags("Gato gracioso #funny #cats jaja")
    assert clean == "Gato gracioso jaja"
    assert tags == ["#funny", "#cats"]


def test_split_hashtags_only_tags():
    clean, tags = tiktok._split_hashtags("#viral #fyp")
    assert clean == ""
    assert tags == ["#viral", "#fyp"]


def test_save_keeps_previous_json_if_write_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(tiktok, "_grabs_dir", lambda: tmp_path)
    tiktok._save({"id": "sample", "status": "queued"})
    original = (tmp_path / "sample.json").read_bytes()

    original_write = Path.write_text

    def fail_temp_write(path, *args, **kwargs):
        if path.name == "sample.json.tmp":
            raise OSError(28, "No space left on device")
        return original_write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_temp_write)
    with pytest.raises(OSError):
        tiktok._save({"id": "sample", "status": "ready"})
    assert (tmp_path / "sample.json").read_bytes() == original


def test_reset_stale_grabs_preserves_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(tiktok, "_grabs_dir", lambda: tmp_path)
    for status in ("queued", "processing", "publishing", "ready", "failed"):
        tiktok._save({"id": status, "status": status, "url": "https://example.com"})

    assert tiktok.reset_stale_grabs() == 3
    for status in ("queued", "processing", "publishing"):
        grab = json.loads((tmp_path / f"{status}.json").read_text(encoding="utf-8"))
        assert grab["status"] == "failed"
        assert "interrumpio" in grab["error"]
    assert tiktok.load_grab("ready")["status"] == "ready"
    assert tiktok.load_grab("failed")["status"] == "failed"
