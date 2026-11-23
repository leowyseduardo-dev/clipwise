import json
import os
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import ai, main


class Settings(SimpleNamespace):
    @property
    def llm_enabled(self):
        return bool(self.llm_api_key)


@pytest.fixture(autouse=True)
def isolated_ai(monkeypatch, tmp_path):
    monkeypatch.setattr(ai, "settings", Settings(data_dir=tmp_path, llm_base_url="", llm_model="",
                                               llm_api_key="", llm_timeout=10))
    monkeypatch.setattr(ai, "_provider", "heuristic")
    monkeypatch.setattr(ai, "_last_error", "")
    monkeypatch.setattr(ai, "_cooldown_until", 0)
    monkeypatch.setattr(ai, "_cache", ai.OrderedDict())


def configure(provider="openrouter", **kwargs):
    return ai.save_settings({"provider": provider, "api_key": "private-test-key", **kwargs})


def transport(monkeypatch, replies):
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            calls.append((url, json.loads(json.dumps(kwargs))))
            return replies.pop(0)
    monkeypatch.setattr(ai.httpx, "Client", Client)
    return calls


def reply(content='{"ok": true}'):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_saved_key_is_never_returned_and_survives_restart():
    public = configure()
    assert public["key_set"] and public["enabled"]
    assert "private-test-key" not in json.dumps(public)
    saved = ai._path().read_text()
    if os.name == "nt":
        assert "private-test-key" not in saved and json.loads(saved)["protected"]
    ai._apply("heuristic", "", "", "")
    ai.load_settings()
    assert ai.settings.llm_api_key == "private-test-key"
    assert ai.public_settings()["provider"] == "openrouter"


def test_key_cannot_leak_to_another_provider_or_custom_endpoint():
    configure()
    with pytest.raises(ValueError, match="clave"):
        ai.save_settings({"provider": "gemini"})
    assert ai.public_settings()["provider"] == "openrouter"
    configure("custom", base_url="https://example.com/v1", model="test")
    with pytest.raises(ValueError, match="clave"):
        ai.save_settings({"provider": "custom", "base_url": "https://another.example/v1", "model": "test"})


@pytest.mark.parametrize("model", ["paid/model", "openrouter/auto", "vendor/model:paid"])
def test_openrouter_rejects_paid_models(model):
    with pytest.raises(ValueError, match="solo se admiten"):
        configure(model=model)


def test_local_and_key_deletion_disable_cloud_calls():
    configure()
    public = ai.save_settings({"provider": "openrouter", "clear_key": True})
    assert not public["enabled"] and not public["key_set"]
    assert not ai.test_connection()["ok"]
    ai.save_settings({"provider": "heuristic"})
    assert ai.test_connection()["ok"]


def test_ollama_needs_no_key_and_uses_local_endpoint(monkeypatch):
    public = ai.save_settings({"provider": "ollama"})
    assert public["enabled"] and not public["key_set"]
    assert ai.settings.llm_base_url == "http://127.0.0.1:11434/v1"
    calls = transport(monkeypatch, [reply()])
    assert ai.test_connection()["ok"]
    assert calls[0][1]["json"]["reasoning_effort"] == "none"
    with pytest.raises(ValueError, match="local"):
        ai.save_settings({"provider": "ollama", "model": "model:cloud"})


@pytest.mark.parametrize("url", ["http://remote.example/v1", "https://key@remote.example/v1", "https://example.com/v1?key=secret"])
def test_bad_endpoints_rejected(url):
    with pytest.raises(ValueError):
        configure("custom", base_url=url, model="test")


def test_quota_error_stops_further_calls_and_does_not_fall_back_to_paid(monkeypatch):
    configure()
    calls = transport(monkeypatch, [httpx.Response(429, headers={"retry-after": "120"})])
    assert ai.complete_json([{"role": "user", "content": "JSON uno"}]) is None
    assert ai.complete_json([{"role": "user", "content": "JSON dos"}]) is None
    assert len(calls) == 1 and ai.public_settings()["retry_after"] > 100
    assert "local" in ai.public_settings()["last_error"]
    assert calls[0][1]["json"]["model"] == "openrouter/free"
    assert "models" not in calls[0][1]["json"]


def test_successful_result_cached_and_probe_always_connects(monkeypatch):
    configure()
    calls = transport(monkeypatch, [reply(), reply()])
    messages = [{"role": "user", "content": "Return JSON"}]
    result = ai.complete_json(messages)
    result["ok"] = False
    assert ai.complete_json(messages) == {"ok": True}
    assert ai.test_connection()["ok"]
    assert len(calls) == 2


def test_unsupported_json_mode_retries_once(monkeypatch):
    configure("gemini")
    calls = transport(monkeypatch, [httpx.Response(400), reply()])
    assert ai.test_connection()["ok"]
    assert "response_format" in calls[0][1]["json"]
    assert "response_format" not in calls[1][1]["json"]
    assert calls[0][0].startswith("https://generativelanguage.googleapis.com/")


@pytest.mark.parametrize("response", [httpx.Response(401), httpx.Response(503), reply("not JSON"),
                                    httpx.Response(200, json={"choices": []}), reply(None)])
def test_provider_errors_are_actionable_and_do_not_expose_secrets(monkeypatch, response):
    configure()
    transport(monkeypatch, [response])
    result = ai.test_connection()
    assert not result["ok"] and result["message"]
    assert "private-test-key" not in json.dumps(result)


def test_api_masks_key_and_rejects_unknown_provider():
    client = TestClient(main.app)
    response = client.put("/api/ai/settings", json={"provider": "openrouter", "api_key": "private-test-key"})
    assert response.status_code == 200 and response.json()["enabled"]
    assert "private-test-key" not in response.text
    assert "private-test-key" not in client.get("/api/ai/settings").text
    assert client.put("/api/ai/settings", json={"provider": "unknown"}).status_code == 422
    assert client.put("/api/ai/settings", json={"provider": "openrouter", "model": "paid"}).status_code == 400
