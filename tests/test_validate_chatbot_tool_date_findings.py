"""
Reviewer findings from the fourth validation of fix/chatbot-answers (after
commit f4b9145, which skips a year-less date only when a tool returned that
month and day). Each test asserts what the grounded chatbot claim needs, so it
fails while the finding is real; a confirmed finding carries xfail(strict=True).
Synthetic data only: no model, no network, no data/plp.db.
"""

import pytest

import chatbot.agent as agent
from chatbot.agent import _ToolCallTracker, answer_turn, enforce_evidence
from chatbot.guards import unverified_numbers

# A sentiment result as the chatbot's tools return it: data_runs_to is in every
# sentiment, compare and trend result.
RUNS_TO = {"bank": "DBS", "score": 0.31, "n": 45, "data_runs_to": "2026-09-25"}
SENT = [{"bank": "DBS", "score": 0.31, "n": 45}]


def _evidence(**item):
    return {"query": "q", "results": [{"sentence_id": "a" * 24, "bank": "DBS", "source": "reddit",
                                        "date": "2026-01-02", "text": "the app is slow", **item}]}


# --- Tool date hides invented figures -----------------------------------------------------

TOOL_DATE_HIDES = "Tool date hides invented figures: a returned date lets 'month day' swallow the figure"


@pytest.mark.parametrize("answer, figure", [
    ("In September 25.7% were negative.", "25.7%"),
    ("In September 25% of sentences were negative.", "25%"),
    ("In Sept 25,000 sentences", "25,000"),
    ("September 25.9 points", "25.9"),
])
def test_a_figure_after_a_month_is_checked_when_data_runs_to_has_that_day(answer, figure):
    assert figure in unverified_numbers(answer, [RUNS_TO])


def test_a_count_before_may_is_checked_when_an_evidence_item_has_that_day():
    assert "12" in unverified_numbers("12 may be bots", SENT + [_evidence(date="2026-05-12")])


def test_a_date_in_the_models_own_search_query_vouches_for_nothing():
    tools = SENT + [{"query": "complaints since 2026-09-25", "results": []}]
    assert "25" in unverified_numbers("In September 25 posts were negative.", tools)


def test_a_date_inside_a_link_vouches_for_nothing():
    tools = SENT + [_evidence(url="https://news.example/2026-09-25/story")]
    assert "25" in unverified_numbers("In September 25 posts were negative.", tools)


@pytest.mark.parametrize("answer, figure", [
    ("DBS reads slightly positive. In September 25.7% were negative.", "25.7%"),
    ("DBS reads slightly positive. In Sept 25,000 sentences were read.", "25,000"),
])
def test_answer_turn_flags_a_figure_hidden_behind_data_runs_to(monkeypatch, answer, figure):
    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(agent, "enforce_evidence_mode", lambda: "strip")
    monkeypatch.setitem(agent.TOOL_FUNCTIONS, "get_sentiment", lambda **k: dict(RUNS_TO))

    class Model:
        name = model = "fake"

        def ask(self, question, system, tool_schemas, tool_executor, verbose=True, history=None):
            tool_executor("get_sentiment", {"bank": "DBS"})
            return answer

    r = answer_turn("How is DBS?", backend=Model(), verbose=False)
    assert figure in r.unverified_numbers


# --- Date tests miss realistic tool data --------------------------------------------------
# The earlier date tests passed tools without a data_runs_to; the same cases with one
# (the tools of tests/test_validate_chatbot_reader_fix_probes.py, whose n is 120).

TOOL_DATES = [{"bank": "DBS", "score": 0.31, "n": 120}] + [{"data_runs_to": d} for d in ("2026-09-25", "2026-09-30", "2026-10-24")]


@pytest.mark.parametrize("answer, figure", [
    ("In September 25% of sentences were negative.", "25%"),
    ("In Sept. 30.5 percent were negative.", "30.5"),
    ("Negative share was 25% in September.", "25%"),
    ("June 30.5% of sentences were negative.", "30.5%"),
    ("Mentions rose to 47 in may.", "47"),
    ("On 25 Sept. 47 new posts appeared.", "47"),
    ("Sentences rose to 25 in May.", "25"),
    ("In May 45 sentences were negative.", "45"),
    ("In September 48 sentences were positive.", "48"),
])
def test_an_invented_figure_near_a_month_is_flagged_with_realistic_dates(answer, figure):
    assert figure in unverified_numbers(answer, TOOL_DATES)


def test_an_invented_figure_after_may_is_flagged_with_realistic_dates():
    assert "0.45" in unverified_numbers("DBS scored 0.45 may be read as mild optimism.",
                                        TOOL_DATES + [_evidence(date="2026-05-12")])


# --- Quote shapes still unchecked (main behaves the same) ---------------------------------

INVENTED = "OCBC will cut its dividend next year for sure"
QUOTE_SHAPES = "Quote shapes still unchecked: an invented quote in this shape is kept unflagged (also on main)"


def _tracker(search: bool):
    calls = [{"name": "get_sentiment", "arguments": {"bank": "OCBC"}, "result": {"score": 0.2, "n": 300}}]
    if search:
        calls.append({"name": "search_evidence", "arguments": {"query": "q"},
                      "result": _evidence(text="the app is slow on weekends for many users")})
    return _ToolCallTracker.from_calls(calls)


@pytest.mark.parametrize("search", [True, False])
@pytest.mark.parametrize("answer", [
    f'One post said "{INVENTED}"(Reddit).',
    f'One post said "{INVENTED}"… and more.',
    f'One post said "{INVENTED}"and left.',
    f'| OCBC |"{INVENTED}"|',
    f'One post said "{INVENTED} " ok.',
    f'One post said " {INVENTED}" ok.',
])
def test_an_invented_quote_in_an_odd_shape_is_caught(answer, search):
    out, flagged = enforce_evidence(answer, _tracker(search), "q", "strip")
    assert flagged or "next year for sure" not in out


@pytest.mark.parametrize("search", [True, False])
def test_an_invented_quote_in_a_spaced_markdown_table_cell_is_caught(search):
    answer = f'| Bank | Quote |\n|---|---|\n| OCBC | "{INVENTED}" |'
    out, flagged = enforce_evidence(answer, _tracker(search), "q", "strip")
    assert flagged or "next year for sure" not in out
