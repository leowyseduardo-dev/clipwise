from __future__ import annotations

import html
import json
import logging
import math
import os
import re
import secrets
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from . import db
from .config import settings

logger = logging.getLogger("Clipwise.publishing")

YOUTUBE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_SCOPE = (
    "https://www.googleapis.com/auth/youtube.upload "
    "https://www.googleapis.com/auth/youtube.readonly"
)
YOUTUBE_UPLOAD_CHUNK = 8 * 1024 * 1024

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_USER_URL = "https://open.tiktokapis.com/v2/user/info/"
TIKTOK_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
TIKTOK_SCOPE = "user.info.basic,video.publish"
TIKTOK_UPLOAD_CHUNK = 10 * 1024 * 1024
TIKTOK_STATUS_TIMEOUT = 600

PENDING_TTL_SECONDS = 900
TOKEN_REFRESH_MARGIN_SECONDS = 90

_PLATFORM_NAMES = {"youtube": "YouTube", "tiktok": "TikTok"}
_SECRET_FIELDS = {"youtube_client_secret", "tiktok_client_secret"}
_YOUTUBE_PRIVACY = {"private", "unlisted", "public"}
_TIKTOK_PRIVACY = {
    "PUBLIC_TO_EVERYONE",
    "MUTUAL_FOLLOW_FRIENDS",
    "FOLLOWER_OF_CREATOR",
    "SELF_ONLY",
}
_REDIRECT_HOSTS = {"127.0.0.1", "localhost"}


class PublishingError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "publishing_error",
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass
class PublishingSettings:
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    redirect_host: str = "127.0.0.1"
    redirect_port: int = 53682
    youtube_privacy: str = "public"
    tiktok_privacy: str = "PUBLIC_TO_EVERYONE"


@dataclass
class OAuthPending:
    platform: str
    state: str
    redirect_uri: str
    status: str = "pending"
    message: str = ""
    created_at: float = field(default_factory=time.time)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _settings_path() -> Path:
    return settings.data_dir / "publishing.json"


def _normalize_settings(cfg: PublishingSettings) -> PublishingSettings:
    try:
        cfg.redirect_port = int(cfg.redirect_port)
    except (TypeError, ValueError):
        cfg.redirect_port = 53682
    if not (1024 <= cfg.redirect_port <= 65535):
        cfg.redirect_port = 53682
    cfg.redirect_host = str(cfg.redirect_host or "127.0.0.1").strip().lower()
    if cfg.redirect_host not in _REDIRECT_HOSTS:
        cfg.redirect_host = "127.0.0.1"
    if cfg.youtube_privacy not in _YOUTUBE_PRIVACY:
        cfg.youtube_privacy = "public"
    if cfg.tiktok_privacy not in _TIKTOK_PRIVACY:
        cfg.tiktok_privacy = "PUBLIC_TO_EVERYONE"
    cfg.youtube_client_id = str(cfg.youtube_client_id or "").strip()
    cfg.youtube_client_secret = str(cfg.youtube_client_secret or "").strip()
    cfg.tiktok_client_key = str(cfg.tiktok_client_key or "").strip()
    cfg.tiktok_client_secret = str(cfg.tiktok_client_secret or "").strip()
    return cfg


def load_publishing_settings() -> PublishingSettings:
    cfg = PublishingSettings(
        youtube_client_id=os.getenv("YOUTUBE_CLIENT_ID", ""),
        youtube_client_secret=os.getenv("YOUTUBE_CLIENT_SECRET", ""),
        tiktok_client_key=os.getenv("TIKTOK_CLIENT_KEY", ""),
        tiktok_client_secret=os.getenv("TIKTOK_CLIENT_SECRET", ""),
        redirect_host=os.getenv("PUBLISHING_REDIRECT_HOST", "127.0.0.1"),
        redirect_port=_env_int("PUBLISHING_REDIRECT_PORT", 53682),
        youtube_privacy=os.getenv("YOUTUBE_PRIVACY", "public"),
        tiktok_privacy=os.getenv("TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE"),
    )
    path = _settings_path()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("No se pudo leer %s; se usan valores por defecto.", path)
            raw = {}
        if isinstance(raw, dict):
            for key in PublishingSettings.__dataclass_fields__:
                if key in raw and raw[key] is not None:
                    setattr(cfg, key, raw[key])
    return _normalize_settings(cfg)


