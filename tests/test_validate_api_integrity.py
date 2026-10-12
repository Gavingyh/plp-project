"""
Validation of the API integrity claim (CLAUDE.md): the index endpoints return the stored
index unchanged, and every endpoint taking `bank`, `window` or `bucket`
rejects a bad value with 422.

Expected rows are read from data/plp.db read-only. The API reads a backup copy
in tmp_path (ingest.db.get_connection runs a PRAGMA on open).

/sentiment/series is computed from aspect_sentiment, not stored; its check is
that the buckets add up to the stored all_time row (n, pos_n, neu_n, neg_n),
and that a single-bucket series reproduces the stored score exactly.
"""

import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from api.main import app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_DB = os.path.join(ROOT, "data", "plp.db")
BANKS = ["DBS", "OCBC", "UOB"]
WINDOWS = ["7d", "30d", "all_time"]
COLS = ["bank", "aspect", "source", "score", "n", "pos_n", "neu_n", "neg_n",
        "confidence_mean", "model_version", "computed_at"]


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _stored(where="1=1", params=()):
    from config.model_version import MODEL_VERSION
    conn = _ro(REAL_DB)
    try:
        rows = conn.execute(
            f"SELECT {', '.join(COLS)}, window FROM sentiment_index "
            f"WHERE model_version = ? AND {where}", (MODEL_VERSION, *params)).fetchall()
    finally:
        conn.close()
    return [dict(zip(COLS + ["window"], r)) for r in rows]


def _aspects():
    return sorted({r["aspect"] for r in _stored()})


@pytest.fixture
def real_db_copy(tmp_path, monkeypatch, served_version):
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


def _headline(bank, aspect, window):
    rows = _stored("bank = ? AND aspect = ? AND window = ? AND source = 'ALL'",
                   (bank, aspect, window))
    assert len(rows) <= 1, rows
    return rows[0] if rows else None


def _check_sentiment_body(body, row, bank, aspect, window):
    assert body["bank"] == bank and body["aspect"] == aspect and body["window"] == window
    if row is None:
        assert body["insufficient_data"] is True and "score" not in body
        return "missing"
    assert body["n"] == row["n"]
    if row["n"] < 5:
        assert body["insufficient_data"] is True and "score" not in body
        return "thin"
    assert body["insufficient_data"] is False
    assert body["score"] == row["score"]
    assert (body["positive_n"], body["neutral_n"], body["negative_n"]) == \
           (row["pos_n"], row["neu_n"], row["neg_n"])
    assert body["confidence_mean"] == row["confidence_mean"]
    assert body["model_version"] == row["model_version"]
    assert body["computed_at"] == row["computed_at"]
    return "full"


# ---------------------------------------------------------------- /sentiment

def test_sentiment_every_cell_matches_stored_row(real_db_copy):
    client = TestClient(app)
    counts = {"full": 0, "thin": 0, "missing": 0}
    for bank in BANKS:
        for window in WINDOWS:
            for aspect in _aspects():
                params = {"bank": bank, "window": window}
                if aspect != "ALL":
                    params["aspect"] = aspect
                resp = client.get("/sentiment", params=params)
                assert resp.status_code == 200
                counts[_check_sentiment_body(resp.json(), _headline(bank, aspect, window),
                                             bank, aspect, window)] += 1
    print(f"\n/sentiment cells checked: {counts}")
    assert counts["full"] > 0


# ------------------------------------------------------- /sentiment/compare

def test_compare_every_aspect_window_matches_stored_rows(real_db_copy):
    client = TestClient(app)
    checked = 0
    for window in WINDOWS:
        for aspect in _aspects():
            params = {"window": window}
            if aspect != "ALL":
                params["aspect"] = aspect
            resp = client.get("/sentiment/compare", params=params)
            assert resp.status_code == 200
            body = resp.json()
            assert body["aspect"] == aspect and body["window"] == window
            assert sorted(body["banks"]) == BANKS
            for bank in BANKS:
                _check_sentiment_body(body["banks"][bank], _headline(bank, aspect, window),
                                      bank, aspect, window)
                checked += 1
    print(f"\n/sentiment/compare bank cells checked: {checked}")


