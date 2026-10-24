"""Tests for aspects/assign.py's assignment_method: new sentences follow the corpus's method."""

import numpy as np
import pandas as pd
import pytest

import aspects.assign as assign
from ingest.db import now_iso


def _setup(temp_db, monkeypatch, method, ids=("s1", "s2")):
    conn = temp_db.get_connection()
    for sid in ids:
        conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, norm_hash, "
                     "processed_at) VALUES (?, 'd', 'DBS', ?, '2026-01-01T00:00:00+00:00', 'arctic_shift', 'u', ?, ?)",
                     (sid, f"text of {sid}", f"h{sid}", now_iso()))
    conn.commit()
    conn.close()
    monkeypatch.setattr(assign, "_load_config", lambda: {
        "assignment_method": method, "similarity_floor": 0.5,
        "aspects": {"dividend_policy": {"seed_terms": ["dividend"]}, "asset_quality": {"seed_terms": ["npl"]},
                    "other": {"seed_terms": []}}})
    monkeypatch.setattr(assign, "update_embeddings", lambda: {})
    monkeypatch.setattr(assign, "update_search_vectors", lambda: {})
    monkeypatch.setattr(assign, "load_for_search", lambda: (list(ids), np.ones((len(ids), 2))))
    monkeypatch.setattr(assign, "embed_sentences", lambda terms: np.ones((len(terms), 2)))


def _assigned(temp_db):
    conn = temp_db.get_connection()
    rows = conn.execute("SELECT sentence_id, aspect, similarity FROM sentence_aspects ORDER BY 1, 2").fetchall()
    conn.close()
    return rows


def test_llm_method_gives_one_aspect_per_new_sentence(temp_db, monkeypatch):
    _setup(temp_db, monkeypatch, "llm")
    import aspects.llm_classify as llm
    seen = []

    def fake_classify(rows, *a, **kw):
        seen.extend(rows["text"])
        return pd.DataFrame({"sentence_id": rows["sentence_id"], "aspect": ["dividend_policy", "other"]})
    monkeypatch.setattr(llm, "classify_rows", fake_classify)
    stats = assign.run()
    assert _assigned(temp_db) == [("s1", "dividend_policy", 1.0), ("s2", "other", 1.0)]
    assert seen == ["text of s1", "text of s2"]
    assert stats["method"] == "llm" and stats["newly_assigned"] == 2 and stats["fell_to_other"] == 1


def test_centroid_method_is_unchanged(temp_db, monkeypatch):
    _setup(temp_db, monkeypatch, "centroid", ids=("s1",))
    assign.run()
    assert [(sid, a) for sid, a, _ in _assigned(temp_db)] == [("s1", "asset_quality"), ("s1", "dividend_policy")]


def test_unknown_method_is_refused(temp_db, monkeypatch):
    _setup(temp_db, monkeypatch, "kmeans")
    with pytest.raises(ValueError, match="assignment_method"):
        assign.run()
