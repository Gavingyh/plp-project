"""
Reviewer findings from the eleventh validation of fix/chatbot-answers (after
f7a90fb). Each test asserts what the grounded chatbot claim needs, so it fails
while the finding is real; a confirmed one carries xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

from chatbot.agent import _ToolCallTracker, enforce_evidence, number_citations
from chatbot.guards import unverified_numbers

SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
REAL = "the app is slow to load at night"
URL = "https://news.example/x"
INV = "OCBC will cut its dividend next year for sure"
ITEM = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
        "text": REAL, "url": URL, "cite_as": CITE}


def _searched():
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [ITEM]}}])


def _sentiment_only():
    return _ToolCallTracker.from_calls([{"name": "get_sentiment", "arguments": {"bank": "DBS"},
                                         "result": {"bank": "DBS", "score": 0.31, "n": 45}}])


# --- short quote cited by link, or by a citation that does not lead its line ---

SHORT_REASON = ("Short quote cited by link: a two-word quote no search returned, cited by a link or by a "
                "citation before it on the line, is kept and unflagged")
SHORT_ANSWERS = [f'One user called OCBC "a scam" ({URL}).',
                 f'According to {CITE}, one user called OCBC "a scam".']


@pytest.mark.parametrize("answer", SHORT_ANSWERS, ids=["link", "citation_first"])
def test_short_unreturned_quote_with_a_source_is_stripped(answer):
    assert enforce_evidence(answer, _searched(), "q", "strip")[0] != answer


@pytest.mark.parametrize("answer", SHORT_ANSWERS, ids=["link", "citation_first"])
def test_short_unreturned_quote_with_a_source_is_flagged_in_off_mode(answer):
    assert enforce_evidence(answer, _searched(), "q", "off")[1]


# --- a returned one-word term shields an invented, de-marked passage ---

SHIELD_REASON = ("Returned term shields invented citation: a returned one-word quote stops the citation's "
                 "backward stretch, so de-marked invented words keep a numbered source, unflagged")
# The single guillemets are the marks the reviewer used: they are de-marked, not cut, so the
# invented words stay on show. Straight or curly double marks get the passage cut whole.
SHIELD_ANSWERS = [f'One user: ‹{INV}›, "slow" {CITE}',
                  f'One user wrote ‹{INV}› calling the app "slow" {CITE}']


@pytest.mark.parametrize("answer", SHIELD_ANSWERS, ids=["list", "calling"])
def test_returned_term_does_not_shield_invented_words(answer):
    tracker = _searched()
    out, flagged = enforce_evidence(answer, tracker, "q", "strip")
    shown = number_citations(out, tracker)
    assert not (INV in shown and "[1]" in shown)


@pytest.mark.parametrize("answer", SHIELD_ANSWERS, ids=["list", "calling"])
def test_off_mode_flags_a_shielded_invented_passage(answer):
    assert enforce_evidence(answer, _searched(), "q", "off")[1]


# --- figures vouched for by common words of an unrelated sentence ---

FIG_REASON = ("Figure vouched by common words: a 3-word window like '37% of the' found in an unrelated "
              "retrieved sentence verifies a share of posts no tool returned")
SENT = {"bank": "DBS", "score": 0.31, "n": 45}


def _search(text):
    return {"query": "q", "results": [{"sentence_id": SID, "text": text, "url": "u"}]}


@pytest.mark.parametrize("answer,text", [
    ("37% of the posts about DBS were negative.", "Around 37% of the bank's profit came from wealth"),
    ("37 per cent of the posts about DBS were negative.",
     "Around 37 per cent of the bank's profit came from wealth"),
    ("DBS had 37… in fees, negative posts out of 45.", "I paid 37 dollars in fees at DBS"),
], ids=["percent_sign", "per_cent", "ellipsis"])
def test_figure_not_vouched_by_unrelated_sentence(answer, text):
    assert "37" in " ".join(unverified_numbers(answer, [_search(text), SENT]))


# --- glued opening mark across a line break ---

GLUED_REASON = ("Glued quote across line kept: an opening mark glued to the word before is read as an "
                "apostrophe when the closing mark is on the next line, so invented words stay, unflagged")


@pytest.mark.parametrize("mark", ["’", "'"], ids=["curly", "straight"])
def test_glued_quote_across_a_line_is_handled(mark):
    answer = f"One user wrote{mark}the bank will cut its\ndividend next year{mark} {CITE}"
    out, _ = enforce_evidence(answer, _searched(), "q", "strip")
    assert f"wrote{mark}the bank" not in out


@pytest.mark.parametrize("mark", ["\u2019", "'"], ids=["curly", "straight"])
def test_off_mode_flags_a_glued_quote_across_a_line(mark):
    answer = f"One user wrote{mark}the bank will cut its\ndividend next year{mark} {CITE}"
    assert enforce_evidence(answer, _searched(), "q", "off")[1]


# --- a real blockquote after a de-marked line keeps its citation ---

BLOCK_REASON = ("Real blockquote loses its citation: the citation's stretch reaches back past the '>' line "
                "to the de-marked line above, so a returned quote loses its source")


def test_real_blockquote_keeps_its_citation():
    answer = f"One user: ‹{INV}›.\n> {REAL} {CITE}"
    assert CITE in enforce_evidence(answer, _searched(), "q", "strip")[0]


# --- evidence markers with no search ---

MARK_REASON = ("Evidence markers kept without search: [E1]-style markers survive strip mode and are not "
               "flagged in off mode when no search was made")
MARK_ANSWERS = [f"Users say {INV} [E1][E2].", f"Users say {INV} [E1], [E2].", f"Users say {INV} [E1, E2]."]


@pytest.mark.parametrize("answer", MARK_ANSWERS, ids=["adjacent", "comma", "list"])
def test_evidence_markers_without_search_are_stripped(answer):
    assert "[E" not in enforce_evidence(answer, _sentiment_only(), "q", "strip")[0]


@pytest.mark.parametrize("answer", MARK_ANSWERS, ids=["adjacent", "comma", "list"])
def test_evidence_markers_without_search_are_flagged_in_off_mode(answer):
    assert enforce_evidence(answer, _sentiment_only(), "q", "off")[1]
