"""
Validation: the OpenAI backend never receives Reddit text under the existing
hosted evidence policy. A fake `_chat` records every
payload that would be sent; the searches are faked at chatbot.tools'
retrieval layer, so the real packaging, tracker and Conversation run.

Reddit text can reach OpenAI three ways: a search result this turn, an
earlier answer in the conversation history (a model or the harness quoted
it), or the API's /chat history. Each is covered.
"""

import json

import pytest
from fastapi.testclient import TestClient

import chatbot.agent as agent
import chatbot.tools as tools
from chatbot.backends.openai_backend import OpenAIBackend

REDDIT = "honestly the dbs app crashed three times while paying my rent this morning"
REDDIT_URL = "https://www.reddit.com/r/singapore/comments/abc123/dbs_app/"
REDDIT_VIA_NEWS = "uob card fees are a total scam according to my whole family group chat"
REDDIT_VIA_NEWS_URL = "https://reddit.com/r/askSingapore/comments/xyz/uob/"
NEWS = "dbs raised its quarterly dividend to 60 cents a share in august"
NEWS_URL = "https://www.straitstimes.com/business/dbs-dividend"
FRAGMENTS = ["dbs app crashed three times", "paying my rent this morning",
             "total scam according to my", "whole family group chat"]


def _hits():
    return [
        {"sentence_id": "a" * 24, "bank": "DBS", "source": "arctic_shift", "published_at": "2026-09-01T00:00:00",
         "text": REDDIT, "url": REDDIT_URL, "score": 0.9},
        {"sentence_id": "b" * 24, "bank": "UOB", "source": "google_news", "published_at": "2026-09-02T00:00:00",
         "text": REDDIT_VIA_NEWS, "url": REDDIT_VIA_NEWS_URL, "score": 0.8},
        {"sentence_id": "c" * 24, "bank": "DBS", "source": "google_news", "published_at": "2026-09-03T00:00:00",
         "text": NEWS, "url": NEWS_URL, "score": 0.7},
    ]


@pytest.fixture(autouse=True)
def fake_search(monkeypatch):
    monkeypatch.setattr(tools, "_search_evidence", lambda query, **kw: _hits())


class _CapturingOpenAI(OpenAIBackend):
    """OpenAI with transport replaced: searches once, then answers."""

    def __init__(self, answer="Done."):
        super().__init__(api_key="fake-key")
        self.sent, self.answer = [], answer

    def _chat(self, messages, tools_):
        self.sent.append(json.dumps(messages, ensure_ascii=False).lower())
        if len(self.sent) == 1:
            return {"choices": [{"message": {"content": "", "tool_calls": [{
                "id": "search1", "type": "function", "function": {
                    "name": "search_evidence", "arguments": json.dumps({"query": "dbs app", "bank": "DBS"})
                }
            }]}}]}
        return {"choices": [{"message": {"content": self.answer}}]}


class _QuotingLocalModel:
    """A non-OpenAI model (e.g. Ollama) that searches and quotes the Reddit text."""
    name, model = "ollama", "fake"

    def __init__(self, answer):
        self.answer = answer

    def ask(self, question, system, tool_schemas, tool_executor, verbose=True, history=None):
        tool_executor("search_evidence", {"query": "dbs app", "bank": "DBS"})
        return self.answer


def _assert_no_reddit(sent):
    blob = "\n".join(sent)
    leaked = [f for f in FRAGMENTS if f in blob] + [u for u in ("reddit.com/r/",) if u in blob]
    assert not leaked, leaked


def _assert_news_kept(sent):
    assert NEWS[:30] in "\n".join(sent)      # control: the filter isn't dropping everything


def test_search_results_sent_to_openai_hold_no_reddit_text():
    g = _CapturingOpenAI()
    agent.answer_turn("What do people say about the DBS app?", backend=g, verbose=False)
    assert len(g.sent) == 2
    _assert_no_reddit(g.sent)
    _assert_news_kept(g.sent)


EARLIER_ANSWERS = {
    "straight quote": f'People complain: "{REDDIT}" (sentence_id {"a" * 24}).',
    "curly quote": f"People complain: “{REDDIT}”.",
    "blockquote": f"People complain:\n\n> {REDDIT}\n\nThat is one view.",
    "quote wrapping a line": f'People complain: "honestly the dbs app crashed three times\nwhile paying my rent this morning".',
    "bare bullet": f"Evidence:\n- {REDDIT} [DBS, 2026-09-01]",
    "link": f"See {REDDIT_URL} for the thread.",
    # The cut falls inside the quote, leaving an opening mark with no closing one.
    "quote cut by the history limit": "x" * (agent.HISTORY_ANSWER_CHARS - 13 - 60) + f' Users said "{REDDIT}".',
}
_LEAKS = {
    "quote wrapping a line": "the earlier history filter's quote pattern stops at a line break, so a wrapped quote is sent",
    "bare bullet": "an earlier answer that repeats Reddit text without quote marks is sent as written",
    "link": "Reddit links in an earlier answer are sent; tool results drop them",
    "quote cut by the history limit": "the history cut leaves an unclosed quote, which the quote pattern misses",
}


def _cases():
    return [pytest.param(c)
            if c in _LEAKS else c for c in EARLIER_ANSWERS]


@pytest.mark.parametrize("case", _cases())
def test_an_earlier_answer_quoting_reddit_is_not_sent_to_openai(monkeypatch, case):
    conv = agent.Conversation()
    monkeypatch.setattr(agent, "get_backend", lambda name=None: _QuotingLocalModel(EARLIER_ANSWERS[case]))
    conv.ask("What do people say about the DBS app?")
    g = _CapturingOpenAI()
    monkeypatch.setattr(agent, "get_backend", lambda name=None: g)
    conv.ask("And what about OCBC?")
    _assert_no_reddit(g.sent)


def test_harness_search_evidence_in_an_earlier_answer_is_not_sent_to_openai(monkeypatch):
    """CHATBOT_ENFORCE_EVIDENCE=search appends real quotes, Reddit ones included."""
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "search")
    conv = agent.Conversation()

    class _NoSearch:
        name, model = "ollama", "fake"

        def ask(self, question, system, tool_schemas, tool_executor, verbose=True, history=None):
            tool_executor("get_sentiment", {"bank": "DBS"})
            return 'Mixed. One user wrote "the app is down again on payday".'
    monkeypatch.setattr(agent, "get_backend", lambda name=None: _NoSearch())
    first = conv.ask("What do people say about the DBS app?")
    assert REDDIT in first.answer          # the harness did add the Reddit quote
    g = _CapturingOpenAI()
    monkeypatch.setattr(agent, "get_backend", lambda name=None: g)
    conv.ask("And what about OCBC?")
    _assert_no_reddit(g.sent)


@pytest.mark.parametrize("case", _cases())
def test_api_chat_history_quoting_reddit_is_not_sent_to_openai(monkeypatch, case):
    from api.main import app
    g = _CapturingOpenAI()
    monkeypatch.setattr(agent, "get_backend", lambda name=None: g)
    history = [{"role": "user", "content": "What do people say about the DBS app?"},
               {"role": "assistant", "content": EARLIER_ANSWERS[case]}]
    resp = TestClient(app).post("/chat", json={"message": "And what about OCBC?", "backend": "openai",
                                               "history": history})
    assert resp.status_code == 200, resp.text[:300]
    _assert_no_reddit(g.sent)
