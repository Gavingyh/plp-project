"""
Phase 2 pipeline: documents -> sentences.

Reads documents not yet processed (doc_id not already represented in
`sentences`), cleans per-source, segments into sentences, resolves bank
attribution per sentence, drops near-duplicates (normalized-text hash) and
sub-length fragments, and writes the result into the `sentences` table.

This is the "unit of analysis is the sentence" step — see MVP plan,
Architecture at a glance. Aspect assignment (Phase 3), sentiment scoring
(Phase 5), the index (Phase 6), and the chatbot's evidence citations (Phase 8)
all key off sentence_id from here.

USAGE:
  python -m preprocess.pipeline
"""

import hashlib
import re
from datetime import datetime

from ingest.base import detect_banks
from ingest.db import get_connection, init_db, now_iso
from preprocess.clean import clean_for_source
from preprocess.segment import segment

_WORD = re.compile(r"\w+")
_MIN_WORDS = 4  # drops trivially short fragments even after segment()'s char filter


def _norm_hash(text: str) -> str:
    """Normalized-text hash for near-duplicate detection (e.g. syndicated wire
    copy republished across outlets) — see MVP plan Phase 2, step 5."""
    normalized = re.sub(r"[^\w]", "", text.lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _sentence_id(doc_id: str, start: int, end: int) -> str:
    return hashlib.sha256(f"{doc_id}:{start}:{end}".encode("utf-8")).hexdigest()[:24]


# Sources short/focused enough that a sentence naming no bank can safely
# inherit the document's bank (a news title+description is ~1-2 sentences,
# almost always entirely about the bank it was queried for). Long, rambling
# multi-topic Reddit threads do NOT get this treatment — empirically,
# inheriting there pulled in unrelated sentences from the same comment
# ("Calling you for $8 transaction is a red flag itself.") as if they were
# about the bank. For those sources we require an explicit in-sentence
# mention. This is the "keyword-plus-length heuristic, known precision
# limitation" the MVP plan flags for the relevance filter (Phase 2, step 4).
_INHERIT_DOC_BANK_SOURCES = {"newsapi", "alphavantage", "earnings"}


def _resolve_sentence_bank(sentence_text: str, doc_bank: str, source: str) -> str | None:
    """Per-sentence bank attribution — a MULTI document usually has each bank
    named in a different sentence, not all sentences about all banks.
    See MVP plan Phase 2, step 3."""
    found = detect_banks(sentence_text)
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        return None  # ambiguous within the sentence itself — drop (known MVP limitation)
    if doc_bank != "MULTI" and source in _INHERIT_DOC_BANK_SOURCES:
        return doc_bank  # implicit reference ("the bank", "it") in a short, single-topic document
    return None  # no explicit mention, and either MULTI or a source we don't inherit for — drop


def fetch_unprocessed_documents(conn) -> list[dict]:
    rows = conn.execute("""
        SELECT d.doc_id, d.source, d.bank, d.body, d.published_at, d.url
        FROM documents d
        WHERE NOT EXISTS (SELECT 1 FROM sentences s WHERE s.doc_id = d.doc_id)
    """).fetchall()
    cols = ["doc_id", "source", "bank", "body", "published_at", "url"]
    return [dict(zip(cols, r)) for r in rows]


def load_existing_hashes(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT DISTINCT norm_hash FROM sentences").fetchall()}


def run() -> dict:
    init_db()
    conn = get_connection()
    stats = {"documents_processed": 0, "sentences_kept": 0, "dropped_short": 0,
              "dropped_ambiguous_bank": 0, "dropped_duplicate": 0, "dropped_cleaner_empty": 0}
    try:
        docs = fetch_unprocessed_documents(conn)
        seen_hashes = load_existing_hashes(conn)
        to_insert = []

        for doc in docs:
            cleaned = clean_for_source(doc["source"], doc["body"])
            if not cleaned:
                stats["dropped_cleaner_empty"] += 1
                continue
            for sent_text, start, end in segment(cleaned):
                if len(_WORD.findall(sent_text)) < _MIN_WORDS:
                    stats["dropped_short"] += 1
                    continue
                bank = _resolve_sentence_bank(sent_text, doc["bank"], doc["source"])
                if bank is None:
                    stats["dropped_ambiguous_bank"] += 1
                    continue
                h = _norm_hash(sent_text)
                if h in seen_hashes:
                    stats["dropped_duplicate"] += 1
                    continue
                seen_hashes.add(h)
                to_insert.append((
                    _sentence_id(doc["doc_id"], start, end), doc["doc_id"], bank,
                    sent_text, start, end, doc["published_at"], doc["source"],
                    doc["url"], h, now_iso(),
                ))
            stats["documents_processed"] += 1

        if to_insert:
            conn.executemany(
                """INSERT OR IGNORE INTO sentences
                   (sentence_id, doc_id, bank, text, char_start, char_end,
                    published_at, source, url, norm_hash, processed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                to_insert,
            )
            conn.commit()
        stats["sentences_kept"] = len(to_insert)
        return stats
    finally:
        conn.close()


if __name__ == "__main__":
    print(f"Run started: {datetime.now().isoformat()}\n")
    stats = run()
    print("=" * 50)
    for k, v in stats.items():
        print(f"  {k:28s} {v}")
    print("=" * 50)
