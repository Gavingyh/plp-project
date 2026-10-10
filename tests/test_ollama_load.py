"""
The local model is loaded before it is asked anything (chatbot/ollama_load.py),
kept loaded between questions, and a request that still times out says why.
Its answer is read as it is written, and the tool descriptions can go at the
start of the instructions, where Ollama caches them.
No test here reaches Ollama: requests.get and requests.post are replaced.
"""

import copy
import json

import pytest
import requests

from chatbot import intent, ollama_load, settings
from chatbot.backends.base import BackendUnavailable
from chatbot.backends._text_tool_call import text_tool_calls, writing_past_its_calls
from chatbot.backends.ollama_backend import OllamaBackend, tools_block
from chatbot.tools import TOOL_SCHEMAS


class _Resp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body

    def iter_lines(self):
        return [json.dumps(line).encode() for line in (self._body if isinstance(self._body, list) else [self._body])]


def _ollama(monkeypatch, loaded: list[str], post=None):
    """A stand-in Ollama holding the `loaded` models; returns the POSTs it received."""
    posts = []

    def fake_get(url, **kw):
        return _Resp({"models": [{"name": m, "model": m} for m in loaded]})

    def fake_post(url, json=None, timeout=None, **kw):
        posts.append({"url": url, "json": copy.deepcopy(json), "timeout": timeout, **kw})   # as sent: the backend adds to it later
        if post:
            return post(url, json)
        return _Resp({"message": {"role": "assistant", "content": '{"intent": "in_scope"}'}, "done": True})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    return posts


def test_an_unloaded_model_is_loaded_with_the_longer_time_limit(monkeypatch, no_model_loading):
    posts = _ollama(monkeypatch, loaded=[])
    assert no_model_loading("llama3.1:8b", "http://localhost:11434") is True
    assert len(posts) == 1
    assert posts[0]["url"].endswith("/api/generate")
    assert posts[0]["json"] == {"model": "llama3.1:8b", "keep_alive": settings.get("ollama_keep_alive")}
    assert posts[0]["timeout"] == settings.get("timeouts_seconds.ollama_load")
    assert posts[0]["timeout"] > settings.get("timeouts_seconds.ollama")


def test_a_loaded_model_is_not_loaded_again(monkeypatch, no_model_loading):
    posts = _ollama(monkeypatch, loaded=["llama3.1:8b"])
    assert no_model_loading("llama3.1:8b", "http://localhost:11434") is False
    assert posts == []


def test_another_model_being_loaded_does_not_count(monkeypatch, no_model_loading):
    posts = _ollama(monkeypatch, loaded=["qwen3:4b"])
    assert no_model_loading("llama3.1:8b", "http://localhost:11434") is True
    assert len(posts) == 1


@pytest.mark.parametrize("error", [requests.ConnectionError("not running"), requests.Timeout("slow")])
def test_a_failed_load_never_raises(monkeypatch, no_model_loading, error):
    def fail(*a, **kw):
        raise error

    monkeypatch.setattr("requests.get", fail)
    assert no_model_loading("llama3.1:8b", "http://localhost:11434") is False


def test_the_chatbot_model_is_loaded_once_per_question_and_kept(monkeypatch):
    loads = []
    monkeypatch.setattr(ollama_load, "ensure_loaded", lambda model, base_url=None: loads.append(model))
    answers = iter([
        {"message": {"role": "assistant", "content": "",
                     "tool_calls": [{"function": {"name": "get_sentiment", "arguments": {"bank": "DBS"}}}]}},
        {"message": {"role": "assistant", "content": "Neutral."}},
    ])
    posts = _ollama(monkeypatch, loaded=["llama3.1:8b"], post=lambda url, json: _Resp(next(answers)))
    answer = OllamaBackend(model="llama3.1:8b").ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)
    assert answer == "Neutral."
    assert loads == ["llama3.1:8b"]                      # once, not before each of the two requests
    assert [p["json"]["keep_alive"] for p in posts] == [settings.get("ollama_keep_alive")] * 2


def test_the_intent_classifier_loads_its_model_and_keeps_it(monkeypatch):
    loads = []
    monkeypatch.setattr(ollama_load, "ensure_loaded", lambda model, base_url=None: loads.append(model))
    posts = _ollama(monkeypatch, loaded=[])
    assert intent_ollama_chat("llama3.1:8b", [{"role": "user", "content": "q"}], ["in_scope"]) == '{"intent": "in_scope"}'
    assert loads == ["llama3.1:8b"]
    assert posts[0]["json"]["keep_alive"] == settings.get("ollama_keep_alive")


