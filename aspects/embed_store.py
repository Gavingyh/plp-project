"""
Persisted cache of per-sentence FinBERT embeddings, shared by:
  - aspect discovery and assignment (aspects/discover.py, aspects/assign.py)
  - chatbot evidence retrieval (chatbot/retrieval.py - the RAG piece)

One embedding space for both consumers rather than computing FinBERT vectors
twice. Incremental: only embeds sentences not already in the cache, so
re-running after a new ingestion batch is cheap.

At this corpus scale (hundreds to low thousands of sentences for an MVP),
brute-force cosine similarity over an in-memory matrix is simpler and just as
correct as a vector-DB - no FAISS/Chroma needed. Revisit only if the corpus
grows into the hundreds of thousands.

USAGE:
  python -m aspects.embed_store   # embed any un-embedded sentences
"""

import os

import numpy as np

from aspects.embed import embed_sentences
from ingest.db import get_connection

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_PATH = os.path.join(BASE_DIR, "data", "sentence_embeddings.npz")


def _load_store() -> tuple[list[str], np.ndarray]:
    if not os.path.exists(STORE_PATH):
        return [], np.zeros((0, 768), dtype=np.float32)
    data = np.load(STORE_PATH, allow_pickle=False)
    return list(data["sentence_ids"]), data["vectors"]


def _save_store(sentence_ids: list[str], vectors: np.ndarray) -> None:
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    np.savez_compressed(STORE_PATH, sentence_ids=np.array(sentence_ids), vectors=vectors)


def update() -> dict:
    """Embed any sentence in the DB not yet in the cache, and drop cache entries
    for sentences that no longer exist in the DB (e.g. purged after a data-quality
    fix) - otherwise stale entries accumulate and consumers that look them back up
    against the `sentences` table (aspects/discover.py) hard-fail on a missing row.
    Returns a small stats dict."""
    existing_ids, existing_vecs = _load_store()
    existing_map = dict(zip(existing_ids, existing_vecs))

    conn = get_connection()
    try:
        rows = conn.execute("SELECT sentence_id, text FROM sentences").fetchall()
    finally:
        conn.close()

    current_ids = {sid for sid, _ in rows}
    pruned = len(existing_ids) - len(set(existing_ids) & current_ids)

    new_rows = [(sid, text) for sid, text in rows if sid not in existing_map]
    new_ids, new_vecs = [], np.zeros((0, 768), dtype=np.float32)
    if new_rows:
        new_ids = [r[0] for r in new_rows]
        new_vecs = embed_sentences([r[1] for r in new_rows])

    # Rebuild the store from current DB rows only (existing ones reused from
    # cache, new ones just embedded) - this is what prunes stale entries.
    kept_ids = [sid for sid, _ in rows if sid in existing_map]
    kept_vecs = np.array([existing_map[sid] for sid in kept_ids]) if kept_ids else np.zeros((0, 768), dtype=np.float32)
    all_ids = kept_ids + new_ids
    all_vecs = np.concatenate([kept_vecs, new_vecs], axis=0) if kept_ids or len(new_ids) else np.zeros((0, 768), dtype=np.float32)
    _save_store(all_ids, all_vecs)
    return {"already_cached": len(kept_ids), "newly_embedded": len(new_ids),
            "pruned_stale": pruned, "total": len(all_ids)}


_search_cache: dict = {}


def load_for_search() -> tuple[list[str], np.ndarray]:
    """Read-only load for retrieval/clustering consumers, kept in memory until
    the file changes: the chatbot searches evidence on most turns, and reading
    the 127 MB file each time made every search slower (4 Oct 2026). Callers
    must not modify what it returns."""
    key = (os.path.getmtime(STORE_PATH), os.path.getsize(STORE_PATH)) if os.path.exists(STORE_PATH) else None
    if _search_cache.get("key") != key or "value" not in _search_cache:
        _search_cache.update(key=key, value=_load_store())
    return _search_cache["value"]


if __name__ == "__main__":
    setup_logging()
    stats = update()
    logger.info(f"Embedding cache: {stats}")