# --------------------------------------------------------- /sentiment/index

def _key(r):
    return (r["bank"], r["aspect"], r["source"])


@pytest.mark.parametrize("window", WINDOWS)
def test_index_default_source_equals_stored_rows(real_db_copy, window):
    resp = TestClient(app).get("/sentiment/index", params={"window": window})
    assert resp.status_code == 200
    api_rows = resp.json()["rows"]
    stored = _stored("window = ? AND source = 'ALL'", (window,))
    api = {_key(r): {k: r[k] for k in COLS} for r in api_rows}
    exp = {_key(r): {k: r[k] for k in COLS} for r in stored}
    print(f"\n/sentiment/index window={window} source=ALL: api {len(api_rows)} rows, db {len(stored)}")
    assert len(api_rows) == len(api)            # no duplicate cells
    assert api == exp
    assert all(r["insufficient_data"] is (r["n"] < 5) for r in api_rows)


@pytest.mark.parametrize("window", WINDOWS)
def test_index_star_source_equals_stored_rows(real_db_copy, window):
    resp = TestClient(app).get("/sentiment/index", params={"window": window, "source": "*"})
    api_rows = resp.json()["rows"]
    stored = _stored("window = ?", (window,))
    api = {_key(r): {k: r[k] for k in COLS} for r in api_rows}
    exp = {_key(r): {k: r[k] for k in COLS} for r in stored}
    print(f"\n/sentiment/index window={window} source=*: api {len(api_rows)} rows, db {len(stored)}")
    assert len(api_rows) == len(api) and api == exp


def test_index_each_named_source_equals_stored_rows(real_db_copy):
    client = TestClient(app)
    sources = sorted({r["source"] for r in _stored()})
    for window in WINDOWS:
        for source in sources:
            api_rows = client.get("/sentiment/index",
                                  params={"window": window, "source": source}).json()["rows"]
            stored = _stored("window = ? AND source = ?", (window, source))
            assert {_key(r): {k: r[k] for k in COLS} for r in api_rows} == \
                   {_key(r): {k: r[k] for k in COLS} for r in stored}, (window, source)
            assert len(api_rows) == len(stored)
    print(f"\n/sentiment/index sources checked: {sources}")


# --------------------------------------------------------- /sentiment/trend

def test_trend_blocks_match_stored_rows(real_db_copy):
    client = TestClient(app)
    summary = []
    for bank in BANKS:
        for aspect in _aspects():
            params = {"bank": bank}
            if aspect != "ALL":
                params["aspect"] = aspect
            resp = client.get("/sentiment/trend", params=params)
            assert resp.status_code == 200
            body = resp.json()
            if body["trend_available"]:
                _check_sentiment_body(body["recent_7d"], _headline(bank, aspect, "7d"),
                                      bank, aspect, "7d")
                _check_sentiment_body(body["baseline_30d"], _headline(bank, aspect, "30d"),
                                      bank, aspect, "30d")
                summary.append((bank, aspect, body["direction"], body["delta_7d_vs_30d"]))
            else:
                # fallback: the all_time snapshot, flattened into the body
                row = _headline(bank, aspect, "all_time")
                fb = {k: v for k, v in body.items()
                      if k not in ("trend_available", "note")}
                _check_sentiment_body(fb, row, bank, aspect, "all_time")
    print(f"\n/sentiment/trend available: {summary}")


# -------------------------------------------------------- /sentiment/series