def save_publishing_settings(payload: dict[str, Any]) -> PublishingSettings:
    cfg = load_publishing_settings()
    for key in PublishingSettings.__dataclass_fields__:
        if key not in payload:
            continue
        value = payload[key]
        if value is None:
            continue
        if key in _SECRET_FIELDS and not str(value).strip():
            continue
        setattr(cfg, key, value)
    cfg = _normalize_settings(cfg)
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.tmp")
    temp.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)
    return cfg


def _redirect_uri(cfg: PublishingSettings | None = None) -> str:
    if os.getenv("CLIPFORGE_TEAM_ENGINE") == "1" and os.getenv("CLIPFORGE_PUBLIC_ORIGIN"):
        return os.environ["CLIPFORGE_PUBLIC_ORIGIN"].rstrip("/") + "/api/publishing/callback"
    cfg = cfg or load_publishing_settings()
    return f"http://{cfg.redirect_host}:{cfg.redirect_port}/oauth/callback"


def public_settings() -> dict[str, Any]:
    cfg = load_publishing_settings()
    return {
        "youtube_client_id": cfg.youtube_client_id,
        "youtube_client_secret_set": bool(cfg.youtube_client_secret),
        "tiktok_client_key": cfg.tiktok_client_key,
        "tiktok_client_secret_set": bool(cfg.tiktok_client_secret),
        "redirect_host": cfg.redirect_host,
        "redirect_port": cfg.redirect_port,
        "redirect_uri": _redirect_uri(cfg),
        "youtube_privacy": cfg.youtube_privacy,
        "tiktok_privacy": cfg.tiktok_privacy,
        "youtube_configured": bool(cfg.youtube_client_id and cfg.youtube_client_secret),
        "tiktok_configured": bool(cfg.tiktok_client_key and cfg.tiktok_client_secret),
    }


def public_account(platform: str) -> dict[str, Any] | None:
    account = db.get_publishing_account(platform)
    if not account:
        return None
    return {
        "platform": platform,
        "connected": True,
        "account_id": account.get("account_id"),
        "account_name": account.get("account_name"),
        "scope": account.get("scope"),
        "expires_at": account.get("expires_at"),
        "metadata": account.get("metadata") or {},
    }


def connections() -> dict[str, Any]:
    return {
        "youtube": public_account("youtube"),
        "tiktok": public_account("tiktok"),
    }


