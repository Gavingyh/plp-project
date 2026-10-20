"""
Tests for ingest/base.py's bank detection/resolution - the logic behind two
regressions this suite guards against:
  1. NewsAPI's bare "DBS" query term matched unrelated global news.
  2. preprocess/pipeline.py inheriting doc-level bank onto every sentence in
     a long Reddit thread produced noise ("Calling you for $8 transaction
     is a red flag itself." tagged as DBS).
These tests don't re-test the query-construction or inheritance-source
logic directly (that's preprocess/pipeline.py's job, tested separately) -
they lock down the underlying detect_banks/resolve_bank primitives both bugs
ultimately depend on.
"""

from ingest.base import detect_banks, resolve_bank


def test_detects_full_name():
    assert detect_banks("DBS Group posted record profits") == ["DBS"]


def test_detects_bare_acronym():
    assert detect_banks("just transfer to DBS") == ["DBS"]


def test_detects_ticker():
    assert detect_banks("D05.SI hit a new high") == ["DBS"]


def test_no_bank_mentioned():
    assert detect_banks("I like index funds") == []


def test_multiple_banks_in_one_sentence():
    found = detect_banks("OCBC and UOB both reported higher profits")
    assert set(found) == {"OCBC", "UOB"}


def test_case_insensitive():
    assert detect_banks("dbs raised its dividend") == ["DBS"]


def test_word_boundary_no_partial_match():
    # "DBSK" (a K-pop group) or similar should NOT match bare "DBS" -
    # detect_banks must respect word boundaries, not substring search.
    assert detect_banks("DBSK reunion tour announced") == []


def test_resolve_bank_single_match():
    assert resolve_bank("DBS raised guidance") == "DBS"


def test_resolve_bank_multi_match_returns_multi():
    assert resolve_bank("OCBC and UOB both reported higher profits") == "MULTI"


def test_resolve_bank_no_match_returns_fallback():
    assert resolve_bank("the market was quiet today", fallback="DBS") == "DBS"


def test_resolve_bank_no_match_no_fallback_returns_none():
    assert resolve_bank("the market was quiet today") is None


# --- POSB counts as DBS at collection --------------------------------------------


def test_posb_alone_is_dbs():
    assert detect_banks("I opened a POSB account last year") == ["DBS"]
    assert resolve_bank("POSB eSavings interest cut again") == "DBS"


def test_posb_and_dbs_together_are_one_bank():
    assert detect_banks("DBS/POSB app is down") == ["DBS"]
    assert resolve_bank("POSB savings versus OCBC 360") == "MULTI"


def test_posb_is_not_found_inside_other_words():
    assert detect_banks("the posbility of a rate cut") == []


class _Response:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def test_alpha_vantage_still_reads_the_ticker_at_position_2(monkeypatch):
    # Appending POSB must not move "D05.SI": Alpha Vantage takes queries[2].
    import ingest.alphavantage as av

    sent = []
    monkeypatch.setattr(av, "AV_KEY", "k")
    monkeypatch.setattr(av.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        av,
        "request_with_retries",
        lambda url, params: sent.append(params) or _Response({"feed": []}),
    )
    av.pull()
    assert [p["tickers"] for p in sent] == ["D05", "O39", "U11"]


def test_newsapi_queries_never_include_posb(monkeypatch):
    # NewsAPI queries only aliases with a space or a dot, so a bare "POSB" (like
    # a bare "DBS") never widens the search to unrelated news.
    import ingest.newsapi as na

    sent = []
    monkeypatch.setenv("NEWSAPI_KEY", "synthetic-key")
    monkeypatch.setattr(na.time, "sleep", lambda s: None)
    import requests
    import json

    def get(url, *, params, headers, timeout, allow_redirects):
        sent.append(params)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(
            {"status": "ok", "articles": [], "totalResults": 0}
        ).encode()
        return response

    monkeypatch.setattr(na.requests, "get", get)
    na.pull()
    dbs = [p["q"] for p in sent if "DBS Bank" in p["q"]]
    assert dbs and all("POSB" not in q for q in dbs)
