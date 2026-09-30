"""
Tests for the pluggable chatbot backend (chatbot/backends/) and the
fabrication-detection safety net in chatbot/agent.py.

Three real bugs were caught live against a running Ollama instance
(llama3.2:3b) before these tests were written — each test below
exists because of one of them, not as generic coverage:
  1. The model fabricated a full "supporting evidence" section (fake URLs,
     fake sentence_ids) despite never calling search_evidence.
  2. After a prompt fix, it still fabricated evidence — this time using
     placeholder tokens ("[insert sentence_id]") instead of a fake URL,
     which a naive URL-only check would miss entirely.
  3. It called search_evidence with k="5" (a string) instead of k=5,
     crashing a list slice in chatbot/retrieval.py with a TypeError.

Ollama's response shapes below are pinned copies of real responses (not
imagined) so a future change in Ollama's tool-calling format surfaces as a
failing test rather than a silent behavior change.
"""

import json

import pytest

from chatbot.agent import _ToolCallTracker, ask
from chatbot.backends import get_backend
from chatbot.backends.claude_backend import ClaudeBackend
from chatbot.backends.ollama_backend import OllamaBackend, _to_ollama_tools
from chatbot.tools import TOOL_SCHEMAS, coerce_tool_arguments


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

def test_auto_detect_prefers_claude_when_key_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    monkeypatch.delenv("CHATBOT_BACKEND", raising=False)
    backend = get_backend()
    assert isinstance(backend, ClaudeBackend)


def test_auto_detect_falls_back_to_ollama_with_no_key(monkeypatch):
    # Every provider's key, not just Claude's: .env is loaded on import, and a
    # real key in it (GEMINI_API_KEY since 2026-09-30) would otherwise win.
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "CHATBOT_BACKEND"):
        monkeypatch.delenv(var, raising=False)
    backend = get_backend()
    assert isinstance(backend, OllamaBackend)


def test_explicit_claude_with_no_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY not set"):
        get_backend("claude")


def test_unknown_backend_name_raises_value_error():
    with pytest.raises(ValueError, match="Unknown CHATBOT_BACKEND"):
        get_backend("not-a-real-backend")


def test_ollama_model_and_url_configurable_via_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example.com:9999")
    backend = get_backend("ollama")
    assert backend.model == "qwen3:4b"
    assert backend.base_url == "http://example.com:9999"


# ---------------------------------------------------------------------------
# Ollama tool schema conversion + tool-calling loop (mocked HTTP)
# ---------------------------------------------------------------------------

def test_tool_schema_conversion_to_ollama_shape():
    ollama_tools = _to_ollama_tools(TOOL_SCHEMAS)
    names = {t["function"]["name"] for t in ollama_tools}
    assert "get_sentiment" in names
    sample = next(t for t in ollama_tools if t["function"]["name"] == "get_sentiment")
    assert sample["type"] == "function"
    assert "parameters" in sample["function"]  # Claude's input_schema renamed to parameters


