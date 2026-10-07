"""
scripts/source_rows.py moves one source's rows between two databases: export
reads only that source, import adds them once. Synthetic databases only.
"""

import importlib.util
import os
import sqlite3

import pytest

_spec = importlib.util.spec_from_file_location(
    "source_rows", os.path.join(os.path.dirname(__file__), "..", "scripts", "source_rows.py"))
source_rows = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(source_rows)


def _db(path, sources):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE documents (doc_id TEXT PRIMARY KEY, source TEXT);
        CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, doc_id TEXT, source TEXT, text TEXT);
        CREATE TABLE sentence_aspects (sentence_id TEXT, aspect TEXT, PRIMARY KEY (sentence_id, aspect));
        CREATE TABLE aspect_sentiment (sentence_id TEXT, aspect TEXT, label TEXT, PRIMARY KEY (sentence_id, aspect));
    """)
    for i, source in enumerate(sources):
        conn.execute("INSERT INTO documents VALUES (?, ?)", (f"d{i}", source))
        conn.execute("INSERT INTO sentences VALUES (?, ?, ?, ?)", (f"s{i}", f"d{i}", source, f"text {i}"))
        conn.execute("INSERT INTO sentence_aspects VALUES (?, 'other')", (f"s{i}",))
        conn.execute("INSERT INTO aspect_sentiment VALUES (?, 'other', 'neutral')", (f"s{i}",))
    conn.commit()
    conn.close()


def test_export_takes_one_source_and_import_adds_it_once_only(tmp_path):
    pc, mac, rows = str(tmp_path / "pc.db"), str(tmp_path / "mac.db"), str(tmp_path / "rows.db")
    _db(pc, ["sgx_research", "sgx_research", "arctic_shift"])
    _db(mac, [])
    assert source_rows.export(pc, "sgx_research", rows) == \
        {"documents": 2, "sentences": 2, "sentence_aspects": 2, "aspect_sentiment": 2}
    first = source_rows.import_rows(rows, mac)
    assert all(v == {"in_file": 2, "added": 2} for v in first.values())
    with pytest.raises(SystemExit, match="already holds"):       # a second import would count the source twice
        source_rows.import_rows(rows, mac)
    conn = sqlite3.connect(mac)
    assert conn.execute("SELECT COUNT(*) FROM sentences WHERE source = 'arctic_shift'").fetchone()[0] == 0
