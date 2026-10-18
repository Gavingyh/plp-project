"""
With no period named, the chatbot's tools use CHATBOT_DEFAULT_WINDOW, all stored data unless set otherwise,
and the answer says so under it. A 30- or 7-day default that holds too little to report falls back to all
stored data. The tests below that use a 30-day default set it, as a deployment would.
The API's own defaults are unchanged.
"""

import pytest

from chatbot import settings, tools
from chatbot.agent import _ToolCallTracker, period_footer
from chatbot.prompts import SYSTEM_PROMPT
from tests.test_chatbot_reader import _index

ALL_BANKS = [(b, "dividend_policy", "2026-08", 8, 1, 1) for b in ("DBS", "OCBC", "UOB")]
THIN_RECENT = [("DBS", "dividend_policy", "2026-01", 8, 1, 1), ("DBS", "dividend_policy", "2026-08", 1, 1, 0)]


@pytest.fixture
def thirty_days(monkeypatch):
    monkeypatch.setenv("CHATBOT_DEFAULT_WINDOW", "30d")


def test_the_default_window_is_all_stored_data(monkeypatch):
    monkeypatch.delenv("CHATBOT_DEFAULT_WINDOW", raising=False)
    assert settings.get("default_window") == "all_time"


def test_a_score_with_no_window_uses_all_stored_data_by_default(temp_db, monkeypatch):
    monkeypatch.delenv("CHATBOT_DEFAULT_WINDOW", raising=False)
    _index(temp_db, ALL_BANKS)
    r = tools.chat_get_sentiment("DBS")
    assert r["window"] == "all_time" and r["period"] == tools.period_text("all_time")
    assert r["period_note"] == "No period was asked for, so all stored data is used."
    assert tools.default_period_sentence() == "If no period is named, all stored data is used."


def test_a_score_with_no_window_uses_the_default_and_says_so(thirty_days, temp_db):
    _index(temp_db, ALL_BANKS)
    r = tools.chat_get_sentiment("DBS")
    assert r["window"] == "30d" and r["period"] == tools.period_text("30d")
    assert "No period was asked for" in r["period_note"] and "last 30 days" in r["period_note"]


def test_a_score_with_a_window_has_no_default_note(thirty_days, temp_db):
    _index(temp_db, ALL_BANKS)
    r = tools.chat_get_sentiment("DBS", window="all_time")
    assert r["window"] == "all_time" and "period_note" not in r


def test_a_default_that_holds_too_little_falls_back_to_all_data_and_says_so(thirty_days, temp_db):
    _index(temp_db, THIN_RECENT)
    r = tools.chat_get_sentiment("DBS")
    assert r["window"] == "all_time" and r["insufficient_data"] is False
    assert "too little" in r["period_note"] and "all stored data" in r["period_note"]


def test_a_window_the_model_asked_for_is_never_replaced(thirty_days, temp_db):
    _index(temp_db, THIN_RECENT)
    r = tools.chat_get_sentiment("DBS", window="30d")
    assert r["window"] == "30d" and r["insufficient_data"] is True and "period_note" not in r


def test_compare_banks_with_no_window_uses_the_default(thirty_days, temp_db):
    _index(temp_db, ALL_BANKS)
    r = tools.chat_compare_banks()
    assert r["window"] == "30d" and "No period was asked for" in r["period_note"]


def test_the_peers_in_a_banks_score_use_the_same_window(thirty_days, temp_db):
    _index(temp_db, ALL_BANKS)
    r = tools.chat_get_sentiment("DBS")
    assert set(r["other_banks"]) == {"OCBC", "UOB"} and r["window"] == "30d"


def test_a_search_with_no_window_covers_the_last_thirty_days(thirty_days, temp_db, monkeypatch):
    _index(temp_db, ALL_BANKS)
    seen = []
    hit = {"sentence_id": "1" * 24, "text": "The DBS app is slow.", "bank": "DBS", "source": "arctic_shift",
           "url": "http://x", "published_at": "2026-08-20T00:00:00+00:00", "score": 0.5}
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: seen.append(kw["date_from"]) or [hit])
    r = tools.chat_search_evidence("DBS app", bank="DBS")
    assert seen == [r["evidence_from"]] and r["period"] == tools.period_text("30d")
    assert "No period was asked for" in r["period_note"]


def test_a_search_that_finds_nothing_in_the_default_period_tries_all_data(thirty_days, temp_db, monkeypatch):
    _index(temp_db, ALL_BANKS)
    seen = []
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: seen.append(kw["date_from"]) or [])
    r = tools.chat_search_evidence("DBS app", bank="DBS")
    assert len(seen) == 2 and seen[0] is not None and seen[1] is None
    assert r["period"].startswith("all stored data") and "nothing" in r["period_note"].lower()


def test_a_search_with_a_window_asked_for_is_not_repeated(thirty_days, temp_db, monkeypatch):
    _index(temp_db, ALL_BANKS)
    seen = []
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: seen.append(kw["date_from"]) or [])
    r = tools.chat_search_evidence("DBS app", bank="DBS", window="7d")
    assert len(seen) == 1 and r["period"] == tools.period_text("7d") and "period_note" not in r


def test_the_footer_always_says_what_no_period_means(thirty_days, temp_db):
    _index(temp_db, ALL_BANKS)
    rule = "If no period is named, the last 30 days is used, or all stored data if that holds too little."
    assert tools.default_period_sentence() == rule
    for args, period in (({"bank": "DBS"}, "30d"), ({"bank": "DBS", "window": "7d"}, "7d")):
        tracker = _ToolCallTracker()
        tracker.execute("get_sentiment", args)
        assert period_footer(tracker) == f"Period searched: {tools.period_text(period)}. {rule}"


def test_the_rule_follows_the_configured_default(temp_db, monkeypatch):
    monkeypatch.setenv("CHATBOT_DEFAULT_WINDOW", "7d")
    assert "the last 7 days is used" in tools.default_period_sentence()
    monkeypatch.setenv("CHATBOT_DEFAULT_WINDOW", "all_time")
    assert tools.default_period_sentence() == "If no period is named, all stored data is used."


def test_the_model_can_name_a_window_for_scores_too():
    for name in ("get_sentiment", "compare_banks", "search_evidence"):
        schema = next(t for t in tools.TOOL_SCHEMAS if t["name"] == name)
        assert schema["input_schema"]["properties"]["window"]["enum"] == ["7d", "30d", "all_time"], name


def test_the_prompt_says_what_no_window_means():
    text = " ".join(SYSTEM_PROMPT.split())
    assert "leave window out" in text and tools.default_period_sentence() in text
