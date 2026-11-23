from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db, main, publishing
from app.publishing import PublishingError, PublishingSettings


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def publish_env(tmp_path, monkeypatch):
    monkeypatch.setattr(publishing.settings, "data_dir", tmp_path)
    for name in (
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "TIKTOK_CLIENT_KEY",
        "TIKTOK_CLIENT_SECRET",
        "PUBLISHING_REDIRECT_HOST",
        "PUBLISHING_REDIRECT_PORT",
        "YOUTUBE_PRIVACY",
        "TIKTOK_PRIVACY",
    ):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.fixture
def publishing_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "publishing.db")
    db.init_db()
    return tmp_path


def _settings_with_credentials(**overrides) -> PublishingSettings:
    values = {
        "youtube_client_id": "yt-client",
        "youtube_client_secret": "yt-secret",
        "tiktok_client_key": "tt-key",
        "tiktok_client_secret": "tt-secret",
        "redirect_port": 53682,
    }
    values.update(overrides)
    return PublishingSettings(**values)


def test_settings_mask_secrets_and_preserve_blank_updates(publish_env) -> None:
    publishing.save_publishing_settings(
        {
            "youtube_client_id": "yt-client",
            "youtube_client_secret": "yt-secret",
            "tiktok_client_key": "tt-key",
            "tiktok_client_secret": "tt-secret",
            "redirect_port": 54000,
            "youtube_privacy": "unlisted",
            "tiktok_privacy": "PUBLIC_TO_EVERYONE",
        }
    )

    public = publishing.public_settings()
    assert public["youtube_client_id"] == "yt-client"
    assert public["youtube_client_secret_set"] is True
    assert "youtube_client_secret" not in public
    assert public["tiktok_client_secret_set"] is True
    assert "tiktok_client_secret" not in public
    assert public["youtube_configured"] is True
    assert public["tiktok_configured"] is True
    assert public["redirect_uri"] == "http://127.0.0.1:54000/oauth/callback"

    publishing.save_publishing_settings(
        {
            "youtube_client_id": "new-client",
            "youtube_client_secret": "",
        }
    )
    raw = json.loads((publish_env / "publishing.json").read_text(encoding="utf-8"))
    assert raw["youtube_client_id"] == "new-client"
    assert raw["youtube_client_secret"] == "yt-secret"

    publishing.save_publishing_settings({"redirect_port": 80})
    assert publishing.load_publishing_settings().redirect_port == 53682


def test_start_oauth_builds_youtube_url_and_tracks_state(
    publish_env, monkeypatch
) -> None:
    publishing.save_publishing_settings(
        {
            "youtube_client_id": "yt-client",
            "youtube_client_secret": "yt-secret",
        }
    )
    opened: list[str] = []
    monkeypatch.setattr(publishing, "_ensure_callback_server", lambda cfg: None)
    monkeypatch.setattr(
        publishing.webbrowser, "open", lambda url: opened.append(url) or True
    )
    publishing._PENDING.clear()

    result = publishing.start_oauth("youtube")

    assert result["auth_url"].startswith(publishing.YOUTUBE_AUTH_URL)
    assert "client_id=yt-client" in result["auth_url"]
    assert f"state={result['state']}" in result["auth_url"]
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A53682%2Foauth%2Fcallback" in (
        result["auth_url"]
    )
    assert opened == [result["auth_url"]]
    status = publishing.oauth_status("youtube", result["state"])
    assert status["status"] == "pending"
    assert status["connected"] is False
    publishing._PENDING.clear()


def test_start_oauth_rejects_missing_credentials(publish_env) -> None:
    with pytest.raises(PublishingError) as error:
        publishing.start_oauth("youtube")

    assert error.value.code == "not_configured"


def test_access_token_refreshes_expired_youtube_account(
    publish_env, publishing_db, monkeypatch
) -> None:
    publishing.save_publishing_settings(
        {
            "youtube_client_id": "yt-client",
            "youtube_client_secret": "yt-secret",
        }
    )
    db.upsert_publishing_account(
        "youtube",
        access_token="old-token",
        refresh_token="refresh-token",
        expires_at="2020-01-01T00:00:00+00:00",
        scope=publishing.YOUTUBE_SCOPE,
        account_id="channel-1",
        account_name="Canal",
    )
    calls: list[tuple[str, dict]] = []

    def fake_post(url, data=None, timeout=None):
        calls.append((url, data or {}))
        return FakeResponse(
            200,
            {
                "access_token": "new-token",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
                "scope": publishing.YOUTUBE_SCOPE,
            },
        )

    monkeypatch.setattr(publishing.requests, "post", fake_post)

    assert publishing._access_token("youtube") == "new-token"
    assert calls[0][0] == publishing.YOUTUBE_TOKEN_URL
    assert calls[0][1]["grant_type"] == "refresh_token"
    assert calls[0][1]["refresh_token"] == "refresh-token"

    updated = db.get_publishing_account("youtube")
    assert updated is not None
    assert updated["access_token"] == "new-token"
    assert updated["refresh_token"] == "new-refresh"
    assert updated["expires_at"] is not None


