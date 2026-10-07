"""
Move one source's rows from one machine's database to another's.

Sentence ids are hashes of the text, so a source rebuilt on another machine
can come out with different ids when its PDF or OCR libraries differ by a
version: on 7 Oct 2026, the broker research PDFs rebuilt on the Mac gave 646
sentences against the Windows PC's 641, and 52 of the 380 labelled sentences
no longer matched (a stray bullet, a sidebar line). The labels point at the
ids of the machine that made them, so its rows are copied, not rebuilt.

  export: the source's documents, sentences, aspect assignments and sentiment
          scores, read-only, into a small SQLite file.
  import: those rows into another database, skipping any already there. Run it
          on a copy (PLP_DB_PATH or --db), not data/plp.db, unless the team
          has decided to change the real database.

USAGE (from the repository root):
  python scripts/source_rows.py export --source sgx_research --out sgx_rows.db            # on the PC
  python scripts/source_rows.py import --rows sgx_rows.db --db data/run/sgx/plp_sgx.db    # on the Mac
"""

import argparse
import os
import sqlite3
import sys

TABLES = {   # table: the WHERE clause that picks the source's rows
    "documents": "source = :source",
    "sentences": "source = :source",
    "sentence_aspects": "sentence_id IN (SELECT sentence_id FROM sentences WHERE source = :source)",
    "aspect_sentiment": "sentence_id IN (SELECT sentence_id FROM sentences WHERE source = :source)",
}


def export(db: str, source: str, out: str) -> dict:
    if os.path.exists(out):
        sys.exit(f"{out} exists; remove it or choose another --out")
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dst = sqlite3.connect(out)
    counts = {}
    try:
        for table, where in TABLES.items():
            ddl = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
            dst.execute(ddl)
            rows = src.execute(f"SELECT * FROM {table} WHERE {where}", {"source": source}).fetchall()
            if rows:
                marks = ",".join("?" * len(rows[0]))
                dst.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
            counts[table] = len(rows)
        dst.commit()
    finally:
        src.close()
        dst.close()
    return counts


def import_rows(rows_path: str, db: str) -> dict:
    src = sqlite3.connect(f"file:{rows_path}?mode=ro", uri=True)
    dst = sqlite3.connect(db)
    counts = {}
    try:
        for table in TABLES:
            cols = [r[1] for r in dst.execute(f"PRAGMA table_info({table})")]
            have = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
            if cols != have:
                sys.exit(f"{table}: columns differ between the two databases ({have} against {cols})")
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            before = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if rows:
                marks = ",".join("?" * len(cols))
                dst.executemany(f"INSERT OR IGNORE INTO {table} VALUES ({marks})", rows)
            counts[table] = {"in_file": len(rows), "added": dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] - before}
        dst.commit()
    finally:
        src.close()
        dst.close()
    return counts


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--db", default=os.environ.get("PLP_DB_PATH") or "data/plp.db")
    e.add_argument("--source", required=True)
    e.add_argument("--out", required=True)
    i = sub.add_parser("import")
    i.add_argument("--rows", required=True)
    i.add_argument("--db", required=True, help="the database to add to: a copy, not data/plp.db")
    a = p.parse_args()
    if a.cmd == "export":
        print(export(a.db, a.source, a.out))
    else:
        if os.path.abspath(a.db) == os.path.abspath("data/plp.db"):
            print("note: importing into the real database (a team decision)")
        print(import_rows(a.rows, a.db))
