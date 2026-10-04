"""
Run every news pull into data/plp.db, then print a source × bank × month table.

Sources run in this order, because the first copy of a duplicated story is the
one kept (see ingest/news_filter.py):
  1. yahoo_news    yfinance, SGX + ADR tickers. Recent stream only, ~12 months
  2. google_news   Google News RSS, month-by-month backfill from --since
  3. newsapi       free tier, last ~30 days (needs NEWSAPI_KEY in .env)
  4. alphavantage  kept for completeness; returns nothing for SGX tickers
                   (needs ALPHAVANTAGE_KEY in .env)

Every source goes through news_filter.filter_and_dedup: bank-mention check,
broker/venue false-positive masking, cross-source dedup. Rejected and
flagged articles are listed in data/news_flagged.csv. Re-running is safe:
already-stored articles are skipped, so a daily run only adds new ones.

Does not preprocess into `sentences`, and does not run aspect discovery.

USAGE:
  python run_news_pull.py                              # all sources, Google from 2023-01-01
  python run_news_pull.py --source yahoo               # one source
  python run_news_pull.py --source google --since 2024-01-01 --until 2024-07-01
  python run_news_pull.py --report                     # just print the count table
  python run_news_pull.py --audit                      # re-check stored news against the
                                                       # current filter rules (flags only)
"""

import argparse
from datetime import datetime, timezone

from ingest import alphavantage, google_news, newsapi, yahoo_news
from ingest.db import get_connection, init_db, upsert_documents
from ingest.news_filter import NEWS_SOURCES, audit_stored, filter_and_dedup, load_index

from config.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

DEFAULT_SINCE = "2023-01-01"  # matches the start of the earnings-PDF corpus
SOURCES = ["yahoo", "google", "newsapi", "alphavantage"]


def _ingest(label: str, docs: list[dict], index) -> tuple[int, dict]:
    kept, stats = filter_and_dedup(docs, index)
    _, inserted = upsert_documents(kept)
    logger.info(f"{label}: inserted {inserted}  filter={stats}")
    return inserted, stats


def run(sources: list[str], since: str, until: str | None) -> dict[str, int]:
    index = load_index()  # shared, so dedup also catches duplicates across sources in this run
    totals = {}
    if "yahoo" in sources:
        logger.info("--- Yahoo Finance news ---")
        totals["yahoo_news"], _ = _ingest("yahoo_news", yahoo_news.pull(), index)
    if "google" in sources:
        logger.info(f"--- Google News RSS, {since} to {until or 'today'} ---")
        totals["google_news"] = 0
        for month, docs in google_news.iter_batches(since, until):
            n, _ = _ingest(f"google_news {month}", docs, index)
            totals["google_news"] += n
    if "newsapi" in sources:
        logger.info("--- NewsAPI ---")
        totals["newsapi"], _ = _ingest("newsapi", newsapi.pull(), index)
    if "alphavantage" in sources:
        logger.info("--- Alpha Vantage ---")
        totals["alphavantage"], _ = _ingest("alphavantage", alphavantage.pull(), index)
    return totals


def count_table() -> str:
    """Markdown table: one row per month, one column per source/bank pair."""
    init_db()
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(NEWS_SOURCES))
        rows = conn.execute(
            f"""SELECT substr(published_at, 1, 7), source, bank, COUNT(*) FROM documents
                WHERE source IN ({placeholders}) GROUP BY 1, 2, 3""", NEWS_SOURCES).fetchall()
    finally:
        conn.close()
    if not rows:
        return "(no news documents)"
    banks = ["DBS", "OCBC", "UOB", "MULTI"]
    cols = [(s, b) for s in NEWS_SOURCES for b in banks
            if any(r[1] == s and r[2] == b for r in rows)]
    cells = {(m, s, b): n for m, s, b, n in rows}
    months = sorted({r[0] for r in rows})
    header = ["month"] + [f"{s} {b}" for s, b in cols] + ["total"]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for m in months:
        vals = [cells.get((m, s, b), 0) for s, b in cols]
        lines.append("| " + " | ".join([m] + [str(v) for v in vals] + [str(sum(vals))]) + " |")
    col_totals = [sum(cells.get((m, s, b), 0) for m in months) for s, b in cols]
    lines.append("| **total** | " + " | ".join(str(v) for v in col_totals)
                 + f" | {sum(col_totals)} |")
    return "\n".join(lines)


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Pull all news sources into data/plp.db")
    parser.add_argument("--source", choices=SOURCES + ["all"], default="all")
    parser.add_argument("--since", default=DEFAULT_SINCE,
                        help=f"Google News backfill start, YYYY-MM-DD (default {DEFAULT_SINCE})")
    parser.add_argument("--until", default=None, help="Google News end, exclusive (default today)")
    parser.add_argument("--report", action="store_true", help="only print the count table")
    parser.add_argument("--audit", action="store_true",
                        help="flag stored news the current rules would reject; changes no rows")
    args = parser.parse_args()

    if args.audit:
        logger.info(f"Audit of stored news: {audit_stored()} (see data/news_flagged.csv)")
    elif not args.report:
        logger.info("NEWS PULL - %s", datetime.now(timezone.utc).isoformat())
        sources = SOURCES if args.source == "all" else [args.source]
        totals = run(sources, args.since, args.until)
        logger.info(f"Newly inserted this run: {totals}")
    print(count_table())
    if google_news.FAILED_WINDOWS:
        raise SystemExit(f"{len(google_news.FAILED_WINDOWS)} Google News window(s) failed and were "
                         "not fetched (listed above); re-run that range")
