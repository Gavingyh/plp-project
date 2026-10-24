"""OpenAI-compatible tool contracts, errors and backend selection; no live calls."""

import copy
import json

import pytest

from chatbot.backends import get_backend
from chatbot.backends._openai_compat import to_openai_function_tools
from chatbot.backends.openai_backend import OpenAIBackend
from chatbot.tools import TOOL_SCHEMAS


class _FakePost:
    """Replays canned responses in sequence, recording every request made."""

    def __init__(self, responses, status_code=200):
        self._responses = list(responses)
        self._status_code = status_code
        self.requests = []

    def __call__(self, url, params=None, headers=None, json=None, timeout=None):
        # Deep-copy the payload, as `requests` serialises it at call time: both
        # backends keep appending to the same `contents`/`messages` list, so a
        # stored reference would show a later state than the one sent.
        self.requests.append({"url": url, "params": params, "headers": headers,
                               "json": copy.deepcopy(json)})
        payload = self._responses.pop(0)

        class _Resp:
            status_code = self._status_code
            text = "fake error body"

            def json(_self):
                return payload

            def raise_for_status(_self):
                pass

        return _Resp()


# ---------------------------------------------------------------------------
# Shared OpenAI-compatible tool schema conversion
# ---------------------------------------------------------------------------

def test_to_openai_function_tools_shape():
    tools = to_openai_function_tools(TOOL_SCHEMAS)
    sample = next(t for t in tools if t["function"]["name"] == "get_sentiment")
    assert sample["type"] == "function"
    assert sample["function"]["parameters"]["type"] == "object"


# ---------------------------------------------------------------------------
# OpenAI backend
# ---------------------------------------------------------------------------

def test_openai_backend_requires_key():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY not set"):
        OpenAIBackend(api_key="")


# Written from OpenAI's documented Chat Completions contract - NOT a pinned
# real response (no key available). The one detail this test exists to
# guard is real and important: `arguments` is a JSON STRING here, unlike
# Ollama's pre-parsed dict.
_OPENAI_TOOL_CALL_RESPONSE = {
    "choices": [{
        "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "call_abc123", "type": "function",
                "function": {"name": "get_sentiment",
                             "arguments": '{"bank": "DBS", "aspect": "dividend_policy"}'},
            }],
        },
    }],
}
_OPENAI_FINAL_ANSWER_RESPONSE = {
    "choices": [{"message": {"role": "assistant",
                              "content": "The sentiment for DBS is neutral."}}],
}


def test_openai_backend_parses_json_string_arguments(monkeypatch):
    fake_post = _FakePost([_OPENAI_TOOL_CALL_RESPONSE, _OPENAI_FINAL_ANSWER_RESPONSE])
    monkeypatch.setattr("requests.post", fake_post)

    calls = []

    def tool_executor(name, args):
        calls.append((name, args))
        return json.dumps({"score": 0.006})

    backend = OpenAIBackend(api_key="fake-key")
    answer = backend.ask("q", "system", TOOL_SCHEMAS, tool_executor, verbose=False)

    assert answer == "The sentiment for DBS is neutral."
    # arguments must have been parsed from a JSON string into a real dict
    assert calls == [("get_sentiment", {"bank": "DBS", "aspect": "dividend_policy"})]
    # auth header must be present on every request
    assert fake_post.requests[0]["headers"]["Authorization"] == "Bearer fake-key"
    # tool result must go back as role="tool" with the matching tool_call_id
    second_messages = fake_post.requests[1]["json"]["messages"]
    tool_msg = next(m for m in second_messages if m.get("role") == "tool")
    assert tool_msg["tool_call_id"] == "call_abc123"


def test_openai_backend_401_gives_clear_error(monkeypatch):
    monkeypatch.setattr("requests.post", _FakePost([{}], status_code=401))
    backend = OpenAIBackend(api_key="bad-key")
    with pytest.raises(RuntimeError, match="rejected the key"):
        backend.ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)


def test_openai_backend_uses_a_compatible_providers_base_url(monkeypatch):
    fake_post = _FakePost([_OPENAI_FINAL_ANSWER_RESPONSE])
    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1/")
    monkeypatch.setenv("OPENAI_MODEL", "openai/gpt-oss-120b")
    backend = get_backend("openai")
    backend.ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)
    assert fake_post.requests[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert fake_post.requests[0]["json"]["model"] == "openai/gpt-oss-120b"


def test_openai_backend_defaults_to_openai(monkeypatch):
    fake_post = _FakePost([_OPENAI_FINAL_ANSWER_RESPONSE])
    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    get_backend("openai").ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)
    assert fake_post.requests[0]["url"] == "https://api.openai.com/v1/chat/completions"


def test_openai_backend_sends_back_only_standard_message_fields(monkeypatch):
    """A reasoning model's extra fields (Groq's gpt-oss returns `reasoning`) aren't echoed back."""
    with_reasoning = copy.deepcopy(_OPENAI_TOOL_CALL_RESPONSE)
    with_reasoning["choices"][0]["message"]["reasoning"] = "I should call get_sentiment."
    fake_post = _FakePost([with_reasoning, _OPENAI_FINAL_ANSWER_RESPONSE])
    monkeypatch.setattr("requests.post", fake_post)
    OpenAIBackend(api_key="k").ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)
    assistant = next(m for m in fake_post.requests[1]["json"]["messages"] if m["role"] == "assistant")
    assert set(assistant) == {"role", "content", "tool_calls"} and assistant["content"] == ""


def test_openai_backend_waits_out_a_rate_limit(monkeypatch):
    fake_post = _FakePost([_OPENAI_FINAL_ANSWER_RESPONSE])
    statuses = iter([429, 503, 200])
    waits = []

    class _Limited:
        text = "rate limited"

        def __init__(self, code, headers):
            self.status_code, self.headers = code, headers

    def flaky_post(url, **kwargs):
        code = next(statuses)
        if code == 429:
            return _Limited(429, {"retry-after": "7"})
        if code == 503:
            return _Limited(503, {})
        return fake_post(url, **kwargs)

    monkeypatch.setattr("requests.post", flaky_post)
    monkeypatch.setattr("chatbot.backends.openai_backend.time.sleep", waits.append)
    answer = OpenAIBackend(api_key="k").ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)
    assert answer == "The sentiment for DBS is neutral."
    assert waits == [7.0, 15]                        # Retry-After when given, else the second default


def test_openai_backend_400_includes_error_body(monkeypatch):
    monkeypatch.setattr("requests.post", _FakePost([{}], status_code=400))
    with pytest.raises(RuntimeError, match="fake error body"):
        OpenAIBackend(api_key="k").ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)


# ---------------------------------------------------------------------------

def test_auto_detect_uses_openai_when_its_key_is_present(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CHATBOT_BACKEND", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    assert isinstance(get_backend(), OpenAIBackend)


def test_auto_detect_without_keys_uses_ollama(monkeypatch):
    from chatbot.backends.ollama_backend import OllamaBackend
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CHATBOT_BACKEND", "auto")
    assert isinstance(get_backend(), OllamaBackend)


def test_the_default_is_openai_when_backend_is_unset(monkeypatch):
    monkeypatch.delenv("CHATBOT_BACKEND", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    backend = get_backend()
    assert isinstance(backend, OpenAIBackend)


def test_explicit_backend_overrides_auto_detection(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("CHATBOT_BACKEND", "auto")
    assert isinstance(get_backend("openai"), OpenAIBackend)
