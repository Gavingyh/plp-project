"""
Tests for chatbot/suggestions.py - the clickable starter questions a chat UI
offers.

Two properties matter here and neither is cosmetic:

1. A suggestion must be answerable. Suggesting a question the data can't
   support means the user clicks it, gets "insufficient data", and concludes
   the system is broken.
2. No suggestion may invite investment advice or an out-of-scope answer. The
   chatbot is built to decline those, and this project carries a
   not-financial-advice disclaimer.
"""

import pytest

from chatbot.suggestions import build_candidates, get_suggestions
from chatbot.tools import MIN_VOLUME_FOR_SCORE
from ingest.db import now_iso


def _insert_index_row(temp_db, bank, aspect, n, window="all_time"):
    conn = temp_db.get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO sentiment_index "
        "(bank, aspect, window, source, score, n, pos_n, neu_n, neg_n, "
        "confidence_mean, model_version, computed_at) "
        "VALUES (?,?,?,'ALL',?,?,?,?,?,?,?,?)",
        (bank, aspect, window, 0.5, n, n, 0, 0, 0.9, "test-model", now_iso()),
    )
    conn.commit()
    conn.close()


def _insert_consensus(temp_db, bank):
    conn = temp_db.get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO analyst_consensus "
        "(bank, as_of_date, ticker, n_analysts, recommendation_key, "
        "recommendation_mean, target_mean, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (bank, "2026-09-08", "D05.SI", 15, "buy", 2.0, 40.0, now_iso()),
    )
    conn.commit()
    conn.close()


def test_no_data_yields_no_suggestions(temp_db):
    # A fresh install must not offer questions nothing can answer.
    assert get_suggestions() == []


def test_below_volume_floor_is_not_suggested(temp_db):
    _insert_index_row(temp_db, "DBS", "dividend_policy", MIN_VOLUME_FOR_SCORE - 1)
    questions = [s["question"] for s in get_suggestions()]
    assert questions == []


def test_at_volume_floor_is_suggested(temp_db):
    _insert_index_row(temp_db, "DBS", "dividend_policy", MIN_VOLUME_FOR_SCORE)
    questions = [s["question"] for s in get_suggestions()]
    assert any("dividend policy" in q for q in questions)


def test_trend_only_suggested_when_recent_window_has_data(temp_db):
    # all_time data alone must not produce a "changed recently?" question -
    # get_trend would have no recent window to compare against.
    _insert_index_row(temp_db, "UOB", "asset_quality", 500, window="all_time")
    categories = {s["category"] for s in get_suggestions(limit=20)}
    assert "trend" not in categories

    _insert_index_row(temp_db, "UOB", "asset_quality", 20, window="7d")
    categories = {s["category"] for s in get_suggestions(limit=20)}
    assert "trend" in categories


def test_compare_requires_all_three_banks(temp_db):
    _insert_index_row(temp_db, "DBS", "net_interest_margin", 100)
    _insert_index_row(temp_db, "OCBC", "net_interest_margin", 100)
    assert "compare" not in {s["category"] for s in get_suggestions(limit=20)}

    _insert_index_row(temp_db, "UOB", "net_interest_margin", 100)
    assert "compare" in {s["category"] for s in get_suggestions(limit=20)}


def test_consensus_only_for_banks_with_a_snapshot(temp_db):
    _insert_index_row(temp_db, "DBS", "ALL", 100)
    _insert_consensus(temp_db, "DBS")
    consensus = [s["question"] for s in get_suggestions(limit=20)
                 if s["category"] == "consensus"]
    assert consensus == ["What do analysts think of DBS?"]


def test_other_aspect_is_never_suggested(temp_db):
    # "other" is a catch-all bucket; "sentiment on other?" is not a question.
    _insert_index_row(temp_db, "DBS", "other", 5000)
    assert get_suggestions() == []


def test_suggestions_spread_across_banks(temp_db):
    # DBS has far more data than the others in the real corpus, so ranking by
    # support alone returns six DBS questions and reads as a single-bank tool.
    for aspect in ["ALL", "dividend_policy", "asset_quality"]:
        _insert_index_row(temp_db, "DBS", aspect, 10_000)
        _insert_index_row(temp_db, "OCBC", aspect, 50)
        _insert_index_row(temp_db, "UOB", aspect, 50)

    questions = " ".join(s["question"] for s in get_suggestions(limit=6))
    assert "OCBC" in questions or "UOB" in questions, questions


def test_suggestions_are_unique(temp_db):
    for aspect in ["ALL", "dividend_policy", "asset_quality"]:
        for bank in ["DBS", "OCBC", "UOB"]:
            _insert_index_row(temp_db, bank, aspect, 100)
            _insert_index_row(temp_db, bank, aspect, 100, window="7d")

    questions = [s["question"] for s in get_suggestions(limit=15)]
    assert len(questions) == len(set(questions))


def test_limit_is_respected(temp_db):
    for aspect in ["ALL", "dividend_policy", "asset_quality", "net_interest_margin"]:
        for bank in ["DBS", "OCBC", "UOB"]:
            _insert_index_row(temp_db, bank, aspect, 100)
    assert len(get_suggestions(limit=3)) == 3


# ---------------------------------------------------------------------------
# The safety property: suggestions must never invite an answer the chatbot is
# built to refuse.
# ---------------------------------------------------------------------------

_ADVICE_PATTERNS = ["should i", "should we", "buy", "sell", "invest",
                    "recommend", "worth it", "good investment", "price target",
                    "will ", "predict", "forecast"]


def test_no_suggestion_seeks_investment_advice(temp_db):
    for aspect in ["ALL", "dividend_policy", "asset_quality",
                   "net_interest_margin", "management_guidance", "other"]:
        for bank in ["DBS", "OCBC", "UOB"]:
            _insert_index_row(temp_db, bank, aspect, 1000)
            _insert_index_row(temp_db, bank, aspect, 1000, window="7d")
    for bank in ["DBS", "OCBC", "UOB"]:
        _insert_consensus(temp_db, bank)

    # Check every candidate, not just the six surfaced by default - a
    # different limit or a different corpus surfaces different ones.
    for candidate in build_candidates():
        lowered = candidate["question"].lower()
        for pattern in _ADVICE_PATTERNS:
            assert pattern not in lowered, f"{candidate['question']} matched {pattern!r}"


def test_no_suggestion_duplicates_a_deliberately_bad_gold_set_question(temp_db):
    """The gold set contains advice-seeking and out-of-scope questions on
    purpose, to test that the chatbot declines them. None may leak into the
    suggestions a user is invited to click."""
    from chatbot.eval_gold_set import GOLD_SET

    bad = {q["question"].strip().lower() for q in GOLD_SET
           if q.get("category") in {"advice", "out_of_scope"}}
    assert bad, "gold set should contain advice/out_of_scope questions"

    for aspect in ["ALL", "dividend_policy", "asset_quality",
                   "net_interest_margin", "management_guidance"]:
        for bank in ["DBS", "OCBC", "UOB"]:
            _insert_index_row(temp_db, bank, aspect, 1000)

    suggested = {c["question"].strip().lower() for c in build_candidates()}
    assert not (suggested & bad)
