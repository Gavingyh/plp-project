"""Tests for train/error_analysis.py: the neutral margin and the dev split."""

import numpy as np
import pandas as pd
import pytest

import train.error_analysis as ea


def test_margin_zero_is_argmax_and_a_large_margin_is_all_neutral():
    probs = np.array([[0.6, 0.3, 0.1], [0.1, 0.5, 0.4], [0.05, 0.4, 0.55]])
    assert ea.apply_margin(probs, 0.0) == ["negative", "neutral", "positive"]
    assert ea.apply_margin(probs, 0.2) == ["negative", "neutral", "neutral"]   # 0.55 - 0.40 is not > 0.2
    assert ea.apply_margin(probs, 1.0) == ["neutral"] * 3


def test_best_margin_prefers_the_smaller_margin_on_a_tie():
    probs = np.array([[0.7, 0.2, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8]])
    margin, f1 = ea.best_margin(probs, ["negative", "neutral", "positive"])
    assert margin == 0.0 and f1 == 1.0


def test_dev_split_is_the_last_15_percent_of_the_seed_shuffle(monkeypatch):
    monkeypatch.setattr(ea, "TRAIN_DEV_ROWS_AT_TRAINING", 100)    # the size this model "was trained on"
    df = pd.DataFrame({"sentence_id": [f"s{i}" for i in range(100)], "label": ["neutral"] * 100})
    dev = ea.dev_split(df, seed=42)
    shuffled = df.sample(frac=1, random_state=42).reset_index(drop=True)      # as train/finetune.py does
    assert dev["sentence_id"].tolist() == shuffled["sentence_id"].tolist()[85:]


def _td(n):
    return pd.DataFrame({"sentence_id": [f"s{i}" for i in range(n)], "aspect": ["a"] * n,
                         "text": ["t"] * n, "label": ["neutral"] * n})


def test_dev_split_reads_the_saved_dev_rows(tmp_path):
    import json
    from train.error_analysis import dev_split
    (tmp_path / "dev_ids.json").write_text(json.dumps([["s3", "a"], ["s1", "a"]]))
    dev = dev_split(_td(1200), seed=42, model_dir=str(tmp_path))
    assert dev["sentence_id"].tolist() == ["s3", "s1"]


def test_dev_split_refuses_a_reshuffle_once_train_dev_has_grown(tmp_path):
    from train.error_analysis import TRAIN_DEV_ROWS_AT_TRAINING, dev_split
    assert len(dev_split(_td(TRAIN_DEV_ROWS_AT_TRAINING), seed=42)) == 147
    with pytest.raises(ValueError, match="retrain"):
        dev_split(_td(TRAIN_DEV_ROWS_AT_TRAINING + 268), seed=42, model_dir=str(tmp_path))
