import pytest
from fastapi import HTTPException

from cloud import hls_proxy


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/api/account",
        "http://localhost/admin",
        "https://10.0.0.5/secret",
        "https://example.com/playlist.m3u8",
        "ftp://stream.kick.com/a.m3u8",
        "",
    ],
)
def test_hls_proxy_rejects_unsafe_urls(url):
    with pytest.raises(HTTPException) as caught:
        hls_proxy.resolve(url)
    assert caught.value.status_code == 400


@pytest.mark.parametrize(
    "url",
    [
        "https://stream.kick.com/abc/playlist.m3u8",
        "https://prod.twitch.tv/segment.ts?token=1",
        "https://video.cloudfront.net/hls/0.ts",
    ],
)
def test_hls_proxy_allows_stream_hosts(url):
    assert hls_proxy.resolve(url) == url
