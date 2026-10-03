"""
Tests for aggregate/index.py's shrinkage math - the mechanism that stops a
single Reddit comment from swinging the index to +/-1.0 (docs/DESIGN.md,
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
    conn.execute("INSERT OR IGNORE INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) VALUES (?,?,1.0,?)", (sentence_id, aspect, now_iso()))
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
        "SELECT score, n FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' AND window='all_time' AND source='ALL'"
    ).fetchone()
    conn.close()
    score, n = row
    assert n == 1
    # aggregate/index.py rounds to 4dp - match that precision, not exact float equality.
    assert abs(score - round(1.0 / 6, 4)) < 1e-4


def test_n_and_class_counts_always_stored(temp_db):
    # By design: a score without its sample size is the main way
    # this dashboard could mislead a retail investor. n/pos/neu/neg must
    # always be present regardless of how thin the data is.
    _insert_scored_sentence(temp_db, "s1", "OCBC", "asset_quality", "negative", 0.9)
    run_aggregate()
    conn = temp_db.get_connection()
    row = conn.execute(
        "SELECT n, pos_n, neu_n, neg_n FROM sentiment_index WHERE bank='OCBC' AND aspect='asset_quality' AND window='all_time' AND source='ALL'"
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
        "SELECT score, n FROM sentiment_index WHERE bank='UOB' AND aspect='dividend_policy' AND window='all_time' AND source='ALL'"
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
    n = conn.execute("SELECT n FROM sentiment_index WHERE bank='DBS' AND aspect='ALL' AND window='all_time' AND source='ALL'").fetchone()[0]
    conn.close()
    assert n == 2  # both sentences counted in the overall bank-level row


def test_news_outweighs_reddit(temp_db):
    # newsapi is weighted 1.5 vs arctic_shift's 1.0, so an equally-confident
    # negative news item should outweigh one positive Reddit comment.
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "negative", 1.0, source="newsapi")
    _insert_scored_sentence(temp_db, "s2", "DBS", "dividend_policy", "positive", 1.0, source="arctic_shift")
    run_aggregate()
    conn = temp_db.get_connection()
    score = conn.execute(
        "SELECT score FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' AND window='all_time' AND source='ALL'"
    ).fetchone()[0]
    conn.close()
    assert score < 0


def test_earnings_no_longer_outweighs_reddit(temp_db):
    # Earnings weight is 1.0, not 3.0: earnings text is management
    # describing its own results (24.7% of its sentences score
    # positive vs 2.3% of Reddit's), so triple-weighting it amplified a known
    # skew. Equal-confidence earnings and Reddit items must now cancel out.
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "negative", 1.0, source="earnings")
    _insert_scored_sentence(temp_db, "s2", "DBS", "dividend_policy", "positive", 1.0, source="arctic_shift")
    run_aggregate()
    conn = temp_db.get_connection()
    score = conn.execute(
        "SELECT score FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' AND window='all_time' AND source='ALL'"
    ).fetchone()[0]
    conn.close()
    assert abs(score) < 1e-6, f"expected earnings and Reddit to cancel, got {score}"


def test_per_source_rows_written_alongside_blended_row(temp_db):
    # The blend must remain inspectable: each contributing source gets its own
    # row so the dashboard/API can show what the headline number is made of.
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "negative", 1.0, source="earnings")
    _insert_scored_sentence(temp_db, "s2", "DBS", "dividend_policy", "positive", 1.0, source="arctic_shift")
    run_aggregate()
    conn = temp_db.get_connection()
    rows = dict(conn.execute(
        "SELECT source, n FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' "
        "AND window='all_time'").fetchall())
    conn.close()
    assert rows["ALL"] == 2          # blended row counts both
    assert rows["earnings"] == 1     # and each source is broken out
    assert rows["arctic_shift"] == 1


def test_old_data_excluded_from_7d_window_but_kept_in_all_time(temp_db):
    from datetime import datetime, timedelta, timezone
    old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "positive", 1.0,
                             published_at=old_ts)
    run_aggregate()
    conn = temp_db.get_connection()
    n_7d = conn.execute(
        "SELECT n FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' AND window='7d' AND source='ALL'"
    ).fetchone()
    n_all = conn.execute(
        "SELECT n FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' AND window='all_time' AND source='ALL'"
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
        "SELECT n FROM sentiment_index WHERE bank='UOB' AND aspect='asset_quality' AND window='7d' AND source='ALL'"
    ).fetchone()
    conn.close()
    assert n_7d == (1,)


def _add_aspect(temp_db, sentence_id, aspect, label, confidence, model_version="test-model"):
    conn = temp_db.get_connection()
    conn.execute("INSERT OR IGNORE INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) VALUES (?,?,1.0,?)", (sentence_id, aspect, now_iso()))
    conn.execute(
        "INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, scored_at) "
        "VALUES (?,?,?,?,?,?)", (sentence_id, aspect, label, confidence, model_version, now_iso()))
    conn.commit()
    conn.close()


def test_rows_across_aspects_count_each_sentence_once(temp_db):
    # s1 matched three aspects, s2 one. Per-aspect rows count pairs; the
    # ALL rows must count two sentences, not four pairs, or s1 outweighs s2 3:1.
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "positive", 0.9)
    _add_aspect(temp_db, "s1", "asset_quality", "positive", 0.9)
    _add_aspect(temp_db, "s1", "wealth_business", "positive", 0.9)
    _insert_scored_sentence(temp_db, "s2", "DBS", "retail_banking_sentiment", "negative", 0.9)
    run_aggregate()
    conn = temp_db.get_connection()
    rows = dict(conn.execute(
        "SELECT source, n FROM sentiment_index WHERE bank='DBS' AND aspect='ALL' AND window='all_time'").fetchall())
    headline = conn.execute(
        "SELECT score, pos_n, neg_n FROM sentiment_index WHERE bank='DBS' AND aspect='ALL' "
        "AND window='all_time' AND source='ALL'").fetchone()
    per_aspect = conn.execute(
        "SELECT n FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' "
        "AND window='all_time' AND source='ALL'").fetchone()[0]
    conn.close()
    assert rows == {"ALL": 2, "arctic_shift": 2}
    assert headline == (0.0, 1, 1)          # one positive, one negative sentence: balanced
    assert per_aspect == 1


def test_7d_cutoff_compares_instants_not_strings(temp_db):
    # 7 days and 4 hours ago, written in Singapore time: the string's digits read 4 hours
    # inside the window, but the instant is outside it. A "Z" timestamp an hour inside counts.
    from datetime import datetime, timedelta, timezone
    sgt = timezone(timedelta(hours=8))
    outside = (datetime.now(timezone.utc) - timedelta(days=7, hours=4)).astimezone(sgt).isoformat()
    inside = (datetime.now(timezone.utc) - timedelta(days=6, hours=23)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "positive", 1.0,
                            source="cna", published_at=outside)
    _insert_scored_sentence(temp_db, "s2", "DBS", "dividend_policy", "positive", 1.0,
                            source="newsapi", published_at=inside)
    run_aggregate()
    conn = temp_db.get_connection()
    n_7d = conn.execute(
        "SELECT n FROM sentiment_index WHERE bank='DBS' AND aspect='dividend_policy' AND window='7d' AND source='ALL'"
    ).fetchone()
    conn.close()
    assert n_7d == (1,)


def test_pairs_no_longer_assigned_are_not_counted(temp_db):
    # After a change of aspect method a sentence's old pair can keep its score; it must not count.
    _add_aspect(temp_db, "s1", "dividend_policy", "positive", 0.9)
    _add_aspect(temp_db, "s1", "asset_quality", "negative", 0.99)
    conn = temp_db.get_connection()
    conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, norm_hash, "
                 "processed_at) VALUES ('s1','d1','DBS','t','2026-01-01T00:00:00+00:00','arctic_shift','u','h',?)",
                 (now_iso(),))
    conn.execute("DELETE FROM sentence_aspects WHERE sentence_id='s1' AND aspect='asset_quality'")
    conn.commit()
    conn.close()
    run_aggregate()
    conn = temp_db.get_connection()
    rows = dict(conn.execute("SELECT aspect, n FROM sentiment_index WHERE bank='DBS' AND window='all_time' "
                             "AND source='ALL'").fetchall())
    head = conn.execute("SELECT pos_n, neg_n FROM sentiment_index WHERE bank='DBS' AND aspect='ALL' "
                        "AND window='all_time' AND source='ALL'").fetchone()
    conn.close()
    assert rows == {"dividend_policy": 1, "ALL": 1}
    assert head == (1, 0)                    # the stale, more confident negative pair is ignored
