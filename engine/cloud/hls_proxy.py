"""Same-origin HLS proxy used by the browser clip studio.

The browser asks ``/api/public/hls?u=<playlist or segment>`` and this module
fetches the upstream stream. Hosts are restricted to the video platforms
Clipwise supports so the endpoint cannot be used to reach internal services.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

ALLOWED_SUFFIXES = (
    "kick.com",
    "twitch.tv",
    "cloudfront.net",
    "ttvnw.net",
    "googlevideo.com",
    "youtube.com",
    "youtu.be",
)
_MAX_URL = 2048


def resolve(url: str) -> str:
    target = (url or "").strip()
    if not target or len(target) > _MAX_URL:
        raise HTTPException(400, "URL de stream no válida.")
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(400, "URL de stream no válida.")
    host = parsed.hostname.strip(".").lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
    ):
        raise HTTPException(400, "Host de stream no permitido.")
    if not any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_SUFFIXES):
        raise HTTPException(400, "Plataforma de stream no soportada.")
    return target


async def stream(request: Request, u: str) -> StreamingResponse:
    target = resolve(u)
    headers = {"Accept": "*/*", "User-Agent": "Clipwise-HLS/1.0"}
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header
    client = httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(30.0, connect=10.0),
        trust_env=False,
        headers=headers,
    )
    try:
        upstream = await client.send(client.build_request("GET", target), stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(502, "No se pudo alcanzar el stream.") from exc
    if upstream.status_code >= 400:
        status = upstream.status_code
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(502, f"El stream devolvió {status}.")
    content_type = upstream.headers.get("content-type") or (
        "application/vnd.apple.mpegurl"
        if ".m3u8" in target
        else "video/mp2t"
    )

    async def body():
        try:
            async for chunk in upstream.aiter_bytes(64 * 1024):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=2",
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
        },
        background=BackgroundTask(lambda: None),
    )
