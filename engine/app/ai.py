"""Optional AI providers, private local configuration and bounded failures."""
from __future__ import annotations

import base64
from collections import OrderedDict
from copy import deepcopy
import ctypes
import hashlib
import json
import logging
import os
import threading
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import settings
from . import meter
from .utils import parse_json_object

logger = logging.getLogger(__name__)
PROVIDERS = {
    "heuristic": {"label": "Local · sin API", "base_url": "", "model": "", "key_url": "",
                  "note": "Analiza voz, escenas y transcripción en tu equipo. Sin cuenta ni consumo de API."},
    "openrouter": {"label": "OpenRouter · modelos gratuitos", "base_url": "https://openrouter.ai/api/v1",
                   "model": "openrouter/free", "key_url": "https://openrouter.ai/settings/keys",
                   "note": "Solo modelos gratuitos; cuota limitada y disponibilidad variable. El router puede cambiar de modelo. La transcripción se envía a OpenRouter y al proveedor elegido."},
    "gemini": {"label": "Gemini · cuota gratuita", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "model": "gemini-3.1-flash-lite", "key_url": "https://aistudio.google.com/apikey",
               "note": "Usa un proyecto sin facturación para mantenerte en la cuota gratuita. Google puede usar el contenido del nivel gratuito para mejorar sus productos. La cuota depende de tu cuenta."},
    "ollama": {"label": "Ollama · LLM local", "base_url": "http://127.0.0.1:11434/v1",
               "model": "qwen3.5:2b", "key_url": "https://ollama.com/download",
               "note": "Sin clave ni coste de API. Requiere Ollama abierto y el modelo descargado; usa RAM y espacio de tu equipo."},
    "custom": {"label": "Proveedor compatible / configuración existente", "base_url": "",
               "model": "", "key_url": "", "note": "Introduce tu endpoint y modelo. Se aplican los precios y condiciones de ese proveedor."},
}
_lock = threading.RLock()
_provider = "custom" if settings.llm_enabled else "heuristic"
_last_error = ""
_cooldown_until = 0.0
_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()


