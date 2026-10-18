"""
The answer says which period its evidence and scores cover. Asked about DBS's app,
the model passed window="30d" on its own, so the quotes and the score covered only the
last 30 days, and the reader was never told. Each tool result now carries a plain
`period` ("the last 30 days of data (26 Aug 2026 to 25 Sep 2026)"), the prompt asks the
model to state it, and the harness adds a "Period searched" line so it is always there.
"""

import pytest

from chatbot import agent, tools
from chatbot.agent import Conversation, _ToolCallTracker, answer_turn, period_footer
from chatbot.prompts import SYSTEM_PROMPT
from tests.test_chatbot_reader import _index


def _data(temp_db):
    # Newest sentence on 2026-08-28 (month cells put sentences on days 1 to 28).
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 8, 1, 1)])
    return tools.data_as_of()


# --- the words ---------------------------------------------------------------------------

def test_period_text_names_the_days_and_the_dates(temp_db):
    newest = _data(temp_db)
    assert tools.period_text("all_time").startswith("all stored data, up to ")
    week = tools.period_text("7d")
    assert week.startswith("the last 7 days of data (") and week.endswith(")") and " to " in week
    assert tools.period_text("30d").startswith("the last 30 days of data (")
    assert tools.period_text("30d", newest=newest) == tools.period_text("30d")


def test_period_text_is_empty_before_any_data(temp_db):
    assert tools.period_text("30d") == ""


# --- the tool results --------------------------------------------------------------------

def test_a_search_result_names_its_period(temp_db, monkeypatch):
    _data(temp_db)
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    week = tools.chat_search_evidence("DBS app", bank="DBS", window="7d")
    assert week["period"] == tools.period_text("7d") and week["evidence_from"] < week["evidence_to"]
    assert tools.chat_search_evidence("DBS app", bank="DBS")["period"].startswith("all stored data")


def test_a_score_result_names_its_period(temp_db):
    _data(temp_db)
    r = tools.chat_get_sentiment("DBS", "dividend_policy", "30d")
    assert r["period"] == tools.period_text("30d")


# --- the prompt and the line under the answer ---------------------------------------------

def test_the_prompt_asks_for_the_period():
    text = " ".join(SYSTEM_PROMPT.split())
    assert "period" in text and "state the period" in text


def test_the_footer_lists_each_period_once(temp_db, monkeypatch):
    _data(temp_db)
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    tracker = _ToolCallTracker()
    tracker.execute("search_evidence", {"query": "DBS app", "bank": "DBS", "window": "30d"})
    tracker.execute("get_sentiment", {"bank": "DBS", "window": "30d"})
    tracker.execute("get_sentiment", {"bank": "DBS", "window": "all_time"})
    footer = period_footer(tracker)
    assert footer == (f"Period searched: {tools.period_text('30d')}; {tools.period_text('all_time')}. "
                      f"{tools.default_period_sentence()}")


def test_no_footer_without_a_lookup():
    assert period_footer(_ToolCallTracker()) == ""


class _Backend:
    name, model = "fake", "fake-model"

    def __init__(self, answer, **call):
        self.answer, self.call = answer, call

    def ask(self, question, system, schemas, execute, verbose=True, history=None):
        if self.call:
            execute("search_evidence", self.call)
        return self.answer


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(agent.intents, "classify_intent", lambda *a, **k: None)
    monkeypatch.setattr(agent.intents, "reply_for", lambda *a, **k: None)
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])


def test_the_answer_ends_with_the_period_searched(temp_db, quiet):
    _data(temp_db)
    r = answer_turn("DBS app?", backend=_Backend("Nothing was found about the DBS app.",
                                                 query="DBS app", bank="DBS", window="30d"), verbose=False)
    assert r.answer.rstrip().endswith(f"Period searched: {tools.period_text('30d')}. {tools.default_period_sentence()}")
    assert r.model_answer == "Nothing was found about the DBS app."          # the model's own text is unchanged


def test_no_period_line_when_nothing_was_looked_up(temp_db, quiet):
    _data(temp_db)
    r = answer_turn("DBS app?", backend=_Backend("Hello."), verbose=False)
    assert "Period searched" not in r.answer


def test_no_period_line_on_a_withheld_answer(temp_db, quiet):
    _data(temp_db)
    r = answer_turn("DBS app?", backend=_Backend("DBS scored 0.99.", query="DBS app", bank="DBS"), verbose=False)
    assert r.repaired == "withheld" and "Period searched" not in r.answer


def test_the_period_line_is_not_sent_back_to_the_model_as_history():
    text = "Nothing found.\n\nPeriod searched: all stored data, up to 25 Sep 2026."
    assert "Period searched" not in agent._strip_warnings(text)
