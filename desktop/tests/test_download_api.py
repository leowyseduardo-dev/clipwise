from __future__ import annotations

import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from launcher import (
    DesktopDownloadApi,
    _filename_from_disposition,
    _safe_filename,
)

PAYLOAD = b"clipforge-download-test\n" * 32


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.send_header(
            "Content-Disposition", 'attachment; filename="clipforge-test.mp4"'
        )
        self.end_headers()
        self.wfile.write(PAYLOAD)

    def log_message(self, *_args: object) -> None:
        return


class _FakeWindow:
    def __init__(self, destination: str | None) -> None:
        self.destination = destination
        self.calls: list[dict[str, object]] = []

    def create_file_dialog(self, *args: object, **kwargs: object) -> str | None:
        self.calls.append({"args": args, "kwargs": kwargs})
        return self.destination


@pytest.fixture()
def server() -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.fixture(autouse=True)
def fake_webview(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "webview",
        types.SimpleNamespace(SAVE_DIALOG="save-dialog"),
    )


def test_safe_filename_strips_paths_and_reserved_names() -> None:
    assert _safe_filename("clip-01-demo.mp4", "fallback.mp4") == "clip-01-demo.mp4"
    assert _safe_filename("..\\..\\clip.mp4", "fallback.mp4") == "clip.mp4"
    assert _safe_filename('bad<>:"|?*.mp4', "fallback.mp4") == "bad_______.mp4"
    assert _safe_filename("CON.mp4", "fallback.mp4") == "_CON.mp4"
    assert _safe_filename("", "") == ""
    assert _safe_filename("", "clipforge-download.bin") == "clipforge-download.bin"


def test_disposition_parser_handles_ascii_and_utf8() -> None:
    assert (
        _filename_from_disposition('attachment; filename="clipforge-video.zip"')
        == "clipforge-video.zip"
    )
    mojibake = 'attachment; filename="qu\u00c3\u00a9-es-esto.srt"'
    assert _filename_from_disposition(mojibake) == "qu\u00e9-es-esto.srt"
    assert _filename_from_disposition(None) is None
    assert _filename_from_disposition("attachment") is None


def test_resolve_rejects_external_and_non_download_urls() -> None:
    api = DesktopDownloadApi(52573)
    assert api._resolve("/api/clips/abc/video.mp4") == (
        "http://127.0.0.1:52573/api/clips/abc/video.mp4"
    )
    with pytest.raises(ValueError):
        api._resolve("https://example.com/api/clips/abc/video.mp4")
    with pytest.raises(ValueError):
        api._resolve("http://127.0.0.1:52573/api/health")
    with pytest.raises(ValueError):
        api._resolve("http://127.0.0.1:52573/static/app.js")


def test_save_download_streams_to_selected_path(
    server: ThreadingHTTPServer, tmp_path: Path
) -> None:
    port = int(server.server_address[1])
    destination = tmp_path / "clip-01-demo"
    api = DesktopDownloadApi(port)
    window = _FakeWindow(str(destination))
    api.window = window

    result = api.save_download("/api/clips/abc/video.mp4", "clip-01-demo")

    assert result["ok"] is True
    assert result["size"] == len(PAYLOAD)
    saved = tmp_path / "clip-01-demo.mp4"
    assert saved.read_bytes() == PAYLOAD
    assert result["path"] == str(saved)
    assert not Path(f"{saved}.part").exists()
    assert window.calls[0]["kwargs"]["save_filename"] == "clip-01-demo.mp4"


def test_save_download_cancel_keeps_no_partial_file(
    server: ThreadingHTTPServer, tmp_path: Path
) -> None:
    port = int(server.server_address[1])
    api = DesktopDownloadApi(port)
    api.window = _FakeWindow(None)

    result = api.save_download("/api/jobs/abc/download.zip")

    assert result == {"ok": False, "cancelled": True}
    assert list(tmp_path.iterdir()) == []
