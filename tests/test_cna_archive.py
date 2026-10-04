"""
Tests for ingest/cna_archive.py: URL parsing and slug matching, CDX range
splitting, live-then-archive fetching, the publish-time read, and loading
through the news filter. No network calls: requests and the extractor are
replaced.
"""

import json

import pytest

import ingest.cna_archive as ca
import ingest.news_filter as nf

LIVE = "https://www.channelnewsasia.com/business/dbs-sued-1-billion-1mdb-6373296"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(ca.time, "sleep", lambda s: None)


@pytest.fixture
def flagged_path(tmp_path, monkeypatch):
    monkeypatch.setattr(nf, "FLAGGED_PATH", str(tmp_path / "news_flagged.csv"))


class _Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


def test_parse_article_url_normalises_scheme_and_query():
    art = ca.parse_article_url("http://www.channelnewsasia.com/business/dbs-sued-1-billion-1mdb-6373296?cid=x")
    assert art == {"section": "business", "slug": "dbs-sued-1-billion-1mdb", "id": "6373296", "url": LIVE}
    assert ca.parse_article_url("https://www.channelnewsasia.com/business") is None


@pytest.mark.parametrize("slug, matches", [
    ("dbs-sued-1-billion-1mdb", True),
    ("face-verification-atm-ocbc", True),
    ("dbs-paylah-cashback-campaign", True),
    ("piyush-gupta-retires", True),
    ("hdbs-flats-resale", False),          # HDB, not DBS
    ("uobam-fund-launch", False),
])
def test_slug_must_name_a_bank_as_a_word(slug, matches):
    assert bool(ca.SLUG_RE.search(slug)) is matches


def test_query_range_halves_until_the_archive_answers(monkeypatch):
    calls = []

    def fake_cdx(section, start, end):
        calls.append((start, end))
        return None if start != end else [f"https://x/{start}"]

    monkeypatch.setattr(ca, "_cdx", fake_cdx)
    lines = ca._query_range("business", ["202301", "202302", "202303"])
    assert lines == ["https://x/202301", "https://x/202302", "https://x/202303"]
    assert calls[0] == ("202301", "202303")


def test_discover_keeps_bank_slugs_and_the_earliest_capture(monkeypatch):
    lines = [f"{LIVE} 20260912000000", f"{LIVE}?x=1 20260910000000",
             "https://www.channelnewsasia.com/business/hdbs-flats-1234567 20260910000000"]
    monkeypatch.setattr(ca, "_query_range", lambda section, months: lines if section == "business" else [])
    found = ca.discover("2026-01-01", "2026-09-26")
    assert list(found) == ["6373296"] and found["6373296"]["timestamp"] == "20260910000000"


def test_published_from_html_reads_cna_metadata():
    html = '<meta name="cXenseParse:recs:publishtime" content="2026-09-09T21:25:00+08:00">'
    assert ca.published_from_html(html) == "2026-09-09T21:25:00+08:00"
    assert ca.published_from_html("<html></html>") is None


def _art(text="DBS rejected the claim."):
    return {"title": "DBS sued", "text": text, "published": "2026-09-09T21:25:00+08:00", "author": "CNA"}


def test_fetch_prefers_the_live_page(monkeypatch):
    monkeypatch.setattr(ca, "_get", lambda url: _Resp(200, "live"))
    monkeypatch.setattr(ca, "extract", lambda html, url: _art() if html == "live" else None)
    rec = ca.fetch_article(ca.parse_article_url(LIVE) | {"timestamp": "20260910000000"})
    assert rec["fetched_from"] == "live" and rec["text"] == "DBS rejected the claim."


def test_fetch_falls_back_to_the_archived_capture(monkeypatch):
    seen = []

    def fake_get(url):
        seen.append(url)
        return _Resp(404) if url == LIVE else _Resp(200, "archived")

    monkeypatch.setattr(ca, "_get", fake_get)
    monkeypatch.setattr(ca, "extract", lambda html, url: _art() if html == "archived" else None)
    rec = ca.fetch_article(ca.parse_article_url(LIVE) | {"timestamp": "20260910000000"})
    assert rec["fetched_from"] == "wayback"
    assert seen[1] == f"https://web.archive.org/web/20260910000000id_/{LIVE}"


def test_fetch_records_an_error_when_nothing_yields_text(monkeypatch):
    monkeypatch.setattr(ca, "_get", lambda url: _Resp(404))
    rec = ca.fetch_article(ca.parse_article_url(LIVE) | {"timestamp": "20260910000000"})
    assert "error" in rec and ca.to_document(rec) is None


