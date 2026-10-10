"""
RAG evidence retrieval for the chatbot (docs/DESIGN.md, `search_evidence` tool).

Hybrid retrieval, matched to this corpus's actual scale rather than a generic
"vector DB + reranker" template:
  1. SQL pre-filter (bank / aspect / sentiment / date range) - cheap, exact,
     and does most of the narrowing before any embedding math happens.
  2. Semantic ranking - cosine similarity between the query and cached FinBERT
     sentence embeddings (aspects/embed_store.py) over whatever survives the
     filter.
  3. Lexical boost - a small score bump for sentences sharing literal query
     keywords, so exact terms (ticker codes, named products like "DBS
     Multiplier") aren't only found by semantic proximity. This is the
     "pure vector search won't reliably match specific identifiers" pattern
     from the RAG literature, right-sized: a keyword overlap term, not a full
     BM25 index, since the corpus doesn't warrant one yet.

Every result carries its source sentence_id, url, and date - the chatbot's
citation requirement is enforced by what this
function returns, not left to the model's discretion.

Aspect query (CHATBOT_ASPECT_QUERY=1, off by default): when an
aspect is given, the semantic score embeds the aspect's readable name plus
the question's content words instead of the whole question. FinBERT's
vectors carry a text's register strongly, so a question embeds like a
Reddit question and ranks the asked topic no better than random, while the
aspect's name ranks it well (docs/evidence/chatbot-eval-build-2026-10-01.md).
The word-overlap boost uses the same cleaned text, since question words
("what", "people", "say") also favour Reddit chatter.
"""

import config.model_version as current_model
from config import aspect_taxonomy
import re

import numpy as np

from chatbot import settings
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


_QUESTION_WORDS = {
    "what", "whats", "how", "is", "are", "was", "were", "do", "does", "did", "the", "a", "an", "of", "on",
    "about", "people", "say", "saying", "said", "think", "feel", "me", "show", "tell", "any", "there",
    "s", "its", "it", "for", "to", "in", "and", "or", "with", "evidence", "some", "you", "can", "i",
}
_BANK_WORDS = {"dbs", "posb", "ocbc", "uob", "bank", "banks"}


def aspect_query_enabled() -> bool:
    return bool(settings.get("aspect_query"))


def ranking_query(query: str, aspect: str | None) -> str:
    """The text whose embedding ranks the candidates: the aspect's readable
    name plus the question's content words when an aspect is given, else the
    query unchanged."""
    if not aspect:
        return query
    label = aspect_taxonomy.labels().get(aspect, aspect)
    # Bank names are already applied as a filter, and words the label carries
    # add nothing; what's left is the question's own topic ("cut", "complaints").
    skip = _QUESTION_WORDS | _BANK_WORDS | set(_WORD.findall(label.lower()))
    content = [w for w in _WORD.findall(query.lower()) if w not in skip]
    return " ".join([label] + content)


def search_evidence(query: str, bank: str | None = None, aspect: str | None = None,
                     sentiment: str | None = None, date_from: str | None = None,
                     date_to: str | None = None, k: int = 5, aspect_query: bool | None = None) -> list[dict]:
    """Semantic + lexical search over sentences, filtered by structured fields first.

    Returns up to k results: [{sentence_id, text, bank, aspect, sentiment,
    score, url, published_at}, ...], ranked by combined score, highest first.
    Empty list means no matching evidence - callers (the chatbot) must not
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
        where.append("a.model_version = ?"); params.append(current_model.MODEL_VERSION)
        if aspect:
            where.append("a.aspect = ?"); params.append(aspect)
        if sentiment:
            where.append("a.label = ?"); params.append(sentiment)

    conn = get_connection()
    try:
        cols = "s.sentence_id, s.text, s.bank, s.url, s.published_at, s.source"
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
    candidates, seen = [], set()
    for r in rows:
        # A sentiment filter without an aspect joins every (sentence, aspect)
        # row, so the same sentence can arrive once per aspect it matched.
        if r[0] in seen:
            continue
        seen.add(r[0])
        d = {"sentence_id": r[0], "text": r[1], "bank": r[2], "url": r[3], "published_at": r[4], "source": r[5]}
        if has_aspect_cols:
            d["aspect"], d["sentiment"] = r[6], r[7]
        candidates.append(d)

    cand_ids = {c["sentence_id"] for c in candidates}
    all_ids, all_vecs = load_for_search()
    id_to_idx = {sid: i for i, sid in enumerate(all_ids) if sid in cand_ids}

    scored = candidates
    use_aspect = aspect_query_enabled() if aspect_query is None else aspect_query
    rank_text = ranking_query(query, aspect) if use_aspect else query
    if id_to_idx:
        query_vec = embed_sentences([rank_text])[0]
        idxs = [id_to_idx[c["sentence_id"]] for c in candidates if c["sentence_id"] in id_to_idx]
        sims = _cosine_sim(query_vec, all_vecs[idxs]) if idxs else np.array([])
        sim_by_id = dict(zip([c["sentence_id"] for c in candidates if c["sentence_id"] in id_to_idx], sims))
    else:
        sim_by_id = {}

    # With the aspect query, the overlap boost uses the same cleaned text, so
    # question words ("what", "people", "say") don't favour chatter.
    query_words = set(_WORD.findall(rank_text.lower()))
    for c in scored:
        cosine = float(sim_by_id.get(c["sentence_id"], 0.0))
        lexical = _lexical_overlap(query_words, c["text"])
        c["score"] = round(cosine + _LEXICAL_WEIGHT * lexical, 4)

    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:max(int(k), 0)]   # a negative k would otherwise drop the last result
