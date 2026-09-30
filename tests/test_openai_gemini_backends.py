"""
Tests for the OpenAI and Gemini backends (chatbot/backends/openai_backend.py,
gemini_backend.py).

IMPORTANT DIFFERENCE from tests/test_chatbot_backends.py's Ollama tests:
those are pinned copies of REAL responses from a running Ollama instance.
No OPENAI_API_KEY or GEMINI_API_KEY is available in this dev environment, so
the mocked responses here are written from each provider's DOCUMENTED
contract, not a verified real response. These tests confirm the code
handles that documented shape correctly — they cannot confirm the
documented shape is what the real API actually returns today. See both
backend modules' docstrings for the specific risk areas (Gemini's schema
type-casing in particular).
"""

import copy
import json

import pytest

from chatbot.backends import get_backend
from chatbot.backends._openai_compat import to_openai_function_tools
from chatbot.backends.gemini_backend import GeminiBackend, _uppercase_schema_types
from chatbot.backends.openai_backend import OpenAIBackend
from chatbot.tools import TOOL_SCHEMAS


class _FakePost:
    """Replays canned responses in sequence, recording every request made."""

    def __init__(self, responses, status_code=200):
        self._responses = list(responses)
        self._status_code = status_code
        self.requests = []

    def __call__(self, url, params=None, headers=None, json=None, timeout=None):
        # Snapshot with deepcopy — the real `requests` library serializes the
        # payload to bytes immediately inside post(), so it can never see a
        # caller's later mutations. A live reference here would (and did,
        # before this fix): both backends keep appending to the same
        # `contents`/`messages` list across loop iterations, so without a
        # snapshot this mock would show a later iteration's state instead of
        # what was actually sent at call time.
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


# Written from OpenAI's documented Chat Completions contract — NOT a pinned
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


# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------

def test_gemini_backend_requires_key():
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY not set"):
        GeminiBackend(api_key="")


def test_uppercase_schema_types_recursive():
    # This is the highest-risk conversion in the whole module (see
    # gemini_backend.py docstring) — test it directly and thoroughly.
    schema = {
        "type": "object",
        "properties": {
            "bank": {"type": "string", "enum": ["DBS", "OCBC"]},
            "k": {"type": "integer"},
            "nested": {"type": "object", "properties": {"flag": {"type": "boolean"}}},
        },
    }
    result = _uppercase_schema_types(schema)
    assert result["type"] == "OBJECT"
    assert result["properties"]["bank"]["type"] == "STRING"
    assert result["properties"]["bank"]["enum"] == ["DBS", "OCBC"]  # non-type fields untouched
    assert result["properties"]["k"]["type"] == "INTEGER"
    assert result["properties"]["nested"]["type"] == "OBJECT"
    assert result["properties"]["nested"]["properties"]["flag"]["type"] == "BOOLEAN"


# Written from Google's documented generateContent contract — NOT a pinned
# real response (no key available). See gemini_backend.py docstring for the
# specific parts of this shape that are most likely to be wrong.
_GEMINI_TOOL_CALL_RESPONSE = {
    "candidates": [{
        "content": {"role": "model",
                    "parts": [{"functionCall": {"name": "get_sentiment",
                                                 "args": {"bank": "DBS"}}}]},
    }],
}
_GEMINI_FINAL_ANSWER_RESPONSE = {
    "candidates": [{"content": {"role": "model",
                                 "parts": [{"text": "The sentiment for DBS is neutral."}]}}],
}


def test_gemini_backend_full_loop(monkeypatch):
    fake_post = _FakePost([_GEMINI_TOOL_CALL_RESPONSE, _GEMINI_FINAL_ANSWER_RESPONSE])
    monkeypatch.setattr("requests.post", fake_post)

    calls = []

    def tool_executor(name, args):
        calls.append((name, args))
        return json.dumps({"score": 0.006})

    backend = GeminiBackend(api_key="fake-key")
    answer = backend.ask("q", "system prompt", TOOL_SCHEMAS, tool_executor, verbose=False)

    assert answer == "The sentiment for DBS is neutral."
    assert calls == [("get_sentiment", {"bank": "DBS"})]
    # the key goes in a header, never the URL (requests puts URLs in error messages)
    assert fake_post.requests[0]["headers"] == {"x-goog-api-key": "fake-key"}
    assert not fake_post.requests[0]["params"]
    assert "fake-key" not in fake_post.requests[0]["url"]
    # system prompt goes in a dedicated field, not the contents array
    assert fake_post.requests[0]["json"]["system_instruction"]["parts"][0]["text"] == "system prompt"
    # the function response must be sent back as a functionResponse part
    second_contents = fake_post.requests[1]["json"]["contents"]
    fn_response_part = second_contents[-1]["parts"][0]
    assert "functionResponse" in fn_response_part
    assert fn_response_part["functionResponse"]["name"] == "get_sentiment"


def test_gemini_backend_400_includes_error_body(monkeypatch):
    monkeypatch.setattr("requests.post", _FakePost([{}], status_code=400))
    backend = GeminiBackend(api_key="fake-key")
    with pytest.raises(RuntimeError, match="fake error body"):
        backend.ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)


def test_gemini_backend_no_candidates_does_not_crash(monkeypatch):
    monkeypatch.setattr("requests.post", _FakePost([{"candidates": []}]))
    backend = GeminiBackend(api_key="fake-key")
    answer = backend.ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)
    assert "no candidates" in answer.lower()


# ---------------------------------------------------------------------------
# Auto-detection priority across all four backends
# ---------------------------------------------------------------------------

def test_auto_detect_priority_openai_over_gemini(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CHATBOT_BACKEND", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    backend = get_backend()
    assert isinstance(backend, OpenAIBackend)


def test_auto_detect_gemini_when_only_gemini_key_present(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CHATBOT_BACKEND", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    backend = get_backend()
    assert isinstance(backend, GeminiBackend)


def test_explicit_backend_name_overrides_auto_detect(monkeypatch):
    # Claude and OpenAI keys are both present (auto-detect would pick Claude
    # first), but an explicit name must win regardless — and still needs its
    # own key, which is set here too.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    backend = get_backend("gemini")
    assert isinstance(backend, GeminiBackend)
