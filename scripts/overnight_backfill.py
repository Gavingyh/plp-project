"""
Safe, resumable overnight Reddit backfill.

WHY THIS EXISTS: `python run_daily_batch.py --reddit-since 2020-01-01` looks
like it does the same thing, but it doesn't commit anything to the database
until the ENTIRE multi-year harvest finishes — ingest/arctic_shift.py's
pull() accumulates every document in memory and calls upsert_documents()
exactly once, at the very end (run_daily_batch.py:43). A multi-year backfill
can run for hours; if the machine sleeps, the terminal closes, or anything
else interrupts it, every bit of that work is lost with nothing saved. Not
safe to leave running unattended overnight. (Caught while setting this up —
the first backfill attempt sat at 34 minutes elapsed with zero new documents
in the database, because it hadn't reached the one write at the end yet.)

This script instead calls `python -m ingest.arctic_shift --since X --until Y`
as a SEPARATE process per month-sized chunk. Each chunk's own __main__ block
commits to the database immediately after that chunk's harvest — confirmed
in ingest/arctic_shift.py:171. So:
  - if interrupted at any point, everything up to the last completed chunk
    is already safely in data/plp.db
  - re-running this script is safe and fast: completed chunks are skipped
    via a local marker file, and even an unmarked repeat is a no-op at the
    database level (doc_id is idempotent, see ingest/db.py)
  - a single bad/slow chunk (Arctic Shift has "no uptime guarantee") doesn't
    take down the whole run — logged and skipped, moves to the next chunk

USAGE:
  # Run directly in your own terminal, NOT inside a Claude Code session that
  # might close — e.g. with caffeinate (macOS) to also stop the machine
  # sleeping mid-run:
  caffeinate -i python3 scripts/overnight_backfill.py

  # Resume after an interruption — already-completed chunks are skipped:
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
    """Thin wrapper kept so call sites read the same; routes through the
    shared logger (console + this script's own log file, configured in run())
    instead of the hand-rolled print+append it used to do."""
    logger.info(msg)


def _check_environment():
    """Fail loudly and immediately if this isn't running under the project's
    venv — rather than silently burning through every chunk with the same
    error. Hit live: a real overnight run got invoked under miniforge's
    Python 3.9 instead of .venv-plp's 3.14 (almost certainly because a
    conda auto-activation in the shell profile ran after `source
    .venv-plp/bin/activate` and shadowed it) and failed all 79 real chunks
    identically — the codebase's `str | None` syntax (PEP 604) doesn't
    parse on 3.9. Zero data was lost that couldn't be recovered by
    re-running, but the whole night's run time was wasted silently."""
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
