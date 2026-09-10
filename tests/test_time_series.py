"""
Tests for aggregate.index.compute_time_series - the continuous series behind
the Time Series tab and /sentiment/series.

The property that matters most is consistency: the series is computed from
the same rows, with the same weighting and shrinkage, as the stored index.
A chart that quietly disagreed with the headline number would be worse than
no chart, because there would be no way to tell which one was wrong.
"""

import pytest

from aggregate.index import compute_time_series
from ingest.db import now_iso


def _insert(temp_db, sentence_id, bank, aspect, label, published_at,
            source="arctic_shift", confidence=0.9):
    conn = temp_db.get_connection()
    conn.execute(
        "INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
        "norm_hash, processed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (sentence_id, f"doc-{sentence_id}", bank, "text", published_at, source,
         "http://example.com", f"hash-{sentence_id}", now_iso()),
    )
    conn.execute(
        "INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, "
        "model_version, scored_at) VALUES (?,?,?,?,?,?)",
        (sentence_id, aspect, label, confidence, "test-model", now_iso()),
    )
    conn.commit()
    conn.close()


def test_empty_database_returns_empty_series(temp_db):
    assert compute_time_series("DBS") == []


def test_groups_rows_into_month_buckets(temp_db):
    _insert(temp_db, "a", "DBS", "dividend_policy", "positive", "2026-01-05T00:00:00+00:00")
    _insert(temp_db, "b", "DBS", "dividend_policy", "positive", "2026-01-20T00:00:00+00:00")
    _insert(temp_db, "c", "DBS", "dividend_policy", "negative", "2026-02-02T00:00:00+00:00")

    series = compute_time_series("DBS", "dividend_policy", bucket="month")
    assert [p["period"] for p in series] == ["2026-01", "2026-02"]
    assert series[0]["n"] == 2
    assert series[1]["n"] == 1


def test_quarter_bucketing_maps_months_correctly(temp_db):
    for i, month in enumerate(["01", "04", "07", "10"]):
        _insert(temp_db, f"s{i}", "DBS", "dividend_policy", "positive",
                f"2026-{month}-15T00:00:00+00:00")
    series = compute_time_series("DBS", "dividend_policy", bucket="quarter")
    assert [p["period"] for p in series] == ["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"]


def test_series_is_ordered_by_period(temp_db):
    for i, date in enumerate(["2026-03-01", "2026-01-01", "2026-02-01"]):
        _insert(temp_db, f"s{i}", "DBS", "dividend_policy", "positive",
                f"{date}T00:00:00+00:00")
    periods = [p["period"] for p in compute_time_series("DBS", "dividend_policy")]
    assert periods == sorted(periods)


def test_thin_buckets_are_flagged_not_dropped(temp_db):
    # A gap must stay visible as a gap. Dropping thin buckets silently would
    # let a chart interpolate straight across a period with no data.
    _insert(temp_db, "a", "DBS", "dividend_policy", "positive", "2026-01-05T00:00:00+00:00")
    series = compute_time_series("DBS", "dividend_policy", min_n=5)
    assert len(series) == 1
    assert series[0]["sufficient"] is False
    assert series[0]["n"] == 1


def test_positive_and_negative_buckets_get_opposite_signs(temp_db):
    for i in range(10):
        _insert(temp_db, f"p{i}", "DBS", "dividend_policy", "positive",
                "2026-01-05T00:00:00+00:00")
    for i in range(10):
        _insert(temp_db, f"n{i}", "DBS", "dividend_policy", "negative",
                "2026-02-05T00:00:00+00:00")
    series = {p["period"]: p for p in compute_time_series("DBS", "dividend_policy")}
    assert series["2026-01"]["score"] > 0
    assert series["2026-02"]["score"] < 0


def test_shrinkage_pulls_a_small_bucket_toward_zero(temp_db):
    """Same 100% positive label ratio, different volumes - the smaller bucket
    must score lower, which is the whole point of the shrinkage term."""
    _insert(temp_db, "small", "DBS", "dividend_policy", "positive", "2026-01-05T00:00:00+00:00")
    for i in range(50):
        _insert(temp_db, f"big{i}", "DBS", "dividend_policy", "positive",
                "2026-02-05T00:00:00+00:00")
    series = {p["period"]: p for p in compute_time_series("DBS", "dividend_policy", min_n=1)}
    assert series["2026-01"]["score"] < series["2026-02"]["score"]


def test_aspect_filter_excludes_other_aspects(temp_db):
    _insert(temp_db, "a", "DBS", "dividend_policy", "positive", "2026-01-05T00:00:00+00:00")
    _insert(temp_db, "b", "DBS", "asset_quality", "positive", "2026-01-05T00:00:00+00:00")
    series = compute_time_series("DBS", "dividend_policy", min_n=1)
    assert series[0]["n"] == 1


def test_aspect_all_spans_every_aspect(temp_db):
    _insert(temp_db, "a", "DBS", "dividend_policy", "positive", "2026-01-05T00:00:00+00:00")
    _insert(temp_db, "b", "DBS", "asset_quality", "positive", "2026-01-05T00:00:00+00:00")
    assert compute_time_series("DBS", "ALL", min_n=1)[0]["n"] == 2
    assert compute_time_series("DBS", None, min_n=1)[0]["n"] == 2


def test_bank_filter_excludes_other_banks(temp_db):
    _insert(temp_db, "a", "DBS", "dividend_policy", "positive", "2026-01-05T00:00:00+00:00")
    _insert(temp_db, "b", "OCBC", "dividend_policy", "positive", "2026-01-05T00:00:00+00:00")
    assert compute_time_series("DBS", min_n=1)[0]["n"] == 1


def test_source_filter(temp_db):
    _insert(temp_db, "a", "DBS", "dividend_policy", "positive",
            "2026-01-05T00:00:00+00:00", source="arctic_shift")
    _insert(temp_db, "b", "DBS", "dividend_policy", "positive",
            "2026-01-05T00:00:00+00:00", source="earnings")
    assert compute_time_series("DBS", source="earnings", min_n=1)[0]["n"] == 1
    assert compute_time_series("DBS", source="ALL", min_n=1)[0]["n"] == 2


def test_unknown_bucket_raises(temp_db):
    with pytest.raises(ValueError, match="bucket must be one of"):
        compute_time_series("DBS", bucket="fortnight")


def test_counts_reconcile_with_the_bucket_totals(temp_db):
    for i in range(4):
        _insert(temp_db, f"p{i}", "DBS", "dividend_policy", "positive", "2026-01-05T00:00:00+00:00")
    _insert(temp_db, "n0", "DBS", "dividend_policy", "negative", "2026-01-06T00:00:00+00:00")
    _insert(temp_db, "u0", "DBS", "dividend_policy", "neutral", "2026-01-07T00:00:00+00:00")
    p = compute_time_series("DBS", "dividend_policy", min_n=1)[0]
    assert p["pos_n"] + p["neu_n"] + p["neg_n"] == p["n"] == 6
