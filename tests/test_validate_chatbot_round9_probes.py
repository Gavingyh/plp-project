"""
Probes from the ninth validation of fix/chatbot-answers (after f511f83: a day
before a comma or a bracket reads as a date only when no other number follows
in its clause; "for" no longer marks a date; a word in quote marks is kept
whatever follows it, unless the glued words end where a quote may end; words
after a returned quote's closing mark are the model's own; a stray mark after a
quote's closing mark is not loose). Each test asserts what the grounded chatbot
claim needs, or that a correct answer is kept as written, so it fails while the
problem is real; a confirmed one carries xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

from chatbot import agent
from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers
from tests.quote_marks import in_quote_marks, removed_flagged_or_unquoted

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


def _not_searched():
    return _ToolCallTracker.from_calls([{"name": "get_sentiment", "arguments": {"bank": "DBS"},
                                         "result": {"score": 0.3, "n": 45}}])


# --- figures next to dates ---------------------------------------------------

# A returned date with no before-word, before a comma or bracket that a number
# follows, or before "for": all read as dates at 31c7e98, all flagged at f511f83.
# Fixed after this validation: after "by", "up to", "through", "ends"
# and the like a comma with no number right after it ends a date. Three stay
# flagged: "for" no longer ends a date (it hid "September 25 for DBS against 40 for
# UOB" until the eighth validation), and a bracket ends one only when it holds no
# digit, as such a bracket may hold a count ("Negative posts: September 25 (45 in
# August)." hid the 25 in a draft of this round's fix).
DATE_FALSE_ALARM = pytest.mark.xfail(
    strict=True, reason="recorded limit: a returned date before 'for' is flagged, an accepted false alarm, "
                        "as 'for' after a day may follow a count ('September 25 for DBS against 40 for UOB') "
                        "(docs/evidence/chatbot-answers-2026-10-04.md, Known limits)")
BRACKET_FALSE_ALARM = pytest.mark.xfail(
    strict=True, reason="recorded limit: a returned date before a bracket holding a digit is flagged, "
                        "an accepted false alarm, as such a bracket may hold a count "
                        "(docs/evidence/chatbot-answers-2026-10-04.md, Known limits)")


@pytest.mark.parametrize("answer", [
    "By September 25, DBS scored 0.31.",
    "Up to September 25, the score was 0.31.",
    "Through September 25, DBS scored 0.31.",
    "Coverage ends September 25, with 45 posts.",
    pytest.param("September 25 (45 posts).", marks=BRACKET_FALSE_ALARM),
    pytest.param("Data covers Sept 25-26 for DBS.", marks=DATE_FALSE_ALARM),
    pytest.param("Data to Sept 25 for all three banks.", marks=DATE_FALSE_ALARM),
])
def test_a_returned_date_is_not_flagged(answer):
    tools = TOOLS + [{"latest": "2026-09-26"}]
    assert unverified_numbers(answer, tools, "") == []


@pytest.mark.parametrize("answer, figure", [
    ("In September 25, 37 posts were negative.", "37"),
    ("In September 25, 37 posts and 45 others.", "25"),
    ("In September 25 (out of 40) posts.", "40"),
    ("September 25 for DBS against 40 for UOB.", "25"),
    ("In September 25, 31.5% posts.", "31.5%"),
    ("Sept 25, 1,234 posts.", "1,234"),
])
def test_an_invented_figure_next_to_a_returned_date_is_flagged(answer, figure):
    assert figure in unverified_numbers(answer, TOOLS, "")


# --- quotes --------------------------------------------------------------------

@pytest.mark.parametrize("tracker", [_searched, _not_searched], ids=["searched", "not_searched"])
@pytest.mark.parametrize("answer", [
    f'"So "{INVENTED}"" [1].',
    f'"{REAL}"" {INVENTED}',
    f'"{REAL}" {CITE}"\n"{INVENTED}"',
    f'""{INVENTED}"',
    f"One investor: '{INVENTED}'",
    f"As one user put it, '{INVENTED}'",
])
def test_an_invented_quote_is_removed_or_flagged(answer, tracker):
    out, flagged = enforce_evidence(answer, tracker(), "q", "strip")
    assert "next year for sure" not in out or flagged


# Changed to the contract of DESIGN decision 26 (after this validation):
# strip mode takes the quote marks off what a search doesn't vouch for, so in these
# shapes the invented words now stand outside quote marks, as the model's own,
# where until then they were removed. The real quote keeps its marks.
@pytest.mark.parametrize("tracker", [_searched, _not_searched], ids=["searched", "not_searched"])
@pytest.mark.parametrize("answer", [
    f'"OK "{REAL}" and {INVENTED}"',
    f'“OK “{REAL}” {INVENTED}”',
    f'"{REAL}" {CITE} {INVENTED}"',
    f'"{REAL}"*{INVENTED}*"',
    f'"x"{INVENTED} 5"',
])
def test_an_invented_quote_is_removed_flagged_or_no_longer_in_quote_marks(answer, tracker):
    out, flagged = enforce_evidence(answer, tracker(), "q", "strip")
    assert removed_flagged_or_unquoted(out, flagged, "next year for sure")


# Glued words kept: confirmed by this validation, fixed by DESIGN decision 26.
# Words glued to a closing mark stay, as the model's own, outside quote marks.
@pytest.mark.parametrize("answer", [
    f'“{REAL}”{INVENTED}.',
    f'“{REAL}”*{INVENTED}*',
    f'"x"{INVENTED}',
    f'""{INVENTED}',
])
def test_words_glued_to_a_closing_mark_are_removed_flagged_or_no_longer_in_quote_marks(answer):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert removed_flagged_or_unquoted(out, flagged, "next year for sure")


# Stray mark opens the next line: confirmed by this validation, fixed by DESIGN
# decision 26. The mark goes, and the words on the next line stand
# outside quote marks.
def test_a_mark_after_a_citation_opening_the_next_line_is_checked():
    answer = f'"{REAL}" {CITE}."\n{INVENTED}'
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert removed_flagged_or_unquoted(out, flagged, "next year for sure")
    assert f'"{REAL}" {CITE}.' in out


# Glued over-strip: confirmed by this validation, fixed by DESIGN decision 26.
# Strip mode reads no words glued to a closing mark as a quote; a word in
# quote marks and an inch mark keep their marks.
@pytest.mark.parametrize("answer", [
    'Users call it "PayLah"and say a 6" phone screen is too small.',
    '"DBS"and OCBC rose 5" in the chart.',
    '“real”DBS fell 5" ok',
    f'One user: “{REAL}”DBS also scored 0.31 on a 6" phone.',
])
def test_a_correct_answer_with_a_word_in_marks_and_an_inch_mark_is_kept(answer):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert out == answer and not flagged


@pytest.mark.parametrize("answer", [
    f'Mixed views. "{REAL}" {CITE}',
    f'One user: “{REAL}”DBS also scored 0.31.',
    f'One user: “{REAL}”and DBS also scored 0.31 [1].',
    f'They call it "PayLah"for short and the app is fine "really" today.',
    f'"Tier 1"ratios are fine; "{REAL}" {CITE}.',
    f'The app is "slow"; one user wrote "{REAL}" {CITE}.',
    "Note: 'app' is the top theme.",
])
def test_a_correct_answer_is_kept(answer):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert not flagged
    assert out == agent._drop_bare_marks(answer)


# --- the whole turn --------------------------------------------------------------

def _turn(monkeypatch, reply, calls):
    class Backend:
        name, model = "fake", "fake"

        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            for name, args in calls:
                execute(name, args)
            return reply

    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(agent, "TOOL_FUNCTIONS", {
        "search_evidence": lambda **kw: {"query": kw["query"], "results": [ITEM]},
        "get_sentiment": lambda **kw: {"bank": "DBS", "score": 0.31, "n": 45, "data_runs_to": "2026-09-25"}})
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    return agent.answer_turn("How is DBS doing?", backend=Backend(), verbose=False)


def test_answer_turn_flags_an_invented_count_after_a_returned_date(monkeypatch):
    r = _turn(monkeypatch, "In September 25, 37 posts were negative; DBS scored 0.31.",
              [("get_sentiment", {"bank": "DBS"})])
    assert "37" in (r.unverified_numbers or [])


def test_answer_turn_keeps_a_returned_date_unflagged(monkeypatch):
    r = _turn(monkeypatch, "By September 25, DBS scored 0.31 from 45 posts.",
              [("get_sentiment", {"bank": "DBS"})])
    assert not r.unverified_numbers


def test_answer_turn_strips_an_invented_quote_in_a_nested_quote(monkeypatch):
    # Since DESIGN decision 26 the outer marks come off: the invented
    # words stand outside quote marks, and the real quote keeps its own.
    r = _turn(monkeypatch, f'Mixed.\n\n"OK "{REAL}" and {INVENTED}" {CITE}',
              [("search_evidence", {"query": "app"})])
    assert removed_flagged_or_unquoted(r.answer, r.citation_unverified, "next year for sure")
    assert in_quote_marks(r.answer, REAL)
