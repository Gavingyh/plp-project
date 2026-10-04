"""
Tests for ingest/yahoo_news.py, ingest/google_news.py and run_news_pull.py.
Payload shapes are pinned from real responses captured on 2026-09-24, so a
change in either feed shows up as a mapping failure here, not as silently
empty rows. No network calls.
"""

import time
from datetime import date

import pytest

import ingest.google_news as gn
import ingest.news_filter as nf
from ingest.db import upsert_documents
from ingest.google_news import _clean_title, _fetch_window, _months
from ingest.yahoo_news import to_document as yahoo_doc
from run_news_pull import count_table

# Trimmed copy of a real yfinance Ticker("U11.SI").get_news() item.
YAHOO_ITEM = {
    "id": "cb90b7fe-f02e-3b6e-b4b3-cc35b002e0d4",
    "content": {
        "id": "cb90b7fe-f02e-3b6e-b4b3-cc35b002e0d4",
        "contentType": "STORY",
        "title": "Allianz to buy UOB’s asset management arm for $432.8m",
        "description": "",
        "summary": "UOBAM has been part of the UOB Group for 40 years and reported assets "
                   "under management of around $32.75bn (S$42bn) as of 31 December 2025.",
        "pubDate": "2026-08-06T15:03:05Z",
        "displayTime": "2026-08-06T15:03:05Z",
        "thumbnail": {"resolutions": [{"url": "https://s.yimg.com/x.jpg", "width": 1200}]},
        "provider": {"displayName": "Life Insurance International",
                     "url": "https://www.globaldata.com/"},
        "canonicalUrl": {"url": "https://www.lifeinsuranceinternational.com/news/"
                                "allianz-uob-asset-management-arm-s555m/"},
        "clickThroughUrl": {"url": "https://finance.yahoo.com/markets/stocks/articles/"
                                   "allianz-buy-uob-asset-management-150305924.html"},
    },
}

# A real Google News RSS entry as feedparser returns it (link shortened).
GOOGLE_ENTRY = {
    "id": "CBMivgFBVV95cUxQZGRsYUF4Z3FmNzRVVGs1dWw0dzduNDVqVUI3eFFQbFVvcmlf",
    "title": "DBS and POSB digital banking services restored after disruption lasting "
             "more than 2 hours - The Straits Times",
    "link": "https://news.google.com/rss/articles/CBMivgFBVV95cUxQZGRsYUF4Z3FmNzRVVGs1dWw0?oc=5",
    "published": "Thu, 02 May 2024 07:00:00 GMT",
    "published_parsed": time.struct_time((2024, 5, 2, 7, 0, 0, 3, 123, 0)),
    "source": {"href": "https://www.straitstimes.com", "title": "The Straits Times"},
}


def test_yahoo_item_maps_to_document():
    d = yahoo_doc(YAHOO_ITEM, "UOB", "U11.SI", "news")
    assert d["source"] == "yahoo_news"
    assert d["title"] == "Allianz to buy UOB’s asset management arm for $432.8m"
    assert d["body"].startswith(d["title"] + ". UOBAM has been part")
    assert d["published_at"] == "2026-08-06T15:03:05+00:00"
    assert d["url"].startswith("https://www.lifeinsuranceinternational.com/")  # publisher, not Yahoo
    assert d["source_detail"] == "Life Insurance International"
    assert "thumbnail" not in d["raw"]  # raw kept lean: plp.db is near GitHub's file limit


def test_yahoo_doc_id_is_stable_across_tickers_and_tabs():
    a = yahoo_doc(YAHOO_ITEM, "UOB", "U11.SI", "news")
    b = yahoo_doc(YAHOO_ITEM, "UOB", "UOVEY", "all")
    assert a["doc_id"] == b["doc_id"]


def test_yahoo_item_without_title_is_skipped():
    assert yahoo_doc({"id": "x", "content": {"title": ""}}, "DBS", "D05.SI", "news") is None


def test_google_entry_maps_to_document():
    d = gn.to_document(GOOGLE_ENTRY, "DBS", "DBS bank Singapore", ("2024-05-01", "2024-06-01"))
    assert d["source"] == "google_news"
    assert d["title"] == ("DBS and POSB digital banking services restored after disruption "
                          "lasting more than 2 hours")  # " - The Straits Times" stripped
    assert d["body"] == d["title"]  # RSS has no real snippet
    assert d["source_detail"] == "The Straits Times"
    assert d["published_at"] == "2024-05-02T07:00:00+00:00"
    assert d["raw"]["source_href"] == "https://www.straitstimes.com"