@pytest.mark.parametrize("bucket", ["week", "month", "quarter"])
def test_series_buckets_add_up_to_stored_all_time(real_db_copy, bucket):
    client = TestClient(app)
    mismatches = []
    for bank in BANKS:
        for aspect in _aspects():
            row = _headline(bank, aspect, "all_time")
            params = {"bank": bank, "bucket": bucket, "min_n": 1}
            if aspect != "ALL":
                params["aspect"] = aspect
            resp = client.get("/sentiment/series", params=params)
            assert resp.status_code == 200
            series = resp.json()["series"]
            got = tuple(sum(p[k] for p in series) for k in ("n", "pos_n", "neu_n", "neg_n"))
            exp = (0, 0, 0, 0) if row is None else (row["n"], row["pos_n"], row["neu_n"], row["neg_n"])
            if got != exp:
                mismatches.append((bank, aspect, got, exp))
    print(f"\n/sentiment/series bucket={bucket} mismatches (bank, aspect, api, db): {mismatches}")
    assert mismatches == []


def test_series_single_bucket_reproduces_stored_score(temp_db):
    """Synthetic: all sentences in one month, so the series' one bucket is the
    all_time cell and must carry the stored score unchanged."""
    import aggregate.index as agg
    from config.model_version import MODEL_VERSION
    from ingest.db import now_iso
    conn = temp_db.get_connection()
    labels = ["positive"] * 7 + ["neutral"] * 4 + ["negative"] * 2
    for i, label in enumerate(labels):
        conn.execute(
            "INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
            "norm_hash, processed_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"s{i}", f"d{i}", "OCBC", f"t{i}", f"2025-03-{10 + i:02d}T00:00:00+00:00",
             "newsapi" if i % 2 else "arctic_shift", "http://x", f"h{i}", now_iso()))
        for aspect in ("asset_quality", "dividend_policy"):
            conn.execute("INSERT OR IGNORE INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) VALUES (?,?,1.0,?)", (f"s{i}", aspect, now_iso()))
            conn.execute(
                "INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, "
                "model_version, scored_at) VALUES (?,?,?,?,?,?)",
                (f"s{i}", aspect, label, 0.5 + 0.03 * i, MODEL_VERSION, now_iso()))
    conn.commit()
    conn.close()
    agg.run()
    client = TestClient(app)
    for aspect in (None, "asset_quality"):
        params = {"bank": "OCBC", "bucket": "month"}
        if aspect:
            params["aspect"] = aspect
        series = client.get("/sentiment/series", params=params).json()["series"]
        stored = client.get("/sentiment", params={"bank": "OCBC", **({"aspect": aspect} if aspect else {})}).json()
        assert len(series) == 1
        assert (series[0]["score"], series[0]["n"]) == (stored["score"], stored["n"])
        assert series[0]["confidence_mean"] == stored["confidence_mean"]


# -------------------------------------------------------------------- 422s

BAD_BANKS = ["NOTABANK", "dbs", "Dbs", "DBS ", " DBS", "DBSX", "", "DBS\n", "DBS|OCBC",
             "DBS%", "ALL", "HSBC", "DBS;--"]
BAD_WINDOWS = ["5years", "ALL_TIME", "7D", "90d", "", "all_time\n", "7d|30d", " 7d", "all"]
BAD_BUCKETS = ["day", "Month", "year", "", "month\n", "week|month", " week", "quarterly"]

BANK_ROUTES = [  # (path, other required params, bank required?)
    ("/sentiment", {}, True),
    ("/sentiment/trend", {}, True),
    ("/sentiment/series", {}, True),
    ("/coverage", {}, False),
    ("/evidence", {"query": "dividend"}, False),
    ("/analyst-consensus", {}, True),
    ("/evidence/latest", {}, True),
]
WINDOW_ROUTES = [
    ("/sentiment", {"bank": "DBS"}),
    ("/sentiment/compare", {}),
    ("/sentiment/index", {}),
]
BUCKET_ROUTES = [("/sentiment/series", {"bank": "DBS"})]


@pytest.fixture
def client(temp_db, monkeypatch):
    monkeypatch.setattr("api.main.search_evidence",   # no embedding model
                        lambda query, **kw: {"query": query, "results": [], "n_found": 0})
    return TestClient(app)


