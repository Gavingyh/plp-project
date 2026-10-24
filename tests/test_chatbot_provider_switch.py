"""Provider selection, costs metadata and real request contracts; no live calls."""

import json
from unittest.mock import patch

import pytest
import requests
from fastapi.testclient import TestClient

from api.main import app
from chatbot.agent import answer_turn
from chatbot.backends import get_backend
from chatbot.backends.base import BackendUnavailable
from chatbot.backends.openai_backend import OpenAIBackend
from chatbot.ratelimit import DailyBudgetExhausted


def response(payload, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    return result


@pytest.mark.parametrize("name,backend_class,model", [
    ("openai", OpenAIBackend, "gpt-6-luna"),
])
def test_server_environment_selects_provider_without_frontend_changes(monkeypatch, name, backend_class, model):
    monkeypatch.setenv("CHATBOT_BACKEND", name)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    for key in ("OPENAI_MODEL",):
        monkeypatch.delenv(key, raising=False)
    with patch("requests.post") as post:
        backend = get_backend()
    assert isinstance(backend, backend_class) and backend.model == model
    assert not post.called


def test_missing_selected_key_does_not_fall_back_to_another_provider(monkeypatch):
    monkeypatch.setenv("CHATBOT_BACKEND", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-other-key")
    with patch("requests.post") as post, pytest.raises(BackendUnavailable, match="OPENAI_API_KEY"):
        get_backend()
    assert not post.called


@pytest.mark.parametrize("name", ["openai"])
def test_chat_uses_server_setting_when_frontend_omits_backend(monkeypatch, name):
    monkeypatch.setenv("CHATBOT_BACKEND", name)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-secret")
    monkeypatch.setattr("chatbot.agent.get_backend", get_backend)
    payload = {"choices": [{"message": {"content": "I can help with bank sentiment."}}]}
    with patch("requests.post", return_value=response(payload)) as post:
        result = TestClient(app).post("/chat", json={"message": "DBS?", "history": []})
    assert result.status_code == 200 and result.json()["provider"] == name
    assert "secret" not in result.text
    assert post.call_count == 1
    headers = post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-openai-secret"


def test_local_quota_limit_returns_service_error_not_internal_error(monkeypatch):
    class LimitedConversation:
        @classmethod
        def from_messages(cls, *args, **kwargs):
            return cls()

        def ask(self, question):
            raise DailyBudgetExhausted("OpenAI daily request budget reached")

    monkeypatch.setattr("api.main.Conversation", LimitedConversation)
    result = TestClient(app).post("/chat", json={"message": "DBS?", "backend": "openai"})
    assert result.status_code == 503 and "budget" in result.json()["detail"]["message"]


def test_luna_request_has_supported_tool_parameters_and_usage_accumulates(monkeypatch):
    payloads = []
    replies = [
        {"usage": {"prompt_tokens": 100, "completion_tokens": 12,
                   "prompt_tokens_details": {"cached_tokens": 20}},
         "choices": [{"message": {"content": None, "tool_calls": [{
             "id": "call1", "type": "function", "function": {"name": "get_sentiment", "arguments": '{"bank":"DBS"}'},
         }]}}]},
        {"usage": {"prompt_tokens": 150, "completion_tokens": 30},
         "choices": [{"message": {"content": "Slightly positive."}}]},
    ]

    def post(url, **kwargs):
        payloads.append(kwargs["json"].copy())
        return response(replies.pop(0))

    monkeypatch.setattr("requests.post", post)
    backend = OpenAIBackend("test-key", model="gpt-6-luna")
    assert backend.ask("DBS?", "system", [], lambda n, a: '{"score":0.1}', verbose=False) == "Slightly positive."
    assert all(p["reasoning_effort"] == "none" and p["max_completion_tokens"] == 1024 for p in payloads)
    assert backend.usage == {"requests": 2, "input_tokens": 250, "output_tokens": 42,
                             "cached_input_tokens": 20, "complete": True}


@pytest.mark.parametrize("backend_class,module", [(OpenAIBackend, "openai_backend")])
def test_remote_quota_errors_are_actionable_without_switching_provider(monkeypatch, backend_class, module):
    monkeypatch.setattr(f"chatbot.backends.{module}._RETRY_WAITS", ())
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: response({}, 429))
    with pytest.raises(BackendUnavailable, match="quota or rate limit"):
        backend_class("test-key").ask("DBS?", "s", [], lambda n, a: "{}", verbose=False)


def test_missing_usage_is_not_claimed_to_be_a_free_response(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: response({"choices": [{"message": {"content": "Answer"}}]}))
    backend = OpenAIBackend("test-key")
    backend.ask("q", "s", [], lambda n, a: "{}", verbose=False)
    assert backend.usage["complete"] is False


@pytest.mark.parametrize("backend_class", [OpenAIBackend])
def test_bad_request_details_redact_the_key(monkeypatch, backend_class):
    secret = "test-key-to-keep-private"
    monkeypatch.setattr("requests.post", lambda *a, **k: response({"error": f"Invalid key '{secret}'"}, 400))
    with pytest.raises(BackendUnavailable) as exc:
        backend_class(secret).ask("q", "s", [], lambda n, a: "{}", verbose=False)
    assert secret not in str(exc.value) and "[redacted]" in str(exc.value)


def test_turn_and_api_include_actual_provider_model_and_reported_usage(monkeypatch):
    backend = OpenAIBackend("test-key", model="gpt-6-luna")
    monkeypatch.setattr("requests.post", lambda *a, **k: response({
        "choices": [{"message": {"content": "I can help with bank sentiment."}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10},
    }))
    turn = answer_turn("DBS?", backend=backend, verbose=False)
    assert turn.provider == "openai" and turn.model == "gpt-6-luna"
    assert turn.usage["input_tokens"] == 100

    class FakeConversation:
        @classmethod
        def from_messages(cls, *args, **kwargs):
            return cls()

        def ask(self, message):
            return turn

    monkeypatch.setattr("api.main.Conversation", FakeConversation)
    payload = TestClient(app).post("/chat", json={"message": "DBS?", "backend": "openai"}).json()
    assert payload["provider"] == "openai" and payload["usage"]["output_tokens"] == 10
