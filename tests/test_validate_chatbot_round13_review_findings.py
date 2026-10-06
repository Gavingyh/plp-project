"""
Reviewer findings from the thirteenth validation of fix/chatbot-answers (after
420ea79). Each test asserts the behaviour the grounded chatbot claim needs, so
it fails while the finding is real; a confirmed one carries xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers

SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
REAL = "the app is slow to load at night"
ITEM = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
        "text": REAL, "url": "https://news.example/x", "cite_as": CITE}
INVENTED = '"OCBC is cutting its payout in 2027"'
CLAIM = "OCBC will cut its dividend next year"


def _searched():
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [ITEM]}}])


# --- Removed quote leaves its citation ------------------------------------------

QUOTE_CITE_REASON = ("recorded limit: Removed quote leaves its citation: strip removes an invented quote but keeps a citation "
                     "not directly after it, now vouching for the model's own claim")

LEFT_CITATION_SHAPES = {
    "em_dash": f"{CLAIM}: {INVENTED} — {CITE}",
    "en_dash": f"{CLAIM}: {INVENTED} – {CITE}",
    "hyphen": f"{CLAIM}: {INVENTED} - {CITE}",
    "bold": f"{CLAIM}: **{INVENTED}** {CITE}",
    "italic": f"{CLAIM}: _{INVENTED}_ {CITE}",
    "close_paren": f"{CLAIM} ({INVENTED}) {CITE}",
    "comma": f"{CLAIM}: {INVENTED}, {CITE}",
    "table_cell": f"| {CLAIM} | {INVENTED} | {CITE} |",
    "next_line": f"{CLAIM}: {INVENTED}\n{CITE}",
}


@pytest.mark.xfail(strict=True, reason=QUOTE_CITE_REASON)
@pytest.mark.parametrize("answer", list(LEFT_CITATION_SHAPES.values()), ids=list(LEFT_CITATION_SHAPES))
def test_strip_removes_citation_of_removed_quote(answer):
    out, _ = enforce_evidence(answer, _searched(), "q", "strip")
    assert "payout in 2027" not in out
    assert SID not in out, out


@pytest.mark.parametrize("answer", [f"{CLAIM}: {INVENTED} {CITE}", f"{CLAIM} ({INVENTED} {CITE})"],
                         ids=["plain", "inside_paren"])
def test_strip_removes_citation_right_after_removed_quote(answer):
    out, _ = enforce_evidence(answer, _searched(), "q", "strip")
    assert SID not in out, out


@pytest.mark.parametrize("answer", list(LEFT_CITATION_SHAPES.values()), ids=list(LEFT_CITATION_SHAPES))
def test_off_flags_invented_quote(answer):
    _, flagged = enforce_evidence(answer, _searched(), "q", "off")
    assert flagged


# --- Year-range counts and durations unchecked ------------------------------------

TOOL = [{"bank": "DBS", "n": 45, "positive_n": 20, "score": 0.31}]
YEAR_REASON = ("recorded limit: Year-range counts and durations unchecked: a count from 1990 to 2100, a number before "
               "day/week/month/year, or one under 10 is never checked")


@pytest.mark.xfail(strict=True, reason=YEAR_REASON)
@pytest.mark.parametrize("answer,figure", [
    ("DBS had 2045 negative posts.", "2045"),
    ("DBS sentiment has been negative for 37 days.", "37"),
    ("DBS had 7 negative posts.", "7"),
], ids=["year_range_count", "duration", "under_ten"])
def test_invented_count_is_flagged(answer, figure):
    assert figure in unverified_numbers(answer, TOOL, "q")


def test_ordinary_invented_count_is_flagged():
    assert unverified_numbers("DBS had 212 negative posts.", TOOL, "q") == ["212"]


# --- Per-cent words bypass share check ---------------------------------------------

PERCENT_REASON = ("recorded limit: Per-cent words bypass share check: '45 per cent' is checked as a plain number, "
                  "so a count of 45 passes as a share")


def test_count_as_percent_sign_is_flagged():
    assert unverified_numbers("45% of DBS posts were positive.", TOOL, "q") == ["45%"]


@pytest.mark.xfail(strict=True, reason=PERCENT_REASON)
@pytest.mark.parametrize("word", ["per cent", "percent", "pct"])
def test_count_as_percent_word_is_flagged(word):
    assert unverified_numbers(f"45 {word} of DBS posts were positive.", TOOL, "q")


# --- Leading-decimal figures never read --------------------------------------------

@pytest.mark.xfail(strict=True, reason="recorded limit: leading-decimal figures never read: '.87' is not read as a figure")
def test_leading_decimal_figure_is_flagged():
    assert unverified_numbers("DBS score was .87.", [{"score": 0.31}], "q")
