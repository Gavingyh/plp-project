"""
Persisted cache of per-sentence FinBERT embeddings, used by aspect discovery
and assignment (aspects/discover.py, aspects/assign.py). The chatbot's
evidence search keeps its own store, from a model trained to match sentences
(chatbot/search_vectors.py), through the same functions with another path.
Incremental: only embeds sentences not already in the cache, so re-running
after a new ingestion batch is cheap.

At this corpus scale (hundreds to low thousands of sentences for an MVP),
brute-force cosine similarity over an in-memory matrix is simpler and just as
correct as a vector-DB - no FAISS/Chroma needed. Revisit only if the corpus
grows into the hundreds of thousands.

USAGE:
  python -m aspects.embed_store   # embed any un-embedded sentences
"""

import os
from pathlib import Path
import sqlite3
import tempfile

import numpy as np

from aspects.embed import embed_sentences
from ingest import db

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_PATH = os.path.abspath(os.environ.get("PLP_EMBEDDINGS_PATH")
                             or os.path.join(BASE_DIR, "data", "sentence_embeddings.npz"))


def _load_store(path: str | None = None, width: int = 768) -> tuple[list[str], np.ndarray]:
    path = path or STORE_PATH
    if not os.path.exists(path):
        return [], np.zeros((0, width), dtype=np.float32)
    with np.load(path, allow_pickle=False) as data:
        return list(data["sentence_ids"]), data["vectors"]


def _save_store(sentence_ids: list[str], vectors: np.ndarray, path: str | None = None) -> None:
    path = path or STORE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Readers keep using the last complete cache if a writer is interrupted.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), prefix=".vectors-", delete=False) as stream:
            temporary = stream.name
            np.savez_compressed(stream, sentence_ids=np.array(sentence_ids, dtype=str), vectors=vectors)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def update(path: str | None = None, embed=None, width: int = 768) -> dict:
    """Embed any sentence in the DB not yet in the cache, and drop cache entries
    for sentences that no longer exist in the DB (e.g. purged after a data-quality
    fix) - otherwise stale entries accumulate and consumers that look them back up
    against the `sentences` table (aspects/discover.py) hard-fail on a missing row.
    Returns a small stats dict. `path`, `embed` and `width` name another store
    and its model; by default, FinBERT's."""
    embed = embed or embed_sentences
    existing_ids, existing_vecs = _load_store(path, width)
    existing_map = dict(zip(existing_ids, existing_vecs))

    conn = sqlite3.connect(Path(db.DB_PATH).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT sentence_id, text FROM sentences").fetchall()
    finally:
        conn.close()

    current_ids = {sid for sid, _ in rows}
    pruned = len(existing_ids) - len(set(existing_ids) & current_ids)

    new_rows = [(sid, text) for sid, text in rows if sid not in existing_map]
    if not new_rows and not pruned and os.path.isfile(path or STORE_PATH):
        return {"already_cached": len(existing_ids), "newly_embedded": 0,
                "pruned_stale": 0, "total": len(existing_ids)}
    new_ids, new_vecs = [], np.zeros((0, width), dtype=np.float32)
    if new_rows:
        new_ids = [r[0] for r in new_rows]
        new_vecs = embed([r[1] for r in new_rows])

    # Rebuild the store from current DB rows only (existing ones reused from
    # cache, new ones just embedded) - this is what prunes stale entries.
    kept_ids = [sid for sid, _ in rows if sid in existing_map]
    kept_vecs = np.array([existing_map[sid] for sid in kept_ids]) if kept_ids else np.zeros((0, width), dtype=np.float32)
    all_ids = kept_ids + new_ids
    all_vecs = np.concatenate([kept_vecs, new_vecs], axis=0) if kept_ids or len(new_ids) else np.zeros((0, width), dtype=np.float32)
    _save_store(all_ids, all_vecs, path)
    return {"already_cached": len(kept_ids), "newly_embedded": len(new_ids),
            "pruned_stale": pruned, "total": len(all_ids)}


_search_cache: dict = {}


def load_for_search(path: str | None = None) -> tuple[list[str], np.ndarray]:
    """Read-only load for retrieval/clustering consumers, kept in memory until
    the file changes: the chatbot searches evidence on most turns, and reading
    the file each time made every search slower. Each store is held under its
    own path. Callers must not modify what it returns."""
    path = path or STORE_PATH
    key = (os.path.getmtime(path), os.path.getsize(path)) if os.path.exists(path) else None
    held = _search_cache.get(path)
    if held is None or held[0] != key:
        held = _search_cache[path] = (key, _load_store(path))
    return held[1]


if __name__ == "__main__":
    setup_logging()
    stats = update()
    logger.info(f"Embedding cache: {stats}")
