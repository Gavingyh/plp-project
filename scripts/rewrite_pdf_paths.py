"""
Rewrite the links of locally read PDFs (earnings reports and broker research)
from absolute local paths to repository-relative ones:
"file:///<any folder>/data/earnings_pdfs/DBS/x.pdf" becomes
"data/earnings_pdfs/DBS/x.pdf", and "file://C:\\<any folder>\\data\\sgx_research\\x.pdf"
becomes "data/sgx_research/x.pdf". The absolute form carried a home folder,
and so a username, into the database, every snapshot and committed files.
ingest/earnings_extract.py and ingest/sgx_research_extract.py now write the
relative form; this script fixes what is already stored.

Three targets, each counted by the dry run (the default) and changed only
with --apply:

  --db          documents.url and sentences.url of one database. Refuses
                data/plp.db (or the database PLP_DB_PATH names) unless
                --real-db is given too, and backs it up first, as
                scripts/rescore.py does. One transaction; the counts after
                must match the counts before, or nothing is written.
  --snapshots   every data/snapshots/*.db.gz: each is unpacked to a temporary
                file, rewritten, packed again, and the original kept beside
                it as <name>.pre-pdf-paths.
  --files       committed text files (git ls-files) under data/, except
                data/logs/plp.log, which is never staged. .project-context/ is
                left alone.

The re-score week runs it once, on the real database, with a team decision.

USAGE:
  .venv-plp/bin/python3 scripts/rewrite_pdf_paths.py --db data/plp.db --snapshots --files      # dry run: counts only
  .venv-plp/bin/python3 scripts/rewrite_pdf_paths.py --db /tmp/copy.db --apply                 # a copy
"""

import argparse
import gzip
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import ingest.db  # noqa: E402

# Any absolute file:// prefix ending in the data folder of one of the two
# sources, on any machine: forward slashes, or a Windows path's backslashes
# (doubled where a JSON file escapes them).
PDF_LINK = re.compile(r"file://[^\n\"',]*?[/\\]+data[/\\]+(earnings_pdfs|sgx_research)[/\\]+")
RELATIVE = r"data/\1/"
SQL_MATCH = "file://%"
TABLES = ("documents", "sentences")
SNAPSHOT_DIR = os.path.join(ROOT, "data", "snapshots")
NEVER_STAGED = {"data/logs/plp.log"}


def relative(url: str) -> str:
    return PDF_LINK.sub(RELATIVE, url)


def _matching(conn, table: str) -> list[tuple[str, str]]:
    """(key, url) of the rows whose link the rewrite would change."""
    key = "doc_id" if table == "documents" else "sentence_id"
    rows = conn.execute(f"SELECT {key}, url FROM {table} WHERE url LIKE ?", (SQL_MATCH,)).fetchall()
    return [(k, u) for k, u in rows if relative(u) != u]


def count_db(conn) -> dict[str, int]:
    return {t: len(_matching(conn, t)) for t in TABLES}


def rewrite_db(conn) -> dict[str, int]:
    """Rewrite every matching url in one transaction; returns rows changed per table."""
    before = count_db(conn)
    changed = {}
    with conn:
        for t in TABLES:
            key = "doc_id" if t == "documents" else "sentence_id"
            rows = _matching(conn, t)
            conn.executemany(f"UPDATE {t} SET url = ? WHERE {key} = ?", [(relative(u), k) for k, u in rows])
            changed[t] = len(rows)
        left = count_db(conn)
        if changed != before or any(left.values()):
            raise RuntimeError(f"counts don't match: before {before}, changed {changed}, left {left}")
    return changed


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "data/"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f not in NEVER_STAGED]


def count_files() -> dict[str, int]:
    found = {}
    for f in tracked_files():
        try:
            text = open(os.path.join(ROOT, f), encoding="utf-8", newline="").read()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        n = len(PDF_LINK.findall(text))
        if n:
            found[f] = n
    return found


def rewrite_files(files: dict[str, int]) -> None:
    for f in files:
        path = os.path.join(ROOT, f)
        text = open(path, encoding="utf-8", newline="").read()   # newline="": line endings stay as they are
        with open(path, "w", encoding="utf-8", newline="") as out:
            out.write(PDF_LINK.sub(RELATIVE, text))


def snapshots() -> list[str]:
    return sorted(os.path.join(SNAPSHOT_DIR, f) for f in os.listdir(SNAPSHOT_DIR)
                  if f.endswith(".db.gz")) if os.path.isdir(SNAPSHOT_DIR) else []


def snapshot(path: str, apply: bool) -> dict[str, int]:
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "snapshot.db")
        with gzip.open(path, "rb") as src, open(db, "wb") as dst:
            shutil.copyfileobj(src, dst)
        if not apply:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            counts = count_db(conn)
            conn.close()
            return counts
        conn = sqlite3.connect(db)
        counts = rewrite_db(conn)
        conn.execute("VACUUM")
        conn.close()
        kept = path.replace(".db.gz", ".pre-pdf-paths.db.gz")
        os.replace(path, kept)
        with open(db, "rb") as src, gzip.open(path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return counts


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--db", help="a database to count or rewrite")
    p.add_argument("--snapshots", action="store_true", help="every data/snapshots/*.db.gz")
    p.add_argument("--files", action="store_true", help="committed text files under data/")
    p.add_argument("--apply", action="store_true", help="write; without it, a dry run that only counts")
    p.add_argument("--real-db", action="store_true", help="allow --db to be the database the project serves")
    args = p.parse_args(argv)
    if not (args.db or args.snapshots or args.files):
        p.error("name at least one of --db, --snapshots, --files")
    mode = "apply" if args.apply else "dry run"

    if args.db:
        db = os.path.realpath(args.db)
        served = {os.path.realpath(ingest.db.DB_PATH), os.path.realpath(ingest.db.DEFAULT_DB_PATH)}
        if args.apply and db in served and not args.real_db:
            print(f"refusing to change {args.db}: work on a copy, or add --real-db once the team has decided",
                  file=sys.stderr)
            return 2
        if not os.path.exists(db):
            print(f"no database at {db}", file=sys.stderr)
            return 2
        if not args.apply:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            print(f"[{mode}] {args.db}: {count_db(conn)}")
            conn.close()
        else:
            if db in served:
                os.makedirs(SNAPSHOT_DIR, exist_ok=True)
                backup = os.path.join(SNAPSHOT_DIR, f"plp-before-pdf-paths-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.db")
                src, dst = sqlite3.connect(f"file:{db}?mode=ro", uri=True), sqlite3.connect(backup)
                src.backup(dst)
                dst.close()
                src.close()
                print(f"backup: {backup}")
            conn = sqlite3.connect(db)
            print(f"[{mode}] {args.db}: rewrote {rewrite_db(conn)}")
            conn.close()

    if args.snapshots:
        for path in snapshots():
            print(f"[{mode}] {os.path.relpath(path, ROOT)}: {snapshot(path, args.apply)}")

    if args.files:
        files = count_files()
        for f, n in files.items():
            print(f"[{mode}] {f}: {n} links")
        print(f"[{mode}] committed files: {len(files)}, links: {sum(files.values())}")
        if args.apply:
            rewrite_files(files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