class _FakePost:
    """Replays pinned real Ollama responses in sequence, one per call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, url, json=None, timeout=None):
        self.calls.append(json)
        payload = self._responses.pop(0)

        class _Resp:
            status_code = 200

            def json(_self):
                return payload

            def raise_for_status(_self):
                pass

        return _Resp()


# Pinned real response: llama3.2:3b requesting a tool call (confirmed against the live site).
_OLLAMA_TOOL_CALL_RESPONSE = {
    "message": {
        "role": "assistant", "content": "",
        "tool_calls": [{"id": "call_lqdagp31",
                         "function": {"name": "get_sentiment",
                                      "arguments": {"aspect": "dividend_policy", "bank": "DBS"}}}],
    },
    "done": True,
}

# Pinned real response: llama3.2:3b's final text answer after a tool result.
_OLLAMA_FINAL_ANSWER_RESPONSE = {
    "message": {"role": "assistant",
                "content": "The sentiment for DBS on dividend policy is neutral."},
    "done": True,
}


def test_ollama_backend_full_loop(monkeypatch):
    fake_post = _FakePost([_OLLAMA_TOOL_CALL_RESPONSE, _OLLAMA_FINAL_ANSWER_RESPONSE])
    monkeypatch.setattr("requests.post", fake_post)

    calls = []

    def tool_executor(name, args):
        calls.append((name, args))
        return json.dumps({"score": 0.006, "n": 9066})

    backend = OllamaBackend(model="llama3.2:3b")
    answer = backend.ask("What's DBS dividend sentiment?", "system prompt",
                          TOOL_SCHEMAS, tool_executor, verbose=False)

    assert answer == "The sentiment for DBS on dividend policy is neutral."
    assert calls == [("get_sentiment", {"aspect": "dividend_policy", "bank": "DBS"})]
    # second request must include the tool result as a role="tool" message
    second_request_messages = fake_post.calls[1]["messages"]
    assert any(m.get("role") == "tool" for m in second_request_messages)


def test_ollama_backend_connection_error_gives_actionable_message(monkeypatch):
    import requests

    def raise_connection_error(*a, **kw):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr("requests.post", raise_connection_error)
    backend = OllamaBackend(model="llama3.2:3b")
    with pytest.raises(RuntimeError, match="ollama serve"):
        backend.ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)


# ---------------------------------------------------------------------------
# Argument type coercion (bug #3 above)
# ---------------------------------------------------------------------------

def test_coerce_string_integer_to_int():
    result = coerce_tool_arguments("search_evidence", {"query": "x", "k": "5"})
    assert result["k"] == 5
    assert isinstance(result["k"], int)


def test_coerce_leaves_correct_types_alone():
    result = coerce_tool_arguments("search_evidence", {"query": "x", "k": 5})
    assert result["k"] == 5


def test_coerce_unknown_tool_passes_through_unchanged():
    result = coerce_tool_arguments("not_a_real_tool", {"k": "5"})
    assert result == {"k": "5"}


def test_coerce_non_numeric_string_left_as_is_not_crashed():
    # Defensive: an unparseable value shouldn't raise, just pass through
    # (the underlying tool call will fail with its own clear error instead).
    result = coerce_tool_arguments("search_evidence", {"query": "x", "k": "not-a-number"})
    assert result["k"] == "not-a-number"


# ---------------------------------------------------------------------------
# Fabrication detection (bugs #1 and #2 above)
# ---------------------------------------------------------------------------

def test_detects_fabricated_url_citation():
    tracker = _ToolCallTracker()
    answer = ('Search evidence: "DBS dividend payout has been stable." '
              '(sentence_id: 1234, url: https://www.bloomberg.com/fake-article)')
    assert tracker.answer_has_unverified_citation(answer)


def test_detects_placeholder_style_fabrication_with_no_url():
    # The exact second failure mode observed live: no URL at all, just a
    # placeholder token and a fabricated quote.
    tracker = _ToolCallTracker()
    answer = ('Sentence_id: [insert sentence_id] from [url]\n'
              '"DBS has increased its dividend payout for the sixth consecutive year."')
    assert tracker.answer_has_unverified_citation(answer)


def test_honest_answer_with_no_evidence_claim_not_flagged():
    tracker = _ToolCallTracker()
    answer = "The sentiment score for DBS is 0.006, based on 9066 data points."
    assert not tracker.answer_has_unverified_citation(answer)


def test_real_verified_citation_not_flagged():
    tracker = _ToolCallTracker()
    tracker.search_evidence_called = True
    tracker.verified_urls.add("https://reddit.com/real-post")
    answer = 'See: "DBS raised fees again" (https://reddit.com/real-post)'
    assert not tracker.answer_has_unverified_citation(answer)


def test_tracker_records_urls_from_real_search_evidence_call():
    tracker = _ToolCallTracker()
    from chatbot import tools as tools_module

    def fake_search_evidence(**kw):
        return {"results": [{"sentence_id": "abc", "url": "https://reddit.com/x"}]}

    orig = tools_module.TOOL_FUNCTIONS["search_evidence"]
    tools_module.TOOL_FUNCTIONS["search_evidence"] = lambda **kw: fake_search_evidence(**kw)
    try:
        tracker.execute("search_evidence", {"query": "x"})
    finally:
        tools_module.TOOL_FUNCTIONS["search_evidence"] = orig

    assert tracker.search_evidence_called is True
    assert "https://reddit.com/x" in tracker.verified_urls


def test_ask_appends_warning_when_backend_fabricates(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CHATBOT_BACKEND", "ollama")

    class _FabricatingBackend:
        name = "fake"
        model = "fake-model"

        def ask(self, question, system, tool_schemas, tool_executor, verbose=True, **kwargs):
            return 'Evidence: "totally made up quote" (sentence_id: 999, url: https://fake.example.com)'

    monkeypatch.setattr("chatbot.agent.get_backend", lambda name=None: _FabricatingBackend())
    answer = ask("How is sentiment on DBS?", verbose=False)  # on-topic, so no guard answers it
    assert "VERIFICATION WARNING" in answer


def test_ask_no_warning_when_backend_is_honest(monkeypatch):
    class _HonestBackend:
        name = "fake"
        model = "fake-model"

        def ask(self, question, system, tool_schemas, tool_executor, verbose=True, **kwargs):
            return "The sentiment score is 0.5 based on 100 data points."

    monkeypatch.setattr("chatbot.agent.get_backend", lambda name=None: _HonestBackend())
    answer = ask("test question", verbose=False)
    assert "VERIFICATION WARNING" not in answer
