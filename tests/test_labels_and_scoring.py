"""
Tests for train/labels.py (building a leak-free, duplicate-free labelled
file), config/device.py (CUDA before MPS before CPU) and sentiment.score's
one-inference-per-sentence scoring. No models are loaded.
"""

import pandas as pd
import pytest

import sentiment.score as score
from config import device
from train.labels import check_splits, prepare


def _row(sid, aspect, split, label):
    return {"sentence_id": sid, "aspect": aspect, "split": split, "label": label, "text": f"text {sid}"}


def _write(tmp_path, cand_rows, blind_rows):
    c, b = tmp_path / "cand.csv", tmp_path / "blind.csv"
    pd.DataFrame(cand_rows).to_csv(c, index=False)
    pd.DataFrame(blind_rows).to_csv(b, index=False)
    return str(c), str(b), str(tmp_path / "out.csv")


def test_prepare_drops_leaks_and_duplicates_and_takes_blind_test_labels(tmp_path):
    cand = [_row("s1", "dividend_policy", "train_dev", "positive"),
            _row("s1", "dividend_policy", "train_dev", "positive"),     # duplicate
            _row("s2", "wealth_business", "train_dev", "neutral"),      # leaked: s2 is also in test
            _row("s2", "wealth_business", "test", "neutral"),
            _row("s3", "asset_quality", "test", "neutral")]
    blind = [{"sentence_id": "s2", "aspect": "wealth_business", "label": "neutral"},
             {"sentence_id": "s3", "aspect": "asset_quality", "label": "negative"}]
    report = prepare(*_write(tmp_path, cand, blind))
    out = pd.read_csv(tmp_path / "out.csv")

    assert report["train_dev_rows_dropped_as_leaked"] == 1 and report["duplicate_rows_dropped"] == 1
    assert report["test_labels_changed_to_blind"] == 1
    assert sorted(zip(out.sentence_id, out.split)) == [("s1", "train_dev"), ("s2", "test"), ("s3", "test")]
    assert out.set_index("sentence_id").loc["s3", "label"] == "negative"


def test_prepare_refuses_duplicates_that_disagree(tmp_path):
    cand = [_row("s1", "dividend_policy", "train_dev", "positive"),
            _row("s1", "dividend_policy", "train_dev", "negative")]
    with pytest.raises(ValueError, match="disagree"):
        prepare(*_write(tmp_path, cand, [{"sentence_id": "x", "aspect": "y", "label": "neutral"}]))


def test_prepare_refuses_test_rows_missing_from_the_blind_sheet(tmp_path):
    cand = [_row("s3", "asset_quality", "test", "neutral")]
    with pytest.raises(KeyError):
        prepare(*_write(tmp_path, cand, [{"sentence_id": "x", "aspect": "y", "label": "neutral"}]))


@pytest.mark.parametrize("rows, message", [
    ([_row("s1", "a", "train_dev", "neutral"), _row("s1", "a", "train_dev", "neutral")], "more than once"),
    ([_row("s1", "a", "train_dev", "neutral"), _row("s1", "b", "test", "neutral")], "both train_dev and test"),
])
def test_check_splits_fails_loudly(rows, message):
    with pytest.raises(ValueError, match=message):
        check_splits(pd.DataFrame(rows))


def test_check_splits_accepts_a_clean_file():
    check_splits(pd.DataFrame([_row("s1", "a", "train_dev", "neutral"), _row("s2", "a", "test", "neutral")]))


@pytest.mark.parametrize("cuda, mps, expected", [(True, True, "cuda"), (False, True, "mps"), (False, False, "cpu")])
def test_best_device_prefers_cuda_then_mps(monkeypatch, cuda, mps, expected):
    monkeypatch.setattr(device.torch.cuda, "is_available", lambda: cuda)
    monkeypatch.setattr(device.torch.backends.mps, "is_available", lambda: mps)
    assert device.best_device() == expected


def test_score_classifies_each_sentence_once_and_fills_every_pair(temp_db, monkeypatch):
    conn = temp_db.get_connection()
    for sid, text in (("s1", "DBS raised its dividend."), ("s2", "UOB loans soured.")):
        conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, char_start, char_end, "
                     "published_at, source, url, norm_hash, processed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (sid, "d", "DBS", text, 0, len(text), "2026-01-01", "cna", "u", sid, "t"))
    for sid, aspect in (("s1", "dividend_policy"), ("s1", "income_profit_results"), ("s2", "asset_quality")):
        conn.execute("INSERT INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) "
                     "VALUES (?,?,?,?)", (sid, aspect, 0.9, "t"))
    conn.commit()
    conn.close()

    seen = []

    def fake_classify(texts):
        seen.extend(texts)
        return [("positive", 0.9) if "dividend" in t else ("negative", 0.8) for t in texts]

    monkeypatch.setattr(score, "classify_sentences", fake_classify)
    assert score.run()["newly_scored"] == 3
    assert sorted(seen) == ["DBS raised its dividend.", "UOB loans soured."]   # once each
    conn = temp_db.get_connection()
    rows = conn.execute("SELECT sentence_id, aspect, label FROM aspect_sentiment ORDER BY 1, 2").fetchall()
    conn.close()
    assert rows == [("s1", "dividend_policy", "positive"), ("s1", "income_profit_results", "positive"),
                    ("s2", "asset_quality", "negative")]


def test_classify_sentences_returns_results_in_input_order_despite_length_batching(monkeypatch):
    import torch

    class Enc(dict):
        def to(self, device):
            return self

    class Tok:
        def __call__(self, batch, **kwargs):
            # one "token" per character; the stand-in model reads the length back
            return Enc(lengths=torch.tensor([len(t) for t in batch]))

    class Model:
        def __call__(self, lengths):
            # long texts -> positive, short -> negative
            logits = torch.stack([torch.where(lengths > 5, -1.0, 1.0), torch.zeros_like(lengths, dtype=torch.float),
                                  torch.where(lengths > 5, 1.0, -1.0)], dim=-1)
            return type("Out", (), {"logits": logits})()

    monkeypatch.setattr(score, "_get_model", lambda: (Tok(), Model(), "cpu", {0: "negative", 1: "neutral", 2: "positive"}))
    monkeypatch.setattr(score, "_BATCH_SIZE", 2)
    texts = ["a long sentence", "hi", "another long one", "yo", "ok"]
    labels = [label for label, _ in score.classify_sentences(texts)]
    assert labels == ["positive", "negative", "positive", "negative", "negative"]
