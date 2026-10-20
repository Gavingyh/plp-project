"""
Google News RSS ingestion, backfilled month by month with date-windowed queries.

The RSS search endpoint (news.google.com/rss/search) is free, needs no key,
and accepts `after:YYYY-MM-DD before:YYYY-MM-DD` operators in the query. That
makes history reachable, which Yahoo and NewsAPI's free tier don't allow.
Each response is capped at 100 items. When a window comes back at or near
the cap, it is split in half and re-queried, so busy months aren't truncated.

What an item contains: headline, publisher, publish date, and a
news.google.com redirect link. The RSS <description> is only the headline
again (occasionally a list of related headlines), not an article snippet. So
the stored body is the headline alone. The redirect link isn't resolved to
the publisher URL (that needs an extra request per article to Google). The
publisher's homepage is kept in raw.source_href. No article pages are fetched,
so paywalled outlets (Straits Times, Business Times) contribute headlines
only.

Three queries per bank:
  - a quoted name from the team brief ("DBS Group" Singapore)
  - a looser unquoted one (DBS bank Singapore); in a live probe for March
    2024 it returned 4-7x as many items as the quoted one
  - an intitle: query, which requires the bank in the headline. In a pilot on
    three sample months it added 27-32 new articles a month on
    top of the first two queries, for 3 requests a month. Bare "DBS" in a
    headline also matches Aston Martin DBS, Dragon Ball Super, American
    football "DBs" and deep brain stimulation, so the DBS query needs a
    banking context word; OCBC and UOB don't. Broker and venue names are
    excluded in the query itself.
Non-bank results are removed by news_filter either way.

The same pilot found no gain worth the requests from weekly windows, other
Google News editions (MY/GB/US), per-outlet site: queries, or full-name
variants. See docs/news-data.md.

USAGE:
  python -m ingest.google_news --since 2023-01-01          # backfill to today
  python -m ingest.google_news --since 2024-03-01 --until 2024-04-01
  python -m ingest.google_news --since 2023-01-01 --query-filter intitle:
"""

import argparse
import time
from datetime import date, datetime, timedelta, timezone

from ingest.base import request_with_retries
from ingest.db import make_doc_id, now_iso, upsert_documents

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

SOURCE = "google_news"
RSS_URL = "https://news.google.com/rss/search"
EDITION = {"hl": "en-SG", "gl": "SG", "ceid": "SG:en"}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; plp-research/1.0; academic project)"}

_EXCLUDE = '-"Kay Hian" -"OCBC Arena" -"OCBC Cycle"'   # DBS Vickers counts as DBS
QUERIES = {
    "DBS": ['"DBS Group" Singapore', "DBS bank Singapore",
            f"intitle:DBS (bank OR Singapore OR SGX OR POSB OR PayLah) {_EXCLUDE}"],
    "OCBC": ['"OCBC Bank" Singapore', "OCBC Singapore", f"intitle:OCBC {_EXCLUDE}"],
    "UOB": ['"UOB bank" Singapore', "UOB Singapore", f"intitle:UOB {_EXCLUDE}"],
}

SPLIT_AT = 90         # Google caps a response at 100 items; a window this full may be truncated, so split it
REQUEST_DELAY = 2.0   # seconds between requests. Google has no published limit; stay well clear

# Windows whose request still failed after retries: missing, not quiet.
# iter_batches lists them at the end; the entry points then exit non-zero.
FAILED_WINDOWS: list[str] = []


def _clean_title(title: str, publisher: str | None) -> str:
    """Google appends " - Publisher" to every headline; strip it."""
    title = (title or "").strip()
    if publisher and title.endswith(f" - {publisher}"):
        return title[: -len(publisher) - 3].strip()
    return title


def to_document(entry, bank: str, query: str, window: tuple[str, str]) -> dict | None:
    source = entry.get("source") or {}
    publisher = source.get("title")
    title = _clean_title(entry.get("title"), publisher)
    if not title:
        return None
    parsed = entry.get("published_parsed")
    published = (datetime(*parsed[:6], tzinfo=timezone.utc).isoformat() if parsed else now_iso())
    link = entry.get("link") or ""
    return {
        "doc_id": make_doc_id(SOURCE, entry.get("id") or link or title),
        "source": SOURCE,
        "source_detail": publisher,
        "bank": bank,
        "doc_type": "article",
        "title": title,
        "body": title,
        "published_at": published,
        "url": link,
        "ingested_at": now_iso(),
        "raw": {"id": entry.get("id"), "source_href": source.get("href"),
                "published": entry.get("published"), "query": query,
                "window": list(window)},
    }


