"""Configuration and service failures across the API boundary; no live inference."""

import json
from unittest.mock import patch

import pytest
import requests
from fastapi.testclient import TestClient

from api.main import app
from chatbot.backends import get_backend
from chatbot.backends.base import BackendUnavailable
from chatbot.backends.ollama_backend import OllamaBackend
from chatbot.backends.openai_backend import OpenAIBackend


def response(status, payload):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    return result


@pytest.mark.parametrize("selection", [None, "", "   "])
@pytest.mark.parametrize("key", [None, "", "   "])
def test_default_requires_openai_key_without_falling_back(monkeypatch, selection, key):
    for name, value in (("CHATBOT_BACKEND", selection), ("OPENAI_API_KEY", key)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "another-provider-is-not-a-fallback")
    with patch("requests.post") as post, patch("requests.get") as get:
        result = TestClient(app).get("/chat/status")
        with pytest.raises(BackendUnavailable):
            get_backend()
    assert result.status_code == 200
    status = result.json()
    assert status["configured"] is False
    assert status["problem"]["code"] == "openai_key_missing"
    assert "OPENAI_API_KEY" in status["problem"]["setup_hint"]
    assert "another-provider-is-not-a-fallback" not in result.text
    post.assert_not_called()
    get.assert_not_called()


def test_configured_status_neither_checks_a_key_remotely_nor_returns_it(monkeypatch):
    monkeypatch.delenv("CHATBOT_BACKEND", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", " test-private-key ")
    with patch("requests.post") as post, patch("requests.get") as get:
        assert isinstance(get_backend(), OpenAIBackend)
        result = TestClient(app).get("/chat/status")
    assert result.json() == {"configured": True, "problem": None}
    assert "test-private-key" not in result.text
    post.assert_not_called()
    get.assert_not_called()


def test_explicit_local_backend_works_without_hosted_credentials(monkeypatch):
    monkeypatch.setenv("CHATBOT_BACKEND", "ollama")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch("requests.post") as post, patch("requests.get") as get:
        assert isinstance(get_backend(), OllamaBackend)
        assert TestClient(app).get("/chat/status").json() == {"configured": True, "problem": None}
    post.assert_not_called()
    get.assert_not_called()


def test_missing_key_is_a_safe_service_error_and_does_not_break_other_routes(monkeypatch):
    monkeypatch.delenv("CHATBOT_BACKEND", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("chatbot.agent.get_backend", get_backend)
    with patch("requests.post") as post:
        client = TestClient(app)
        result = client.post("/chat", json={"message": "DBS?"})
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/banks").json() == {"banks": ["DBS", "OCBC", "UOB"]}
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "openai_key_missing"
    assert "not been configured" in result.json()["detail"]["message"]
    post.assert_not_called()


def test_invalid_server_provider_is_configuration_error_not_dashboard_outage(monkeypatch):
    monkeypatch.setenv("CHATBOT_BACKEND", "accidentally-private-value")
    client = TestClient(app)
    result = client.get("/chat/status")
    assert result.json()["problem"]["code"] == "invalid_configuration"
    assert "accidentally-private-value" not in result.text
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("status,error,code,fragment", [
    (401, {}, "openai_key_rejected", "key was rejected"),
    (403, {}, "provider_access_denied", "does not have access"),
    (429, {"code": "insufficient_quota"}, "provider_quota_exhausted", "quota"),
    (429, {"code": "rate_limit_exceeded"}, "provider_rate_limited", "too many requests"),
    (400, {}, "backend_unavailable", "temporarily unavailable"),
])
def test_provider_failures_have_safe_distinct_api_messages(monkeypatch, status, error, code, fragment):
    monkeypatch.setenv("CHATBOT_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    monkeypatch.setattr("chatbot.agent.get_backend", get_backend)
    monkeypatch.setattr("chatbot.backends.openai_backend._RETRY_WAITS", ())
    body = {"error": {**error, "message": "private-test-key and private provider diagnostics"}}
    with patch("requests.post", return_value=response(status, body)) as post:
        result = TestClient(app).post("/chat", json={"message": "DBS?"})
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == code
    assert fragment in result.json()["detail"]["message"]
    assert "private-test-key" not in result.text and "private provider diagnostics" not in result.text
    assert post.call_count == 1


@pytest.mark.parametrize("error,code", [
    (requests.ConnectionError("private connection diagnostic"), "provider_connection_failed"),
    (requests.Timeout("private timeout diagnostic"), "provider_timed_out"),
])
def test_transport_failure_has_readable_message_without_internal_details(monkeypatch, error, code):
    monkeypatch.setenv("CHATBOT_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    monkeypatch.setattr("chatbot.agent.get_backend", get_backend)
    with patch("requests.post", side_effect=error):
        result = TestClient(app).post("/chat", json={"message": "DBS?"})
    assert result.status_code == 503 and result.json()["detail"]["code"] == code
    assert "diagnostic" not in result.text


@pytest.mark.parametrize("error", [
    {"code": "insufficient_quota"},
    {"code": "project_spend_limit_exceeded", "type": "insufficient_quota"},
    {"code": "organization_spend_limit_exceeded"},
])
def test_billing_failures_stop_without_rate_limit_retries(monkeypatch, error):
    monkeypatch.setattr("chatbot.backends.openai_backend._RETRY_WAITS", (5, 15))
    with patch("requests.post", return_value=response(429, {"error": error})) as post, \
            patch("chatbot.backends.openai_backend.time.sleep") as sleep:
        with pytest.raises(BackendUnavailable) as caught:
            OpenAIBackend("test-key").ask("DBS?", "system", [], lambda *_: "{}", verbose=False)
    assert caught.value.code == "provider_quota_exhausted"
    post.assert_called_once()
    sleep.assert_not_called()
