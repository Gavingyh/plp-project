"""
Reviewer findings from the third validation of fix/chatbot-answers (after
commit b79fbc3). Each test asserts the behaviour the grounded chatbot claim
needs, so it fails while the finding is real; a confirmed finding carries
xfail(strict=True). Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

import chatbot.agent as agent
from chatbot.agent import _ToolCallTracker, answer_turn, enforce_evidence, number_citations
from chatbot.guards import unverified_numbers

TOOL = [{"score": 0.12, "n": 3}]
A = "ocbc raised its dividend this quarter"
B = "dbs fees remain a sore point for many customers"


def _item(sid, bank, text):
    return {"sentence_id": sid * 24, "bank": bank, "source": "cna", "date": "2026-09-02", "text": text,
            "url": f"https://news.example/{sid}", "cite_as": f"[{bank}, 2026-09-02, sentence_id {sid * 24}]"}


IA, IB = _item("a", "OCBC", A), _item("b", "DBS", B)


def _tracker(*items):
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"results": [dict(i) for i in items]}}])


# --- Monthly count lists hidden by dates ------------------------------------------------------

@pytest.mark.parametrize("answer, figures", [
    ("Mentions by month:\n- July 18\n- August 24\n- September 29\n", ["18", "24", "29"]),
    ("In September 29\nposts were negative", ["29"]),
])
def test_counts_listed_one_month_per_line_are_checked(answer, figures):
    assert unverified_numbers(answer, TOOL) == figures


# --- Markers inside quotes point at wrong sources ---------------------------------------------

def test_an_invented_marker_inside_a_real_quote_does_not_reach_the_reader():
    tracker = _tracker(IA, IB)
    answer = f'Users said "{A} [2]" {IA["cite_as"]} and "{B}" {IB["cite_as"]}.'
    out, flagged = enforce_evidence(answer, tracker, "q", "strip")
    shown = number_citations(out, tracker)
    assert flagged or f'"{A} [2]"' not in shown


# --- Unclosed or mixed quotes go unchecked (also on main) ------------------------------------

@pytest.mark.parametrize("answer", [
    'He said "the app is the best in all of Singapore and more.',
    'He said “the app is the best in all of Singapore and more." ok',
])
def test_an_unclosed_or_mixed_invented_quote_is_caught(answer):
    out, flagged = enforce_evidence(answer, _tracker(IA), "q", "strip")
    assert flagged or "best in all of Singapore" not in out


# --- Counts before uncovered nouns hidden -----------------------------------------------------

@pytest.mark.parametrize("answer, figure", [
    ("There were 21 Oct tweets", "21"),
    ("21 Oct threads", "21"),
    ("23 Sep replies", "23"),
    ("21 October negative sentences", "21"),
])
def test_a_count_before_a_month_and_an_uncovered_noun_is_checked(answer, figure):
    assert unverified_numbers(answer, TOOL) == [figure]


# --- Marker regex drops bracketed ranges ------------------------------------------------------

class _Model:
    name, model = "fake", "fake"

    def __init__(self, answer):
        self.answer = answer

    def ask(self, question, system, tool_schemas, tool_executor, verbose=True, history=None):
        return self.answer


@pytest.mark.parametrize("answer, bracket, figure", [
    ("Scores sat in a range [12-45] last month.", "[12-45]", "45"),
    ("Scores run on a scale of [0, 1] here.", "[0, 1]", None),
])
def test_a_bracketed_range_is_kept_or_its_figures_checked(monkeypatch, answer, bracket, figure):
    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(agent, "enforce_evidence_mode", lambda: "strip")
    r = answer_turn("How is DBS?", backend=_Model(answer), verbose=False)
    assert bracket in r.answer or (figure is not None and figure in r.unverified_numbers)