def test_route_lists_cover_every_endpoint_with_these_params():
    """Guards the lists below: every route in api/main.py taking bank, window or
    bucket is checked."""
    from fastapi.routing import APIRoute
    found = {"bank": set(), "window": set(), "bucket": set()}
    for r in app.routes:
        if isinstance(r, APIRoute):
            for p in r.dependant.query_params:
                if p.name in found:
                    found[p.name].add(r.path)
    print(f"\nroutes by param: {found}")
    assert found["bank"] == {p for p, _, _ in BANK_ROUTES}
    assert found["window"] == {p for p, _ in WINDOW_ROUTES}
    assert found["bucket"] == {p for p, _ in BUCKET_ROUTES}


@pytest.mark.parametrize("path,extra,_req", BANK_ROUTES)
@pytest.mark.parametrize("bank", BAD_BANKS)
def test_bad_bank_422(client, path, extra, _req, bank):
    resp = client.get(path, params={**extra, "bank": bank})
    assert resp.status_code == 422, (path, repr(bank), resp.status_code, resp.text[:200])


@pytest.mark.parametrize("path,extra,required", BANK_ROUTES)
def test_missing_required_bank_422(client, path, extra, required):
    if not required:
        pytest.skip("bank is optional here")
    assert client.get(path, params=extra).status_code == 422


@pytest.mark.parametrize("path,extra", WINDOW_ROUTES)
@pytest.mark.parametrize("window", BAD_WINDOWS)
def test_bad_window_422(client, path, extra, window):
    resp = client.get(path, params={**extra, "window": window})
    assert resp.status_code == 422, (path, repr(window), resp.status_code, resp.text[:200])


@pytest.mark.parametrize("path,extra", BUCKET_ROUTES)
@pytest.mark.parametrize("bucket", BAD_BUCKETS)
def test_bad_bucket_422(client, path, extra, bucket):
    resp = client.get(path, params={**extra, "bucket": bucket})
    assert resp.status_code == 422, (path, repr(bucket), resp.status_code, resp.text[:200])


# Controls: the same routes accept every good value, so the 422s come from the value.

@pytest.mark.parametrize("path,extra,_req", BANK_ROUTES)
@pytest.mark.parametrize("bank", BANKS)
def test_good_bank_200(client, path, extra, _req, bank):
    resp = client.get(path, params={**extra, "bank": bank})
    assert resp.status_code == 200, (path, bank, resp.status_code, resp.text[:200])


@pytest.mark.parametrize("path,extra", WINDOW_ROUTES)
@pytest.mark.parametrize("window", WINDOWS)
def test_good_window_200(client, path, extra, window):
    assert client.get(path, params={**extra, "window": window}).status_code == 200


@pytest.mark.parametrize("bucket", ["week", "month", "quarter"])
def test_good_bucket_200(client, bucket):
    assert client.get("/sentiment/series", params={"bank": "DBS", "bucket": bucket}).status_code == 200


# ---------------------------------------------------------------------------
# Step 3: reviewer findings. Each test fails if the finding is real.
# ---------------------------------------------------------------------------

import logging
from datetime import datetime, timedelta, timezone


def _add_scored(temp_db, sid, bank, aspect, days_ago, label, version=None):
    from config.model_version import MODEL_VERSION
    from ingest.db import now_iso
    published = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn = temp_db.get_connection()
    conn.execute(
        "INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
        "norm_hash, processed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (sid, f"doc-{sid}", bank, f"text {sid}", published, "arctic_shift", "http://x",
         f"hash-{sid}", now_iso()))
    conn.execute("INSERT OR IGNORE INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) VALUES (?,?,1.0,?)", (sid, aspect, now_iso()))
    conn.execute(
        "INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, "
        "scored_at) VALUES (?,?,?,?,?,?)",
        (sid, aspect, label, 1.0, version or MODEL_VERSION, now_iso()))
    conn.commit()
    conn.close()


# Trend self-consistency: the delta and direction come from unshrunk
# scores, and the response now returns them, so the delta can be recomputed.

