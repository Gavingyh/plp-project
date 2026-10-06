"""
Reviewer findings on fix/chatbot-answers after the fixes of 4 Oct 2026
(commit 8082469). Each test fails if its finding is real; a confirmed finding
carries xfail(strict=True). Synthetic data, plus one recorded gold-set row
under data/eval/. No model, no network, no data/plp.db.
"""

import os

import pytest

from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers
from chatbot.judge import load_results

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = "ocbc raised its dividend this quarter"
INVENTED = "OCBC will cut its dividend next year for sure"


def _tracker():
    return _ToolCallTracker.from_calls([{
        "name": "search_evidence", "arguments": {"query": "q"},
        "result": {"results": [{"sentence_id": "b" * 24, "text": REAL, "url": "https://news.example/ocbc"}]}}])


# --- Strip keeps quotes beside markers ------------------------------------------------------

@pytest.mark.parametrize("answer", [
    f'One analyst said "{INVENTED} [2]".',
    f'One analyst said "{INVENTED}"[2].',
])
def test_strip_removes_an_invented_quote_beside_a_bare_marker(answer):
    out, _ = enforce_evidence(answer, _tracker(), "q", "strip")
    assert INVENTED not in out


# --- Bare marker flags real quotes ----------------------------------------------------------

def test_a_real_quote_followed_by_a_marker_is_not_flagged():
    assert not _tracker().answer_has_unverified_citation(f'One report said "{REAL}" [1].')


RECORDED = "data/eval/chatbot_eval_results_llama3.1_8b_10aspects_2026-09-30.jsonl"


def test_recorded_answer_with_real_quotes_and_markers_is_not_flagged():
    path = os.path.join(ROOT, RECORDED)
    if not os.path.exists(path):
        pytest.skip(f"{RECORDED} not present")
    row = next(r for r in load_results(path) if r["id"] == "evidence-1")
    tracker = _ToolCallTracker.from_calls(row["tool_calls"])
    answer = row.get("model_answer") or row["answer"]
    assert not tracker.unverified_quotes(answer) and not tracker.unverified_urls(answer)   # all quotes real
    assert not tracker.answer_has_unverified_citation(answer)


# --- Day-first date pattern hides counts ----------------------------------------------------

@pytest.mark.parametrize("answer, figure", [
    ("The total was 27\nSeptember was quieter.", "27"),
    ("DBS had a score with 21 Oct sentences.", "21"),
    ("The change was -21 May data.", "-21"),
])
def test_a_count_before_a_month_word_is_flagged(answer, figure):
    assert unverified_numbers(answer, [{"score": 0.777}]) == [figure]
