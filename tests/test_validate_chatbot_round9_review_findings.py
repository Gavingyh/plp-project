"""
Reviewer findings from the ninth validation of fix/chatbot-answers (after
f511f83). Each test asserts what the grounded chatbot claim needs, or that a
correct answer is kept as written, so it fails while the finding is real; a
confirmed one carries xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers
from tests.quote_marks import in_quote_marks

SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
REAL = "the app is slow to load at night"
INVENTED = "OCBC will cut its dividend next year for sure"
ITEM = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
        "text": REAL, "url": "https://news.example/x", "cite_as": CITE}
TOOLS = [{"score": 0.31, "n": 45, "data_runs_to": "2026-09-25"}]


def _searched():
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [ITEM]}}])


# --- Stray rule hides opening mark --------------------------------------------
# Confirmed by this validation, fixed by DESIGN decision 26: the rule
# went; off mode flags the mark, and strip mode takes it off, so the invented words
# on the next line stand outside quote marks (changed from "not in stripped" to the
# decision's contract: removed, or no longer in quote marks).

@pytest.mark.parametrize("answer", [
    f'"{REAL}" "\n{INVENTED}',
    f'"{REAL}" {CITE} "\n{INVENTED}',
    f'- "{REAL}" {CITE} "\n- {INVENTED}',
    f'“{REAL}” “\n{INVENTED}',
    f'Users wrote "{REAL}" {CITE} "\n{INVENTED}\n\nOverall sentiment is mixed.',
], ids=["plain", "citation", "list", "curly", "paragraph"])
def test_an_opening_mark_at_line_end_after_a_real_quote_is_caught(answer):
    _, flagged = enforce_evidence(answer, _searched(), "q", "off")
    stripped, _ = enforce_evidence(answer, _searched(), "q", "strip")
    assert flagged and (INVENTED not in stripped or not in_quote_marks(stripped, INVENTED))
    assert in_quote_marks(stripped, REAL)


# --- Abbreviation ends the date clause ----------------------------------------

# Confirmed by this validation, fixed after it: a clause no longer ends
# at the full stop of an abbreviation, and a bracket ends a date only where its
# clause ends right after it.
@pytest.mark.parametrize("answer", [
    "In September 25, vs. 45 in August, posts were negative.",
    "In September 25, approx. 40 posts were negative.",
    "In September 25, i.e. 40 more posts.",
    "In September 25 (approx.) posts were negative.",
])
def test_an_invented_count_before_an_abbreviation_is_flagged(answer):
    assert "25" in unverified_numbers(answer, TOOLS, "")


# --- Bracket with 'of' flags real date ----------------------------------------

# Confirmed by this validation, fixed after it: only "of" before a
# number in the bracket ("(out of 40)") makes the day a count to check.
@pytest.mark.parametrize("answer", [
    "The latest post is September 25 (the end of the data).",
    "Latest data: September 25 (end of the window).",
])
def test_a_returned_date_before_a_bracket_with_of_is_not_flagged(answer):
    assert unverified_numbers(answer, TOOLS, "") == []
