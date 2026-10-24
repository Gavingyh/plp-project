"""Tests for chatbot/search_vectors.py: the evidence search's own store of
sentence vectors, beside FinBERT's in aspects/embed_store.py."""

import numpy as np

import aspects.embed_store as embed_store
import chatbot.retrieval as retrieval
import chatbot.search_vectors as search_vectors
from ingest.db import now_iso


def _add(conn, sid, text):
    conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, norm_hash, "
                 "processed_at) VALUES (?, 'd', 'DBS', ?, '2026-09-01', 'arctic_shift', 'u', ?, ?)",
                 (sid, text, f"h{sid}", now_iso()))


def _fake_embed(calls):
    def embed(texts):
        calls.append(list(texts))
        return np.ones((len(texts), search_vectors.WIDTH), dtype=np.float32)
    return embed


def test_the_store_embeds_only_new_sentences_and_drops_removed_ones(temp_db, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(search_vectors, "STORE_PATH", str(tmp_path / "search.npz"))
    monkeypatch.setattr(search_vectors, "embed_sentences", _fake_embed(calls))
    conn = temp_db.get_connection()
    _add(conn, "a", "first"); _add(conn, "b", "second")
    conn.commit()
    assert search_vectors.update()["newly_embedded"] == 2
    _add(conn, "c", "third"); conn.execute("DELETE FROM sentences WHERE sentence_id = 'a'")
    conn.commit(); conn.close()
    stats = search_vectors.update()
    assert stats["newly_embedded"] == 1 and stats["pruned_stale"] == 1
    assert calls[-1] == ["third"]                                   # the kept vectors are not recomputed
    ids, vecs = search_vectors.load_for_search()
    assert sorted(ids) == ["b", "c"] and vecs.shape == (2, search_vectors.WIDTH)


def test_the_two_stores_are_held_apart(tmp_path, monkeypatch):
    finbert, search = tmp_path / "finbert.npz", tmp_path / "search.npz"
    np.savez_compressed(finbert, sentence_ids=np.array(["a"]), vectors=np.ones((1, 768), dtype=np.float32))
    np.savez_compressed(search, sentence_ids=np.array(["a"]), vectors=np.ones((1, 384), dtype=np.float32))
    monkeypatch.setattr(embed_store, "STORE_PATH", str(finbert))
    monkeypatch.setattr(embed_store, "_search_cache", {})
    monkeypatch.setattr(search_vectors, "STORE_PATH", str(search))
    first = search_vectors.load_for_search()
    assert embed_store.load_for_search()[1].shape == (1, 768)       # FinBERT's, for the aspects
    assert search_vectors.load_for_search() is first                # still held, not read again
    assert first[1].shape == (1, 384)


def test_the_evidence_search_reads_the_search_models_vectors():
    assert retrieval.load_for_search is search_vectors.load_for_search
    assert retrieval.embed_sentences is search_vectors.embed_sentences
