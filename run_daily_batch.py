"""
Daily batch ingestion entrypoint - the "recomputed after each batch cycle"
requirement from the project proposal. Run manually or via cron; not a
live/streaming pipeline (a scope decision; see docs/DESIGN.md).

Pulls news (Yahoo, Google News for the last 45 days, NewsAPI, Alpha Vantage;
see run_news_pull.py) and Arctic Shift
(incremental Reddit pull since the last run), upserts into data/plp.db.
Earnings PDFs are NOT part of this - that corpus is static, run
`python -m ingest.earnings_extract` once after adding PDFs.

USAGE:
  python run_daily_batch.py                  # incremental: Reddit since 7 days ago
  python run_daily_batch.py --reddit-since 2020-01-01   # full Reddit backfill
"""

import argparse
from datetime import datetime, timedelta, timezone

from ingest import arctic_shift, yahoo_analyst
from ingest.db import count_by_source_bank, total_count, upsert_documents
from ingest.news_filter import recent_window
from run_news_pull import run as run_news

from config.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

GOOGLE_DAYS = 45  # overlap generously; already-stored articles are skipped


def main(reddit_since: str | None):
    logger.info("DAILY BATCH RUN — %s", datetime.now(timezone.utc).isoformat())

    total_inserted = 0

    # News: Yahoo, Google News (last GOOGLE_DAYS days), NewsAPI, Alpha Vantage,
    # all through ingest/news_filter.py's relevance + cross-source dedup rules.
    # Yahoo has no history, so running this daily is how its coverage grows.
    since, until = recent_window(GOOGLE_DAYS)
    news_totals = run_news(["yahoo", "google", "newsapi", "alphavantage"], since, until)
    for source, n in news_totals.items():
        logger.info(f"{source}: {n} new")
    total_inserted += sum(news_totals.values())

    logger.info("--- Arctic Shift (Reddit) ---")
    since = reddit_since or (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    docs = arctic_shift.pull(since=since)
    a, i = upsert_documents(docs)
    logger.info(f"Arctic Shift: {i}/{a} new")
    total_inserted += i

    logger.info("--- Yahoo analyst consensus ---")
    consensus_rows = yahoo_analyst.pull()
    n_consensus = yahoo_analyst.upsert(consensus_rows)
    logger.info(f"Analyst consensus: {n_consensus} bank snapshots")

    logger.info("BATCH SUMMARY")
    logger.info(f"Total this run: {total_inserted} new documents inserted")
    logger.info(f"Total documents in store: {total_count()}")
    logger.info("Per source × bank:")
    for source, bank, n in count_by_source_bank():
        logger.info(f"  {source:15s} {bank:6s} {n}")


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Run the daily ingestion batch")
    parser.add_argument("--reddit-since", default=None,
                         help="YYYY-MM-DD; default is 7 days ago (incremental). "
                              "Use an early date (e.g. 2020-01-01) for the initial backfill.")
    args = parser.parse_args()
    main(reddit_since=args.reddit_since)
