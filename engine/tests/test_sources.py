from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db, ingest, live, main, pipeline


URLS = [
    ("youtube", "https://youtu.be/dQw4w9WgXcQ"),
    ("twitch", "https://www.twitch.tv/videos/6528877"),
    ("twitch", "https://m.twitch.tv/videos/6528877?t=1h2m"),
    ("twitch", "https://clips.twitch.tv/FaintLightGullWholeWheat"),
    ("twitch", "https://www.twitch.tv/xqc/clip/CulturedAmazingKuduDatSheffy-TiZ_-ixAGYR3y2Uy"),
    ("twitch", "https://player.twitch.tv/?video=v6528877&parent=example.com"),
    ("kick", "https://kick.com/xqc/videos/01a0251f-ef48-702d-9289-d66922da0e84"),
    ("kick", "https://kick.com/mxddy?clip=clip_01GYXVB5Y8PWAPWCWMSBCFB05X"),
    ("kick", "https://kick.com/spreen/clips/clip_01J8RGZRKHXHXXKJEHGRM932A5"),
]


@pytest.mark.parametrize("platform,url", URLS)
def test_metadata_accepts_platform_links(monkeypatch, platform, url):
    calls = []
    monkeypatch.setattr(ingest, "_cookie_option_sets", lambda: [])
    monkeypatch.setattr(ingest, "_extract_info", lambda _, link, opts, **kw:
                        calls.append(link) or {"duration": 42, "title": "Mi clip"})
    assert ingest.validate_source_url(url) == url
    info, auth = ingest.fetch_source_info(url)
    assert info["duration"] == 42 and auth == {} and calls == [url]
    assert live.platform_for(url) == platform


@pytest.mark.parametrize("url", [
    "https://kick.com", "https://kick.com/xqc", "https://twitch.tv/xqc",
    "https://twitch.tv/directory", "https://kick.com/xqc/videos/invalid",
    "https://twitch.tv.evil.example/videos/123", "https://evil.example/kick.com/xqc",
    "https://user:pass@twitch.tv/videos/123", "ftp://twitch.tv/videos/123",
    "https://kick.com:8080/xqc?clip=clip_123", "https://twitch.tv:invalid/videos/123",
])
def test_invalid_or_channel_links_fail_before_download(url):
    with pytest.raises(ingest.IngestError):
        ingest.validate_source_url(url)


def test_live_broadcast_does_not_start_unbounded_download():
    with pytest.raises(ingest.IngestError, match="Directos"):
        ingest._validate_source_info({"is_live": True, "duration": 600})


@pytest.fixture
def source_api(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "settings", SimpleNamespace(db_path=tmp_path / "test.sqlite"))
    db.init_db()
    monkeypatch.setattr(main, "_workdir", lambda job_id: tmp_path / job_id)
    enqueued = []
    monkeypatch.setattr(main.jobs, "enqueue_job", enqueued.append)
    return TestClient(main.app), enqueued, tmp_path


@pytest.mark.parametrize("platform,url", URLS)
def test_create_job_detects_platform_and_preserves_source(source_api, platform, url):
    client, enqueued, _ = source_api
    response = client.post("/api/jobs", data={
        "source_type": "url", "url": url, "rights_accepted": "true",
        "streamer_name": "Ana", "game_name": "Minecraft",
    })
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["source_type"] == platform and job["source_url"] == url
    assert job["streamer"] == "Ana" and job["game"] == "Minecraft"
    # A temporary "Video de Kick/Twitch" label must not override the actual
    # provider title when metadata is merged during processing.
    assert job["meta"]["source_title"] == ""
    assert enqueued == [job["id"]]


def test_rejected_source_does_not_enqueue_job(source_api):
    client, enqueued, _ = source_api
    response = client.post("/api/jobs", data={
        "source_type": "url", "url": "https://kick.com/xqc", "rights_accepted": "true",
    })
    assert response.status_code == 400 and "Directos" in response.json()["detail"]
    assert enqueued == [] and db.list_jobs() == []


@pytest.mark.parametrize("platform,url", [URLS[1], URLS[6]])
def test_platform_jobs_enter_remote_pipeline(source_api, monkeypatch, platform, url):
    client, _, folder = source_api
    response = client.post("/api/jobs", data={
        "source_type": platform, "url": url, "rights_accepted": "true",
    })
    job_id = response.json()["id"]
    monkeypatch.setattr(pipeline, "settings", SimpleNamespace(jobs_dir=folder, default_subtitle_style="bold"))
    calls = []
    def stop_after_metadata(link):
        calls.append(link)
        raise ingest.IngestError("metadata sentinel")
    monkeypatch.setattr(pipeline, "fetch_source_info", stop_after_metadata)
    pipeline.process_job(job_id)
    assert calls == [url]
    assert db.get_job(job_id)["error"] == "metadata sentinel"


@pytest.mark.parametrize("platform,url", [URLS[1], URLS[6]])
def test_long_source_sections_preserve_requested_window(monkeypatch, tmp_path, platform, url):
    captured = {}
    destination = tmp_path / "section.mp4"
    def download(_, link, opts, **kwargs):
        captured["url"] = link
        captured["ranges"] = opts["download_ranges"]({}, None)
        destination.write_bytes(b"media")
    monkeypatch.setattr(ingest, "_run_download", download)
    monkeypatch.setattr(ingest, "probe_media", lambda _: {"duration": 30})
    result = ingest.download_source_section(url, tmp_path, {"duration": 5000}, {}, 120, 150, destination)
    assert result == destination and captured["url"] == url
    assert captured["ranges"] == [{"start_time": 120, "end_time": 150}]