def test_clean_title_keeps_hyphens_that_are_not_the_publisher():
    assert _clean_title("UOB - Kay Hian merger talk - Reuters", "Reuters") == "UOB - Kay Hian merger talk"
    assert _clean_title("DBS Q1 - record profit", "Bloomberg") == "DBS Q1 - record profit"


def test_months_cover_range_exactly():
    assert list(_months(date(2024, 11, 15), date(2025, 2, 10))) == [
        (date(2024, 11, 15), date(2024, 12, 1)),
        (date(2024, 12, 1), date(2025, 1, 1)),
        (date(2025, 1, 1), date(2025, 2, 1)),
        (date(2025, 2, 1), date(2025, 2, 10)),
    ]


def test_full_window_is_split_and_requeried(monkeypatch):
    calls = []

    def fake_fetch(query):
        calls.append(query)
        n = gn.SPLIT_AT if "after:2024-03-01 before:2024-04-01" in query else 3
        return [{**GOOGLE_ENTRY, "id": f"{query}-{i}", "title": f"DBS story {i}"} for i in range(n)]

    monkeypatch.setattr(gn, "_fetch", fake_fetch)
    docs = _fetch_window("DBS", "DBS bank Singapore", date(2024, 3, 1), date(2024, 4, 1))
    assert len(calls) == 3  # the full month, then its two halves
    assert len(docs) == 6


def _google_down(query):
    raise RuntimeError("HTTP 503 after retries")


def test_a_failed_window_is_recorded_not_read_as_a_quiet_month(monkeypatch):
    monkeypatch.setattr(gn, "FAILED_WINDOWS", [])
    monkeypatch.setattr(gn, "QUERIES", {"DBS": ["DBS bank Singapore"]})
    monkeypatch.setattr(gn, "_fetch", _google_down)
    assert list(gn.iter_batches("2024-03-01", "2024-04-01")) == [("2024-03", [])]
    assert len(gn.FAILED_WINDOWS) == 1
    assert "DBS" in gn.FAILED_WINDOWS[0] and "2024-03-01" in gn.FAILED_WINDOWS[0]


def test_news_pull_exits_non_zero_when_a_google_window_failed(temp_db, monkeypatch, tmp_path):
    import runpy
    import sys

    import config.logging_config as logging_config

    monkeypatch.setattr(nf, "FLAGGED_PATH", str(tmp_path / "f.csv"))
    monkeypatch.setattr(gn, "FAILED_WINDOWS", [])
    monkeypatch.setattr(gn, "QUERIES", {"DBS": ["DBS bank Singapore"]})
    monkeypatch.setattr(gn, "_fetch", _google_down)
    monkeypatch.setattr(logging_config, "setup_logging", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["run_news_pull.py", "--source", "google",
                                      "--since", "2024-03-01", "--until", "2024-04-01"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("run_news_pull", run_name="__main__")
    assert exit_info.value.code not in (0, None)


def test_count_table_lists_news_by_month(temp_db, monkeypatch, tmp_path):
    monkeypatch.setattr(nf, "FLAGGED_PATH", str(tmp_path / "f.csv"))
    upsert_documents([
        {"doc_id": "a", "source": "google_news", "bank": "DBS", "doc_type": "article",
         "title": "t", "body": "b", "published_at": "2024-03-02T00:00:00+00:00", "url": "u1"},
        {"doc_id": "b", "source": "yahoo_news", "bank": "UOB", "doc_type": "article",
         "title": "t", "body": "b", "published_at": "2024-04-02T00:00:00+00:00", "url": "u2"},
    ])
    table = count_table()
    assert "| 2024-03 | 0 | 1 | 1 |" in table  # columns: yahoo UOB, google DBS, total
    assert table.splitlines()[-1] == "| **total** | 1 | 1 | 2 |"


def test_query_filter_runs_only_matching_queries(monkeypatch):
    seen = []
    monkeypatch.setattr(gn, "_fetch_window", lambda bank, q, s, e: seen.append(q) or [])
    list(gn.iter_batches("2024-03-01", "2024-04-01", query_filter="intitle:"))
    assert len(seen) == 3 and all(q.startswith("intitle:") for q in seen)


def test_dbs_intitle_query_needs_banking_context():
    # bare intitle:DBS pulls in Aston Martin DBS, Dragon Ball Super, "DBs" in
    # American football; the pilot found about a third of results were junk
    dbs_intitle = [q for q in gn.QUERIES["DBS"] if q.startswith("intitle:")]
    assert dbs_intitle and "bank" in dbs_intitle[0] and "Singapore" in dbs_intitle[0]
