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


def test_ratio_weights_move_training_mix_to_target_and_average_one():
    w = ft.ratio_weights(["neutral"] * 2 + ["positive"] * 2, {"neutral": 0.75, "positive": 0.25})
    assert w["neutral"] == pytest.approx(1.5) and w["positive"] == pytest.approx(0.5)
    assert (2 * w["neutral"] + 2 * w["positive"]) / 4 == pytest.approx(1.0)


def test_collator_pads_per_batch_and_carries_weights():
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("ProsusAI/finbert")
    df = _train_dev(2)
    enc, labels = ft._tokenize(tok, df)
    ds = ft.PairDataset(enc, labels, weights=[2.0, 0.5])
    batch = ft.WeightedCollator(tok)([ds[0], ds[1]])
    assert batch["input_ids"].shape[1] == max(len(x) for x in enc["input_ids"])   # padded to this batch only
    assert batch["sample_weight"].tolist() == [2.0, 0.5]
    assert batch["labels"].tolist() == labels


def test_weighted_loss_matches_hand_computation():
    import torch

    class Tiny(torch.nn.Module):
        def forward(self, input_ids):
            return type("Out", (), {"logits": torch.tensor([[2.0, 0.0, 0.0], [0.0, 0.0, 2.0]])})()

    trainer = ft.WeightedTrainer.__new__(ft.WeightedTrainer)          # skip Trainer setup
    trainer.class_weights = torch.tensor([1.0, 1.0, 3.0])
    inputs = {"input_ids": torch.zeros(2, 1), "labels": torch.tensor([0, 2]),
              "sample_weight": torch.tensor([1.0, 2.0])}
    loss = ft.WeightedTrainer.compute_loss(trainer, Tiny(), dict(inputs))
    ce = torch.nn.functional.cross_entropy(torch.tensor([[2.0, 0.0, 0.0], [0.0, 0.0, 2.0]]),
                                           torch.tensor([0, 2]), reduction="none")
    w = torch.tensor([1.0 * 1.0, 2.0 * 3.0])
    assert float(loss) == pytest.approx(float((ce * w).sum() / w.sum()))


def test_aspect_text_label_uses_config_labels():
    df = pd.DataFrame({"aspect": ["retail_banking_sentiment", "dividend_policy"]})
    assert ft.aspect_inputs(df, "key") == ["retail_banking_sentiment", "dividend_policy"]
    labels = ft.aspect_inputs(df, "label")
    assert labels[1] == "Dividend Policy" and "_" not in labels[0]


def test_input_spec_defaults_for_older_models(tmp_path):
    assert ft.read_input_spec(str(tmp_path)) == {"with_aspect": True, "aspect_text": "key"}
    ft.write_input_format(str(tmp_path), with_aspect=True, aspect_text="label")
    assert ft.read_input_spec(str(tmp_path))["aspect_text"] == "label"


@pytest.mark.slow
def test_weighted_training_and_ensemble_run(tmp_path, monkeypatch):
    import train.evaluate as ev

    path = tmp_path / "candidates.csv"
    _make_synthetic_candidates().to_csv(path, index=False)
    for module in (ft, ev):
        monkeypatch.setattr(module, "CANDIDATES_PATH", str(path))
    monkeypatch.setattr(ft, "corpus_shares", lambda col: {"negative": 0.1, "neutral": 0.7, "positive": 0.2}
                        if col == "label" else {"synthetic": 1.0})
    out = tmp_path / "models"
    for seed in (1, 2):
        ft.run(seed=seed, epochs=1, batch_size=8, out_dir=str(out), class_weights="prior",
               source_weights=True, aspect_text="label")
    dirs = [str(out / f"seed_{s}" / "final") for s in (1, 2)]
    assert ft.read_input_spec(dirs[0])["aspect_text"] == "label"
    assert "macro_f1" in ev.eval_ensemble(dirs, ev._load_test_set())


def test_accuracy_by_source_counts_each_source():
    import train.evaluate as ev
    acc = ev.accuracy_by_source(["neutral", "positive", "negative", "neutral"],
                                ["neutral", "neutral", "negative", "positive"],
                                ["reddit", "reddit", "earnings", "reddit"])
    assert list(acc) == ["reddit", "earnings"]                      # largest first
    assert acc["reddit"] == (1 / 3, 3) and acc["earnings"] == (1.0, 1)


def test_training_uses_the_pretrained_heads_label_order(monkeypatch):
    # ProsusAI/finbert's head is positive 0, negative 1, neutral 2. Training in
    # another order starts every output answering for the wrong class.
    import transformers

    class Cfg:
        def __init__(self, label2id):
            self.label2id = label2id
    monkeypatch.setattr(transformers.AutoConfig, "from_pretrained",
                        lambda name: Cfg({"positive": 0, "negative": 1, "neutral": 2}))
    assert ft.head_label2id() == {"positive": 0, "negative": 1, "neutral": 2}
    monkeypatch.setattr(transformers.AutoConfig, "from_pretrained",
                        lambda name: Cfg({"LABEL_0": 0, "LABEL_1": 1, "LABEL_2": 2}))
    assert ft.head_label2id() == ft.LABEL2ID          # a head with no class meaning


def test_real_finbert_head_order_is_used():
    import os
    if not os.path.isdir(os.path.expanduser("~/.cache/huggingface/hub/models--ProsusAI--finbert")):
        pytest.skip("ProsusAI/finbert not in the local cache")
    order = ft.head_label2id()
    assert order["positive"] == 0 and order["negative"] == 1 and order["neutral"] == 2
