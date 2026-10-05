"""
Reviewer findings from the seventh validation of fix/chatbot-answers (after
7446c89). Each test asserts what the grounded chatbot claim needs, so it fails
while the finding is real; a confirmed one carries xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers

SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
REAL = "the app is slow to load at night"
INV = "the bank secretly charges invented hidden fees on every transfer"
ITEM = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
        "text": REAL, "url": "https://news.example/x", "cite_as": CITE}


def _tracker():
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [ITEM]}}])


def _caught(answer: str, phrase: str) -> bool:
    out, flagged = enforce_evidence(answer, _tracker(), "q", "strip")
    return phrase not in out or flagged


# Unlisted count noun hides day: a returned day followed by a count noun not on
# the fixed list is blanked as a date, so an invented count passes.
@pytest.mark.parametrize("text", [
    "In September 25 customers complained about fees.",
    "In September 25 complaints were about fees.",
    "In September 25 DBS posts were negative.",
    "In September 25 very angry posts appeared.",
    "In September 25 or so posts were negative.",
])
def test_unlisted_count_noun_after_returned_day_is_checked(text):
    tools = [{"data_runs_to": "2026-09-25", "score": 0.31, "n": 120}]
    assert "25" in unverified_numbers(text, tools)


# Inch-holding quote swallows next opener: an inch mark in one quote makes the
# detector run on to the next quote's opening mark, leaving the invented quote out.
@pytest.mark.parametrize("answer", [
    f'One user said “my rate went up to 5" in one post {CITE}. Another wrote ”{INV}” {CITE}',
    f'- “the fee rose 5" {CITE}\n- ”{INV}” {CITE}',
    f'«fees rose 5" {CITE} and »{INV}« {CITE}',
])
def test_inch_mark_quote_does_not_hide_next_quote(answer):
    assert _caught(answer, "invented hidden fees")


# Short single-quoted inventions pass: a single-quoted passage under six words
# is never checked, while a double-quoted one is checked from ten characters.
def test_short_single_quoted_invention_is_caught():
    assert _caught(f"One user wrote 'banks secretly charge hidden fees' {CITE}", "secretly charge")


# Merged nested quotes strip real quote: two inner quotes inside an outer one
# are read as one span, so the real quote is stripped with the invented one.
@pytest.mark.xfail(strict=True, reason="recorded limit: merged nested quotes strip a real quote, as a quote "
                                       "holding quotes of the other style is checked and removed whole (the safe "
                                       "direction; docs/evidence/chatbot-answers-2026-10-04.md, Known limits)")
@pytest.mark.parametrize("answer", [
    f'One said "x “{REAL}” and “{INV}” y" {CITE}',
    f'“{REAL} "and" {INV}” {CITE}',
])
def test_real_quote_kept_next_to_invented_one(answer):
    out, _ = enforce_evidence(answer, _tracker(), "q", "strip")
    assert REAL in out
