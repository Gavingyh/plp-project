"""
Yahoo Finance news ingestion via yfinance.

Yahoo's news endpoint (/xhr/ncp, which yfinance's Ticker.get_news wraps) has
no date parameter and no paging. It returns the most recent stream for a
ticker, up to `count` items (yfinance defaults to 10). In a live probe,
count=100 or more returned at most 33-67 items per bank on the
"news"/"all" tabs, reaching back about 12 months. So one pull cannot backfill
history. This adapter is meant to run daily (run_daily_batch.py does) and
accumulate: doc_id is keyed on Yahoo's article uuid, so a re-run inserts
only articles not seen before.

Both listings are queried: SGX (D05.SI / O39.SI / U11.SI) and the US OTC ADRs
(DBSDY / OVCHY / UOVEY). In that probe the ADR streams were near
copies of the SGX ones (DBS: 1 extra article out of 35), but it costs 9
requests, so both are kept for coverage.

USAGE:
  python -m ingest.yahoo_news          # pull, filter, dedup, insert
"""

import time
from datetime import datetime, timezone

from ingest.db import make_doc_id, now_iso, upsert_documents

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

SOURCE = "yahoo_news"

TICKERS = {
    "DBS": ["D05.SI", "DBSDY"],
    "OCBC": ["O39.SI", "OVCHY"],
    "UOB": ["U11.SI", "UOVEY"],
}
TABS = ["news", "all", "press releases"]
COUNT = 200          # above the observed cap, so we always get everything Yahoo will give
REQUEST_DELAY = 1.0  # seconds between calls; Yahoo rate-limits aggressive clients


def _to_iso(ts: str | None) -> str:
    if not ts:
        return now_iso()
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return now_iso()


def to_document(item: dict, bank: str, ticker: str, tab: str) -> dict | None:
    """Map one yfinance news item to a documents row. The bank is provisional:
    news_filter re-resolves it from the text."""
    c = item.get("content") or {}
    title = (c.get("title") or "").strip()
    summary = (c.get("summary") or c.get("description") or "").strip()
    if not title:
        return None
    body = title if not summary or summary == title else f"{title}. {summary}"
    url = ((c.get("canonicalUrl") or {}).get("url")
           or (c.get("clickThroughUrl") or {}).get("url") or "")
    provider = (c.get("provider") or {}).get("displayName")
    return {
        "doc_id": make_doc_id(SOURCE, item.get("id") or url or title),
        "source": SOURCE,
        "source_detail": provider,
        "bank": bank,
        "doc_type": "article",
        "title": title,
        "body": body,
        "published_at": _to_iso(c.get("pubDate") or c.get("displayTime")),
        "url": url,
        "ingested_at": now_iso(),
        # Lean on purpose: plp.db is committed to git and close to GitHub's
        # 100MB file limit, so thumbnails and tracking metadata are dropped.
        "raw": {"id": item.get("id"), "contentType": c.get("contentType"),
                "provider": provider, "url": url, "pubDate": c.get("pubDate"),
                "ticker": ticker, "tab": tab},
    }


def pull() -> list[dict]:
    import yfinance as yf  # imported here so the rest of the pipeline doesn't need it installed

    docs, seen = [], set()
    for bank, tickers in TICKERS.items():
        n_bank = 0
        for ticker in tickers:
            for tab in TABS:
                try:
                    items = yf.Ticker(ticker).get_news(count=COUNT, tab=tab)
                except Exception as e:
                    logger.error(f"{bank} {ticker} [{tab}]: ERROR - {e}")
                    items = []
                for item in items:
                    doc = to_document(item, bank, ticker, tab)
                    if doc and doc["doc_id"] not in seen:
                        seen.add(doc["doc_id"])
                        docs.append(doc)
                        n_bank += 1
                time.sleep(REQUEST_DELAY)
        logger.info(f"{bank}: {n_bank} unique Yahoo items across {', '.join(tickers)}")
    return docs


if __name__ == "__main__":
    from ingest.news_filter import filter_and_dedup

    setup_logging()
    kept, stats = filter_and_dedup(pull())
    attempted, inserted = upsert_documents(kept)
    logger.info(f"filter: {stats}")
    logger.info(f"Yahoo news: {inserted}/{attempted} newly inserted")