def test_trend_delta_reproducible_from_returned_fields(temp_db):
    import aggregate.index as agg
    i = 0
    for label in ["positive"] * 4 + ["neutral"] * 2:          # 7d: raw 0.6667, shrunk 0.3636
        _add_scored(temp_db, f"r{i}", "UOB", "asset_quality", 1, label); i += 1
    for k, label in enumerate(["positive"] * 41 + ["neutral"] * 53):  # 30d: raw 0.45, shrunk 0.4286
        _add_scored(temp_db, f"o{i}", "UOB", "asset_quality", 10 + k % 15, label); i += 1
    agg.run()
    body = TestClient(app).get("/sentiment/trend", params={"bank": "UOB"}).json()
    r, b = body["recent_7d"], body["baseline_30d"]
    print(f"\ntrend: direction={body['direction']} delta={body['delta_7d_vs_30d']} "
          f"7d score={r['score']} n={r['n']}; 30d score={b['score']} n={b['n']}; "
          f"other keys={sorted(set(body) - {'recent_7d', 'baseline_30d', 'monthly_series'})}")
    assert body["trend_available"] is True
    # Every number the response returns that could be a 7d or 30d score.
    candidates_7d = [v for k, v in r.items() if isinstance(v, float) and "score" in k]
    candidates_30d = [v for k, v in b.items() if isinstance(v, float) and "score" in k]
    candidates_7d += [v for k, v in body.items() if isinstance(v, float) and "7d" in k and "delta" not in k]
    candidates_30d += [v for k, v in body.items() if isinstance(v, float) and "30d" in k and "delta" not in k]
    reproducible = any(abs((x - y) - body["delta_7d_vs_30d"]) <= 2e-4
                       for x in candidates_7d for y in candidates_30d)
    assert reproducible, ("delta not reproducible from returned scores", candidates_7d, candidates_30d)


# Wrong model version: a MODEL_VERSION with no rows is reported and
# logged, not shown as ordinary "no data".

def test_wrong_model_version_is_distinguishable_from_no_data(temp_db, monkeypatch, caplog):
    import aggregate.index as agg
    import config.model_version
    for i in range(10):
        _add_scored(temp_db, f"v{i}", "DBS", "asset_quality", 200, "positive")
    agg.run()
    client = TestClient(app)
    caplog.set_level(logging.DEBUG)
    for name in ("chatbot.tools", "api.main", "aggregate.index", "chatbot.suggestions"):
        logging.getLogger(name).addHandler(caplog.handler)

    # Genuine no-data: right version, bank with no rows.
    no_data = client.get("/sentiment", params={"bank": "OCBC"}).json()
    monkeypatch.setattr(config.model_version, "MODEL_VERSION", "no-such-model-v9")
    caplog.clear()
    wrong = client.get("/sentiment", params={"bank": "DBS"}).json()
    sugg = client.get("/suggestions").json()
    logged = [rec.getMessage() for rec in caplog.records
              if rec.levelno >= logging.WARNING and "httpx" not in rec.name]
    print(f"\nno-data body: {no_data}\nwrong-version body: {wrong}\n"
          f"suggestions: {sugg}\nwarnings logged: {logged}")
    strip = lambda d: {k: v for k, v in d.items() if k != "bank"}
    distinguishable = (strip(wrong) != strip(no_data)
                       or "no-such-model-v9" in str(wrong)
                       or any("no-such-model-v9" in m or "model_version" in m.lower() for m in logged))
    assert distinguishable


# Evidence result count: k is bounded, and a negative k no longer
# slices off the last result.

@pytest.mark.parametrize("k", [-1, 0, 51])
def test_evidence_k_out_of_range_returns_422(monkeypatch, k):
    monkeypatch.setattr("api.main.search_evidence", lambda query, **kw: {"results": [], "n_found": 0})
    assert TestClient(app).get("/evidence", params={"query": "dividend", "k": k}).status_code == 422


def test_retrieval_negative_k_returns_nothing(temp_db):
    import chatbot.retrieval as retrieval
    assert retrieval.search_evidence("dividend", bank="DBS", k=-1) == []