def test_fetch_all_resumes_from_the_cache(tmp_path, monkeypatch):
    path = str(tmp_path / "articles.jsonl")
    fetched = []
    monkeypatch.setattr(ca, "fetch_article", lambda c: fetched.append(c["id"]) or {"id": c["id"]})
    cands = {"1": {"id": "1"}, "2": {"id": "2"}}
    ca.fetch_all(cands, path=path)
    ca.fetch_all(cands | {"3": {"id": "3"}}, path=path)
    assert fetched == ["2", "1", "3"] and set(ca.load_cache(path)) == {"1", "2", "3"}


def test_fetch_all_retries_a_cached_failure_but_not_a_missing_page(tmp_path, monkeypatch):
    # A network error or a server error is a blip; caching it lost the article
    # for good. A 404 is a page that is gone.
    path = tmp_path / "articles.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in [
        {"id": "1", "error": "no text (live status 503)"},
        {"id": "2", "error": "no text (live status None)"},
        {"id": "3", "error": "no text (live status 404)"},
        {"id": "4", "text": "DBS rejected the claim."},
    ]))
    fetched = []
    monkeypatch.setattr(ca, "fetch_article",
                        lambda c: fetched.append(c["id"]) or {"id": c["id"], "text": "fetched"})
    ca.fetch_all({k: {"id": k} for k in "1234"}, path=str(path))
    assert fetched == ["2", "1"]
    cache = ca.load_cache(str(path))
    assert cache["1"]["text"] == "fetched" and cache["2"]["text"] == "fetched"   # the retry wins
    assert "error" in cache["3"] and cache["4"]["text"] == "DBS rejected the claim."


def test_candidates_are_discovered_once_then_read_from_the_cache(tmp_path, monkeypatch):
    path = str(tmp_path / "candidates.json")
    calls = []
    monkeypatch.setattr(ca, "discover", lambda since, until: calls.append(1) or {"1": {"id": "1"}})
    assert ca.candidates_for("2023-01-01", "2026-09-26", path=path) == {"1": {"id": "1"}}
    assert ca.candidates_for("2023-01-01", "2026-09-26", path=path) == {"1": {"id": "1"}}
    ca.candidates_for("2023-01-01", "2026-09-26", rediscover=True, path=path)
    assert calls == [1, 1]


def test_in_window_uses_the_singapore_date():
    assert ca.in_window("2023-01-01T00:30:00+08:00", "2023-01-01", "2026-09-26")
    assert not ca.in_window("2026-09-26T08:00:00+08:00", "2023-01-01", "2026-09-26")


def test_load_filters_and_inserts_cna_documents(temp_db, flagged_path):
    rec = {"id": "6373296", "url": LIVE, "section": "business", "fetched_from": "live", **_art(
        "DBS sued for US$1 billion\nDBS rejected the claim.")}
    off_topic = {"id": "1", "url": "https://www.channelnewsasia.com/business/x-1", "section": "business",
                 **_art("Nothing about the banks."), "title": "Markets rise"}
    old = {**rec, "id": "2", "published": "2022-05-01T10:00:00+08:00"}
    stats = ca.load([rec, off_topic, old], "2023-01-01", "2026-09-26")
    assert stats["in_window"] == 2 and stats["inserted"] == 1 and stats["no_bank_mention"] == 1
    conn = temp_db.get_connection()
    source, bank, detail, raw = conn.execute(
        "SELECT source, bank, source_detail, raw FROM documents").fetchone()
    conn.close()
    assert (source, bank, detail) == ("cna", "DBS", "CNA/business")
    assert json.loads(raw)["cna_id"] == "6373296"
    assert ca.load([rec], "2023-01-01", "2026-09-26")["already_stored"] == 1


def test_scraper_json_loads_the_same_way(tmp_path):
    path = tmp_path / "cna.json"
    path.write_text(json.dumps([{"title": "DBS sued", "link": LIVE, "published": "Wed, 09 Sep 2026 21:25:00 +0800",
                                 "full_text": "DBS rejected the claim.", "author": None},
                                {"title": "no link", "link": "", "full_text": "x"}]))
    recs = ca.records_from_scraper_json(str(path))
    assert len(recs) == 1 and recs[0]["published"] == "2026-09-09T21:25:00+08:00"
    assert recs[0]["fetched_from"] == "rss"
