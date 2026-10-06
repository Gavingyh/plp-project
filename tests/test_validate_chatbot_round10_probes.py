"""
Probes from the tenth validation of fix/chatbot-answers (after 03dc631: strip
mode shows only quotes a search returned, each ellipsis piece as whole words;
date clauses end only at sentence ends). Each test asserts what the grounded
chatbot claim needs, or that a correct answer is kept as written, so it fails
while the problem is real; a confirmed one carries xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

from chatbot import agent
from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers
from tests.quote_marks import in_quote_marks, removed_flagged_or_unquoted

SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
REAL = "the app is slow to load at night"
INVENTED = "OCBC will cut its dividend next year"
ITEM = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
        "text": REAL, "url": "https://news.example/x", "cite_as": CITE}
TOOLS = [{"score": 0.31, "n": 45, "data_runs_to": "2026-09-25"}, {"latest": "2026-09-26"}]


def _searched():
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [ITEM]}}])


def _not_searched():
    return _ToolCallTracker.from_calls([{"name": "get_sentiment", "arguments": {"bank": "DBS"},
                                         "result": {"score": 0.3, "n": 45}}])


def _blockquoted_after_cr(text: str, phrase: str) -> bool:
    """Whether markdown shows the phrase in a blockquote when a lone carriage
    return ends a line, as CommonMark reads it (a CR not followed by LF is a
    line ending). tests/quote_marks.py splits lines on LF only."""
    return in_quote_marks(text.replace("\r\n", "\n").replace("\r", "\n"), phrase)


# --- carriage-return line endings --------------------------------------------

CR_ANSWERS = [
    f"He said\r> {INVENTED}\r",
    f"He said:\r\r> {INVENTED}",
    f"Users:\r- > {INVENTED}",
    f"Users:\r>{INVENTED} {CITE}",
]


@pytest.mark.parametrize("answer", CR_ANSWERS)
@pytest.mark.parametrize("tracker", [_searched, _not_searched], ids=["searched", "not_searched"])
def test_an_invented_blockquote_after_a_carriage_return_is_removed_or_flagged(answer, tracker):
    out, flagged = enforce_evidence(answer, tracker(), "q", "strip")
    assert INVENTED not in out or flagged or not _blockquoted_after_cr(out, INVENTED)


@pytest.mark.parametrize("answer", CR_ANSWERS[:3])
def test_off_mode_flags_an_invented_blockquote_after_a_carriage_return(answer):
    assert enforce_evidence(answer, _searched(), "q", "off")[1]


def test_answer_turn_strips_an_invented_blockquote_after_a_carriage_return(monkeypatch):
    class Backend:
        name, model = "fake", "fake"

        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            execute("search_evidence", {"query": "app"})
            return f'Mixed views. "{REAL}" {CITE}\r> {INVENTED}'

    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(agent, "TOOL_FUNCTIONS", {
        "search_evidence": lambda **kw: {"query": kw["query"], "results": [ITEM]}})
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    r = agent.answer_turn("What do people say about the DBS app?", backend=Backend(), verbose=False)
    assert INVENTED not in r.answer or r.citation_unverified or not _blockquoted_after_cr(r.answer, INVENTED)


# The same answers with LF or CRLF line endings: removed, as the claim needs.
@pytest.mark.parametrize("answer", [f"He said\n> {INVENTED}\n", f"He said\r\n> {INVENTED}\r\n"])
@pytest.mark.parametrize("tracker", [_searched, _not_searched], ids=["searched", "not_searched"])
def test_an_invented_blockquote_after_lf_or_crlf_is_removed(answer, tracker):
    out, flagged = enforce_evidence(answer, tracker(), "q", "strip")
    assert removed_flagged_or_unquoted(out, flagged, INVENTED)


# --- invented quotes in new mark styles and shapes: all held at 03dc631 ------

@pytest.mark.parametrize("answer", [
    f"❮{INVENTED}❯", f"❟{INVENTED}❜", f"❠{INVENTED}❞", f"\U0001f678{INVENTED}\U0001f677",
    f"&#x201C;{INVENTED}&#x201D;", f'"{REAL}... {INVENTED}" {CITE}', f'"{INVENTED} 2" {CITE}',
    f'"{REAL}" {CITE}"{INVENTED}"', f'1. "{REAL}" {CITE}\n2. "{INVENTED}" {CITE}',
    f"DBS' fans: '{INVENTED}'", f'"{REAL}\r"{INVENTED}"\r',
])
@pytest.mark.parametrize("tracker", [_searched, _not_searched], ids=["searched", "not_searched"])
def test_an_invented_quote_is_removed_flagged_or_unquoted(answer, tracker):
    out, flagged = enforce_evidence(answer, tracker(), "q", "strip")
    assert removed_flagged_or_unquoted(out, flagged, INVENTED)


@pytest.mark.parametrize("answer", ['"the app is sl"', '"pp is slow to load at night"'])
def test_a_partial_word_quote_loses_its_marks_and_citation(answer):
    out, flagged = enforce_evidence(f"{answer} {CITE}", _searched(), "q", "strip")
    assert out == answer.strip('"') and not flagged


@pytest.mark.parametrize("answer", [
    f"One user wrote “{REAL}” {CITE}.",
    f'"{REAL}," one said {CITE}.',
    f'"the app is slow … at night" {CITE}',
    f'- "{REAL}" {CITE}\n- DBS scored 0.3.',
    f'"The app is slow to load at night" {CITE}',
    "DBS's app and the banks' fees",
])
def test_a_correct_answer_is_kept(answer):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert out == answer and not flagged


# --- figures next to returned dates: all flagged at 03dc631 ------------------

@pytest.mark.parametrize("answer, figure", [
    ("By September 25 (37 posts), DBS led.", "37"),
    ("Through Sept 25, 2026, 37 posts.", "37"),
    ("By September 25, DBS led, with 37 posts.", "37"),
    ("Up to September 25, about 37 posts.", "37"),
    ("Since September 25,\n37 posts.", "37"),
    ("By **September 25**, DBS had 37 posts.", "37"),
    ("Data runs to September 25.37 posts were negative.", "37"),
])
def test_an_invented_figure_next_to_a_returned_date_is_flagged(answer, figure):
    assert any(figure in str(g) for g in unverified_numbers(answer, TOOLS, ""))


@pytest.mark.parametrize("answer", [
    "Through Sept 25, 2026, DBS scored 0.31.",
    "As of 25 September 2026, DBS scored 0.31.",
    "Coverage ends September 25, 2026.",
    "In late September, DBS scored 0.31.",
])
def test_a_returned_date_is_not_flagged(answer):
    assert unverified_numbers(answer, TOOLS, "") == []
