"""
Tests for ingest/yahoo_analyst.py and the get_analyst_consensus chatbot tool.
No network calls - Yahoo's payload shape is pinned as a fixture so a change in
their API surfaces as a real ingestion failure, not a silently-passing test.
"""

import pytest

from chatbot.tools import get_analyst_consensus
from ingest.yahoo_analyst import _raw, fetch_bank, upsert

# Trimmed copy of a real Yahoo quoteSummary response (confirmed against the live API).
_FAKE_PAYLOAD = {
    "quoteSummary": {
        "result": [{
            "financialData": {
                "numberOfAnalystOpinions": {"raw": 16},
                "recommendationKey": "buy",
                "recommendationMean": {"raw": 2.1875},
                "targetMeanPrice": {"raw": 76.72708},
                "targetMedianPrice": {"raw": 79.5},
                "targetHighPrice": {"raw": 85.86},
                "targetLowPrice": {"raw": 63.0},
                "currentPrice": {"raw": 78.65},
                "ebitda": {},  # Yahoo returns absent numerics as empty dicts
            },
            "recommendationTrend": {"trend": [
                {"period": "0m", "strongBuy": 1, "buy": 7, "hold": 7, "sell": 1, "strongSell": 0},
                {"period": "-1m", "strongBuy": 1, "buy": 8, "hold": 7, "sell": 0, "strongSell": 0},
            ]},
        }]
    }
}


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "fake"

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self._status_code = status_code

    def get(self, url, params=None, timeout=None):
        return _FakeResponse(self._payload, self._status_code)


def test_raw_handles_empty_dict_fields():
    # Yahoo sends absent numerics as {} - a naive ['raw'] read would KeyError.
    assert _raw({"ebitda": {}}, "ebitda") is None
    assert _raw({"targetMeanPrice": {"raw": 76.7}}, "targetMeanPrice") == 76.7
    assert _raw({}, "missing") is None


def test_fetch_bank_parses_real_payload_shape():
    row = fetch_bank(_FakeSession(_FAKE_PAYLOAD), "crumb", "DBS", "D05.SI")
    assert row["bank"] == "DBS"
    assert row["ticker"] == "D05.SI"
    assert row["n_analysts"] == 16
    assert row["recommendation_key"] == "buy"
    assert row["target_mean"] == pytest.approx(76.72708)
    # must take the '0m' (current month) trend entry, not just the first one
    assert row["buy"] == 7 and row["hold"] == 7


def test_fetch_bank_returns_none_on_http_error():
    assert fetch_bank(_FakeSession({}, status_code=401), "c", "DBS", "D05.SI") is None


def test_fetch_bank_returns_none_on_empty_result():
    empty = {"quoteSummary": {"result": None}}
    assert fetch_bank(_FakeSession(empty), "c", "DBS", "D05.SI") is None


def test_upsert_and_read_back(temp_db):
    row = fetch_bank(_FakeSession(_FAKE_PAYLOAD), "crumb", "DBS", "D05.SI")
    assert upsert([row]) == 1
    result = get_analyst_consensus("DBS")
    assert result["has_data"] is True
    assert result["n_analysts"] == 16
    assert result["consensus_rating"] == "buy"
    # implied upside: (76.72708 - 78.65) / 78.65 * 100 = -2.4%
    assert result["implied_upside_pct"] == pytest.approx(-2.4, abs=0.1)


def test_upsert_same_day_replaces_not_duplicates(temp_db):
    row = fetch_bank(_FakeSession(_FAKE_PAYLOAD), "crumb", "DBS", "D05.SI")
    upsert([row])
    upsert([row])
    conn = temp_db.get_connection()
    count = conn.execute("SELECT COUNT(*) FROM analyst_consensus WHERE bank='DBS'").fetchone()[0]
    conn.close()
    assert count == 1


def test_get_analyst_consensus_no_data(temp_db):
    result = get_analyst_consensus("OCBC")
    assert result["has_data"] is False


def test_latest_per_bank_keeps_a_bank_fetched_on_an_earlier_day(temp_db):
    """UOB last fetched a day before DBS must still appear (the dashboard lost it on 2026-09-25)."""
    from ingest.db import get_connection
    from ingest.yahoo_analyst import latest_per_bank
    base = fetch_bank(_FakeSession(_FAKE_PAYLOAD), "crumb", "DBS", "D05.SI")
    upsert([{**base, "bank": "DBS", "as_of_date": "2026-09-25"},
            {**base, "bank": "UOB", "ticker": "U11.SI", "as_of_date": "2026-09-24"},
            {**base, "bank": "UOB", "ticker": "U11.SI", "as_of_date": "2026-09-10"}])
    conn = get_connection()
    try:
        rows = latest_per_bank(conn)
    finally:
        conn.close()
    assert [(r[0], r[1]) for r in rows] == [("DBS", "2026-09-25"), ("UOB", "2026-09-24")]
