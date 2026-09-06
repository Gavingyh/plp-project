"""
Shared SQLite storage for the ingestion pipeline.

Single `documents` table, schema per the MVP plan (.project-context/plan/mvp-implementation-plan.md,
Phase 1a). `doc_id` is a deterministic hash of (source, native id or URL), so re-running
any ingest adapter is idempotent: INSERT OR IGNORE means a duplicate doc_id is silently
skipped rather than creating a second row or overwriting the first.
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "plp.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id         TEXT PRIMARY KEY,
    source         TEXT NOT NULL,      -- newsapi | alphavantage | arctic_shift | earnings
    source_detail  TEXT,               -- publication name, subreddit, or doc type
    bank           TEXT NOT NULL,      -- DBS | OCBC | UOB | MULTI
    doc_type       TEXT NOT NULL,      -- article | submission | comment | earnings_release
    title          TEXT,
    body           TEXT NOT NULL,
    published_at   TEXT NOT NULL,      -- ISO 8601 UTC
    url            TEXT NOT NULL,
    ingested_at    TEXT NOT NULL,      -- ISO 8601 UTC, batch provenance
    raw            TEXT                -- original payload as JSON, for auditability
);
CREATE INDEX IF NOT EXISTS idx_documents_bank ON documents(bank);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_documents_published_at ON documents(published_at);

-- Phase 2 (preprocess/): the sentence is the unit of analysis for everything
-- downstream — aspect assignment, sentiment labels, the index, and the
-- chatbot's evidence citations all key off sentence_id. See MVP plan,
-- "Architecture at a glance".
CREATE TABLE IF NOT EXISTS sentences (
    sentence_id    TEXT PRIMARY KEY,
    doc_id         TEXT NOT NULL REFERENCES documents(doc_id),
    bank           TEXT NOT NULL,      -- resolved per-sentence, may differ from documents.bank
    text           TEXT NOT NULL,
    char_start     INTEGER,
    char_end       INTEGER,
    published_at   TEXT NOT NULL,
    source         TEXT NOT NULL,      -- denormalized from documents for query speed
    url            TEXT NOT NULL,
    norm_hash      TEXT NOT NULL,      -- normalized-text hash, used for dedup
    processed_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sentences_doc ON sentences(doc_id);
CREATE INDEX IF NOT EXISTS idx_sentences_bank ON sentences(bank);
CREATE INDEX IF NOT EXISTS idx_sentences_norm_hash ON sentences(norm_hash);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_doc_id(source: str, native_id: str) -> str:
    """Deterministic id so re-ingesting the same item is a no-op, not a duplicate."""
    return hashlib.sha256(f"{source}:{native_id}".encode("utf-8")).hexdigest()[:24]


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def upsert_documents(rows: list[dict]) -> tuple[int, int]:
    """Insert new documents, ignore ones we've already ingested.

    Returns (attempted, inserted) so callers can report how many rows were
    genuinely new vs. already-seen duplicates from a prior run.
    """
    if not rows:
        return (0, 0)
    init_db()
    conn = get_connection()
    try:
        cur = conn.cursor()
        inserted = 0
        for r in rows:
            payload = (
                r["doc_id"], r["source"], r.get("source_detail"), r["bank"],
                r["doc_type"], r.get("title"), r["body"], r["published_at"],
                r["url"], r.get("ingested_at") or now_iso(),
                json.dumps(r.get("raw", {}), default=str),
            )
            cur.execute(
                """INSERT OR IGNORE INTO documents
                   (doc_id, source, source_detail, bank, doc_type, title, body,
                    published_at, url, ingested_at, raw)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                payload,
            )
            inserted += cur.rowcount
        conn.commit()
        return (len(rows), inserted)
    finally:
        conn.close()


def count_by_source_bank() -> list[tuple]:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT source, bank, COUNT(*) FROM documents GROUP BY source, bank ORDER BY source, bank"
        ).fetchall()
    finally:
        conn.close()


def total_count() -> int:
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    finally:
        conn.close()
