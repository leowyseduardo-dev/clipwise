from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import ingest
from app.ingest import IngestError, validate_youtube_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=42",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
        "http://youtube.com/watch?v=abc123",
    ],
)
def test_validate_youtube_url_accepts_video_urls(url: str) -> None:
    assert validate_youtube_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://youtube.com/watch?v=abc123",
        "javascript:alert(1)",
        "https://vimeo.com/12345",
        "https://notyoutube.com/watch?v=abc123",
        "https://youtube.com.evil.example/watch?v=abc123",
        "https://www.youtube.com/",
        "https://www.youtube.com/playlist?list=abc",
        "https://youtu.be/",
    ],
)
def test_validate_youtube_url_rejects_other_sources(url: str) -> None:
    with pytest.raises(IngestError):
        validate_youtube_url(url)


class FakeDownloadError(Exception):
    pass


def _fake_ytdlp(handler) -> SimpleNamespace:
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            return handler(url, self.opts)

        def download(self, urls):
            return handler(urls[0], self.opts)

    return SimpleNamespace(
        YoutubeDL=FakeYDL,
        utils=SimpleNamespace(DownloadError=FakeDownloadError),
    )


def test_bot_check_markers() -> None:
    assert ingest._is_bot_check(
        "ERROR: Sign in to confirm you're not a bot. Use --cookies-from-browser."
    )
    assert not ingest._is_bot_check("ERROR: Requested format is not available")


def test_transient_network_markers() -> None:
    assert ingest._is_transient_error(
        "ERROR: Unable to download API page: Failed to resolve 'www.youtube.com' "
        "([Errno 11001] getaddrinfo failed)"
    )
    assert ingest._is_transient_error("Connection reset by peer")
    assert not ingest._is_transient_error("Requested format is not available")


def test_extract_info_retries_transient_network_error(monkeypatch) -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    def handler(_url, _opts):
        calls["count"] += 1
        if calls["count"] < 3:
            raise FakeDownloadError(
                "Unable to download API page: Failed to resolve 'www.youtube.com' "
                "([Errno 11001] getaddrinfo failed)"
            )
        return {"duration": 12.5, "title": "ok"}

    monkeypatch.setattr(ingest.time, "sleep", lambda seconds: sleeps.append(seconds))
    fake = _fake_ytdlp(handler)

    info = ingest._extract_info(fake, "https://youtu.be/abc", {}, attempts=3)

    assert info == {"duration": 12.5, "title": "ok"}
    assert calls["count"] == 3
    assert sleeps == [2.0, 4.0]


def test_friendly_bot_check_message_is_actionable() -> None:
    message = ingest._friendly_ytdlp_error(
        "ERROR: [youtube] abc: Sign in to confirm you're not a bot. "
        "Use --cookies-from-browser or --cookies for the authentication."
    )
    assert "anti-bot" in message
    assert "navegador" in message
    assert "sube el archivo" in message


def test_extract_info_retries_bot_check(monkeypatch) -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    def handler(_url, _opts):
        calls["count"] += 1
        if calls["count"] < 3:
            raise FakeDownloadError(
                "Sign in to confirm you're not a bot. "
                "Use --cookies-from-browser or --cookies for the authentication."
            )
        return {"duration": 12.5, "title": "ok"}

    monkeypatch.setattr(ingest.time, "sleep", lambda seconds: sleeps.append(seconds))
    fake = _fake_ytdlp(handler)

    info = ingest._extract_info(fake, "https://youtu.be/abc", {}, attempts=3)

    assert info == {"duration": 12.5, "title": "ok"}
    assert calls["count"] == 3
    assert sleeps == [1.5, 3.0]


def test_extract_info_does_not_retry_non_bot_error(monkeypatch) -> None:
    calls = {"count": 0}

    def handler(_url, _opts):
        calls["count"] += 1
        raise FakeDownloadError("Requested format is not available")

    monkeypatch.setattr(ingest.time, "sleep", lambda _seconds: None)
    fake = _fake_ytdlp(handler)

    with pytest.raises(FakeDownloadError):
        ingest._extract_info(fake, "https://youtu.be/abc", {}, attempts=3)
    assert calls["count"] == 1


def test_browser_cookie_option_parses_profile() -> None:
    assert ingest._browser_cookie_option("edge:Default") == {
        "cookiesfrombrowser": ("edge", "Default", None, None)
    }
    assert ingest._browser_cookie_option("nope") is None


def test_prepare_working_copy_keeps_audio_only_source(tmp_path, monkeypatch) -> None:
    source = tmp_path / "audio.m4a"
    source.write_bytes(b"not a real audio file")
    info = {
        "duration": 100.0,
        "width": 0,
        "height": 0,
        "video_codec": "",
        "rotation": 0,
    }

    def fail_run(*args, **kwargs):
        raise AssertionError("audio-only sources must not be transcoded")

    monkeypatch.setattr(ingest, "run_ffmpeg", fail_run)

    working, prepared = ingest.prepare_working_copy(source, tmp_path, info)

    assert working == source
    assert prepared == info
    assert not (tmp_path / "working.mp4").exists()


def test_cookie_option_sets_include_configured_file(tmp_path, monkeypatch) -> None:
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    monkeypatch.setattr(ingest.settings, "ytdlp_cookies", str(cookies))
    monkeypatch.setattr(ingest.settings, "ytdlp_cookies_from_browser", "")
    monkeypatch.setattr(ingest.settings, "ytdlp_auto_cookies", False)

    assert ingest._cookie_option_sets() == [{"cookiefile": str(cookies)}]
