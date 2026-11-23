from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import live


@pytest.fixture()
def live_env(tmp_path, monkeypatch):
    monkeypatch.setattr(live.settings, "data_dir", tmp_path)
    live._sessions.clear()
    live._threads.clear()
    live._stop_events.clear()
    live._procs.clear()
    yield tmp_path
    live._sessions.clear()
    live._threads.clear()
    live._stop_events.clear()
    live._procs.clear()


def test_platform_for_known_hosts():
    assert live.platform_for("https://kick.com/ibai") == "kick"
    assert live.platform_for("https://www.twitch.tv/xqc") == "twitch"
    assert live.platform_for("https://youtube.com/watch?v=abc123") == "youtube"
    assert live.platform_for("https://youtu.be/abc123") == "youtube"


def test_platform_for_rejects_other_sites():
    with pytest.raises(live.LiveError):
        live.platform_for("https://www.tiktok.com/@user/live")


def test_select_segments_leaves_the_newest_two():
    segments = [Path(f"seg_{index:06d}.ts") for index in range(12)]
    selected = live._select_segments(segments, 30)
    needed = int(30 / live.SEGMENT_SECONDS) + 2
    assert len(selected) == needed
    assert selected[-1].name == "seg_000009.ts"
    assert all(path.name not in {"seg_000010.ts", "seg_000011.ts"} for path in selected)


def test_select_segments_needs_a_usable_buffer():
    assert live._select_segments([Path("seg_000000.ts")], 30) == []
    assert live._select_segments([], 15) == []


def test_pick_streams_prefers_muxed_playlist():
    info = {
        "formats": [
            {"url": "mux-720", "height": 720, "vcodec": "avc1", "acodec": "mp4a"},
            {"url": "mux-1080", "height": 1080, "vcodec": "avc1", "acodec": "mp4a"},
            {"url": "video-only", "height": 1440, "vcodec": "vp9", "acodec": "none"},
        ]
    }
    assert live._pick_streams(info) == ("mux-1080", None)


def test_pick_streams_splits_video_and_audio_for_youtube_live():
    info = {
        "formats": [
            {"url": "v144", "height": 144, "vcodec": "avc1", "acodec": "none"},
            {"url": "v1080", "height": 1080, "vcodec": "avc1", "acodec": "none"},
            {"url": "a-low", "vcodec": "none", "acodec": None, "abr": 128},
            {"url": "a-high", "vcodec": "none", "acodec": None, "abr": 256},
        ]
    }
    assert live._pick_streams(info) == ("v1080", "a-high")


def test_pick_streams_requires_a_url():
    with pytest.raises(live.LiveError):
        live._pick_streams({"formats": [{"format_id": "x"}]})


def test_prune_keeps_only_the_configured_minutes(live_env):
    buffer_dir = live._buffer_dir("session-1")
    for index in range(100):
        (buffer_dir / f"seg_{index:06d}.ts").write_bytes(b"x")
    live._prune("session-1")
    kept = sorted(buffer_dir.glob("seg_*.ts"))
    maximum = int(live.BUFFER_MINUTES * 60 / live.SEGMENT_SECONDS) + live.SAFE_TAIL_SEGMENTS
    assert len(kept) == maximum
    assert kept[-1].name == "seg_000099.ts"
    assert kept[0].name == f"seg_{100 - maximum:06d}.ts"


def test_recover_stale_sessions_marks_interrupted_recordings(live_env):
    session_dir = live_env / "live" / "leftover"
    session_dir.mkdir(parents=True)
    payload = {
        "id": "leftover",
        "url": "https://www.twitch.tv/xqc",
        "platform": "twitch",
        "status": "recording",
        "error": None,
    }
    (session_dir / "session.json").write_text(json.dumps(payload), encoding="utf-8")
    live.recover_stale_sessions()
    saved = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    assert saved["status"] == "stopped"
    assert "reinicio" in saved["error"].lower()


def test_make_clip_uses_buffer_tail_and_writes_metadata(live_env, monkeypatch):
    session = {
        "id": "clip-session",
        "url": "https://kick.com/ibai",
        "platform": "kick",
        "title": "Directo de prueba",
        "author": "ibai",
        "status": "recording",
        "error": None,
        "started_at": "2026-11-18T20:00:00",
    }
    live._sessions["clip-session"] = session
    live._save(session)
    buffer_dir = live._buffer_dir("clip-session")
    for index in range(12):
        (buffer_dir / f"seg_{index:06d}.ts").write_bytes(b"segment")

    calls = []
    concat_list = {}

    def fake_run_ffmpeg(args, *, timeout=None):
        calls.append(list(args))
        if "-f" in args and "concat" in args:
            list_path = Path(args[args.index("-i") + 1])
            concat_list["text"] = list_path.read_text(encoding="utf-8")
        else:
            Path(args[-1]).write_bytes(b"fake-mp4")

    monkeypatch.setattr(live, "run_ffmpeg", fake_run_ffmpeg)
    clip = live.make_clip("clip-session", 30)

    assert clip["seconds"] == 30
    assert clip["title"].startswith("Directo de prueba")
    assert clip["author"] == "ibai"
    assert callable(live.run_ffmpeg)
    assert len(calls) == 2

    selected_names = [
        Path(line.split("'")[1]).name for line in concat_list["text"].splitlines()
    ]
    assert len(selected_names) == int(30 / live.SEGMENT_SECONDS) + 2
    assert selected_names[-1] == "seg_000009.ts"

    clip_path = live._clips_dir("clip-session") / f"{clip['id']}.mp4"
    assert clip_path.is_file()
    meta_path = live._clips_dir("clip-session") / f"{clip['id']}.json"
    assert json.loads(meta_path.read_text(encoding="utf-8"))["id"] == clip["id"]
    assert live.load_clip(clip["id"])["session_id"] == "clip-session"

    listed = live.list_sessions()
    assert len(listed) == 1
    assert listed[0]["clips"][0]["id"] == clip["id"]


def test_make_clip_refuses_without_a_buffer(live_env):
    session = {
        "id": "empty-session",
        "url": "https://www.youtube.com/watch?v=abc",
        "platform": "youtube",
        "status": "recording",
    }
    live._sessions["empty-session"] = session
    live._save(session)
    with pytest.raises(live.LiveError):
        live.make_clip("empty-session", 30)


def test_make_clip_refuses_a_stopped_session(live_env):
    session = {
        "id": "stopped-session",
        "url": "https://www.twitch.tv/xqc",
        "platform": "twitch",
        "status": "stopped",
    }
    live._sessions["stopped-session"] = session
    live._save(session)
    with pytest.raises(live.LiveError):
        live.make_clip("stopped-session", 15)