def publish_record_out(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata") or {}
    return {
        "id": record["id"],
        "clip_id": record["clip_id"],
        "platform": record["platform"],
        "status": record["status"],
        "progress": float(metadata.get("progress") or 0),
        "remote_id": record.get("remote_id"),
        "remote_url": record.get("remote_url"),
        "error": record.get("error"),
        "metadata": metadata,
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def _truncate(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _one_line(text: Any, limit: int) -> str:
    return _truncate(str(text or ""), limit)


def _youtube_title(clip: dict[str, Any]) -> str:
    title = _one_line(clip.get("title") or clip.get("hook") or "Clipwise", 100)
    title = title.replace("<", "").replace(">", "").strip()
    return title or "Clipwise"


def _youtube_description(clip: dict[str, Any]) -> str:
    description = str(
        clip.get("description")
        or clip.get("caption")
        or clip.get("title")
        or ""
    ).strip()
    return description[:5000] or _youtube_title(clip)


def _youtube_tags(clip: dict[str, Any], job: dict[str, Any]) -> list[str]:
    meta = job.get("meta") or {}
    raw = list(clip.get("tags") or []) + [
        meta.get("game"),
        meta.get("streamer") or meta.get("channel"),
    ]
    seen: set[str] = set()
    result: list[str] = []
    total = 0
    for value in raw:
        tag = _one_line(value, 60).replace("<", "").replace(">", "").strip()
        if not tag or tag.lower() in seen:
            continue
        if total + len(tag) + 1 > 480:
            break
        seen.add(tag.lower())
        result.append(tag)
        total += len(tag) + 1
        if len(result) >= 15:
            break
    return result


def _youtube_category_id(clip: dict[str, Any], job: dict[str, Any]) -> str:
    meta = job.get("meta") or {}
    haystack = " ".join(
        [
            str(meta.get("game") or ""),
            str(clip.get("title") or ""),
            " ".join(str(tag) for tag in (clip.get("tags") or [])),
        ]
    ).lower()
    if meta.get("is_gaming") or meta.get("game") or any(
        word in haystack for word in ("gameplay", "roblox", "minecraft", "fortnite")
    ):
        return "20"
    return "22"


def _clip_caption(clip: dict[str, Any]) -> str:
    caption = str(clip.get("caption") or "").strip()
    if not caption:
        caption = str(
            clip.get("description") or clip.get("title") or "Clipwise"
        ).strip()
    return _truncate(caption, 2200) or "Clipwise"


def _clip_video_path(clip: dict[str, Any]) -> Path:
    video_file = str(clip.get("video_file") or "").strip()
    if not video_file:
        raise PublishingError(
            "El clip todavía no tiene un video renderizado.",
            code="no_video",
            status_code=409,
        )
    path = Path(video_file)
    if not path.is_absolute():
        path = settings.jobs_dir / str(clip["job_id"]) / video_file
    if not path.exists() or not path.is_file():
        raise PublishingError(
            "No se encontró el archivo MP4 del clip.",
            code="no_video",
            status_code=409,
        )
    if path.stat().st_size <= 0:
        raise PublishingError(
            "El archivo MP4 del clip está vacío.",
            code="no_video",
            status_code=409,
        )
    return path


def _response_error(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("error_description")
            code = error.get("code")
            if message:
                return f"{message} ({code})" if code else str(message)
        if isinstance(error, str):
            description = payload.get("error_description")
            return f"{description} ({error})" if description else error
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    text = (response.text or "").strip()
    if text:
        return text[:300]
    return f"HTTP {response.status_code}"


def _raise_http(response: requests.Response, prefix: str) -> None:
    if response.status_code >= 400:
        raise PublishingError(
            f"{prefix}: {_response_error(response)}",
            code="platform_error",
            status_code=502,
        )


def _json_or_empty(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _check_tiktok_response(
    response: requests.Response, prefix: str
) -> dict[str, Any]:
    _raise_http(response, prefix)
    payload = _json_or_empty(response)
    error = payload.get("error")
    if isinstance(error, dict):
        code = str(error.get("code") or "").strip()
        if code and code.lower() != "ok":
            message = str(error.get("message") or code)
            raise PublishingError(
                f"{prefix}: {message} ({code})",
                code="platform_error",
                status_code=502,
            )
    return payload


def _post_form(url: str, data: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(url, data=data, timeout=45)
    if response.status_code >= 400:
        raise PublishingError(
            f"No se pudo completar la conexión: {_response_error(response)}",
            code="oauth_error",
            status_code=502,
        )
    payload = _json_or_empty(response)
    if not payload:
        raise PublishingError(
            "La plataforma devolvió una respuesta vacía al conectar la cuenta.",
            code="oauth_error",
            status_code=502,
        )
    return payload


def _expires_at(seconds: Any) -> str | None:
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=value)).isoformat(
        timespec="seconds"
    )


def _expires_soon(account: dict[str, Any]) -> bool:
    raw = account.get("expires_at")
    if not raw:
        return True
    try:
        expiry = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return True
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry <= datetime.now(timezone.utc) + timedelta(
        seconds=TOKEN_REFRESH_MARGIN_SECONDS
    )


def _exchange_youtube_code(code: str, redirect_uri: str) -> dict[str, Any]:
    cfg = load_publishing_settings()
    token = _post_form(
        YOUTUBE_TOKEN_URL,
        {
            "code": code,
            "client_id": cfg.youtube_client_id,
            "client_secret": cfg.youtube_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    access_token = str(token.get("access_token") or "")
    if not access_token:
        raise PublishingError(
            "YouTube no devolvió un token de acceso.",
            code="oauth_error",
            status_code=502,
        )
    account_id: str | None = None
    account_name: str | None = None
    try:
        response = requests.get(
            YOUTUBE_CHANNELS_URL,
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        if response.status_code < 400:
            items = _json_or_empty(response).get("items") or []
            if items:
                account_id = str(items[0].get("id") or "") or None
                account_name = (
                    str((items[0].get("snippet") or {}).get("title") or "") or None
                )
    except Exception:
        logger.warning("No se pudo leer el canal de YouTube.", exc_info=True)
    return db.upsert_publishing_account(
        "youtube",
        access_token=access_token,
        refresh_token=str(token.get("refresh_token") or "") or None,
        expires_at=_expires_at(token.get("expires_in")),
        scope=str(token.get("scope") or "") or None,
        account_id=account_id,
        account_name=account_name,
        metadata={"token_type": token.get("token_type")},
    )


def _exchange_tiktok_code(code: str, redirect_uri: str) -> dict[str, Any]:
    cfg = load_publishing_settings()
    token = _post_form(
        TIKTOK_TOKEN_URL,
        {
            "client_key": cfg.tiktok_client_key,
            "client_secret": cfg.tiktok_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    access_token = str(token.get("access_token") or "")
    if not access_token:
        raise PublishingError(
            "TikTok no devolvió un token de acceso.",
            code="oauth_error",
            status_code=502,
        )
    account_id = str(token.get("open_id") or "") or None
    account_name: str | None = None
    try:
        response = requests.get(
            TIKTOK_USER_URL,
            params={"fields": "open_id,display_name,username,avatar_url"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        if response.status_code < 400:
            payload = _json_or_empty(response)
            user = (payload.get("data") or {}).get("user") or {}
            account_id = str(user.get("open_id") or account_id or "") or None
            account_name = (
                str(user.get("display_name") or user.get("username") or "") or None
            )
    except Exception:
        logger.warning("No se pudo leer el perfil de TikTok.", exc_info=True)
    return db.upsert_publishing_account(
        "tiktok",
        access_token=access_token,
        refresh_token=str(token.get("refresh_token") or "") or None,
        expires_at=_expires_at(token.get("expires_in")),
        scope=str(token.get("scope") or "") or None,
        account_id=account_id,
        account_name=account_name,
        metadata={
            "token_type": token.get("token_type"),
            "open_id": token.get("open_id"),
        },
    )


_TOKEN_LOCK = threading.RLock()


def _access_token(platform: str) -> str:
    with _TOKEN_LOCK:
        account = db.get_publishing_account(platform)
        if not account:
            raise PublishingError(
                f"Conecta tu cuenta de {_PLATFORM_NAMES[platform]} antes de publicar.",
                code="not_connected",
                status_code=409,
            )
        if not _expires_soon(account):
            return str(account["access_token"])
        refresh_token = str(account.get("refresh_token") or "")
        if not refresh_token:
            raise PublishingError(
                f"La conexión con {_PLATFORM_NAMES[platform]} caducó. "
                "Vuelve a conectarla.",
                code="token_expired",
                status_code=409,
            )
        cfg = load_publishing_settings()
        if platform == "youtube":
            token = _post_form(
                YOUTUBE_TOKEN_URL,
                {
                    "client_id": cfg.youtube_client_id,
                    "client_secret": cfg.youtube_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        else:
            token = _post_form(
                TIKTOK_TOKEN_URL,
                {
                    "client_key": cfg.tiktok_client_key,
                    "client_secret": cfg.tiktok_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        access_token = str(token.get("access_token") or "")
        if not access_token:
            raise PublishingError(
                f"{_PLATFORM_NAMES[platform]} no renovó el token de acceso. "
                "Vuelve a conectar la cuenta.",
                code="token_expired",
                status_code=409,
            )
        db.upsert_publishing_account(
            platform,
            access_token=access_token,
            refresh_token=str(token.get("refresh_token") or "") or refresh_token,
            expires_at=_expires_at(token.get("expires_in")),
            scope=str(token.get("scope") or "") or account.get("scope"),
            account_id=account.get("account_id"),
            account_name=account.get("account_name"),
            metadata=account.get("metadata") or {},
        )
        return access_token


_OAUTH_LOCK = threading.RLock()
_PENDING: dict[str, OAuthPending] = {}
_CALLBACK_SERVER: ThreadingHTTPServer | None = None


def _prune_pending() -> None:
    cutoff = time.time() - PENDING_TTL_SECONDS
    for state, pending in list(_PENDING.items()):
        if pending.created_at < cutoff:
            _PENDING.pop(state, None)


def _finish_pending(pending: OAuthPending, status: str, message: str) -> None:
    with _OAUTH_LOCK:
        pending.status = status
        pending.message = message


def _request_callback_stop() -> None:
    global _CALLBACK_SERVER
    with _OAUTH_LOCK:
        server = _CALLBACK_SERVER
        _CALLBACK_SERVER = None
    if server is None:
        return

    def stop() -> None:
        try:
            server.shutdown()
        finally:
            server.server_close()

    threading.Thread(
        target=stop,
        name="Clipwise-oauth-stop",
        daemon=True,
    ).start()


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    server_version = "ClipwiseOAuth/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path != "/oauth/callback":
            self._respond(404, "Ruta no válida.")
            return
        params = parse_qs(parsed.query)
        state = (params.get("state") or [""])[0]
        with _OAUTH_LOCK:
            pending = _PENDING.get(state)
        if pending is None:
            self._respond(
                400,
                "Estado OAuth inválido o caducado. Vuelve a intentarlo desde Clipwise.",
            )
            return
        error = (params.get("error") or [""])[0]
        if error:
            message = (params.get("error_description") or [error])[0]
            _finish_pending(pending, "error", message)
            self._respond(400, f"Autorización cancelada: {message}")
            _request_callback_stop()
            return
        code = (params.get("code") or [""])[0]
        if not code:
            _finish_pending(
                pending, "error", "No se recibió el código de autorización."
            )
            self._respond(400, "No se recibió el código de autorización.")
            _request_callback_stop()
            return
        pending.status = "exchanging"
        try:
            if pending.platform == "youtube":
                account = _exchange_youtube_code(code, pending.redirect_uri)
            else:
                account = _exchange_tiktok_code(code, pending.redirect_uri)
        except Exception as exc:
            logger.exception("Fallo al canjear el código OAuth.")
            _finish_pending(pending, "error", str(exc))
            self._respond(400, f"No se pudo completar la conexión: {exc}")
        else:
            label = (
                account.get("account_name")
                or account.get("account_id")
                or _PLATFORM_NAMES[pending.platform]
            )
            _finish_pending(pending, "success", f"Conectado como {label}.")
            self._respond(
                200,
                "Clipwise conectado. Ya puedes cerrar esta ventana y volver a la app.",
            )
        finally:
            _request_callback_stop()

    def _respond(self, status: int, message: str) -> None:
        body = (
            "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Clipwise</title></head>"
            "<body style=\"margin:0;min-height:100vh;display:grid;place-items:center;"
            "background:#0a0b11;color:#e4e4e7;font-family:system-ui,-apple-system,"
            "Segoe UI,sans-serif\">"
            "<div style=\"width:min(430px,calc(100vw - 40px));padding:30px;"
            "border:1px solid #27272a;border-radius:20px;background:#111118;"
            "text-align:center;box-shadow:0 30px 80px rgba(0,0,0,.45)\">"
            "<div style=\"width:42px;height:42px;margin:0 auto 14px;border-radius:14px;"
            "background:linear-gradient(135deg,#8b5cf6,#22d3ee);display:grid;"
            "place-items:center;font-size:18px\">CF</div>"
            "<h1 style=\"margin:0 0 10px;font-size:18px;letter-spacing:-.02em\">"
            "Clipwise</h1>"
            f"<p style=\"margin:0;font-size:13px;line-height:1.65;color:#a1a1aa\">"
            f"{html.escape(message)}</p>"
            "<p style=\"margin:18px 0 0;font-size:11px;color:#52525b\">"
            "Puedes cerrar esta pestaña.</p></div></body></html>"
        )
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except OSError:
            pass

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("OAuth callback: " + format, *args)


def _ensure_callback_server(cfg: PublishingSettings) -> None:
    global _CALLBACK_SERVER
    with _OAUTH_LOCK:
        if _CALLBACK_SERVER is not None:
            return
        try:
            server = ThreadingHTTPServer(
                (cfg.redirect_host, cfg.redirect_port),
                _OAuthCallbackHandler,
            )
        except OSError as exc:
            raise PublishingError(
                f"No se pudo abrir el puerto {cfg.redirect_port} para la conexión "
                "OAuth. Cierra la app que lo esté usando o cambia el puerto en "
                "Ajustes de publicación.",
                code="oauth_port_busy",
                status_code=409,
            ) from exc
        server.daemon_threads = True
        thread = threading.Thread(
            target=server.serve_forever,
            name="Clipwise-oauth-callback",
            daemon=True,
        )
        thread.start()
        _CALLBACK_SERVER = server


def start_oauth(platform: str) -> dict[str, Any]:
    if platform not in _PLATFORM_NAMES:
        raise PublishingError("Plataforma no soportada.")
    cfg = load_publishing_settings()
    if platform == "youtube" and not (
        cfg.youtube_client_id and cfg.youtube_client_secret
    ):
        raise PublishingError(
            "Configura el Client ID y el Client Secret de YouTube en Ajustes "
            "de publicación.",
            code="not_configured",
            status_code=400,
        )
    if platform == "tiktok" and not (
        cfg.tiktok_client_key and cfg.tiktok_client_secret
    ):
        raise PublishingError(
            "Configura el Client Key y el Client Secret de TikTok en Ajustes "
            "de publicación.",
            code="not_configured",
            status_code=400,
        )
    state = secrets.token_urlsafe(24)
    redirect_uri = _redirect_uri(cfg)
    pending = OAuthPending(
        platform=platform,
        state=state,
        redirect_uri=redirect_uri,
    )
    with _OAUTH_LOCK:
        _prune_pending()
        _PENDING[state] = pending
    try:
        if os.getenv("CLIPFORGE_TEAM_ENGINE") != "1":
            _ensure_callback_server(cfg)
    except PublishingError:
        with _OAUTH_LOCK:
            _PENDING.pop(state, None)
        raise

    if platform == "youtube":
        auth_url = YOUTUBE_AUTH_URL + "?" + urlencode(
            {
                "client_id": cfg.youtube_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": YOUTUBE_SCOPE,
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
                "state": state,
            }
        )
    else:
        auth_url = TIKTOK_AUTH_URL + "?" + urlencode(
            {
                "client_key": cfg.tiktok_client_key,
                "scope": TIKTOK_SCOPE,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "state": state,
            }
        )

    opened = False
    try:
        opened = os.getenv("CLIPFORGE_TEAM_ENGINE") != "1" and bool(webbrowser.open(auth_url))
    except Exception:
        logger.warning("No se pudo abrir el navegador para OAuth.", exc_info=True)
    return {
        "platform": platform,
        "state": state,
        "auth_url": auth_url,
        "redirect_uri": redirect_uri,
        "browser_opened": opened,
    }


def hosted_callback(state: str, code: str, error: str) -> str:
    if os.getenv("CLIPFORGE_TEAM_ENGINE") != "1":
        raise PublishingError("Ruta no disponible.", status_code=404)
    with _OAUTH_LOCK:
        _prune_pending()
        pending = _PENDING.get(state)
        if not pending or pending.status != "pending":
            raise PublishingError("La autorización ha caducado o ya se completó.")
        pending.status = "exchanging"
    if error or not code:
        _finish_pending(pending, "error", "La autorización fue cancelada.")
        raise PublishingError("La autorización fue cancelada.")
    try:
        exchange = _exchange_youtube_code if pending.platform == "youtube" else _exchange_tiktok_code
        exchange(code, pending.redirect_uri)
    except Exception:
        _finish_pending(pending, "error", "La plataforma no pudo verificar el código.")
        raise PublishingError("La plataforma no pudo verificar el código.")
    _finish_pending(pending, "success", "Cuenta conectada.")
    return "Cuenta conectada. Puedes cerrar esta pestaña y volver a Clipwise."


def oauth_status(platform: str, state: str) -> dict[str, Any]:
    if platform not in _PLATFORM_NAMES:
        raise PublishingError("Plataforma no soportada.")
    with _OAUTH_LOCK:
        _prune_pending()
        pending = _PENDING.get(state)
        if pending is None:
            raise PublishingError(
                "Estado OAuth no encontrado o caducado. Vuelve a conectar la cuenta.",
                code="oauth_state_missing",
                status_code=404,
            )
        if pending.platform != platform:
            raise PublishingError(
                "El estado OAuth pertenece a otra plataforma.",
                code="oauth_state_mismatch",
                status_code=400,
            )
        status = pending.status
        message = pending.message
    return {
        "platform": platform,
        "state": state,
        "status": status,
        "message": message,
        "connected": status == "success",
        "account": public_account(platform) if status == "success" else None,
    }


def disconnect(platform: str) -> dict[str, Any]:
    if platform not in _PLATFORM_NAMES:
        raise PublishingError("Plataforma no soportada.")
    db.delete_publishing_account(platform)
    return {"platform": platform, "connected": False}


def _update_record(
    record_id: str,
    *,
    status: str | None = None,
    progress: float | None = None,
    remote_id: str | None = None,
    remote_url: str | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    record = db.get_publish_record(record_id)
    if not record:
        return
    values = dict(record.get("metadata") or {})
    if metadata:
        values.update(metadata)
    if progress is not None:
        values["progress"] = max(0.0, min(100.0, round(float(progress), 2)))
    fields: dict[str, Any] = {"metadata": values}
    if status is not None:
        fields["status"] = status
    if remote_id is not None:
        fields["remote_id"] = remote_id
    if remote_url is not None:
        fields["remote_url"] = remote_url
    if error is not None:
        fields["error"] = _truncate(error, 900)
    db.update_publish_record(record_id, **fields)


def _fail_record(record_id: str, message: str) -> None:
    _update_record(record_id, status="failed", error=message)


def _upload_youtube(
    record_id: str,
    video_path: Path,
    clip: dict[str, Any],
    job: dict[str, Any],
) -> None:
    token = _access_token("youtube")
    cfg = load_publishing_settings()
    size = video_path.stat().st_size
    body = {
        "snippet": {
            "title": _youtube_title(clip),
            "description": _youtube_description(clip),
            "tags": _youtube_tags(clip, job),
            "categoryId": _youtube_category_id(clip, job),
        },
        "status": {
            "privacyStatus": cfg.youtube_privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    init = requests.post(
        f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        },
        timeout=60,
    )
    _raise_http(init, "YouTube rechazó la creación del video")
    upload_url = init.headers.get("Location")
    if not upload_url:
        raise PublishingError(
            "YouTube no devolvió la URL de subida.",
            code="platform_error",
            status_code=502,
        )
    _update_record(
        record_id,
        status="uploading",
        progress=0,
        metadata={"remote_state": "uploading"},
    )
    with video_path.open("rb") as handle:
        offset = 0
        while offset < size:
            chunk = handle.read(YOUTUBE_UPLOAD_CHUNK)
            if not chunk:
                break
            end = offset + len(chunk) - 1
            response = requests.put(
                upload_url,
                data=chunk,
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {offset}-{end}/{size}",
                },
                timeout=300,
            )
            if response.status_code in {200, 201}:
                payload = _json_or_empty(response)
                video_id = str(payload.get("id") or "")
                if not video_id:
                    raise PublishingError(
                        "YouTube terminó la subida sin devolver el ID del video.",
                        code="platform_error",
                        status_code=502,
                    )
                _update_record(
                    record_id,
                    status="published",
                    progress=100,
                    remote_id=video_id,
                    remote_url=f"https://youtube.com/shorts/{video_id}",
                    metadata={
                        "remote_state": "published",
                        "privacy": cfg.youtube_privacy,
                        "video_id": video_id,
                    },
                )
                return
            if response.status_code == 308:
                next_offset = end + 1
                range_header = response.headers.get("Range")
                if range_header:
                    try:
                        next_offset = int(range_header.rsplit("-", 1)[-1]) + 1
                    except ValueError:
                        next_offset = end + 1
                offset = max(end + 1, min(size, next_offset))
                _update_record(
                    record_id,
                    status="uploading",
                    progress=(offset / size) * 100,
                )
                continue
            _raise_http(response, "YouTube rechazó un fragmento de la subida")
    raise PublishingError(
        "YouTube no confirmó la subida completa del video.",
        code="platform_error",
        status_code=502,
    )


def _tiktok_chunk_plan(size: int) -> tuple[int, int]:
    if size <= TIKTOK_UPLOAD_CHUNK:
        return max(1, size), 1
    return TIKTOK_UPLOAD_CHUNK, math.ceil(size / TIKTOK_UPLOAD_CHUNK)


def _upload_tiktok(
    record_id: str,
    video_path: Path,
    clip: dict[str, Any],
    job: dict[str, Any],
) -> None:
    del job
    token = _access_token("tiktok")
    cfg = load_publishing_settings()
    size = video_path.stat().st_size
    chunk_size, total_chunks = _tiktok_chunk_plan(size)
    init = requests.post(
        TIKTOK_INIT_URL,
        json={
            "post_info": {
                "title": _clip_caption(clip),
                "privacy_level": cfg.tiktok_privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=60,
    )
    payload = _check_tiktok_response(init, "TikTok rechazó la publicación")
    data = payload.get("data") or {}
    publish_id = str(data.get("publish_id") or "")
    upload_url = str(data.get("upload_url") or "")
    if not publish_id or not upload_url:
        raise PublishingError(
            "TikTok no devolvió la URL de subida.",
            code="platform_error",
            status_code=502,
        )
    _update_record(
        record_id,
        status="uploading",
        progress=0,
        metadata={"remote_state": "uploading", "publish_id": publish_id},
    )
    with video_path.open("rb") as handle:
        offset = 0
        while offset < size:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            end = offset + len(chunk) - 1
            response = requests.put(
                upload_url,
                data=chunk,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{end}/{size}",
                },
                timeout=300,
            )
            if response.status_code not in {200, 201, 204}:
                _raise_http(
                    response, "TikTok rechazó un fragmento de la subida"
                )
            offset = end + 1
            _update_record(
                record_id,
                status="uploading",
                progress=(offset / size) * 100,
            )
    _update_record(
        record_id,
        status="processing",
        progress=100,
        metadata={"remote_state": "processing", "publish_id": publish_id},
    )
    deadline = time.monotonic() + TIKTOK_STATUS_TIMEOUT
    last_status = ""
    while time.monotonic() < deadline:
        response = requests.post(
            TIKTOK_STATUS_URL,
            json={"publish_id": publish_id},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            timeout=30,
        )
        payload = _check_tiktok_response(
            response, "TikTok no pudo consultar el estado"
        )
        data = payload.get("data") or {}
        status = str(data.get("status") or "").upper()
        if status:
            last_status = status
        if status == "PUBLISH_COMPLETE":
            post_ids = (
                data.get("publicaly_available_post_id")
                or data.get("publicly_available_post_id")
                or []
            )
            remote_id = ""
            if isinstance(post_ids, list) and post_ids:
                remote_id = str(post_ids[0])
            elif isinstance(post_ids, str):
                remote_id = post_ids
            remote_id = remote_id or str(data.get("publish_id") or publish_id)
            _update_record(
                record_id,
                status="published",
                progress=100,
                remote_id=remote_id,
                remote_url=(
                    f"https://www.tiktok.com/@me/video/{remote_id}"
                    if remote_id
                    else "https://www.tiktok.com/"
                ),
                metadata={
                    "remote_state": "published",
                    "publish_id": publish_id,
                    "privacy": cfg.tiktok_privacy,
                },
            )
            return
        if status == "SEND_TO_USER_INBOX":
            raise PublishingError(
                "TikTok envió el video a tu bandeja de entrada en lugar de "
                "publicarlo. Ábrelo en TikTok para publicarlo.",
                code="tiktok_inbox",
                status_code=409,
            )
        if status in {"FAILED", "CANCELLED"}:
            reason = data.get("fail_reason") or status
            raise PublishingError(
                f"TikTok rechazó el video: {reason}",
                code="platform_error",
                status_code=502,
            )
        time.sleep(3)
    raise PublishingError(
        "TikTok no confirmó la publicación a tiempo "
        f"(último estado: {last_status or 'desconocido'}). "
        "Revisa tu cuenta antes de reintentar.",
        code="platform_timeout",
        status_code=504,
    )


def _publish_worker(record_id: str, clip_id: str, platform: str) -> None:
    try:
        clip = db.get_clip(clip_id)
        if not clip:
            raise PublishingError("Clip no encontrado.", status_code=404)
        job = db.get_job(clip["job_id"])
        if not job:
            raise PublishingError("Trabajo no encontrado.", status_code=404)
        if clip.get("status") != "ready":
            raise PublishingError(
                "El clip todavía no está listo para publicarse.",
                code="clip_not_ready",
                status_code=409,
            )
        video_path = _clip_video_path(clip)
        _update_record(record_id, status="uploading", progress=0)
        if platform == "youtube":
            _upload_youtube(record_id, video_path, clip, job)
        elif platform == "tiktok":
            _upload_tiktok(record_id, video_path, clip, job)
        else:
            raise PublishingError("Plataforma no soportada.")
    except PublishingError as exc:
        _fail_record(record_id, str(exc))
    except Exception as exc:
        logger.exception(
            "Fallo inesperado al publicar el clip %s en %s.", clip_id, platform
        )
        _fail_record(record_id, f"Error inesperado: {exc}")


def publish_clip(clip_id: str, platform: str) -> dict[str, Any]:
    if platform not in _PLATFORM_NAMES:
        raise PublishingError("Plataforma no soportada.")
    clip = db.get_clip(clip_id)
    if not clip:
        raise PublishingError("Clip no encontrado.", status_code=404)
    if clip.get("status") != "ready":
        raise PublishingError(
            "El clip todavía no está listo para publicarse.",
            code="clip_not_ready",
            status_code=409,
        )
    _clip_video_path(clip)
    if not db.get_publishing_account(platform):
        raise PublishingError(
            f"Conecta tu cuenta de {_PLATFORM_NAMES[platform]} antes de publicar.",
            code="not_connected",
            status_code=409,
        )
    active = db.active_publish_record(clip_id, platform)
    if active:
        raise PublishingError(
            "Ya hay una publicación en curso para este clip en esta plataforma.",
            code="publish_in_progress",
            status_code=409,
        )
    record = db.add_publish_record(
        clip_id=clip_id,
        platform=platform,
        status="queued",
        metadata={
            "progress": 0,
            "title": (
                _youtube_title(clip)
                if platform == "youtube"
                else _clip_caption(clip)[:160]
            ),
            "clip_title": _one_line(clip.get("title"), 160),
        },
    )
    threading.Thread(
        target=_publish_worker,
        args=(record["id"], clip_id, platform),
        name=f"Clipwise-publish-{platform}",
        daemon=True,
    ).start()
    return publish_record_out(record)