def test_youtube_upload_chunks_and_marks_published(tmp_path, monkeypatch) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0123456789")
    updates: list[dict] = []
    puts: list[dict] = []
    posts: list[dict] = []
    put_responses = [
        FakeResponse(308, {}, {"Range": "bytes=0-3"}),
        FakeResponse(308, {}, {"Range": "bytes=0-7"}),
        FakeResponse(200, {"id": "abc123"}),
    ]

    monkeypatch.setattr(publishing, "YOUTUBE_UPLOAD_CHUNK", 4)
    monkeypatch.setattr(publishing, "_access_token", lambda platform: "token")
    monkeypatch.setattr(
        publishing,
        "load_publishing_settings",
        lambda: PublishingSettings(youtube_privacy="unlisted"),
    )
    monkeypatch.setattr(
        publishing,
        "_update_record",
        lambda record_id, **fields: updates.append(fields),
    )

    def fake_post(url, json=None, headers=None, timeout=None):
        posts.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(200, {}, {"Location": "https://upload.example/session"})

    def fake_put(url, data=None, headers=None, timeout=None):
        puts.append({"url": url, "data": data, "headers": headers})
        return put_responses.pop(0)

    monkeypatch.setattr(publishing.requests, "post", fake_post)
    monkeypatch.setattr(publishing.requests, "put", fake_put)

    publishing._upload_youtube(
        "record-1",
        video,
        {
            "title": "Un momento increíble",
            "description": "Descripción completa del clip.",
            "tags": ["Roblox"],
        },
        {"meta": {"game": "Roblox", "streamer": "Adrity 35"}},
    )

    assert posts[0]["json"]["snippet"]["title"] == "Un momento increíble"
    assert posts[0]["json"]["snippet"]["description"] == (
        "Descripción completa del clip."
    )
    assert posts[0]["json"]["snippet"]["categoryId"] == "20"
    assert posts[0]["json"]["status"]["privacyStatus"] == "unlisted"
    assert posts[0]["headers"]["X-Upload-Content-Length"] == "10"
    assert [put["headers"]["Content-Range"] for put in puts] == [
        "bytes 0-3/10",
        "bytes 4-7/10",
        "bytes 8-9/10",
    ]
    assert updates[-1]["status"] == "published"
    assert updates[-1]["progress"] == 100
    assert updates[-1]["remote_id"] == "abc123"
    assert updates[-1]["remote_url"] == "https://youtube.com/shorts/abc123"


def test_tiktok_upload_chunks_and_waits_for_publish(tmp_path, monkeypatch) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0123456789")
    updates: list[dict] = []
    puts: list[dict] = []
    posts: list[dict] = []
    post_responses = [
        FakeResponse(
            200,
            {
                "data": {
                    "publish_id": "pub1",
                    "upload_url": "https://upload.example/tiktok",
                },
                "error": {"code": "ok"},
            },
        ),
        FakeResponse(
            200,
            {
                "data": {"status": "PROCESSING_UPLOAD"},
                "error": {"code": "ok"},
            },
        ),
        FakeResponse(
            200,
            {
                "data": {
                    "status": "PUBLISH_COMPLETE",
                    "publicaly_available_post_id": ["video123"],
                },
                "error": {"code": "ok"},
            },
        ),
    ]

    monkeypatch.setattr(publishing, "TIKTOK_UPLOAD_CHUNK", 4)
    monkeypatch.setattr(publishing, "_access_token", lambda platform: "token")
    monkeypatch.setattr(
        publishing,
        "load_publishing_settings",
        lambda: PublishingSettings(tiktok_privacy="SELF_ONLY"),
    )
    monkeypatch.setattr(
        publishing,
        "_update_record",
        lambda record_id, **fields: updates.append(fields),
    )
    monkeypatch.setattr(publishing.time, "sleep", lambda seconds: None)

    def fake_post(url, json=None, headers=None, timeout=None):
        posts.append({"url": url, "json": json, "headers": headers})
        return post_responses.pop(0)

    def fake_put(url, data=None, headers=None, timeout=None):
        puts.append({"url": url, "data": data, "headers": headers})
        return FakeResponse(201)

    monkeypatch.setattr(publishing.requests, "post", fake_post)
    monkeypatch.setattr(publishing.requests, "put", fake_put)

    publishing._upload_tiktok(
        "record-1",
        video,
        {"title": "Un momento increíble", "caption": "Caption para TikTok."},
        {"meta": {}},
    )

    assert posts[0]["url"] == publishing.TIKTOK_INIT_URL
    assert posts[0]["json"]["post_info"]["title"] == "Caption para TikTok."
    assert posts[0]["json"]["post_info"]["privacy_level"] == "SELF_ONLY"
    assert posts[0]["json"]["source_info"] == {
        "source": "FILE_UPLOAD",
        "video_size": 10,
        "chunk_size": 4,
        "total_chunk_count": 3,
    }
    assert [put["headers"]["Content-Range"] for put in puts] == [
        "bytes 0-3/10",
        "bytes 4-7/10",
        "bytes 8-9/10",
    ]
    assert updates[-1]["status"] == "published"
    assert updates[-1]["progress"] == 100
    assert updates[-1]["remote_id"] == "video123"
    assert "tiktok.com" in updates[-1]["remote_url"]


