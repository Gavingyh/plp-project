"""
Validation of claim S2 (api/main.py): GET /sentiment?bank=DBS&window=all_time
returns the score and n of the blended headline row in sentiment_index
(source='ALL', aspect='ALL'), and a bad bank, window or bucket gives 422.

The expected row is read from data/plp.db read-only. The API reads a backup
copy of that database in tmp_path (ingest.db.get_connection runs a PRAGMA on
open, so it is never pointed at the live file).
"""

import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from api.main import app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_DB = os.path.join(ROOT, "data", "plp.db")


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


@pytest.fixture
def real_db_copy(tmp_path, monkeypatch):
    if not os.path.exists(REAL_DB):
        pytest.skip("data/plp.db not present")
    import ingest.db as db_module
    copy = str(tmp_path / "plp_copy.db")
    src, dst = _ro(REAL_DB), sqlite3.connect(copy)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    monkeypatch.setattr(db_module, "DB_PATH", copy)
    return copy


def test_sentiment_dbs_all_time_matches_headline_row_in_db(real_db_copy):
    conn = _ro(REAL_DB)
    try:
        rows = conn.execute(
            "SELECT score, n, model_version, computed_at FROM sentiment_index "
            "WHERE bank = 'DBS' AND aspect = 'ALL' AND window = 'all_time' AND source = 'ALL'"
        ).fetchall()
        decoys = conn.execute(
            "SELECT source, score, n FROM sentiment_index "
            "WHERE bank = 'DBS' AND aspect = 'ALL' AND window = 'all_time' AND source != 'ALL'"
        ).fetchall()
    finally:
        conn.close()
    assert rows, "no DBS/ALL/all_time/ALL row in sentiment_index"
    exp_score, exp_n, exp_model, exp_at = max(rows, key=lambda r: r[3])
    print(f"\nDB headline rows: {rows}\nDB per-source rows (must not be returned): {decoys}")

    resp = TestClient(app).get("/sentiment", params={"bank": "DBS", "window": "all_time"})
    assert resp.status_code == 200
    body = resp.json()
    print(f"API: score={body.get('score')} n={body.get('n')} aspect={body.get('aspect')} "
          f"model_version={body.get('model_version')}")
    assert body["insufficient_data"] is False
    assert body["aspect"] == "ALL" and body["window"] == "all_time"
    assert body["score"] == exp_score
    assert body["n"] == exp_n
    assert body["model_version"] == exp_model


@pytest.mark.parametrize("bank", ["NOTABANK", "dbs", "DBS ", " DBS", "DBSX", "", "DBS\n", "DBS|OCBC"])
def test_sentiment_bad_bank_returns_422(temp_db, bank):
    resp = TestClient(app).get("/sentiment", params={"bank": bank, "window": "all_time"})
    assert resp.status_code == 422, (bank, resp.status_code, resp.text[:200])


@pytest.mark.parametrize("window", ["5years", "ALL_TIME", "7D", "90d", "", "all_time\n", "7d|30d"])
def test_sentiment_bad_window_returns_422(temp_db, window):
    resp = TestClient(app).get("/sentiment", params={"bank": "DBS", "window": window})
    assert resp.status_code == 422, (window, resp.status_code, resp.text[:200])


@pytest.mark.parametrize("bucket", ["day", "Month", "year", "", "month\n", "week|month"])
def test_series_bad_bucket_returns_422(temp_db, bucket):
    # `bucket` is a parameter of /sentiment/series only; /sentiment has none.
    resp = TestClient(app).get("/sentiment/series", params={"bank": "DBS", "bucket": bucket})
    assert resp.status_code == 422, (bucket, resp.status_code, resp.text[:200])


@pytest.mark.parametrize("bucket", ["week", "month", "quarter"])
def test_series_good_bucket_is_accepted(temp_db, bucket):
    # Control: the 422s above come from the bucket value, not from the route.
    resp = TestClient(app).get("/sentiment/series", params={"bank": "DBS", "bucket": bucket})
    assert resp.status_code == 200, (bucket, resp.status_code, resp.text[:200])
    assert resp.json()["bucket"] == bucket


@pytest.mark.parametrize("window", ["7d", "30d", "all_time"])
def test_sentiment_good_window_is_accepted(temp_db, window):
    # Control for the bank/window 422s.
    resp = TestClient(app).get("/sentiment", params={"bank": "DBS", "window": window})
    assert resp.status_code == 200, (window, resp.status_code, resp.text[:200])


# ---------------------------------------------------------------------------
# Step 3: reviewer findings R1-R3. Each test fails if the finding is real.
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone

from ingest.db import now_iso


def _add_scored(temp_db, sid, bank, aspect, days_ago, labels_by_version, source="arctic_shift"):
    """One sentence, scored once per model version ({version: label}), confidence 1.0."""
    published = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn = temp_db.get_connection()
    conn.execute(
        "INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
        "norm_hash, processed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (sid, f"doc-{sid}", bank, f"text {sid}", published, source, "http://example.com",
         f"hash-{sid}", now_iso()))
    for version, label in labels_by_version.items():
        conn.execute(
            "INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, "
            "scored_at) VALUES (?,?,?,?,?,?)", (sid, aspect, label, 1.0, version, now_iso()))
    conn.commit()
    conn.close()


# R1: /sentiment/trend compares shrunk scores, so a thin 7d window reads as "declining".

