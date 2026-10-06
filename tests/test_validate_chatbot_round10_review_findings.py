"""
Reviewer findings from the tenth validation of fix/chatbot-answers. Each test
asserts what the grounded chatbot claim needs, so it fails while the finding
is real; a confirmed one carries xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

from chatbot.agent import _ToolCallTracker, enforce_evidence, number_citations
from chatbot.guards import unverified_numbers

SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
REAL = "the app is slow to load at night"
INVENTED = "OCBC will cut its dividend next year for sure"
ITEM = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
        "text": REAL, "url": "https://news.example/x", "cite_as": CITE}


def _searched():
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [ITEM]}}])


# --- citation outlives a demarked quote ---------------------------------------

@pytest.mark.parametrize("answer", [
    f"One user: ‹{INVENTED}›. {CITE}",
    f'"{REAL}" "\n{INVENTED}, one user wrote {CITE}',
    f'One user: ‹{INVENTED}›, {CITE}',
    f'One user: ‹{INVENTED}› - {CITE}',
    f'One user: ‹{INVENTED}› ({CITE})',
    f'One user: ‹{INVENTED}›（{CITE}）',
])
def test_a_citation_after_a_removed_mark_goes_or_the_answer_is_flagged(answer):
    tracker = _searched()
    out, flagged = enforce_evidence(answer, tracker, "q", "strip")
    shown = number_citations(out, tracker)
    line = next((ln for ln in shown.splitlines() if INVENTED in ln), "")
    assert flagged or not line or ("[1]" not in line and SID not in line), shown


# --- two-word invented quote with a citation ------------------------------------

@pytest.mark.parametrize("quote", ['"a scam"', "“total scam”", '"unusable"'])
def test_a_short_invented_quote_with_a_citation_is_flagged_or_unquoted(quote):
    answer = f"One user called OCBC {quote} {CITE}"
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert flagged or quote not in out or SID not in out, out


@pytest.mark.parametrize("quote", ['"a scam"', "“total scam”", '"unusable"'])
def test_off_mode_flags_a_short_invented_quote_with_a_citation(quote):
    assert enforce_evidence(f"One user called OCBC {quote} {CITE}", _searched(), "q", "off")[1]


# --- glued opening mark read as an apostrophe ------------------------------------

@pytest.mark.parametrize("answer, mark", [
    (f"One user wrote‘the bank will cut its dividend next year’ {CITE}", "‘"),
    ("Users called it‘a total disaster for everyone’.", "‘"),
    (f"One user wrote'the bank will cut its dividend next year' {CITE}", "'the bank"),
])
def test_a_glued_opening_mark_before_invented_words_goes_or_is_flagged(answer, mark):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert flagged or mark not in out, out


# --- numbers in evidence text vouch for counts ------------------------------------

def test_a_number_in_evidence_text_does_not_vouch_for_an_unquoted_count():
    tools = [{"query": "q", "results": [dict(ITEM, text="I paid 37 dollars in fees at DBS")]},
             {"bank": "DBS", "score": 0.31, "n": 45}]
    assert unverified_numbers("DBS had 37 negative posts out of 45.", tools) == ["37"]
