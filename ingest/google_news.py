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

Queries per bank are a quoted name from the team brief plus a looser
unquoted one. In a live probe for March 2024 the loose query returned 4-7x
as many items. Non-bank results from the loose query are removed by
news_filter.

USAGE:
  python -m ingest.google_news --since 2023-01-01          # backfill to today
  python -m ingest.google_news --since 2024-03-01 --until 2024-04-01
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

QUERIES = {
    "DBS": ['"DBS Group" Singapore', "DBS bank Singapore"],
    "OCBC": ['"OCBC Bank" Singapore', "OCBC Singapore"],
    "UOB": ['"UOB bank" Singapore', "UOB Singapore"],
}

SPLIT_AT = 90         # Google caps a response at 100 items; a window this full may be truncated, so split it
REQUEST_DELAY = 2.0   # seconds between requests. Google has no published limit; stay well clear


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
    return feedparser.parse(resp.content).entries


def _fetch_window(bank: str, query: str, start: date, end: date) -> list[dict]:
    """All items for [start, end), splitting the window if the cap was hit."""
    q = f"{query} after:{start.isoformat()} before:{end.isoformat()}"
    try:
        entries = _fetch(q)
    except Exception as e:
        logger.error(f"{bank} {q!r}: ERROR — {e}")
        return []
    if len(entries) >= SPLIT_AT and (end - start).days > 1:
        mid = start + (end - start) / 2
        logger.debug(f"{bank} {q!r}: {len(entries)} items, splitting at {mid}")
        return _fetch_window(bank, query, start, mid) + _fetch_window(bank, query, mid, end)
    window = (start.isoformat(), end.isoformat())
    return [d for d in (to_document(e, bank, query, window) for e in entries) if d]


def _months(since: date, until: date):
    start = since
    while start < until:
        nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        yield start, min(nxt, until)
        start = nxt


def iter_batches(since: str, until: str | None = None):
    """Yield (month_label, docs) one calendar month at a time, all banks and
    queries, so a caller can insert as it goes and an interrupted backfill
    keeps what it already fetched."""
    s = date.fromisoformat(since)
    u = date.fromisoformat(until) if until else datetime.now(timezone.utc).date() + timedelta(days=1)
    for start, end in _months(s, u):
        docs, seen = [], set()
        for bank, queries in QUERIES.items():
            for query in queries:
                for d in _fetch_window(bank, query, start, end):
                    if d["doc_id"] not in seen:
                        seen.add(d["doc_id"])
                        docs.append(d)
        logger.info(f"{start:%Y-%m}: {len(docs)} unique Google News items")
        yield f"{start:%Y-%m}", docs


def pull(since: str, until: str | None = None) -> list[dict]:
    return [d for _, docs in iter_batches(since, until) for d in docs]


if __name__ == "__main__":
    from ingest.news_filter import load_index, filter_and_dedup

    setup_logging()
    parser = argparse.ArgumentParser(description="Backfill Google News RSS headlines")
    parser.add_argument("--since", required=True, help="YYYY-MM-DD")
    parser.add_argument("--until", default=None, help="YYYY-MM-DD, exclusive (default: today)")
    args = parser.parse_args()
    index = load_index()
    for month, docs in iter_batches(args.since, args.until):
        kept, stats = filter_and_dedup(docs, index)
        _, inserted = upsert_documents(kept)
        logger.info(f"{month}: inserted {inserted}  filter={stats}")
