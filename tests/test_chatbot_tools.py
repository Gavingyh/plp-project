"""
Tests for chatbot/tools.py — the structured-data tools the agent calls.
Includes a regression test for a previously-fixed defect:
get_coverage's `where` clause list was built for one query (joined to
sentence_aspects when `aspect` was given) and reused verbatim for a second
query that never performed that join, causing
"sqlite3.OperationalError: no such column: sa.aspect".
"""

from chatbot.tools import get_coverage, get_sentiment
from ingest.db import now_iso


def _insert_scored_sentence(temp_db, sentence_id, bank, aspect, label, confidence, n_docs=1):
    conn = temp_db.get_connection()
    conn.execute(
        "INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
        "norm_hash, processed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (sentence_id, f"doc-{sentence_id}", bank, "some text", "2026-01-01T00:00:00+00:00",
         "arctic_shift", "http://example.com", f"hash-{sentence_id}", now_iso()),
    )
    conn.execute(
        "INSERT INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) VALUES (?,?,?,?)",
        (sentence_id, aspect, 0.9, now_iso()),
    )
    conn.execute(
        "INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, scored_at) "
        "VALUES (?,?,?,?,?,?)",
        (sentence_id, aspect, label, confidence, "test-model", now_iso()),
    )
    conn.commit()
    conn.close()


def test_get_coverage_with_bank_and_aspect_does_not_crash(temp_db):
    # This is the exact regression case: bank + aspect both given, which
    # triggers the join-mismatch bug if it's reintroduced.
    _insert_scored_sentence(temp_db, "s1", "OCBC", "dividend_policy", "positive", 0.9)
    result = get_coverage(bank="OCBC", aspect="dividend_policy")
    assert result["has_data"] is True
    assert result["n"] == 1
    assert result["by_source"] == {"arctic_shift": 1}


def test_get_coverage_bank_only(temp_db):
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "positive", 0.9)
    result = get_coverage(bank="DBS")
    assert result["has_data"] is True
    assert result["n"] == 1


def test_get_coverage_no_data_returns_false(temp_db):
    result = get_coverage(bank="UOB", aspect="net_interest_margin")
    assert result["has_data"] is False
    assert result["n"] == 0


def test_get_sentiment_no_data_flags_insufficient(temp_db):
    result = get_sentiment("DBS", "asset_quality")
    assert result["insufficient_data"] is True
