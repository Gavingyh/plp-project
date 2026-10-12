"""scripts/rewrite_pdf_paths.py: earnings-PDF links from absolute paths to
repository-relative ones. Dry run by default."""

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
    assert rw.PDF_LINK.sub(rw.RELATIVE, line) == f'"{NEW}",earnings,DBS'


def test_a_windows_path_to_broker_research_becomes_a_repository_path():
    old = "file://C:\\Users\\some one\\plp\\data\\sgx_research\\0408 DBS - OCBC Update.pdf"
    assert rw.relative(old) == "data/sgx_research/0408 DBS - OCBC Update.pdf"
    escaped = old.replace("\\", "\\\\")                       # as a JSON file writes it
    assert rw.relative(escaped) == "data/sgx_research/0408 DBS - OCBC Update.pdf"
    assert rw.relative("file:///srv/other/data/reports/x.pdf") == "file:///srv/other/data/reports/x.pdf"


def test_rewriting_files_keeps_their_line_endings(tmp_path, monkeypatch):
    f = tmp_path / "rows.csv"
    f.write_bytes(f"id,url\r\n1,{OLD}\r\n2,x\r\n".encode())
    monkeypatch.setattr(rw, "ROOT", str(tmp_path))
    rw.rewrite_files({"rows.csv": 1})
    assert f.read_bytes() == f"id,url\r\n1,{NEW}\r\n2,x\r\n".encode()


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