def test_a_request_that_times_out_says_the_model_is_slow_not_missing(monkeypatch):
    def slow(*a, **kw):
        raise requests.exceptions.ReadTimeout("Read timed out. (read timeout=120)")

    monkeypatch.setattr("requests.post", slow)
    with pytest.raises(BackendUnavailable, match="short of memory") as e:
        OllamaBackend(model="llama3.1:8b").ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)
    assert "went silent for" in str(e.value)
    assert "ollama serve" not in str(e.value)            # it is running: don't send the reader to start it


def test_a_silence_while_the_answer_is_being_read_says_the_same(monkeypatch):
    class _Stalls(_Resp):
        def iter_lines(self):
            yield b'{"message": {"role": "assistant", "content": "The"}}'
            raise requests.exceptions.ConnectionError("HTTPConnectionPool(host='localhost', port=11434): Read timed out.")

    monkeypatch.setattr("requests.post", lambda *a, **kw: _Stalls({}))
    with pytest.raises(BackendUnavailable, match="short of memory"):
        OllamaBackend(model="llama3.1:8b").ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)


def test_the_answer_is_read_as_it_is_written(monkeypatch):
    """The time limit is then the longest silence, not the longest answer."""
    lines = [{"message": {"role": "assistant", "content": "DBS is "}},
             {"message": {"role": "assistant", "content": "neutral."}},
             {"message": {"role": "assistant", "content": ""}, "done": True, "eval_count": 5}]
    posts = _ollama(monkeypatch, loaded=["llama3.1:8b"], post=lambda url, body: _Resp(lines))
    backend = OllamaBackend(model="llama3.1:8b")
    assert backend.ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False) == "DBS is neutral."
    assert posts[0]["json"]["stream"] is True and posts[0]["stream"] is True
    connect, silence = posts[0]["timeout"]
    assert silence == settings.get("timeouts_seconds.ollama") and connect < silence


def test_tool_calls_arriving_in_separate_lines_are_all_run(monkeypatch):
    call = lambda bank: {"function": {"name": "get_sentiment", "arguments": {"bank": bank}}}
    answers = iter([
        [{"message": {"role": "assistant", "content": "", "tool_calls": [call("DBS")]}},
         {"message": {"role": "assistant", "content": "", "tool_calls": [call("UOB")]}},
         {"message": {"role": "assistant", "content": ""}, "done": True}],
        [{"message": {"role": "assistant", "content": "Both neutral."}, "done": True}],
    ])
    _ollama(monkeypatch, loaded=["llama3.1:8b"], post=lambda url, body: _Resp(next(answers)))
    ran = []
    answer = OllamaBackend(model="llama3.1:8b", tools_in_system=False).ask(
        "q", "s", TOOL_SCHEMAS, lambda n, a: ran.append(a["bank"]) or "{}", verbose=False)
    assert answer == "Both neutral." and ran == ["DBS", "UOB"]


# --- the tool descriptions at the start of the instructions ----------------------

def test_tools_in_the_instructions_are_sent_once_as_text_not_as_tools(monkeypatch):
    answers = iter([
        {"message": {"role": "assistant", "content":
                     '{"name": "compare_banks", "parameters": {"aspect": "dividend_policy"}}\n'
                     '{"name": "search_evidence", "parameters": {"query": "dividend", "bank": "DBS"}}'}},
        {"message": {"role": "assistant", "content": "DBS leads."}},
    ])
    posts = _ollama(monkeypatch, loaded=["llama3.1:8b"], post=lambda url, body: _Resp(next(answers)))
    ran = []
    answer = OllamaBackend(model="llama3.1:8b", tools_in_system=True).ask(
        "Compare dividends", "RULES. STATE: DBS.", TOOL_SCHEMAS, lambda n, a: ran.append(n) or "{}", verbose=False)
    assert answer == "DBS leads."
    assert ran == ["compare_banks", "search_evidence"]            # both calls written in one message
    for post in posts:
        assert "tools" not in post["json"]                        # Ollama would put them inside the question
        system = post["json"]["messages"][0]["content"]
        assert system.endswith("RULES. STATE: DBS.")              # what varies comes last, after what is cached
        assert all(f'"name":"{t["name"]}"' in system for t in TOOL_SCHEMAS)
    first, second = (p["json"]["messages"] for p in posts)
    assert second[: len(first)] == first                          # the second request only adds to the first
    made = second[len(first)]
    assert made["content"] == "" and [c["function"]["name"] for c in made["tool_calls"]] == ran
    assert [m["role"] for m in second[len(first) + 1:]][:2] == ["tool", "tool"]


