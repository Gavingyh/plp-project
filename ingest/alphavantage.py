"""
Alpha Vantage NEWS_SENTIMENT ingestion (free tier: 25 req/day).

Per the MVP plan (finding (b)): Alpha Vantage's news coverage is overwhelmingly
US-listed tickers, and SGX listings (D05.SI / O39.SI / U11.SI) are generally not
indexed. This adapter exists so the team can *prove* that empirically (Phase 0)
rather than assume it — if it returns zero rows across all three tickers, that
confirms the finding and Alpha Vantage is dropped from the pipeline.

Per the original constraint carried over from news_pull.py: Alpha Vantage's own
`overall_sentiment_score` must NOT be used as a training label — only the raw
title/summary text is kept.

USAGE:
  python -m ingest.alphavantage
"""

import os
import time
from datetime import datetime

from dotenv import load_dotenv

from ingest.base import BANKS, request_with_retries, resolve_bank
from ingest.db import make_doc_id, now_iso, upsert_documents

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

AV_KEY = os.environ.get("ALPHAVANTAGE_KEY")


def pull() -> list[dict]:
    if not AV_KEY:
        logger.warning("Skipped — set ALPHAVANTAGE_KEY in .env to run this.")
        return []

    docs = []
    for bank, queries in BANKS.items():
        # AV's ticker validator rejects periods ("Invalid ticker format" for
        # "D05.SI" — confirmed live), so strip the exchange suffix. This is a
        # format fix only: valid-format tickers ("D05", "D05SI", "D05-SI")
        # were also tested live and all returned 0 results — AV genuinely
        # doesn't index SGX-listed names, format aside (see MVP plan finding b).
        ticker = queries[2].split(".")[0]  # "D05.SI" -> "D05"
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ticker,
            "apikey": AV_KEY,
            "limit": 50,
        }
        try:
            resp = request_with_retries(url, params)
            data = resp.json()
            feed = data.get("feed", [])
            logger.info(f"{bank} ({ticker}): {len(feed)} articles "
                  f"(raw response keys: {list(data.keys())})")
            if "Note" in data or "Information" in data:
                logger.info(f"AV message: {data.get('Note') or data.get('Information')}")
            for a in feed:
                title = a.get("title") or ""
                summary = a.get("summary") or ""
                body = f"{title}. {summary}".strip(". ")
                if not body:
                    continue
                resolved_bank = resolve_bank(body, fallback=bank)
                # Deliberately not copying overall_sentiment_score — see module docstring.
                docs.append({
                    "doc_id": make_doc_id("alphavantage", a.get("url") or title),
                    "source": "alphavantage",
                    "source_detail": a.get("source"),
                    "bank": resolved_bank,
                    "doc_type": "article",
                    "title": title,
                    "body": body,
                    "published_at": _parse_av_time(a.get("time_published")),
                    "url": a.get("url") or "",
                    "ingested_at": now_iso(),
                    "raw": a,
                })
        except Exception as e:
            logger.error(f"{bank}: ERROR — {e}")
        time.sleep(15)  # free tier is 25 req/day — space calls out, avoid burning quota fast

    return docs


def _parse_av_time(t: str | None) -> str:
    """AV format: YYYYMMDDTHHMMSS -> ISO 8601."""
    if not t:
        return now_iso()
    try:
        return datetime.strptime(t, "%Y%m%dT%H%M%S").isoformat()
    except ValueError:
        return now_iso()


if __name__ == "__main__":
    setup_logging()
    logger.info(f"Run started: {datetime.now().isoformat()}")
    docs = pull()
    attempted, inserted = upsert_documents(docs)
    logger.info(f"Documents attempted: {attempted}  |  newly inserted: {inserted}  "
          f"|  already-seen (skipped): {attempted - inserted}")
