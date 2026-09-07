"""
RAG evidence retrieval for the chatbot (docs/DESIGN.md, `search_evidence` tool).

Hybrid retrieval, matched to this corpus's actual scale rather than a generic
"vector DB + reranker" template:
  1. SQL pre-filter (bank / aspect / sentiment / date range) — cheap, exact,
     and does most of the narrowing before any embedding math happens.
  2. Semantic ranking — cosine similarity between the query and cached FinBERT
     sentence embeddings (aspects/embed_store.py) over whatever survives the
     filter.
  3. Lexical boost — a small score bump for sentences sharing literal query
     keywords, so exact terms (ticker codes, named products like "DBS
     Multiplier") aren't only found by semantic proximity. This is the
     "pure vector search won't reliably match specific identifiers" pattern
     from the RAG literature, right-sized: a keyword overlap term, not a full
     BM25 index, since the corpus doesn't warrant one yet.

Every result carries its source sentence_id, url, and date — the chatbot's
citation requirement is enforced by what this
function returns, not left to the model's discretion.
"""

import re

import numpy as np

from aspects.embed import embed_sentences
from aspects.embed_store import load_for_search
from ingest.db import get_connection

_WORD = re.compile(r"\w+")
_LEXICAL_WEIGHT = 0.15  # small boost relative to cosine similarity, see module docstring


def _cosine_sim(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q = query_vec / (np.linalg.norm(query_vec) + 1e-9)
    m = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    return m @ q


def _lexical_overlap(query_words: set[str], text: str) -> float:
    text_words = set(_WORD.findall(text.lower()))
    if not query_words:
        return 0.0
    return len(query_words & text_words) / len(query_words)


def search_evidence(query: str, bank: str | None = None, aspect: str | None = None,
                     sentiment: str | None = None, date_from: str | None = None,
                     date_to: str | None = None, k: int = 5) -> list[dict]:
    """Semantic + lexical search over sentences, filtered by structured fields first.

    Returns up to k results: [{sentence_id, text, bank, aspect, sentiment,
    score, url, published_at}, ...], ranked by combined score, highest first.
    Empty list means no matching evidence — callers (the chatbot) must not
    fabricate an answer when this comes back empty.
    """
    where, params = ["1=1"], []
    if bank:
        where.append("s.bank = ?"); params.append(bank)
    if date_from:
        where.append("s.published_at >= ?"); params.append(date_from)
    if date_to:
        where.append("s.published_at <= ?"); params.append(date_to)

    join = ""
    if aspect or sentiment:
        join = "JOIN aspect_sentiment a ON a.sentence_id = s.sentence_id"
        if aspect:
            where.append("a.aspect = ?"); params.append(aspect)
        if sentiment:
            where.append("a.label = ?"); params.append(sentiment)

    conn = get_connection()
    try:
        cols = "s.sentence_id, s.text, s.bank, s.url, s.published_at"
        if aspect or sentiment:
            cols += ", a.aspect, a.label"
        rows = conn.execute(
            f"SELECT {cols} FROM sentences s {join} WHERE {' AND '.join(where)}",
            params,
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    has_aspect_cols = bool(aspect or sentiment)
    candidates = []
    for r in rows:
        d = {"sentence_id": r[0], "text": r[1], "bank": r[2], "url": r[3], "published_at": r[4]}
        if has_aspect_cols:
            d["aspect"], d["sentiment"] = r[5], r[6]
        candidates.append(d)

    cand_ids = {c["sentence_id"] for c in candidates}
    all_ids, all_vecs = load_for_search()
    id_to_idx = {sid: i for i, sid in enumerate(all_ids) if sid in cand_ids}

    scored = candidates
    if id_to_idx:
        query_vec = embed_sentences([query])[0]
        idxs = [id_to_idx[c["sentence_id"]] for c in candidates if c["sentence_id"] in id_to_idx]
        sims = _cosine_sim(query_vec, all_vecs[idxs]) if idxs else np.array([])
        sim_by_id = dict(zip([c["sentence_id"] for c in candidates if c["sentence_id"] in id_to_idx], sims))
    else:
        sim_by_id = {}

    query_words = set(_WORD.findall(query.lower()))
    for c in scored:
        cosine = float(sim_by_id.get(c["sentence_id"], 0.0))
        lexical = _lexical_overlap(query_words, c["text"])
        c["score"] = round(cosine + _LEXICAL_WEIGHT * lexical, 4)

    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:k]
