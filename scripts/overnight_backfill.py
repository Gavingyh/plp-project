"""
Resumable Reddit backfill, one month at a time.

`python run_daily_batch.py --reddit-since 2020-01-01` covers the same range
but writes nothing until the whole harvest finishes: ingest/arctic_shift.py's
pull() keeps every document in memory and calls upsert_documents() once, at
the end. A multi-year backfill runs for hours, and an interruption loses all
of it.

This script runs `python -m ingest.arctic_shift --since X --until Y` as a
separate process per month. Each process commits its month before the next
starts, so:
  - after an interruption, every completed month is already in data/plp.db
  - re-running skips completed months (a marker file), and repeating one is
    harmless anyway, because doc_id makes inserts idempotent (ingest/db.py)
  - a failed or slow month (Arctic Shift has no uptime guarantee) is logged
    and skipped

USAGE:
  # From your own terminal; caffeinate keeps a Mac awake for the run:
  caffeinate -i python3 scripts/overnight_backfill.py

  # Resume after an interruption (completed months are skipped):
  python3 scripts/overnight_backfill.py

  # Custom range:
  python3 scripts/overnight_backfill.py --since 2022-01-01 --until 2026-09-06
"""

import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from config.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
MARKER_FILE = BASE_DIR / "data" / ".backfill_progress.txt"
LOG_FILE = BASE_DIR / "data" / "backfill_overnight.log"


def month_chunks(since: str, until: str):
    start = datetime.strptime(since, "%Y-%m-%d")
    end = datetime.strptime(until, "%Y-%m-%d")
    cur = start
    while cur < end:
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)  # first of next month
        chunk_end = min(nxt, end)
        yield cur.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        cur = nxt


def load_completed() -> set[str]:
    if not MARKER_FILE.exists():
        return set()
    return set(MARKER_FILE.read_text().splitlines())


def mark_completed(chunk_key: str):
    MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MARKER_FILE, "a") as f:
        f.write(chunk_key + "\n")


def log(msg: str):
    """Log to the console and this script's own log file (set up in run())."""
    logger.info(msg)


def _check_environment():
    """Stop at once unless this is the project's Python (3.10 or later): the
    code uses `str | None` (PEP 604), so an older interpreter, for example a
    conda base environment that shadows the venv, would fail every month the
    same way."""
    if sys.version_info < (3, 10):
        print(f"FATAL: running under Python {sys.version.split()[0]} ({sys.executable}), "
              "but this codebase requires 3.10+ (uses `X | None` type syntax throughout). "
              "This almost always means .venv-plp wasn't actually active when this script "
              "was launched — a conda/miniforge base env auto-activating in your shell "
              "profile is a common cause, since it can run *after* `source "
              ".venv-plp/bin/activate` and silently take over `python3` on PATH.\n\n"
              "Fix: invoke the venv's interpreter by absolute path instead of relying on "
              "shell activation:\n"
              "  caffeinate -i /Users/gavin/Projects/plp-project/.venv-plp/bin/python3 "
              "scripts/overnight_backfill.py", file=sys.stderr)
        sys.exit(1)
    try:
        import requests  # noqa: F401
    except ImportError:
        print(f"FATAL: 'requests' isn't importable under {sys.executable} — this isn't the "
              "project's venv. See the Python-version message above for the fix.", file=sys.stderr)
        sys.exit(1)


def run():
    _check_environment()
    setup_logging(log_file=str(LOG_FILE))

    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2020-01-01")
    parser.add_argument("--until", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    completed = load_completed()
    chunks = list(month_chunks(args.since, args.until))
    log(f"Backfill plan: {len(chunks)} monthly chunks from {args.since} to {args.until} "
        f"({len(completed)} already marked done from a prior run)")

    for since, until in chunks:
        chunk_key = f"{since}:{until}"
        if chunk_key in completed:
            log(f"SKIP  {since} -> {until} (already completed)")
            continue

        log(f"START {since} -> {until}")
        result = subprocess.run(
            [sys.executable, "-m", "ingest.arctic_shift", "--since", since, "--until", until],
            cwd=str(BASE_DIR), capture_output=True, text=True,
        )
        if result.returncode == 0:
            # pull final summary line out of the child's stdout for the log
            summary = next((l for l in result.stdout.splitlines() if "attempted" in l), "")
            log(f"DONE  {since} -> {until}  {summary}")
            mark_completed(chunk_key)
        else:
            log(f"ERROR {since} -> {until}  exit={result.returncode}  "
                f"stderr_tail={result.stderr[-500:]!r}")
            log("       Continuing to next chunk — Arctic Shift has no uptime guarantee, "
                "a transient failure here doesn't need to stop the whole run. "
                "Re-run this script later to retry unmarked chunks.")

    log(f"Backfill run finished. Progress marker: {MARKER_FILE}")
    log("Next step once you're happy with the data volume: "
        "python -m preprocess.pipeline && python -m aspects.assign && "
        "python -m sentiment.score && python -m aggregate.index")


if __name__ == "__main__":
    run()
