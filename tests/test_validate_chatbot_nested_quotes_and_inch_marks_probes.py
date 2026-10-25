"""
Probes from the seventh validation of fix/chatbot-answers (after 7446c89: quote
marks known by the letters and digits around them, nested quotes, inch marks;
a returned day after a month is a date unless a count follows). Each test
asserts what the grounded chatbot claim needs, so it fails while the problem is
real; a confirmed one carries xfail(strict=True). Synthetic data only: no
model, no network, no data/plp.db.
"""

import pytest

from chatbot import agent
from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers

SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
REAL = "the app is slow to load at night"
INVENTED = "OCBC will cut its dividend next year for sure"
ITEM = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
        "text": REAL, "url": "https://news.example/x", "cite_as": CITE}
TOOLS = [{"score": 0.3, "n": 45, "data_runs_to": "2026-09-25"}]


def _tracker(text=REAL):
    item = dict(ITEM, text=text)
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [item]}}])


def _removed_or_flagged(answer: str) -> bool:
    out, flagged = enforce_evidence(answer, _tracker(), "q", "strip")
    return "next year for sure" not in out or flagged


# The new shapes of 7446c89, each holding an invented quote: all caught.
@pytest.mark.parametrize("answer", [
    f'It was bad."{INVENTED}" {CITE}',                 # a straight mark after punctuation
    f'It was bad!"{INVENTED}"(Reddit) ok',
    f'Note."{INVENTED}” ok',                            # straight open, curly close
    f'“the target is 78" and {INVENTED}” ok',           # an inch mark inside a curly quote
    f'«the target is 78" and {INVENTED}» ok',
    f'“a 6" phone and a 7" tablet {INVENTED}”',
    f'"{REAL}" said one. "{INVENTED}" said another.',   # two quotes, not one around the gap
    f'"{REAL}", then “{INVENTED}”, then "{REAL}"',
    f'One: "{REAL} “and” {INVENTED}"',                  # a nested curly pair
    f'“{REAL}" and “{INVENTED}”',
    f'He said "{REAL}" — and "{INVENTED}" {CITE}',
    f'- "{INVENTED}" {CITE}',
    f'1. “{INVENTED}” {CITE}',
    f'**"{INVENTED}"**',
    f'_"{INVENTED}"_',
    f'He said:"{INVENTED}"',
    f'| DBS | "{INVENTED}" |',
    f'|"{INVENTED}"|',
    f'He said "{INVENTED}',
    f'He said “{INVENTED}',
    f'Posts at 12" screens: "{INVENTED}"',
    f'2"x3" frame: "{INVENTED}"',
    f'”{INVENTED}” ok',
    f'»{INVENTED}« ok',
    f"‘{INVENTED}’ ok",
])
def test_an_invented_quote_in_the_new_shapes_is_removed_or_flagged(answer):
    assert _removed_or_flagged(answer)


# Correct answers stay as written.
@pytest.mark.parametrize("answer", [
    f'One post said "{REAL}" {CITE}.',
    f'“{REAL}” {CITE}',
    f'- "{REAL}" {CITE}',
    f'**"{REAL}"** {CITE}',
    f'_"{REAL}"_ {CITE}',
    f'"{REAL}"(Reddit)',
    'On a 6" phone the app is slow.',
    'The 12" and 13" laptops both look fine for "work".',
])
def test_a_correct_answer_is_kept_and_not_flagged(answer):
    out, flagged = enforce_evidence(answer, _tracker(), "q", "strip")
    assert out.startswith(answer) and not flagged


def test_a_scare_quote_keeps_its_words_without_its_marks():
    # Until DESIGN decision 26 a case of the test above: since then a
    # passage of three or more words that no search returned loses its quote marks.
    out, flagged = enforce_evidence("DBS's 'customer first digital approach' is praised.", _tracker(), "q", "strip")
    assert out == "DBS's customer first digital approach is praised." and not flagged


def test_a_real_quote_with_a_comma_inside_its_marks_is_kept():
    answer = f'One said "{REAL}," and more {CITE}'
    out, flagged = enforce_evidence(answer, _tracker("The app is slow to load at night."), "q", "strip")
    assert REAL in out and not flagged


def test_an_invented_quote_in_low_nine_marks_is_removed_or_flagged():
    assert _removed_or_flagged(f"One post said „{INVENTED}“ {CITE}")


def test_answer_turn_strips_an_invented_quote_after_punctuation(monkeypatch):
    class Backend:
        name, model = "fake", "fake"

        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            execute("search_evidence", {"query": "app"})
            return f'Mixed views.“the target is 78" and {INVENTED}” and "{REAL}" {CITE}'

    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(agent, "TOOL_FUNCTIONS", {
        "search_evidence": lambda **kw: {"query": kw["query"], "results": [ITEM]}})
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    r = agent.answer_turn("What do people say about the DBS app?", backend=Backend(), verbose=False)
    assert ("next year for sure" not in r.answer or r.citation_unverified) and REAL in r.answer


# Dates: a returned day is a date, a count beside it a figure.
@pytest.mark.parametrize("answer, figure", [
    ("September 25 sentences were negative.", "25"),
    ("September 25 negative comments", "25"),
    ("September 25 Reddit posts", "25"),
    ("September 25 percent", "25"),
    ("September 25 to 31 posts", "31"),
    ("September 25-31% negative", "31%"),
    ("about September 25, 46 posts", "46"),
    ("Sep 25: 31 posts", "31"),
])
def test_an_invented_count_beside_a_returned_date_is_flagged(answer, figure):
    assert figure in unverified_numbers(answer, TOOLS)


@pytest.mark.parametrize("answer", [
    "Data runs to September 25.",
    "Data runs to September 25 for DBS.",
    "Data to 25 September.",
    "Data runs to September 25th.",
])
def test_a_returned_date_is_not_flagged(answer):
    assert unverified_numbers(answer, TOOLS) == []
