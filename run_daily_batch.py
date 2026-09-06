"""
Daily batch ingestion entrypoint — the "recomputed after each batch cycle"
requirement from the project proposal. Run manually or via cron; not a
live/streaming pipeline (that's a deliberate scope decision, see MVP plan).

Pulls NewsAPI + Alpha Vantage (last day or so of news) and Arctic Shift
(incremental Reddit pull since the last run), upserts into data/plp.db.
Earnings PDFs are NOT part of this — that corpus is static, run
`python -m ingest.earnings` once after adding PDFs.

USAGE:
  python run_daily_batch.py                  # incremental: Reddit since 7 days ago
  python run_daily_batch.py --reddit-since 2020-01-01   # full Reddit backfill
"""

import argparse
from datetime import datetime, timedelta, timezone

from ingest import alphavantage, arctic_shift, newsapi, yahoo_analyst
from ingest.db import count_by_source_bank, total_count, upsert_documents


def main(reddit_since: str | None):
    print(f"{'=' * 60}\nDAILY BATCH RUN — {datetime.now(timezone.utc).isoformat()}\n{'=' * 60}\n")

    total_attempted = total_inserted = 0

    print("--- NewsAPI ---")
    docs = newsapi.pull()
    a, i = upsert_documents(docs)
    print(f"NewsAPI: {i}/{a} new\n")
    total_attempted += a; total_inserted += i

    print("--- Alpha Vantage ---")
    docs = alphavantage.pull()
    a, i = upsert_documents(docs)
    print(f"Alpha Vantage: {i}/{a} new\n")
    total_attempted += a; total_inserted += i

    print("--- Arctic Shift (Reddit) ---")
    since = reddit_since or (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    docs = arctic_shift.pull(since=since)
    a, i = upsert_documents(docs)
    print(f"Arctic Shift: {i}/{a} new\n")
    total_attempted += a; total_inserted += i

    print("--- Yahoo analyst consensus ---")
    consensus_rows = yahoo_analyst.pull()
    n_consensus = yahoo_analyst.upsert(consensus_rows)
    print(f"Analyst consensus: {n_consensus} bank snapshots\n")

    print(f"{'=' * 60}\nBATCH SUMMARY\n{'=' * 60}")
    print(f"Total this run: {total_inserted}/{total_attempted} new documents inserted")
    print(f"Total documents in store: {total_count()}\n")
    print("Per source × bank:")
    for source, bank, n in count_by_source_bank():
        print(f"  {source:15s} {bank:6s} {n}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the daily ingestion batch")
    parser.add_argument("--reddit-since", default=None,
                         help="YYYY-MM-DD; default is 7 days ago (incremental). "
                              "Use an early date (e.g. 2020-01-01) for the initial backfill.")
    args = parser.parse_args()
    main(reddit_since=args.reddit_since)
