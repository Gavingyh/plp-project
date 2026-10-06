"""
Probes from the twelfth validation of fix/chatbot-answers (after 174c77d: a
citation vouches for its own sentence, off mode flags what strip changes,
figures vouch through their nearest words). Each test asserts what the
grounded chatbot claim needs, or that a correct answer is kept as written, so
it fails while the problem is real; a confirmed one carries xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

from chatbot import agent
from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers
from tests.quote_marks import in_quote_marks

SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
REAL = "the app is slow to load at night"
INVENTED = "OCBC will cut its dividend next year"
ITEM = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
        "text": REAL, "url": "https://news.example/x", "cite_as": CITE}


def _searched(item=ITEM):
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [item]}}])


def _turn(monkeypatch, answer, item=ITEM):
    class Backend:
        name, model = "fake", "fake"

        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            execute("search_evidence", {"query": "app"})
            return answer

    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(agent, "TOOL_FUNCTIONS", {
        "search_evidence": lambda **kw: {"query": kw["query"], "results": [item]}})
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    return agent.answer_turn("What do people say about the DBS app?", backend=Backend(), verbose=False)


# --- invented quotes in many shapes: strip leaves none shown, nothing flagged --

INVENTED_SHAPES = {
    "long_introduction": f'As one long-time user on the DBS subreddit put it {CITE}, "{INVENTED}".',
    "colon_then_list": f'Users said {CITE}:\n- "{INVENTED}"\n- "{REAL}"',
    "colon_blank_line_list": f'Users said {CITE}:\n\n- "{INVENTED}"',
    "unlisted_abbreviation": f'Per the Sgt. on the forum "{INVENTED}" {CITE}.',
    "lower_case_start": f'One user wrote "{REAL}" {CITE}. another wrote "{INVENTED}".',
    "unclosed": f'One user wrote "{INVENTED} {CITE}.',
    "nested": f"One user wrote \"they said '{INVENTED}' online\" {CITE}.",
    "guillemets": f"One user wrote «{INVENTED}» {CITE}.",
    "low_high_marks": f"One user wrote „{INVENTED}“ {CITE}.",
    "single_marks": f"One user wrote '{INVENTED}' {CITE}.",
    "list_items": f'- "{REAL}" {CITE}\n- "{INVENTED}"',
    "numbered_list": f'1. "{INVENTED}"\n2. {CITE}',
    "blockquote_lazy": f'> "{INVENTED}"\n> {CITE}',
    "blockquote_plain": f"> {INVENTED} {CITE}",
    "stray_closing_mark": f'One user wrote: {INVENTED}" {CITE}.',
    "emphasised_quote": f'One user wrote *"{INVENTED}"* {CITE}.',
    "citation_first": f'{CITE} One user wrote "{INVENTED}".',
    "semicolon": f'Users complain "{REAL}"; {CITE} "{INVENTED}".',
    "real_then_invented": f'One user wrote "{REAL} and {INVENTED}" {CITE}.',
    "ellipsis_join": f'One user wrote "the app is slow ... {INVENTED}" {CITE}.',
}


@pytest.mark.parametrize("answer", list(INVENTED_SHAPES.values()), ids=list(INVENTED_SHAPES))
def test_strip_shows_no_invented_quote(answer):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert not flagged
    assert not in_quote_marks(out, INVENTED)
    assert not (INVENTED in out and CITE in out), out


@pytest.mark.parametrize("answer", list(INVENTED_SHAPES.values()), ids=list(INVENTED_SHAPES))
def test_off_mode_flags_an_invented_quote(answer):
    assert enforce_evidence(answer, _searched(), "q", "off")[1]


# --- correct answers stay as written ------------------------------------------

CORRECT = {
    "plain": f'One user wrote "{REAL}" {CITE}.',
    "long_introduction": f'According to a long-time user of the bank {CITE}, "{REAL}".',
    "colon_then_list": f'Users said {CITE}:\n- "{REAL}"',
    "abbreviation": f'Users (e.g. commuters) say "{REAL}" {CITE}.',
    "single_marks": f"One user wrote '{REAL}' {CITE}.",
    "two_sentences": f'Users said "{REAL}" {CITE}. Others agreed "{REAL}" {CITE}.',
    "blockquote_lazy_citation": f"> {REAL}\n{CITE}",
}


@pytest.mark.parametrize("answer", list(CORRECT.values()), ids=list(CORRECT))
def test_a_correct_answer_is_kept_and_unflagged(answer):
    assert enforce_evidence(answer, _searched(), "q", "strip") == (answer, False)
    assert not enforce_evidence(answer, _searched(), "q", "off")[1]


def test_answer_turn_strips_an_invented_quote_after_a_long_introduction(monkeypatch):
    r = _turn(monkeypatch, INVENTED_SHAPES["long_introduction"])
    assert INVENTED not in r.model_answer and not r.citation_unverified


BLOCKQUOTE_CITATION_LINE = [f'> "{REAL}"\n> {CITE}', f"> {REAL}\n> {CITE}"]
BLOCKQUOTE_REASON = ("recorded limit: blockquote citation line flagged: a returned blockquote with its citation on its own "
                     "'> ' line is flagged in off mode and loses the '> ' in strip (also at f7a90fb)")


@pytest.mark.xfail(strict=True, reason=BLOCKQUOTE_REASON)
@pytest.mark.parametrize("answer", BLOCKQUOTE_CITATION_LINE, ids=["marked", "plain"])
def test_a_returned_blockquote_with_its_citation_on_the_next_line_is_kept(answer):
    assert enforce_evidence(answer, _searched(), "q", "strip") == (answer, False)
    assert not enforce_evidence(answer, _searched(), "q", "off")[1]


BACKTICK_REASON = ("recorded limit: invented text in backticks keeps its citation: words no search returned, shown in a code "
                   "span next to a citation, are kept and unflagged in strip and off mode (also at f7a90fb)")


@pytest.mark.xfail(strict=True, reason=BACKTICK_REASON)
def test_invented_words_in_backticks_lose_their_citation():
    answer = f"One user wrote `{INVENTED}` {CITE}."
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert flagged or not (INVENTED in out and CITE in out)


# --- figures vouched by a retrieved sentence about something else -------------

def _results(text):
    return [{"query": "q", "results": [{**ITEM, "text": text}]}]


FIGURE_REASON = ("recorded limit: figure vouched by subject words: a retrieved figure vouches for the same number of a "
                 "different quantity when two of its nearest words are the subject ('the DBS app had 30 "
                 "minutes' vouches for '30 negative posts')")
MOVED = [
    ("the DBS app had 30 minutes of downtime", "The DBS app had 30 negative posts."),
    ("DBS mobile app crashed 13 times during payday", "Negative posts: 13 on the DBS mobile app."),
]


@pytest.mark.xfail(strict=True, reason=FIGURE_REASON)
@pytest.mark.parametrize("retrieved,answer", MOVED, ids=["minutes_to_posts", "times_to_posts"])
def test_a_figure_of_another_quantity_is_flagged(retrieved, answer):
    figure = next(w for w in answer.split() if w.isdigit())
    assert figure in unverified_numbers(answer, _results(retrieved), "What do people say?")


@pytest.mark.xfail(strict=True, reason=FIGURE_REASON)
def test_answer_turn_flags_a_figure_of_another_quantity(monkeypatch):
    item = {**ITEM, "text": "the DBS app had 30 minutes of downtime"}
    r = _turn(monkeypatch, f"The DBS app had 30 negative posts {CITE}.", item)
    assert "30" in r.unverified_numbers


@pytest.mark.parametrize("retrieved,answer,figure", [
    ("the app crashed 13 times on 2026-09-01", "On 2026-09-01 the app crashed 14 times.", "14"),
    ("the app crashed 13 times on 2026-09-01", "The app crashed 13 times; sentiment fell 13 points.", "13"),
    ("DBS fees rose 12% in 2025", "DBS fees rose 15% in 2025.", "15%"),
    ("I paid 37 dollars in fees", "DBS had 37 negative posts.", "37"),
])
def test_an_invented_figure_near_returned_words_is_flagged(retrieved, answer, figure):
    assert figure in unverified_numbers(answer, _results(retrieved), "What do people say?")


def test_a_returned_figure_in_its_own_words_is_not_flagged():
    assert unverified_numbers("The DBS app crashed 13 times.", _results("the app crashed 13 times"), "q") == []