def test_the_default_still_passes_tools_to_ollama(monkeypatch):
    monkeypatch.delenv("OLLAMA_TOOLS_IN_SYSTEM", raising=False)
    posts = _ollama(monkeypatch, loaded=["llama3.1:8b"],
                    post=lambda url, body: _Resp({"message": {"role": "assistant", "content": "ok"}}))
    backend = OllamaBackend(model="llama3.1:8b")
    assert backend.tools_in_system is settings.get("ollama_tools_in_system")
    OllamaBackend(model="llama3.1:8b", tools_in_system=False).ask("q", "s", TOOL_SCHEMAS, lambda n, a: "{}", verbose=False)
    assert len(posts[0]["json"]["tools"]) == len(TOOL_SCHEMAS)
    assert posts[0]["json"]["messages"][0]["content"] == "s"


def test_the_tools_text_does_not_change_between_questions():
    from chatbot.backends.ollama_backend import _to_ollama_tools
    tools = _to_ollama_tools(TOOL_SCHEMAS)
    assert tools_block(tools) == tools_block(tools)
    assert tools_block(tools).count("\n{") == len(TOOL_SCHEMAS)   # one tool a line


def test_every_written_call_is_found_and_other_json_left_alone():
    names = {"get_sentiment", "search_evidence"}
    text = ('Checking. {"name": "get_sentiment", "parameters": {"bank": "DBS", "filter": {"a": 1}}} and '
            '{"note": "not a call"} {"name": "search_evidence", "arguments": "{\\"query\\": \\"fees\\"}"}')
    assert text_tool_calls(text, names) == [("get_sentiment", {"bank": "DBS", "filter": {"a": 1}}),
                                            ("search_evidence", {"query": "fees"})]
    assert text_tool_calls('{"name": "unknown_tool", "parameters": {}}', names) == []
    assert text_tool_calls("DBS is neutral.", names) == []


def test_reading_stops_when_the_model_writes_on_past_its_call(monkeypatch):
    """Seen on 10 Oct: a call, then an answer with invented figures before any result came back."""
    read = []

    class _Runs(_Resp):
        closed = False

        def iter_lines(self):
            for piece in ['{"name": "get_sentiment", ', '"parameters": {"bank": "DBS"}}', " \n\nThe overall",
                          " sentiment on DBS is +0.12", " based on 80% positive"]:
                read.append(piece)
                yield json.dumps({"message": {"role": "assistant", "content": piece}}).encode()

        def close(self):
            _Runs.closed = True

    answers = iter([_Runs({}), _Resp({"message": {"role": "assistant", "content": "Neutral."}})])
    monkeypatch.setattr("requests.post", lambda *a, **kw: next(answers))
    ran = []
    answer = OllamaBackend(model="llama3.1:8b", tools_in_system=True).ask(
        "q", "s", TOOL_SCHEMAS, lambda n, a: ran.append((n, a)) or "{}", verbose=False)
    assert answer == "Neutral." and ran == [("get_sentiment", {"bank": "DBS"})]
    assert _Runs.closed and len(read) == 3               # stopped at the first words after the call


@pytest.mark.parametrize("text, past", [
    ('{"name": "get_sentiment", "parameters": {"bank": "DBS"}}', False),
    ('{"name": "get_sentiment", "parameters": {"bank": "DBS"}} \n', False),
    ('{"name": "get_sentiment", "parameters": {"bank": "DBS"}}; {"name": "search_', False),   # a second call begun
    ('Let me check. {"name": "get_sentiment", "parameters": {"bank": "DBS"}}', False),
    ('{"name": "get_sentiment", "parameters": {"bank": "DBS"}} The overall', True),
    ("DBS is neutral.", False),
    ('{"name": "get_sentim', False),
])
def test_writing_past_its_calls(text, past):
    assert writing_past_its_calls(text, {"get_sentiment", "search_evidence"}) is past


intent_ollama_chat = intent.ollama_chat                  # the real one, before conftest replaces it per test
