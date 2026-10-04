"""
Third validation of the grounded chatbot claim on fix/chatbot-answers (commit
b79fbc3): probes of the bare-marker drop (_drop_bare_marks, _BARE_MARK,
_norm_text in chatbot/agent.py), the "[" now accepted after a closing quote
mark (_QUOTE_PATTERN), follow-ups in process and through the API, and the
year-less date patterns in chatbot/guards.py.

Each test asserts the behaviour the claim needs; a confirmed hole carries
xfail(strict=True). Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest
from fastapi.testclient import TestClient

import chatbot.agent as agent
from chatbot import tools
from chatbot.agent import Conversation, _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers

REAL = "ocbc raised its dividend this quarter"
INVENTED = "OCBC will cut its dividend next year for sure"
FOOTNOTE = ("ASEAN consumers remained optimistic about both the macroeconomic environment and "
            "their personal finances in 2026, with the UOB ASEAN Consumer Sentiment Index "
            "(the Index)[1] holding steady at 54.")
ITEMS = [{"sentence_id": "b" * 24, "bank": "OCBC", "source": "cna", "date": "2026-09-02", "text": REAL,
          "url": "https://news.example/ocbc", "cite_as": f"[OCBC, 2026-09-02, sentence_id {'b' * 24}]"},
         {"sentence_id": "c" * 24, "bank": "UOB", "source": "yahoo_news", "date": "2026-09-03", "text": FOOTNOTE,
          "url": "https://news.example/uob", "cite_as": f"[UOB, 2026-09-03, sentence_id {'c' * 24}]"}]


def _tracker(searched: bool):
    if searched:
        return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                             "result": {"results": [dict(i) for i in ITEMS]}}])
    return _ToolCallTracker.from_calls([{"name": "get_sentiment", "arguments": {"bank": "OCBC"},
                                         "result": {"bank": "OCBC", "score": 0.2, "n": 100}}])


def _kept_unflagged(answer, searched, mode="strip"):
    out, flagged = enforce_evidence(answer, _tracker(searched), "q", mode)
    return "cut its" in out and not flagged


# --- an invented quote with a marker, then a character the quote pattern doesn't accept ---------

MARKER_THEN = {
    "em dash": f'One analyst said "{INVENTED}"[2]—a bold call.',
    "hyphen": f'One analyst said "{INVENTED}"[2]-ish, then moved on.',
    "letter": f'One analyst said "{INVENTED}"[2]and moved on.',
    "apostrophe": f'The gist, "{INVENTED}"[2]\'s point, holds.',
    "slash": f'One analyst said "{INVENTED}"[2]/ wow.',
}


@pytest.mark.parametrize("searched", [True, False], ids=["after a search", "no search"])
@pytest.mark.parametrize("name", list(MARKER_THEN))
def test_off_mode_flags_an_invented_quote_with_a_marker(name, searched):
    """The same answers are flagged with enforcement off: the marker makes the quote visible."""
    out, flagged = enforce_evidence(MARKER_THEN[name], _tracker(searched), "q", "off")
    assert flagged


@pytest.mark.parametrize("searched", [True, False], ids=["after a search", "no search"])
@pytest.mark.parametrize("name", list(MARKER_THEN))
def test_strip_removes_or_flags_an_invented_quote_with_a_marker(name, searched):
    assert not _kept_unflagged(MARKER_THEN[name], searched)


@pytest.mark.parametrize("mode", ["off", "strip"])
def test_an_invented_quote_before_an_em_dash_is_caught(mode):
    assert not _kept_unflagged(f'One analyst said "{INVENTED}"—a bold call.', True, mode)


@pytest.mark.parametrize("mode", ["off", "strip"])
def test_an_unclosed_invented_quote_with_a_marker_is_caught(mode):
    assert not _kept_unflagged(f'One analyst said "{INVENTED} [2] and moved on.', True, mode)


# --- what b79fbc3 does handle --------------------------------------------------------------------

HANDLED = {
    "marker inside the quote": f'One analyst said "{INVENTED}[2]".',
    "marker after, then a full stop": f'One analyst said "{INVENTED}"[2].',
    "marker after, then a colon": f'He said "{INVENTED}"[2]: wow.',
    "marker after, then a bracket": f'(one analyst: "{INVENTED}"[2]).',
    "'\"[' then a line break": f'One analyst said "{INVENTED}"[\n2] today.',
    "wrapped quote, '\"[' then a line break": f'One analyst said "OCBC will cut its\ndividend next year for sure"[\n2]',
    "nested single quotes": f'He wrote "they said \'{INVENTED}\' [2]" in a post.',
    "real and invented on one line": f'Report: "{REAL}"[1] and "{INVENTED}"[2].',
    "curly quotes and a dash": f'One analyst said “{INVENTED}”[2]—bold.',
    "bold and a dash": f'One analyst said **"{INVENTED}"**[2]—bold.',
    "marker before the quote, no space": f'One analyst said:[2]"{INVENTED}".',
    "invented text around a real footnote": 'UOB: "Index (the Index)[1] will collapse to 30 next year" [2]',
}


@pytest.mark.parametrize("searched", [True, False], ids=["after a search", "no search"])
@pytest.mark.parametrize("name", list(HANDLED))
def test_strip_removes_or_flags_these_invented_quotes(name, searched):
    out, flagged = enforce_evidence(HANDLED[name], _tracker(searched), "q", "strip")
    assert flagged or ("cut its" not in out and "collapse" not in out)


def test_a_real_quote_that_omits_the_stored_footnote_marker_passes():
    answer = ('UOB: "the UOB ASEAN Consumer Sentiment Index (the Index) holding steady at 54." '
              f'{ITEMS[1]["cite_as"]}')
    out, flagged = enforce_evidence(answer, _tracker(True), "q", "strip")
    assert not flagged and "holding steady" in out


# --- follow-ups -----------------------------------------------------------------------------------

class _Model:
    name, model = "fake", "fake"

    def __init__(self, answers, search_first=False):
        self.answers, self.search_first, self.turn = list(answers), search_first, 0

    def ask(self, question, system, tool_schemas, tool_executor, verbose=True, history=None):
        if self.search_first and self.turn == 0:
            tool_executor("search_evidence", {"query": question, "bank": "OCBC"})
        self.turn += 1
        return self.answers.pop(0)


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(agent.settings, "get", (lambda get: lambda key: "strip" if key == "enforce_evidence"
                                                else get(key))(agent.settings.get))
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [dict(i, score=0.9, sentiment="positive")
                                                                     for i in ITEMS])
    monkeypatch.setattr(tools, "_data_runs_to", lambda bank=None: "2026-10-01")


def _conversation(monkeypatch, second):
    model = _Model([f'OCBC readers were upbeat: "{REAL}" {ITEMS[0]["cite_as"]}', second], search_first=True)
    monkeypatch.setattr(agent, "get_backend", lambda name=None: model)
    conv = Conversation()
    conv.ask("How is OCBC's dividend seen?")
    return conv.ask("Say more")


def test_in_process_follow_up_repeating_a_real_quote_with_its_marker_passes(harness, monkeypatch):
    r = _conversation(monkeypatch, f'As before, "{REAL}" [1].')
    assert not r.citation_unverified and REAL in r.answer


def test_in_process_follow_up_with_a_plain_invented_quote_is_stripped(harness, monkeypatch):
    r = _conversation(monkeypatch, f'And one said "{INVENTED}" [2].')
    assert "cut its" not in r.answer or r.citation_unverified


def test_in_process_follow_up_with_a_marker_and_dash_is_caught(harness, monkeypatch):
    r = _conversation(monkeypatch, f'And one said "{INVENTED}"[2]—bold.')
    assert "cut its" not in r.answer or r.citation_unverified


def _api_chat(monkeypatch, second):
    from api.main import app
    monkeypatch.setattr(agent, "get_backend", lambda name=None: _Model([second]))
    history = [{"role": "user", "content": "How is OCBC's dividend seen?"},
               {"role": "assistant", "content": f'OCBC readers were upbeat: "{REAL}" [1]\n\nSources:\n'
                                                f'- [1] CNA, OCBC, 2 Sep 2026: https://news.example/ocbc'}]
    resp = TestClient(app).post("/chat", json={"message": "Say more", "history": history})
    assert resp.status_code == 200
    return resp.json()


def test_api_follow_up_with_a_plain_invented_quote_is_stripped(harness, monkeypatch):
    body = _api_chat(monkeypatch, f'And one said "{INVENTED}" [2].')
    assert "cut its" not in body["answer"] or body["citation_unverified"]


def test_api_follow_up_with_a_marker_and_dash_is_caught(harness, monkeypatch):
    body = _api_chat(monkeypatch, f'And one said "{INVENTED}"[2]—bold.')
    assert "cut its" not in body["answer"] or body["citation_unverified"]


# --- year-less dates in the number check ----------------------------------------------------------

# A date written without its year is skipped only when a tool returned it (4 Oct 2026),
# as a real answer's date always is (data_runs_to): these tests give the tools that date.
TOOL = [{"bank": "DBS", "score": 0.31, "n": 120}]
TOOL_DATES = TOOL + [{"data_runs_to": d} for d in ("2026-09-03", "2026-09-23", "2026-05-02", "2026-05-22",
                                                   "2026-03-05", "2026-03-15", "2026-10-24")]


@pytest.mark.parametrize("answer", [
    "The data runs to Sept. 3rd.", "The data runs to 3 Sept.", "The data runs to May 2nd.",
    "The data runs to march 5th.", "The data runs to Sept. 23rd.", "The data runs to 23 Sept.",
    "The data runs to May 22nd.", "The data runs to march 15th.",
])
def test_a_real_year_less_date_is_not_a_figure(answer):
    assert unverified_numbers(answer, TOOL_DATES) == []


@pytest.mark.parametrize("answer, figure", [
    ("on 24 Oct 30 sentences were negative.", "30"),
    ("on 24 Oct 30 tweets were negative.", "30"),
    ("There were 45 may tweets.", "45"),
])
def test_a_count_next_to_a_date_is_checked(answer, figure):
    assert unverified_numbers(answer, TOOL_DATES) == [figure]


@pytest.mark.parametrize("noun", ["tweets", "threads", "replies"])
def test_a_count_before_a_month_and_another_count_noun_is_checked(noun):
    assert unverified_numbers(f"There were 21 Oct {noun} about fees.", TOOL) == ["21"]
