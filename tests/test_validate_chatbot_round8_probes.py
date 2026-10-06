"""
Probes from the eighth validation of fix/chatbot-answers (after 31c7e98: quote
marks the checks can't place flag the answer and take their line in strip mode;
single quotes after a cue word or a colon are checked; a returned day after a
month is a date only where it reads as one). Each test asserts what the
grounded chatbot claim needs, or that a correct answer is kept as written, so it
fails while the problem is real; a confirmed one carries xfail(strict=True).
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
TOOLS = [{"score": 0.3, "n": 45, "data_runs_to": "2026-09-25"}]


def _searched():
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [ITEM]}}])


def _not_searched():
    return _ToolCallTracker.from_calls([{"name": "get_sentiment", "arguments": {"bank": "DBS"},
                                         "result": {"score": 0.3, "n": 45}}])


# Invented quotes in the shapes 31c7e98 changed: removed or flagged, with or
# without a search.
@pytest.mark.parametrize("tracker", [_searched, _not_searched], ids=["searched", "not_searched"])
@pytest.mark.parametrize("answer", [
    f'for sure!" {INVENTED}',
    f'sure!" "{INVENTED}"',
    f'"x" sure" "{INVENTED}',
    f'a 6" and "{INVENTED}',
    f'"a 6" {INVENTED}"',
    f'„{REAL}“ „{INVENTED}“',
    f'“{REAL}“ {INVENTED}”',                  # an opening mark typed to close
    f'«{REAL}« {INVENTED}»',
    f'”{REAL}” ”{INVENTED}”',
    f'Line one "{REAL}\n{INVENTED}"',
    f'"{REAL}" [1] "{INVENTED}" [2]',
    f'"{INVENTED}" [1, 2]',
    f"One user wrote: '{INVENTED}'",
    f"'{REAL}' and '{INVENTED}'",
    f'"{REAL} ‘{INVENTED}’ end" ok',
    f'"{REAL}" "{INVENTED}"',
    f'| "{REAL}" | "{INVENTED}" |',
    f'"{INVENTED}"\n\n"{REAL}"',
])
def test_an_invented_quote_is_removed_or_flagged(answer, tracker):
    out, flagged = enforce_evidence(answer, tracker(), "q", "strip")
    assert "next year for sure" not in out or flagged


# Changed to the contract of DESIGN decision 26 (5 Oct 2026, after the ninth
# validation): strip mode takes the quote marks off what a search doesn't vouch for,
# so the words after a real quote's closing mark now stand outside quote marks, as
# the model's own, where until then they were removed.
@pytest.mark.parametrize("tracker", [_searched, _not_searched], ids=["searched", "not_searched"])
@pytest.mark.parametrize("answer", [
    f'"{REAL}"{INVENTED}"',                   # a closing mark with a letter after it
    f'“{REAL}”{INVENTED}“',
    f'"{REAL}" *{INVENTED}*"',
])
def test_an_invented_quote_is_removed_flagged_or_no_longer_in_quote_marks(answer, tracker):
    out, flagged = enforce_evidence(answer, tracker(), "q", "strip")
    assert removed_flagged_or_unquoted(out, flagged, "next year for sure")


def test_answer_turn_strips_an_invented_quote_after_a_closing_mark(monkeypatch):
    class Backend:
        name, model = "fake", "fake"

        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            execute("search_evidence", {"query": "app"})
            return f'Mixed views.\n\n"{REAL}" {CITE}\n\n“{REAL}”{INVENTED}“'

    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(agent, "TOOL_FUNCTIONS", {
        "search_evidence": lambda **kw: {"query": kw["query"], "results": [ITEM]}})
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    r = agent.answer_turn("What do people say about the DBS app?", backend=Backend(), verbose=False)
    # Since DESIGN decision 26 (5 Oct 2026): or no longer in quote marks.
    assert removed_flagged_or_unquoted(r.answer, r.citation_unverified, "next year for sure")
    assert in_quote_marks(r.answer, REAL)


# Correct answers that 31c7e98 still keeps as written.
@pytest.mark.parametrize("answer", [
    f'One post said "{REAL}" {CITE}.',
    'The "Tier 1" ratio and "CET1" rose.',
    'DBS calls it a "digibank"; OCBC calls it "OneWealth".',
    'Mixed marks: “service” and "fees" dominate.',
    'Reddit users post about “PayLah!” and «NETS».',
    "It's DBS's and OCBC's year; users' views vary.",
    'A 27" monitor and a "work" PC.',
    "The theme is 'customer service' (Reddit) mostly.",
    '“DBS”的分数上升。',
])
def test_a_correct_answer_is_kept(answer):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert out == answer and not flagged


# Confirmed, and fixed after this validation: a word in quote marks with a letter
# right after the closing mark ('"DBS"and', '"buy-now"s') left both marks unplaced,
# so strip mode deleted the whole line. 7446c89 and main keep each of these as written.
@pytest.mark.parametrize("answer", [
    '"DBS"and "OCBC" both rose.',
    'Users dislike the "buy-now"s offer.',
    'The terms "fees" and "charges"s are common.',
    '"Tier 1"and "CET1" rose.',
    'Users said “fees”and «app» matter.',
    'Fees rose. "fees"are high.',
])
def test_a_word_in_quote_marks_without_a_space_after_is_kept(answer):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert out == answer and not flagged


# Confirmed, and fixed after this validation: the cue words' noun forms (report,
# note, post) and a label's colon ("Note:") made a three to five word term in single
# marks a checked quote, so after a search a correct term was stripped. 7446c89 and
# main keep them. Changed by DESIGN decision 26 (5 Oct 2026): the words stay, but a
# term of three or more words that no search returned loses its quote marks.
@pytest.mark.parametrize("answer, shown", [
    ("Users report 'long queue times' at branches.", "Users report long queue times at branches."),
    ("The bank's report notes 'net interest margin' fell.", "The bank's report notes net interest margin fell."),
    ("The posts note that 'customer service quality' is down.",
     "The posts note that customer service quality is down."),
    ("Window: last 90 days. Note: 'fees are high' is the theme.",
     "Window: last 90 days. Note: fees are high is the theme."),
])
def test_a_term_in_single_marks_after_a_cue_noun_keeps_its_words(answer, shown):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert out == shown and not flagged


# Dates: a returned day reads as a date only where it reads as one.
@pytest.mark.parametrize("answer", [
    "In September 25 customers complained.",
    "September 25 of the 45 posts were negative.",
    "Sept 25 & 45 sentences.",
    "Sept 25 / 45 posts.",
    "September 25 per cent of posts.",
    "Sept 25-30% of posts.",
    "Sept 25 percent.",
    "Sept. 25 users complained.",
    "In September 25 or so posts",
    "In September 25 posts",
    "In September 25\tposts",
])
def test_an_invented_count_on_a_returned_day_is_flagged(answer):
    assert any(f.strip("%") == "25" for f in unverified_numbers(answer, TOOLS, "q"))


@pytest.mark.parametrize("answer", [
    "Data runs to September 25.",
    "On September 25 DBS scored 0.3.",
    "September 25, 45 posts.",
    "As of September 25 users were unhappy.",
])
def test_a_returned_date_is_not_flagged(answer):
    assert unverified_numbers(answer, TOOLS, "q") == []
