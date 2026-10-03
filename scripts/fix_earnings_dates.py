"""
Re-date earnings documents stored with their ingestion time instead of their
announcement date.

Until 3 Oct 2026, ingest/earnings_extract.py could not read a period from
names like "cfo-slides-q1-2024.pdf" or "cfo-presentation-2023-results.pdf",
so those documents fell back to the time they were extracted (10 Sep 2026)
and their 2023-2024 sentences were counted in the 7d and 30d windows. The
parser is fixed; re-running the extraction does not repair stored rows,
because existing documents are skipped. This script does.

It prints what it would change. With --apply it updates documents and
sentences (a database write: run it only with the team's approval), after
which the index must be recomputed:

USAGE:
  .venv-plp/bin/python3 scripts/fix_earnings_dates.py            # dry run
  .venv-plp/bin/python3 scripts/fix_earnings_dates.py --apply
  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.index
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest.earnings_extract import _quarter_to_announcement_date  # noqa: E402


def misdated(conn) -> list[tuple[str, str, str, str, int]]:
    """(doc_id, title, stored date, parsed date, sentences) for earnings
    documents whose name now gives a different date from the stored one."""
    out = []
    for doc_id, title, published in conn.execute(
            "SELECT doc_id, title, published_at FROM documents WHERE source = 'earnings'"):
        parsed = _quarter_to_announcement_date(title or "")
        if parsed and parsed != published:
            n = conn.execute("SELECT COUNT(*) FROM sentences WHERE doc_id = ?", (doc_id,)).fetchone()[0]
            out.append((doc_id, title, published, parsed, n))
    return out


def apply(conn, rows) -> None:
    with conn:
        for doc_id, _title, _old, new, _n in rows:
            conn.execute("UPDATE documents SET published_at = ? WHERE doc_id = ?", (new, doc_id))
            conn.execute("UPDATE sentences SET published_at = ? WHERE doc_id = ?", (new, doc_id))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--apply", action="store_true", help="write the corrected dates (needs team approval)")
    p.add_argument("--db", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                "data", "plp.db"))
    args = p.parse_args()
    # Checked before connecting: --apply opens read-write, which would create
    # an empty database at a mistyped path before failing on it.
    if not os.path.isfile(args.db):
        p.error(f"no database at {args.db}")
    uri = f"file:{args.db}" + ("" if args.apply else "?mode=ro")
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = misdated(conn)
        for _doc_id, title, old, new, n in rows:
            print(f"{title}: {old} -> {new} ({n} sentences)")
        print(f"{len(rows)} documents, {sum(r[4] for r in rows)} sentences")
        if args.apply and rows:
            apply(conn, rows)
            print("written. Now recompute the index: HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.index")
        elif rows:
            print("dry run: nothing written (add --apply)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
