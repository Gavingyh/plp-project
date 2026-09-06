"""
Tests for aggregate/index.py's shrinkage math — the mechanism that stops a
single Reddit comment from swinging the index to +/-1.0 (plan Phase 6,
"Sentiment aggregation"). Verifies against hand-computed expected values on
a synthetic dataset, not just "it runs."
"""

from aggregate.index import run as run_aggregate
from ingest.db import now_iso


def _insert_scored_sentence(temp_db, sentence_id, bank, aspect, label, confidence,
                             source="arctic_shift", model_version="test-model",
                             published_at="2026-01-01T00:00:00+00:00"):
    conn = temp_db.get_connection()
    conn.execute(
        "INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
        "norm_hash, processed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (sentence_id, f"doc-{sentence_id}", bank, "some text", published_at,
         source, "http://example.com", f"hash-{sentence_id}", now_iso()),
    )
    conn.execute(
        "INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, scored_at) "
        "VALUES (?,?,?,?,?,?)",
        (sentence_id, aspect, label, confidence, model_version, now_iso()),
    )
    conn.commit()
    conn.close()


def test_single_positive_sentence_is_shrunk_toward_neutral(temp_db):
    # Raw score would be +1.0 (single positive item), but with n=1 and k=5,
    # shrinkage factor is 1/(1+5) = 1/6 -> expected score = 1.0 * 1/6.
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "positive", 1.0)
    run_aggregate()
    conn = temp_db.get_connection()
    row = conn.execute(
        "SELECT score, n FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' AND window='all_time'"
    ).fetchone()
    conn.close()
    score, n = row
    assert n == 1
    # aggregate/index.py rounds to 4dp — match that precision, not exact float equality.
    assert abs(score - round(1.0 / 6, 4)) < 1e-4


def test_n_and_class_counts_always_stored(temp_db):
    # The plan is explicit: a score without its sample size is the main way
    # this dashboard could mislead a retail investor. n/pos/neu/neg must
    # always be present regardless of how thin the data is.
    _insert_scored_sentence(temp_db, "s1", "OCBC", "asset_quality", "negative", 0.9)
    run_aggregate()
    conn = temp_db.get_connection()
    row = conn.execute(
        "SELECT n, pos_n, neu_n, neg_n FROM sentiment_index WHERE bank='OCBC' AND aspect='asset_quality' AND window='all_time'"
    ).fetchone()
    conn.close()
    assert row == (1, 0, 0, 1)


def test_larger_volume_shrinks_less(temp_db):
    # Same unanimous-positive signal, but more data points -> shrinkage
    # factor n/(n+k) should be closer to 1, i.e. less pulled toward zero.
    for i in range(20):
        _insert_scored_sentence(temp_db, f"s{i}", "UOB", "dividend_policy", "positive", 1.0)
    run_aggregate()
    conn = temp_db.get_connection()
    score, n = conn.execute(
        "SELECT score, n FROM sentiment_index WHERE bank='UOB' AND aspect='dividend_policy' AND window='all_time'"
    ).fetchone()
    conn.close()
    assert n == 20
    expected = 1.0 * (20 / (20 + 5))
    assert abs(score - expected) < 1e-6
    assert score > (1.0 / 6)  # strictly less shrunk than the n=1 case above


def test_overall_all_row_aggregates_across_aspects(temp_db):
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "positive", 1.0)
    _insert_scored_sentence(temp_db, "s2", "DBS", "asset_quality", "negative", 1.0)
    run_aggregate()
    conn = temp_db.get_connection()
    n = conn.execute("SELECT n FROM sentiment_index WHERE bank='DBS' AND aspect='ALL' AND window='all_time'").fetchone()[0]
    conn.close()
    assert n == 2  # both sentences counted in the overall bank-level row


def test_source_weight_affects_score(temp_db):
    # Earnings-sourced items are weighted 3x a Reddit comment (aggregate/index.py
    # _SOURCE_WEIGHT) — two positive Reddit comments should NOT fully offset
    # one negative earnings-sourced item at equal confidence.
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "negative", 1.0, source="earnings")
    _insert_scored_sentence(temp_db, "s2", "DBS", "dividend_policy", "positive", 1.0, source="arctic_shift")
    run_aggregate()
    conn = temp_db.get_connection()
    score = conn.execute(
        "SELECT score FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' AND window='all_time'"
    ).fetchone()[0]
    conn.close()
    assert score < 0  # earnings' negative should outweigh Reddit's positive


def test_old_data_excluded_from_7d_window_but_kept_in_all_time(temp_db):
    from datetime import datetime, timedelta, timezone
    old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "positive", 1.0,
                             published_at=old_ts)
    run_aggregate()
    conn = temp_db.get_connection()
    n_7d = conn.execute(
        "SELECT n FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' AND window='7d'"
    ).fetchone()
    n_all = conn.execute(
        "SELECT n FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' AND window='all_time'"
    ).fetchone()
    conn.close()
    # 60-day-old data has no row at all in the 7d window (no groups formed for
    # this bank/aspect once filtered out) rather than a zero-n row.
    assert n_7d is None
    assert n_all == (1,)


def test_recent_data_included_in_7d_window(temp_db):
    from datetime import datetime, timezone
    recent_ts = datetime.now(timezone.utc).isoformat()
    _insert_scored_sentence(temp_db, "s1", "UOB", "asset_quality", "negative", 1.0,
                             published_at=recent_ts)
    run_aggregate()
    conn = temp_db.get_connection()
    n_7d = conn.execute(
        "SELECT n FROM sentiment_index WHERE bank='UOB' AND aspect='asset_quality' AND window='7d'"
    ).fetchone()
    conn.close()
    assert n_7d == (1,)
