"""
Tests for train/finetune.py's experiment options: sentence-only input,
the input-format marker evaluation reads, and K-fold splits of train_dev.
The last test trains on synthetic data (like test_finetune_smoke.py).
"""

import pandas as pd
import pytest

import train.finetune as ft
from tests.test_finetune_smoke import _make_synthetic_candidates


def _train_dev(n=50):
    labels = ["negative", "neutral", "positive"]
    return pd.DataFrame({"sentence_id": [f"s{i}" for i in range(n)],
                         "text": [f"text {i}" for i in range(n)],
                         "aspect": ["dividend_policy"] * n,
                         "label": [labels[i % 3] for i in range(n)],
                         "split": ["train_dev"] * n})


def test_folds_partition_train_dev_exactly():
    df = _train_dev()
    seen_dev = []
    for fold in range(5):
        train, dev = ft.fold_split(df, 5, fold, seed=42)
        assert not set(train.sentence_id) & set(dev.sentence_id)
        assert len(train) + len(dev) == len(df)
        seen_dev.extend(dev.sentence_id)
    assert sorted(seen_dev) == sorted(df.sentence_id)          # every row is dev exactly once


def test_folds_are_stratified_and_seeded():
    df = _train_dev(60)
    _, dev = ft.fold_split(df, 5, 0, seed=42)
    assert dev.label.value_counts().to_dict() == {"negative": 4, "neutral": 4, "positive": 4}
    assert list(ft.fold_split(df, 5, 0, seed=42)[1].sentence_id) == list(dev.sentence_id)


def test_fold_out_of_range_is_refused():
    with pytest.raises(ValueError):
        ft.fold_split(_train_dev(), 5, 5, seed=42)


def test_tokenize_with_and_without_aspect():
    calls = []

    def tok(*segments, **kwargs):
        calls.append(len(segments))
        return {}

    df = _train_dev(3)
    ft._tokenize(tok, df, with_aspect=True)
    ft._tokenize(tok, df, with_aspect=False)
    assert calls == [2, 1]


def test_input_format_marker_round_trips(tmp_path):
    assert ft.read_input_format(str(tmp_path)) is True             # older models: pairs
    ft.write_input_format(str(tmp_path), with_aspect=False)
    assert ft.read_input_format(str(tmp_path)) is False


@pytest.mark.slow
def test_no_aspect_model_and_fold_run(tmp_path, monkeypatch):
    import train.evaluate as ev

    path = tmp_path / "candidates.csv"
    _make_synthetic_candidates().to_csv(path, index=False)
    for module in (ft, ev):
        monkeypatch.setattr(module, "CANDIDATES_PATH", str(path))

    out = tmp_path / "models"
    ft.run(seed=1, epochs=1, batch_size=8, with_aspect=False, out_dir=str(out))
    final = out / "seed_1" / "final"
    assert ft.read_input_format(str(final)) is False
    ev.eval_finetuned(str(final), ev._load_test_set())               # tokenizes single-segment

    metrics = ft.run(seed=1, epochs=1, batch_size=8, out_dir=str(out), folds=3, fold=0)
    assert "eval_macro_f1" in metrics
    assert not (out / "seed_1_fold0of3").exists()                    # fold models are not kept