@pytest.mark.xfail(strict=True, reason="R1: trend compares shrunk scores, so a thin 7d window reads as declining")
def test_r1_trend_not_declining_when_raw_7d_is_higher(temp_db):
    import aggregate.index as agg
    from chatbot.tools import get_trend
    i = 0
    # 7d: 6 sentences, 4 positive + 2 neutral -> raw 0.6667
    for label in ["positive"] * 4 + ["neutral"] * 2:
        _add_scored(temp_db, f"r{i}", "UOB", "asset_quality", 1, {"finbert-base-zeroshot-v1": label}); i += 1
    # days 10-25: 94 more -> 30d window = 100 sentences, 45 positive + 55 neutral -> raw 0.45
    for k, label in enumerate(["positive"] * 41 + ["neutral"] * 53):
        _add_scored(temp_db, f"o{i}", "UOB", "asset_quality", 10 + k % 15, {"finbert-base-zeroshot-v1": label}); i += 1
    agg.run()
    trend = get_trend("UOB")
    raw_7d, raw_30d = 4 / 6, 45 / 100
    print(f"\nR1 synthetic: raw 7d={raw_7d:.4f} raw 30d={raw_30d:.4f} raw delta={raw_7d - raw_30d:+.4f}; "
          f"stored delta={trend['delta_7d_vs_30d']} direction={trend['direction']}")
    assert trend["trend_available"] is True
    assert trend["direction"] != "declining"


# R2: two model versions written in one run share computed_at; nothing picks between them.

OLD_V, NEW_V = "finbert-base-zeroshot-v1", "finbert-finetuned-v2"


def _two_version_index(temp_db):
    """A version bump: every DBS sentence scored by both versions (old positive, new negative),
    then the real aggregator run once."""
    import aggregate.index as agg
    for i in range(10):
        _add_scored(temp_db, f"s{i}", "DBS", "asset_quality", 200, {OLD_V: "positive", NEW_V: "negative"})
    agg.run()


@pytest.mark.xfail(strict=True, reason="R2: one run writes a row per model_version with the same computed_at")
def test_r2_aggregator_writes_one_row_per_cell(temp_db):
    _two_version_index(temp_db)
    conn = temp_db.get_connection()
    dup = conn.execute(
        "SELECT bank, aspect, window, source, COUNT(*), COUNT(DISTINCT computed_at), "
        "GROUP_CONCAT(model_version || '=' || score) FROM sentiment_index "
        "GROUP BY 1,2,3,4 HAVING COUNT(*) > 1").fetchall()
    conn.close()
    print(f"\nR2 cells with more than one row: {len(dup)}, e.g. {dup[:2]}")
    assert dup == []


@pytest.mark.xfail(strict=True, reason="R2: /sentiment/index returns one row per model_version per cell")
def test_r2_index_endpoint_has_no_duplicate_cells(temp_db):
    _two_version_index(temp_db)
    rows = TestClient(app).get("/sentiment/index", params={"window": "all_time"}).json()["rows"]
    cells = [(r["bank"], r["aspect"]) for r in rows]
    print(f"\nR2 /sentiment/index: {len(cells)} rows, {len(set(cells))} distinct (bank, aspect)")
    assert len(cells) == len(set(cells))


@pytest.mark.parametrize("current", [OLD_V, pytest.param(NEW_V, marks=pytest.mark.xfail(
    strict=True, reason="R2: get_sentiment ignores model_version and returns the other version's row"))])
def test_r2_sentiment_returns_the_current_model_version(temp_db, monkeypatch, current):
    import sentiment.score
    _two_version_index(temp_db)
    monkeypatch.setattr(sentiment.score, "MODEL_VERSION", current)
    body = TestClient(app).get("/sentiment", params={"bank": "DBS", "window": "all_time"}).json()
    print(f"\nR2 current={current}: API returned model_version={body.get('model_version')} "
          f"score={body.get('score')} n={body.get('n')}")
    assert body["model_version"] == current


# R3: /coverage and /evidence take any bank string; spec A2 says bank is validated.

_R3_COVERAGE = pytest.mark.xfail(strict=True, reason="R3: /coverage has no bank pattern, so a bad bank gives 200")


@pytest.mark.parametrize("bank", [pytest.param("dbs", marks=_R3_COVERAGE), pytest.param("HSBC", marks=_R3_COVERAGE)])
def test_r3_coverage_bad_bank_returns_422(temp_db, bank):
    resp = TestClient(app).get("/coverage", params={"bank": bank})
    print(f"\nR3 /coverage?bank={bank}: {resp.status_code} {resp.text[:120]}")
    assert resp.status_code == 422


_R3_EVIDENCE = pytest.mark.xfail(strict=True, reason="R3: /evidence has no bank pattern, so a bad bank gives 200")


@pytest.mark.parametrize("bank", [pytest.param("dbs", marks=_R3_EVIDENCE), pytest.param("HSBC", marks=_R3_EVIDENCE)])
def test_r3_evidence_bad_bank_returns_422(monkeypatch, bank):
    calls = []
    monkeypatch.setattr("api.main.search_evidence",   # stub: no embedding model is loaded
                        lambda query, **kw: calls.append(kw) or {"results": [], "n_found": 0})
    resp = TestClient(app).get("/evidence", params={"query": "dividend", "bank": bank})
    print(f"\nR3 /evidence?bank={bank}: {resp.status_code}; search called with {calls}")
    assert resp.status_code == 422
