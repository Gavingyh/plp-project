"""
Reviewer findings from the fifth validation of fix/chatbot-answers (after
04af72a, which pairs quote marks in order, and 6e8298b). Each test asserts what
the grounded chatbot claim needs, so it fails while the finding is real; a
confirmed finding carries xfail(strict=True). Synthetic data only: no model,
no network, no data/plp.db.
"""

import pytest

from chatbot.agent import _QUOTE_PATTERN, _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers

SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
INVENTED = "OCBC will cut its dividend next year for sure"


def _tracker():
    item = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
            "text": "the app is slow to load at night", "url": "https://news.example/x", "cite_as": CITE}
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [item]}}])


def _removed_or_flagged(answer: str) -> bool:
    out, flagged = enforce_evidence(answer, _tracker(), "q", "strip")
    return "next year for sure" not in out or flagged


@pytest.mark.parametrize("answer", [
    f'One user called the app "a nightmare to use. Another wrote "{INVENTED}" {CITE}.',
    f'- One user called the app "a nightmare to use.\n- Another wrote "{INVENTED}" {CITE}.',
])
def test_an_unclosed_quote_does_not_let_the_next_invented_quote_through(answer):
    assert _removed_or_flagged(answer)


@pytest.mark.parametrize("answer", [
    f'On a 6" phone "{INVENTED}" ok',
    f'"He said "{INVENTED}" to fees"',
])
def test_a_quote_after_a_stray_or_nested_mark_is_checked(answer):
    assert _removed_or_flagged(answer)


def test_an_invented_single_quoted_quote_is_removed_or_flagged():
    assert _removed_or_flagged(f"One post said '{INVENTED}' {CITE}.")


@pytest.mark.parametrize("answer", [f"One said »{INVENTED}« ok.", f"One said ”{INVENTED}” ok."])
def test_a_quote_opened_with_a_closing_mark_is_found(answer):
    assert _QUOTE_PATTERN.findall(answer)


def test_a_bare_count_after_a_month_is_checked():
    tools = [{"score": 0.3, "n": 45, "data_runs_to": "2026-09-25"}]
    assert "25" in unverified_numbers("In September 25 sentences were negative.", tools)


def test_a_nested_marker_does_not_crash_enforcement():
    enforce_evidence("See note [1[2]] here", _ToolCallTracker(), "q", "strip")
