"""scripts/rewrite_pdf_paths.py: earnings-PDF links from absolute paths to
repository-relative ones (decided 4 Oct 2026). Dry run by default."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("rewrite_pdf_paths", ROOT / "scripts" / "rewrite_pdf_paths.py")
rw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rw)

OLD = "file:///Users/someone/Projects/plp-project/data/earnings_pdfs/DBS/2Q26_results.pdf"
NEW = "data/earnings_pdfs/DBS/2Q26_results.pdf"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "copy.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE documents (doc_id TEXT PRIMARY KEY, url TEXT)")
    conn.execute("CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, url TEXT)")
    conn.executemany("INSERT INTO documents VALUES (?, ?)", [("d1", OLD), ("d2", "https://www.cna.sg/x")])
    conn.executemany("INSERT INTO sentences VALUES (?, ?)", [("s1", OLD), ("s2", OLD), ("s3", "https://reddit.com/r/x")])
    conn.commit()
    conn.close()
    return str(path)


def _urls(path):
    conn = sqlite3.connect(path)
    out = conn.execute("SELECT url FROM documents UNION ALL SELECT url FROM sentences").fetchall()
    conn.close()
    return [u for (u,) in out]


def test_any_home_folder_becomes_a_repository_path():
    assert rw.relative(OLD) == NEW
    assert rw.relative("file:///home/other/plp/data/earnings_pdfs/UOB/a b.pdf") == "data/earnings_pdfs/UOB/a b.pdf"
    assert rw.relative("https://www.dbs.com/data/earnings_pdfs/x") == "https://www.dbs.com/data/earnings_pdfs/x"
    line = f'"{OLD}",earnings,DBS'
    assert rw.PDF_LINK.sub(r"\1", line) == f'"{NEW}",earnings,DBS'


def test_the_dry_run_counts_and_writes_nothing(db, capsys):
    before = _urls(db)
    assert rw.main(["--db", db]) == 0
    assert "'documents': 1, 'sentences': 2" in capsys.readouterr().out
    assert _urls(db) == before


def test_apply_on_a_copy_rewrites_only_the_pdf_links(db):
    assert rw.main(["--db", db, "--apply"]) == 0
    assert sorted(_urls(db)) == sorted([NEW, "https://www.cna.sg/x", NEW, NEW, "https://reddit.com/r/x"])


def test_the_served_database_needs_real_db(db, monkeypatch):
    import ingest.db
    monkeypatch.setattr(ingest.db, "DEFAULT_DB_PATH", db)
    assert rw.main(["--db", db, "--apply"]) == 2
    assert OLD in _urls(db)
    assert rw.main(["--db", db]) == 0                      # a dry run is always allowed


def test_plp_log_is_never_touched():
    assert "data/logs/plp.log" not in rw.tracked_files()
