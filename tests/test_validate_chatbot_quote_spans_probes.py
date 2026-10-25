"""
Probes from the sixth validation of fix/chatbot-answers (after 6e1560f, which
combines pattern-based quote spans with ordered pairing in the gaps between
them). Each test asserts what the grounded chatbot claim needs, so it fails
while the problem is real; a confirmed one carries xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

from chatbot import agent
from chatbot.agent import _QUOTE_PATTERN, _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers

SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
REAL = "the app is slow to load at night"
INVENTED = "OCBC will cut its dividend next year for sure"
ITEM = {"sentence_id": SID, "bank": "DBS", "source": "google_news", "date": "2026-09-01",
        "text": REAL, "url": "https://news.example/x", "cite_as": CITE}


def _tracker():
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"query": "q", "results": [ITEM]}}])


def _removed_or_flagged(answer: str) -> bool:
    out, flagged = enforce_evidence(answer, _tracker(), "q", "strip")
    return "next year for sure" not in out or flagged


# Correct answers stay as written.
@pytest.mark.parametrize("answer", [
    f'One post said "{REAL}" {CITE}.',
    f'One post said "the app is slow\nto load at night” {CITE}.',
])
def test_a_real_quote_is_kept_and_not_flagged(answer):
    out, flagged = enforce_evidence(answer, _tracker(), "q", "strip")
    assert "slow" in out and not flagged


# Shapes that were already handled in this round's probes: kept as guards.
@pytest.mark.parametrize("answer", [
    f'- "{REAL}" {CITE}\n- "{INVENTED} {CITE}',
    f'He said "{REAL} and "{INVENTED} today.',
    f'On a 6" phone, "{INVENTED}"(Reddit)',
    f'"{REAL}" and a 6" screen "{INVENTED}"',
    f'“{REAL} and he said "{INVENTED}" ok',
    f'One post: “He wrote "a nice short quote" and then {INVENTED}” {CITE}.',
    f'One post: "He wrote “a nice short quote” and then {INVENTED}" ok.',
])
def test_an_invented_quote_near_odd_marks_is_removed_or_flagged(answer):
    assert _removed_or_flagged(answer)


def test_the_words_after_a_nested_quote_are_checked():
    assert _removed_or_flagged(f'One post: “Someone told me "fees are too high" but {INVENTED}”.')


@pytest.mark.parametrize("answer", [
    f'He said "unclosed thing and also "{INVENTED}"(Reddit) ok',
    f'He said "{REAL} and later "{INVENTED}"(Reddit).',
])
def test_an_invented_quote_after_an_unclosed_one_is_checked(answer):
    assert _removed_or_flagged(answer)


@pytest.mark.parametrize("answer", [
    f"|DBS|”{INVENTED}”|",
    f"One said ”{INVENTED}”(Reddit).",
    f"|DBS|»{INVENTED}«|",
])
def test_a_quote_opened_with_a_closing_mark_in_odd_places_is_checked(answer):
    assert _removed_or_flagged(answer)


def test_answer_turn_does_not_present_the_invented_quote(monkeypatch):
    class Backend:
        name, model = "fake", "fake"

        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            execute("search_evidence", {"query": "app"})
            return f'He said "{REAL} and later "{INVENTED}"(Reddit).'

    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(agent, "TOOL_FUNCTIONS", {
        "search_evidence": lambda **kw: {"query": kw["query"], "results": [ITEM]}})
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "strip")
    r = agent.answer_turn("What do people say about the DBS app?", backend=Backend(), verbose=False)
    assert "next year for sure" not in r.answer or r.citation_unverified


def test_scare_quotes_in_single_marks_are_not_stripped():
    out, flagged = enforce_evidence("DBS's 'customer first digital approach' is praised.", _tracker(), "q", "strip")
    assert "customer first digital approach" in out and not flagged


def test_a_returned_date_before_for_is_not_flagged():
    tools = [{"score": 0.3, "n": 45, "data_runs_to": "2026-09-25"}]
    assert unverified_numbers("Data runs to September 25 for DBS.", tools) == []


@pytest.mark.parametrize("answer, figure", [
    ("In September 25 sentences were negative.", "25"),
    ("On September 25, 12% were negative.", "12%"),
    ("September 25: 33 posts", "33"),
    ("Sept. 25, 99 posts", "99"),
    ("data to September 25th; 17 sentences", "17"),
])
def test_an_invented_figure_beside_a_returned_date_is_flagged(answer, figure):
    tools = [{"score": 0.3, "n": 45, "data_runs_to": "2026-09-25"}]
    assert figure in unverified_numbers(answer, tools)


def test_the_spans_never_overlap():
    text = f'“Someone told me "fees are too high" but {INVENTED}”, "x" and \'{REAL}\' and "{REAL}"'
    spans = [(m.start(), m.end()) for m in _QUOTE_PATTERN.finditer(text)]
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))
