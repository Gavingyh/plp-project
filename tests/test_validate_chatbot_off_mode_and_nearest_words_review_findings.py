"""
Reviewer findings from the twelfth validation of fix/chatbot-answers (after
174c77d). Each test asserts the behaviour the grounded chatbot claim needs, so
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


def _searched(item=ITEM):
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [item]}}])


def _results(text):
    return [{"query": "q", "results": [{**ITEM, "text": text}]}]


# --- Source note after quote keeps citation -----------------------------------

SOURCE_NOTE_REASON = ("recorded limit: Source note after quote keeps citation: a citation behind a source note "
                      "('(Reddit, CITE)') never reads the quote in the sentence before it")

SOURCE_NOTE_SHAPES = {
    "paren_reddit": f'One user called OCBC "a scam". (Reddit, {CITE})',
    "a_reddit_post": f'One user called OCBC "a scam". A Reddit post {CITE}.',
    "dash_reddit_user": f'One user called OCBC "a scam". - a Reddit user {CITE}',
    "semicolon_see": f'One user called OCBC "a scam"; see the post {CITE}.',
    "source_label": f'One user called OCBC "a scam". Source: a Reddit thread {CITE}',
    "single_marks": f"One user called OCBC 'a scam'. (Reddit, {CITE})",
    "next_line": f'One user called OCBC "a scam".\n(Reddit, {CITE})',
}


@pytest.mark.xfail(strict=True, reason=SOURCE_NOTE_REASON)
@pytest.mark.parametrize("answer", list(SOURCE_NOTE_SHAPES.values()), ids=list(SOURCE_NOTE_SHAPES))
def test_strip_removes_unreturned_quote_behind_source_note(answer):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert flagged or not ("a scam" in out and CITE in out), out


@pytest.mark.xfail(strict=True, reason=SOURCE_NOTE_REASON)
@pytest.mark.parametrize("answer", list(SOURCE_NOTE_SHAPES.values()), ids=list(SOURCE_NOTE_SHAPES))
def test_off_flags_unreturned_quote_behind_source_note(answer):
    _, flagged = enforce_evidence(answer, _searched(), "q", "off")
    assert flagged


@pytest.mark.xfail(strict=True, reason=SOURCE_NOTE_REASON)
def test_strip_does_not_show_invented_passage_with_citation():
    invented = "OCBC will cut its dividend next year"
    out, flagged = enforce_evidence(f"One user: ‹{invented}›. (Reddit, {CITE})", _searched(), "q", "strip")
    assert flagged or not (invented in out and CITE in out), out


# --- Nearest-word figure rule vouches counts ----------------------------------

FIGURE_REASON = ("recorded limit: Nearest-word figure rule vouches counts: two topic words near a retrieved figure "
                 "vouch for the same number used as a post count")


@pytest.mark.xfail(strict=True, reason=FIGURE_REASON)
@pytest.mark.parametrize("retrieved,answer,figure", [
    ("On 1 Sep 2026 DBS raised fees by 45 dollars.", "On 1 Sep 2026, 45 posts about DBS fees were negative.", "45"),
    ("DBS charges S$37 in fees.", "S$37 of the posts were negative, DBS fees.", "37"),
], ids=["dollars_as_posts", "currency_as_posts"])
def test_retrieved_amount_does_not_vouch_for_post_count(retrieved, answer, figure):
    assert figure in unverified_numbers(answer, _results(retrieved), "q")


# --- Blockquote citation line flagged correct ---------------------------------

BLOCKQUOTE_REASON = ("recorded limit: Blockquote citation line flagged correct: strip drops the '>' of a citation-only "
                     "blockquote line, so off mode flags a correct quote")


@pytest.mark.xfail(strict=True, reason=BLOCKQUOTE_REASON)
@pytest.mark.parametrize("answer", [f"> {REAL}\n> {CITE}", f'> "{REAL}"\n> {CITE}'], ids=["plain", "quoted"])
def test_correct_blockquote_kept_and_not_flagged(answer):
    out, _ = enforce_evidence(answer, _searched(), "q", "strip")
    assert out == answer
    _, flagged = enforce_evidence(answer, _searched(), "q", "off")
    assert not flagged
