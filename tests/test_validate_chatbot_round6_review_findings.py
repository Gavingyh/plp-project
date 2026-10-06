"""
Reviewer findings from the sixth validation of fix/chatbot-answers (after
6e1560f). Each test asserts what the grounded chatbot claim needs, so it fails
while the finding is real; a confirmed one carries xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers

SID = "0123" + "a" * 20
CITE = f"[DBS, 2026-09-20, sentence_id {SID}]"
REAL = "the app keeps logging me out every single time i open it"
INV = "the bank secretly charges invented hidden fees on every transfer"
ITEM = {"sentence_id": SID, "bank": "DBS", "source": "reddit", "date": "2026-09-20",
        "text": REAL, "url": "https://reddit.example/x", "cite_as": CITE}


def _tracker():
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [ITEM]}}])


def _invented_removed_or_flagged(answer: str) -> bool:
    out, flagged = enforce_evidence(answer, _tracker(), "q", "strip")
    return "invented hidden fees" not in out or flagged


def test_nested_quote_curly_outer_tail_is_checked():
    answer = f'One user wrote “I asked them "{REAL}" and they said {INV}” {CITE}'
    assert _invented_removed_or_flagged(answer)


def test_nested_quote_straight_outer_tail_is_checked():
    answer = f'One user wrote "I asked them “{REAL}” and they said {INV}" {CITE}'
    assert _invented_removed_or_flagged(answer)


def test_unclosed_quote_before_reddit_quote():
    answer = f'One said "{REAL}. Another wrote "{INV}"(Reddit) and more.'
    out, flagged = enforce_evidence(answer, _tracker(), "q", "strip")
    assert "invented hidden fees" not in out or flagged


def test_table_cell_closing_mark_quote_is_checked():
    answer = f'| DBS |”{INV}”| x |'
    assert _tracker().answer_has_unverified_citation(answer)
    assert _invented_removed_or_flagged(answer)


def test_table_cell_straight_quote_is_checked():
    assert _tracker().answer_has_unverified_citation(f'| DBS |"{INV}"| x |')


def test_count_before_to_percent_is_flagged():
    flagged = unverified_numbers("In September 25 to 30% of posts were negative.",
                                 [{"data_runs_to": "2026-09-25"}])
    assert any(f.startswith("25") for f in flagged), flagged


def test_returned_day_before_word_is_not_flagged():
    flagged = unverified_numbers("On September 25 for DBS the score was 0.31",
                                 [{"data_runs_to": "2026-09-25", "score": 0.31}])
    assert not any(f.startswith("25") for f in flagged), flagged