def _fetch(query: str) -> list:
    import feedparser

    params = {"q": query, **EDITION}
    resp = request_with_retries(RSS_URL, params, timeout=20, headers=HEADERS)
    time.sleep(REQUEST_DELAY)
    feed = feedparser.parse(resp.content)
    if not feed.version or feed.bozo:
        raise ValueError("Google News returned an invalid RSS feed.")
    return feed.entries


def _fetch_window(bank: str, query: str, start: date, end: date) -> list[dict]:
    """All items for [start, end), splitting the window if the cap was hit."""
    q = f"{query} after:{start.isoformat()} before:{end.isoformat()}"
    try:
        entries = _fetch(q)
    except Exception as e:
        logger.error(f"{bank} {q!r}: ERROR - {e}")
        FAILED_WINDOWS.append(f"{bank} {start.isoformat()} to {end.isoformat()} {query!r}: {e}")
        return []
    if len(entries) >= SPLIT_AT and (end - start).days > 1:
        mid = start + (end - start) / 2
        logger.debug(f"{bank} {q!r}: {len(entries)} items, splitting at {mid}")
        return _fetch_window(bank, query, start, mid) + _fetch_window(bank, query, mid, end)
    if len(entries) >= SPLIT_AT:
        FAILED_WINDOWS.append(f"{bank} {start.isoformat()} to {end.isoformat()} {query!r}: daily feed cap reached; coverage may be incomplete")
    window = (start.isoformat(), end.isoformat())
    return [d for d in (to_document(e, bank, query, window) for e in entries) if d]


def _months(since: date, until: date):
    start = since
    while start < until:
        nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        yield start, min(nxt, until)
        start = nxt


def iter_batches(since: str, until: str | None = None, query_filter: str | None = None):
    """Yield (month_label, docs) one calendar month at a time, all banks and
    queries, so a caller can insert as it goes and an interrupted backfill
    keeps what it already fetched. query_filter, if given, runs only the
    queries containing that substring, e.g. "intitle:" to backfill a newly
    added query without re-fetching the others."""
    s = date.fromisoformat(since)
    u = date.fromisoformat(until) if until else datetime.now(timezone.utc).date() + timedelta(days=1)
    for start, end in _months(s, u):
        docs, seen = [], set()
        for bank, queries in QUERIES.items():
            for query in queries:
                if query_filter and query_filter not in query:
                    continue
                for d in _fetch_window(bank, query, start, end):
                    if d["doc_id"] not in seen:
                        seen.add(d["doc_id"])
                        docs.append(d)
        logger.info(f"{start:%Y-%m}: {len(docs)} unique Google News items")
        yield f"{start:%Y-%m}", docs
    if FAILED_WINDOWS:
        logger.error(f"{len(FAILED_WINDOWS)} Google News window(s) failed and were not fetched; "
                     "re-run them: " + "; ".join(FAILED_WINDOWS))


def pull(since: str, until: str | None = None) -> list[dict]:
    return [d for _, docs in iter_batches(since, until) for d in docs]


if __name__ == "__main__":
    from ingest.news_filter import load_index, filter_and_dedup

    setup_logging()
    parser = argparse.ArgumentParser(description="Backfill Google News RSS headlines")
    parser.add_argument("--since", required=True, help="YYYY-MM-DD")
    parser.add_argument("--until", default=None, help="YYYY-MM-DD, exclusive (default: today)")
    parser.add_argument("--query-filter", default=None,
                        help='only run queries containing this text, e.g. "intitle:"')
    args = parser.parse_args()
    index = load_index()
    for month, docs in iter_batches(args.since, args.until, args.query_filter):
        kept, stats = filter_and_dedup(docs, index)
        _, inserted = upsert_documents(kept)
        logger.info(f"{month}: inserted {inserted}  filter={stats}")
    if FAILED_WINDOWS:
        raise SystemExit(f"{len(FAILED_WINDOWS)} window(s) failed and were not fetched (listed above)")
