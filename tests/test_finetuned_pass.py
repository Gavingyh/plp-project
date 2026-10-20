"""Tests for sentiment/finetuned.py: new pairs get the served fine-tuned version's scores."""

import json

import numpy as np
import pytest

import config.model_version as current_model
import sentiment.finetuned as ft
from config.model_version import MODEL_VERSION as BASE
from ingest.db import now_iso

VERSION = "finbert-finetuned-test-1seed-m0.13"


@pytest.fixture
def db(temp_db, monkeypatch):
    conn = temp_db.get_connection()
    for sid, text in (("s1", "up"), ("s2", "down")):
        conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, norm_hash, "
                     "processed_at) VALUES (?, 'd', 'DBS', ?, '2026-01-01T00:00:00+00:00', 'arctic_shift', 'u', ?, ?)",
                     (sid, text, f"h{sid}", now_iso()))
        conn.execute("INSERT INTO sentence_aspects VALUES (?, 'dividend_policy', 1.0, ?)", (sid, now_iso()))
    conn.execute("INSERT INTO aspect_sentiment VALUES ('s1', 'dividend_policy', 'positive', 0.9, ?, ?)",
                 (VERSION, now_iso()))                                 # s1 already scored, s2 is new
    conn.commit()
    conn.close()
    monkeypatch.setattr(ft, "FINETUNED", {VERSION: {"models": ["m/seed_1/final"], "margin": 0.13}})
    import train.evaluate
    monkeypatch.setattr(train.evaluate, "finetuned_probs",
                        lambda d, df: np.array([[0.8, 0.1, 0.1] if t == "down" else [0.1, 0.1, 0.8]
                                                for t in df["text"]]))
    import aggregate.preview as pv
    monkeypatch.setattr(pv, "scores_cache_path", lambda models: None)
    return temp_db


def _versions(temp_db):
    conn = temp_db.get_connection()
    rows = conn.execute("SELECT sentence_id, label, model_version FROM aspect_sentiment ORDER BY 1, 3").fetchall()
    conn.close()
    return rows


def test_only_missing_pairs_are_scored(db):
    conn = db.get_connection()
    assert ft.score_missing(conn, VERSION, now_iso()) == 1
    conn.close()
    assert _versions(db) == [("s1", "positive", VERSION), ("s2", "negative", VERSION)]


def test_first_finetuned_run_creates_its_cache_directory(db, tmp_path, monkeypatch):
    import aggregate.preview as pv

    cache = tmp_path / "data" / "preview" / "scores.test.jsonl"
    monkeypatch.setattr(pv, "scores_cache_path", lambda models: str(cache))
    assert not cache.parent.exists()
    conn = db.get_connection()
    try:
        assert ft.score_missing(conn, VERSION, now_iso()) == 1
        assert ft.score_missing(conn, VERSION, now_iso()) == 0
    finally:
        conn.close()
    rows = [json.loads(line) for line in cache.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["sentence_id"] == "s2"
    assert _versions(db) == [("s1", "positive", VERSION), ("s2", "negative", VERSION)]


def test_a_served_version_without_models_is_refused(db):
    conn = db.get_connection()
    with pytest.raises(ValueError, match="no models in FINETUNED"):
        ft.score_missing(conn, "finbert-finetuned-unknown", now_iso())
    conn.close()


def test_the_scorer_runs_the_fine_tuned_pass_while_it_is_served(db, monkeypatch):
    import sentiment.score as score
    monkeypatch.setattr(score, "classify_sentences", lambda texts: [("neutral", 0.6)] * len(texts))
    monkeypatch.setattr(current_model, "MODEL_VERSION", VERSION)
    result = score.run()
    assert result["finetuned_scored"] == 1 and result["finetuned_version"] == VERSION
    assert ("s2", "negative", VERSION) in _versions(db) and ("s2", "neutral", BASE) in _versions(db)


def test_no_fine_tuned_pass_while_base_is_served(db, monkeypatch):
    import sentiment.score as score
    monkeypatch.setattr(score, "classify_sentences", lambda texts: [("neutral", 0.6)] * len(texts))
    assert "finetuned_scored" not in score.run()


def test_the_served_version_is_base_or_has_its_models_listed(served_version):
    from config.model_version import BASE_VERSION, FINETUNED
    assert served_version == BASE_VERSION or served_version in FINETUNED
