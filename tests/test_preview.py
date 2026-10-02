"""Tests for aggregate/preview.py: scoring like the index, and refusing garbage probabilities."""

import numpy as np
import pandas as pd
import pytest

import aggregate.preview as pv
from config.model_version import MODEL_VERSION


def test_headline_counts_each_sentence_once_with_its_most_confident_pair():
    meta = pd.DataFrame({"sentence_id": ["s1", "s2"], "bank": ["DBS", "DBS"], "source": ["arctic_shift"] * 2})
    pairs = pd.DataFrame({"sentence_id": ["s1", "s1", "s2"], "aspect": ["a", "b", "a"],
                          "label": ["positive", "negative", "neutral"], "confidence": [0.9, 0.6, 0.8]})
    out = pv.summarize(pairs, meta).set_index("aspect")
    assert out.loc["ALL", "n"] == 2 and out.loc["ALL", "pos"] == 1 and out.loc["ALL", "neg"] == 0
    assert out.loc["a", "n"] == 2 and out.loc["b", "n"] == 1


def test_garbage_probabilities_are_refused(monkeypatch):
    import train.evaluate
    monkeypatch.setattr(train.evaluate, "finetuned_probs", lambda d, df: np.zeros((len(df), 3)))
    with pytest.raises(RuntimeError, match="sum to 1"):
        pv.finetuned_labels(pd.DataFrame({"sentence_id": ["s1"], "aspect": ["a"], "text": ["t"]}), ["m"])


def _fake_models(monkeypatch, probs_for, calls):
    import train.evaluate

    def fake(model_dir, df):
        calls.append(len(df))
        return np.array([probs_for(t) for t in df["text"]])
    monkeypatch.setattr(train.evaluate, "finetuned_probs", fake)


def test_scores_are_cached_and_resumed(tmp_path, monkeypatch):
    calls = []
    _fake_models(monkeypatch, lambda t: [0.1, 0.2, 0.7], calls)
    pairs = pd.DataFrame({"sentence_id": ["s1", "s1", "s2"], "aspect": ["a", "b", "a"], "text": ["t1", "t1", "t2"]})
    cache = str(tmp_path / "scores.jsonl")
    first = pv.averaged_probs(pairs, ["m1", "m2"], cache, chunk=2)
    assert calls == [2, 2, 1, 1]                                  # two chunks, two models each
    again = pv.averaged_probs(pairs, ["m1", "m2"], cache, chunk=2)
    assert calls == [2, 2, 1, 1]                                  # all cached: nothing scored
    more = pd.concat([pairs, pd.DataFrame({"sentence_id": ["s3"], "aspect": ["a"], "text": ["t3"]})])
    pv.averaged_probs(more, ["m1", "m2"], cache, chunk=2)
    assert calls[4:] == [1, 1]                                    # only the new pair
    assert np.allclose(first, again) and first.shape == (3, 3)


def test_garbage_is_never_cached(tmp_path, monkeypatch):
    _fake_models(monkeypatch, lambda t: [0.0, 0.0, 0.0], [])
    cache = tmp_path / "scores.jsonl"
    with pytest.raises(RuntimeError, match="sum to 1"):
        pv.averaged_probs(pd.DataFrame({"sentence_id": ["s1"], "aspect": ["a"], "text": ["t"]}), ["m"], str(cache))
    assert cache.read_text() == ""


def test_neutral_margin_matches_the_model_card(monkeypatch):
    rows = {"clear": [0.10, 0.35, 0.55], "close": [0.05, 0.42, 0.53], "neutral": [0.20, 0.45, 0.35],
            "negative": [0.70, 0.20, 0.10]}
    _fake_models(monkeypatch, lambda t: rows[t], [])
    pairs = pd.DataFrame({"sentence_id": list(rows), "aspect": ["a"] * 4, "text": list(rows)})
    plain = pv.finetuned_labels(pairs, ["m"])
    assert plain["label"].tolist() == ["positive", "positive", "neutral", "negative"]
    m = pv.finetuned_labels(pairs, ["m"], margin=0.13)
    assert m["label"].tolist() == ["positive", "neutral", "neutral", "negative"]
    assert m["confidence"].tolist() == [0.55, 0.42, 0.45, 0.70]   # the chosen label's probability


def test_stored_pairs_beyond_sqlites_parameter_limit():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sentence_aspects (sentence_id TEXT, aspect TEXT)")
    conn.execute("CREATE TABLE aspect_sentiment (sentence_id TEXT, aspect TEXT, label TEXT, confidence REAL, "
                 "model_version TEXT)")
    ids = [f"s{i:05d}" for i in range(35000)]
    conn.executemany("INSERT INTO sentence_aspects VALUES (?, 'a')", [(i,) for i in ids])
    conn.executemany("INSERT INTO aspect_sentiment VALUES (?, 'a', 'neutral', 0.9, ?)", [(i, MODEL_VERSION) for i in ids])
    assert len(pv.stored_pairs(conn, ids)) == 35000


def test_scores_cache_is_named_by_models_and_device(tmp_path, monkeypatch):
    import train.evaluate
    d = tmp_path / "m"
    d.mkdir()
    (d / "model.safetensors").write_bytes(b"x")
    monkeypatch.setattr(train.evaluate, "best_device", lambda: "cpu")
    cpu = pv.scores_cache_path([str(d)])
    assert cpu == pv.scores_cache_path([str(d)])
    monkeypatch.setattr(train.evaluate, "best_device", lambda: "mps")
    assert pv.scores_cache_path([str(d)]) != cpu                  # GPU and CPU figures kept apart
    monkeypatch.setattr(train.evaluate, "best_device", lambda: "cpu")
    (d / "model.safetensors").write_bytes(b"retrained")
    assert pv.scores_cache_path([str(d)]) != cpu                  # new weights, new file