def test_publish_clip_queues_record_and_blocks_duplicate(
    publish_env, publishing_db, monkeypatch
) -> None:
    monkeypatch.setattr(db.settings, "jobs_dir", publish_env / "jobs")
    job = db.create_job(
        job_id="job1",
        source_type="youtube",
        source_url="https://youtu.be/abc",
        title="Directo",
        options={},
        clips_target=1,
        meta={"streamer": "Adrity 35", "game": "Roblox", "is_gaming": True},
    )
    clip = db.add_clip(
        clip_id="clip1",
        job_id=job["id"],
        idx=0,
        start=0.0,
        end=30.0,
        duration=30.0,
        score=90,
        score_breakdown={},
        title="Un momento",
        hook="No puede ser",
        reason="Buen gancho",
        caption="Caption",
        description="Descripción",
        tags=["Roblox"],
        subtitles={"cues": []},
        style="shorts",
        status="ready",
    )
    db.update_clip(clip["id"], video_file="clips/clip1/clip.mp4")
    clip = db.get_clip(clip["id"])
    assert clip is not None
    video = publish_env / "jobs" / job["id"] / clip["video_file"]
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"video")
    db.upsert_publishing_account(
        "youtube",
        access_token="token",
        refresh_token="refresh",
        expires_at="2099-01-01T00:00:00+00:00",
        scope=publishing.YOUTUBE_SCOPE,
        account_id="channel",
        account_name="Canal",
    )
    started: list[tuple] = []

    class FakeThread:
        def __init__(self, target, args, name=None, daemon=None):
            self.target = target
            self.args = args

        def start(self):
            started.append(self.args)

    monkeypatch.setattr(
        publishing, "threading", SimpleNamespace(Thread=FakeThread)
    )

    record = publishing.publish_clip(clip["id"], "youtube")

    assert record["status"] == "queued"
    assert record["progress"] == 0
    assert started == [(record["id"], clip["id"], "youtube")]
    with pytest.raises(PublishingError) as error:
        publishing.publish_clip(clip["id"], "youtube")
    assert error.value.code == "publish_in_progress"

    db.delete_publishing_account("youtube")
    db.update_publish_record(record["id"], status="failed")
    with pytest.raises(PublishingError) as error:
        publishing.publish_clip(clip["id"], "youtube")
    assert error.value.code == "not_connected"


def test_publishing_settings_http_endpoints(publish_env, publishing_db) -> None:
    with TestClient(main.app) as client:
        response = client.get("/api/publishing/settings")
        assert response.status_code == 200
        assert response.json()["youtube_configured"] is False

        response = client.put(
            "/api/publishing/settings",
            json={
                "youtube_client_id": "yt-client",
                "youtube_client_secret": "yt-secret",
                "youtube_privacy": "unlisted",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["youtube_client_secret_set"] is True
        assert payload["youtube_configured"] is True
        assert "youtube_client_secret" not in payload

        response = client.get("/api/publishing/connections")
        assert response.status_code == 200
        assert response.json()["connections"] == {
            "youtube": None,
            "tiktok": None,
        }
