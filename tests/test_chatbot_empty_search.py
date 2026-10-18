"""
Asked "what do people think of DBS's app", the model searched with
sentiment="all", which is not a sentiment. The filter was applied as written, so
the search matched nothing; the result carried only the bank's overall score,
and the answer gave that score as if it were about the app, without saying that
nothing had been found.
"""

import pytest

from chatbot import tools
from chatbot.agent import _ToolCallTracker
from tests.test_chatbot_reader import _index


# --- a sentiment that is not one is not a filter ---------------------------------------

@pytest.mark.parametrize("given", ["all", "any", "ALL", "none", "", "mixed", "n/a"])
def test_a_sentiment_that_is_not_one_is_dropped(given):
    args = tools.coerce_tool_arguments("search_evidence", {"query": "q", "bank": "DBS", "sentiment": given})
    assert "sentiment" not in args and args["query"] == "q" and args["bank"] == "DBS"


@pytest.mark.parametrize("given, kept", [("negative", "negative"), ("Negative", "negative"),
                                         (" POSITIVE ", "positive"), ("neutral", "neutral")])
def test_a_real_sentiment_is_kept(given, kept):
    assert tools.coerce_tool_arguments("search_evidence", {"query": "q", "sentiment": given})["sentiment"] == kept


def test_the_search_is_not_filtered_when_the_model_says_all(temp_db, monkeypatch):
    seen = {}
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: seen.update(kw) or [])
    tracker = _ToolCallTracker()
    tracker.execute("search_evidence", {"query": "DBS app", "bank": "DBS", "k": "5", "sentiment": "all"})
    assert seen["sentiment"] is None


# --- an empty search says so -------------------------------------------------------------

def test_a_search_that_finds_nothing_says_so(temp_db, monkeypatch):
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 3, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    r = tools.chat_search_evidence("DBS app", bank="DBS")
    assert r["results"] == [] and "DBS app" in r["no_evidence"] and "nothing was found" in r["no_evidence"].lower()


def test_a_search_with_results_has_no_such_message(temp_db, monkeypatch):
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 3, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [
        {"sentence_id": "1" * 24, "text": "The DBS app is slow.", "bank": "DBS", "source": "arctic_shift",
         "url": "http://x", "published_at": "2026-09-02T00:00:00+00:00", "score": 0.5}])
    assert "no_evidence" not in tools.chat_search_evidence("DBS app", bank="DBS")


def test_the_attached_overall_score_says_it_is_not_about_the_query(temp_db, monkeypatch):
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 3, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    note = tools.chat_search_evidence("DBS app", bank="DBS")["bank_overall_score"]["covers"]
    assert "all topics" in note and "DBS app" in note and "not" in note


def test_the_attached_topic_score_says_which_topic_it_covers(temp_db, monkeypatch):
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 3, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    note = tools.chat_search_evidence("DBS app", bank="DBS", aspect="dividend_policy")["topic_score"]["covers"]
    assert "Dividend Policy" in note and "DBS app" in note and "not" in note


def test_the_added_wording_carries_no_figure_to_be_checked(temp_db, monkeypatch):
    from chatbot.guards import unverified_numbers
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 3, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    r = tools.chat_search_evidence("DBS app", bank="DBS")
    assert unverified_numbers(r["no_evidence"] + " " + r["bank_overall_score"]["covers"], [r]) == []