def _crypt(raw: bytes, decrypt: bool = False) -> bytes:
    """Windows DPAPI ties saved credentials to the current Windows account."""
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    target = Blob()
    if decrypt:
        ok = ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise OSError("No se pudo proteger o leer la clave de IA de este usuario.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(target.data)


def _path():
    return settings.data_dir / "ai-settings.json"


def load_settings() -> None:
    global _provider
    if not _path().is_file():
        return
    try:
        saved = json.loads(_path().read_text(encoding="utf-8"))
        secret = saved.pop("secret", "")
        if saved.get("provider") == "ollama":
            secret = "ollama"  # Public placeholder used by the OpenAI-compatible client.
        elif saved.pop("protected", False):
            secret = _crypt(base64.b64decode(secret), decrypt=True).decode()
        _apply(saved["provider"], saved["base_url"], saved["model"], secret)
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("No se pudo cargar la configuración de IA; se conserva la configuración del entorno.")


def _apply(provider: str, base_url: str, model: str, secret: str) -> None:
    global _provider, _last_error, _cooldown_until
    with _lock:
        _provider = provider
        settings.llm_base_url = base_url
        settings.llm_model = model
        settings.llm_api_key = secret
        _last_error = ""
        _cooldown_until = 0
        _cache.clear()


def public_settings() -> dict[str, Any]:
    with _lock:
        return {"provider": _provider, "model": settings.llm_model,
                "base_url": settings.llm_base_url, "key_set": bool(settings.llm_api_key) and _provider != "ollama",
                "enabled": settings.llm_enabled, "last_error": _last_error,
                "retry_after": max(0, round(_cooldown_until - time.monotonic())),
                "providers": [{"id": key, **value} for key, value in PROVIDERS.items()]}


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    provider = payload["provider"]
    preset = PROVIDERS[provider]
    model = str(payload.get("model") or preset["model"]).strip()
    base_url = str(preset["base_url"] if provider != "custom" else payload.get("base_url") or "").strip().rstrip("/")
    with _lock:
        # Never carry a key to a different provider or endpoint.
        secret = settings.llm_api_key if provider == _provider and base_url == settings.llm_base_url else ""
        if payload.get("api_key"):
            secret = payload["api_key"].strip()
        if payload.get("clear_key"):
            secret = ""
        if provider == "heuristic":
            model, base_url, secret = "", "", ""
        else:
            parsed = urlparse(base_url)
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("El endpoint no debe contener credenciales, parámetros ni fragmentos.")
            if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
                raise ValueError("Usa HTTPS para una API externa o HTTP en localhost para un modelo local.")
            if not parsed.hostname or not model:
                raise ValueError("Completa el endpoint y el modelo.")
            if provider == "openrouter" and model != "openrouter/free" and not model.endswith(":free"):
                raise ValueError("En OpenRouter solo se admiten openrouter/free o modelos terminados en :free.")
            if provider == "ollama":
                if "cloud" in model.lower():
                    raise ValueError("Selecciona un modelo local de Ollama, sin el sufijo cloud.")
                secret = "ollama"
            elif not secret and not payload.get("clear_key"):
                raise ValueError("Pega tu clave de API para activar este proveedor.")
        protected = provider != "ollama" and os.name == "nt" and bool(secret)
        stored = base64.b64encode(_crypt(secret.encode())).decode() if protected else secret
        data = {"provider": provider, "base_url": base_url, "model": model, "secret": stored, "protected": protected}
        _path().parent.mkdir(parents=True, exist_ok=True)
        temporary = _path().with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        temporary.replace(_path())
        _apply(provider, base_url, model, secret)
        return public_settings()


def _failure(message: str, cooldown: float = 0) -> None:
    global _last_error, _cooldown_until
    with _lock:
        _last_error = message
        _cooldown_until = time.monotonic() + cooldown
    logger.warning("IA: %s", message)


def complete_json(messages: list[dict[str, str]], *, probe: bool = False) -> dict[str, Any] | None:
    global _last_error, _cooldown_until
    with _lock:
        base_url, model, secret = settings.llm_base_url, settings.llm_model, settings.llm_api_key
        quick_review = _provider == "ollama" and model == PROVIDERS["ollama"]["model"]
        if not secret or (not probe and time.monotonic() < _cooldown_until):
            return None
        identity = json.dumps([base_url, model, messages], ensure_ascii=False)
        cache_key = hashlib.sha256(identity.encode()).hexdigest()
        if not probe and cache_key in _cache:
            meter.record(model, cached=1)
            return deepcopy(_cache[cache_key])
    payload = {"model": model, "messages": messages, "temperature": 0.3,
               "max_tokens": 256 if probe else 4096, "response_format": {"type": "json_object"}}
    if quick_review:
        payload["reasoning_effort"] = "none"
    headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
    for attempt in range(2):
        try:
            with httpx.Client(timeout=min(settings.llm_timeout, 90), follow_redirects=False) as client:
                response = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            if response.status_code == 400 and attempt == 0:
                payload.pop("response_format", None)
                continue
            if response.status_code == 429:
                try:
                    delay = max(30, min(3600, float(response.headers.get("retry-after", 60))))
                except ValueError:
                    delay = 60
                _failure("Cuota o límite de solicitudes alcanzado. Se continúa con el análisis local.", delay)
                return None
            if response.status_code in {401, 403}:
                _failure("La API rechazó la clave o el acceso al modelo. Revisa la configuración.", 300)
                return None
            if response.status_code >= 300:
                _failure(f"La API respondió HTTP {response.status_code}. Se conserva el análisis local.", 30)
                return None
            data = response.json()
            if not probe:
                meter.record(model, calls=1, usage=data.get("usage"))
            content = data["choices"][0]["message"]["content"]
            result = parse_json_object(content) if isinstance(content, str) else None
            if not isinstance(result, dict):
                _failure("La IA no devolvió un objeto JSON válido. Se conserva el análisis local.")
                return None
            with _lock:
                if not probe:
                    _cache[cache_key] = deepcopy(result)
                    while len(_cache) > 64:
                        _cache.popitem(last=False)
                _last_error, _cooldown_until = "", 0
            return result
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            _failure("No se pudo conectar con la IA o interpretar su respuesta. Se conserva el análisis local.", 30)
            return None
    return None


def test_connection() -> dict[str, Any]:
    if not settings.llm_enabled:
        return {"ok": _provider == "heuristic", "message": "Modo local activo; no se necesita una API." if _provider == "heuristic" else "Falta configurar la clave de API."}
    response = complete_json([{"role": "user", "content": 'Devuelve únicamente este JSON: {"ok": true}'}], probe=True)
    ok = isinstance(response, dict) and response.get("ok") is True
    return {"ok": ok, "message": "Conexión verificada. La IA devuelve JSON válido." if ok else public_settings()["last_error"] or "La IA respondió con un formato inesperado."}
