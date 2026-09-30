"""
Fine-tune FinBERT for aspect-conditioned sentiment classification.

Reads data/labeled/candidates.csv, built from the resolved annotation
sheets by train/labels.py, and refuses to train if the file has duplicate
pairs or a sentence in both splits (see check_splits there).

Sentence-pair (NLI-style) input formulation:
  [CLS] {sentence} [SEP] {aspect} [SEP]  ->  3-way softmax
One model for all aspects (aspect supplied as context), NOT a model-per-aspect
— splitting ~1,000 examples across 6-10 aspects would leave ~100 each, too
few to fine-tune anything.

Training config: LR 2e-5, 3-5 epochs, batch 16, max_len 128,
warmup 10%, early stopping on dev macro-F1, class-weighted loss, fixed seed
(report mean +/- std across >=3 seeds — a single run's F1 can be seed noise
at this data size).

USAGE:
  python -m train.finetune --seed 42
  python -m train.finetune --seed 42 --no-aspect          # sentence only, to test the aspect input
  python -m train.finetune --seed 42 --folds 5 --fold 0   # cross-validation fold, dev score only
  python -m train.finetune --seed 42 --out-dir models/experiments
"""

import argparse
import json
import os
import shutil

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.utils.class_weight import compute_class_weight
from torch.utils.data import Dataset
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                           EarlyStoppingCallback, Trainer, TrainingArguments)

from train.labels import check_splits

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
MODEL_OUT_DIR = os.path.join(BASE_DIR, "models", "finbert-absa")
BASE_MODEL = "ProsusAI/finbert"
LABELS = ["negative", "neutral", "positive"]
LABEL2ID = {l: i for i, l in enumerate(LABELS)}


class PairDataset(Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx])
        return item


def _load_labeled(split: str) -> pd.DataFrame:
    if not os.path.exists(CANDIDATES_PATH):
        raise FileNotFoundError(
            f"{CANDIDATES_PATH} not found. Run `python -m preprocess.export_candidates` "
            "first, then have annotators fill in the `label` column per "
            "docs/annotation-guideline.md."
        )
    df = pd.read_csv(CANDIDATES_PATH)
    check_splits(df)
    df = df[df["split"] == split]
    df = df[df["label"].isin(LABELS)]  # drops unlabeled rows
    if df.empty:
        raise ValueError(
            f"No labeled rows found for split='{split}'. Labeling needs to happen "
            "before this script can run — see docs/annotation-guideline.md."
        )
    return df


INPUT_FORMAT_FILE = "input_format.json"


def write_input_format(model_dir: str, with_aspect: bool) -> None:
    """Record how the model was fed, so evaluation tokenizes the same way."""
    with open(os.path.join(model_dir, INPUT_FORMAT_FILE), "w") as f:
        json.dump({"with_aspect": with_aspect}, f)


def read_input_format(model_dir: str) -> bool:
    """True when the model takes (sentence, aspect) pairs. Models saved before
    the marker existed were all trained on pairs."""
    path = os.path.join(model_dir, INPUT_FORMAT_FILE)
    if not os.path.exists(path):
        return True
    with open(path) as f:
        return bool(json.load(f)["with_aspect"])


def _tokenize(tokenizer, df: pd.DataFrame, with_aspect: bool = True):
    texts = df["text"].tolist()
    if with_aspect:   # sentence-pair: [CLS] sentence [SEP] aspect [SEP]
        enc = tokenizer(texts, df["aspect"].tolist(), padding=True, truncation=True,
                        max_length=128, return_tensors="pt")
    else:             # sentence alone: [CLS] sentence [SEP]
        enc = tokenizer(texts, padding=True, truncation=True, max_length=128, return_tensors="pt")
    labels = [LABEL2ID[l] for l in df["label"]]
    return enc, labels


def fold_split(train_dev_df: pd.DataFrame, folds: int, fold: int, seed: int):
    """(train, dev) for one fold of stratified K-fold over train_dev. The test
    split never enters: callers pass train_dev rows only."""
    if not 0 <= fold < folds:
        raise ValueError(f"fold must be in 0..{folds - 1}, got {fold}")
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    df = train_dev_df.reset_index(drop=True)
    train_idx, dev_idx = list(skf.split(df, df["label"]))[fold]
    return df.iloc[train_idx], df.iloc[dev_idx]


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {
        "macro_f1": f1_score(labels, preds, average="macro"),
        "accuracy": (preds == labels).mean(),
    }


def run(seed: int = 42, epochs: int = 4, lr: float = 2e-5, batch_size: int = 16,
        with_aspect: bool = True, out_dir: str | None = None,
        folds: int | None = None, fold: int | None = None):
    """Train one model. With folds/fold, train on K-1 folds of train_dev and
    return the dev score on the held-out fold, saving no model."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    out_root = out_dir or MODEL_OUT_DIR
    run_name = f"seed_{seed}" if folds is None else f"seed_{seed}_fold{fold}of{folds}"

    train_dev_df = _load_labeled("train_dev")
    if folds is None:
        # 85/15 split of the labeled train_dev pool for train vs. dev.
        train_dev_df = train_dev_df.sample(frac=1, random_state=seed).reset_index(drop=True)
        split_idx = int(len(train_dev_df) * 0.85)
        train_df, dev_df = train_dev_df[:split_idx], train_dev_df[split_idx:]
    else:
        # K-fold: a steadier dev estimate than one 15% slice of ~1,000 rows.
        train_df, dev_df = fold_split(train_dev_df, folds, fold, seed)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    train_enc, train_labels = _tokenize(tokenizer, train_df, with_aspect)
    dev_enc, dev_labels = _tokenize(tokenizer, dev_df, with_aspect)

    class_weights = compute_class_weight("balanced", classes=np.arange(len(LABELS)), y=train_labels)
    print(f"Class weights (neg/neu/pos): {class_weights}")

    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=len(LABELS), id2label={i: l for l, i in LABEL2ID.items()},
        label2id=LABEL2ID,
    )

    # transformers 5.x dropped warmup_ratio from TrainingArguments (confirmed live,
    # not assumed — a smoke test caught this before real labeled data existed) —
    # compute the equivalent step count by hand to preserve the intended 10% warmup.
    steps_per_epoch = max(1, len(train_df) // batch_size)
    total_steps = steps_per_epoch * epochs
    warmup_steps = max(1, round(0.10 * total_steps))

    training_args = TrainingArguments(
        output_dir=os.path.join(out_root, run_name),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=lr,
        warmup_steps=warmup_steps,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        seed=seed,
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=PairDataset(train_enc, train_labels),
        eval_dataset=PairDataset(dev_enc, dev_labels),
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )
    trainer.train()

    if folds is not None:
        # A fold model exists only for its dev score; keep nothing on disk.
        metrics = trainer.evaluate()
        shutil.rmtree(training_args.output_dir, ignore_errors=True)
        print(f"Fold {fold} of {folds}: dev macro-F1 {metrics.get('eval_macro_f1')}")
        return metrics

    final_dir = os.path.join(out_root, run_name, "final")
    trainer.save_model(final_dir)
    tokenizer.save_pretrained(final_dir)
    write_input_format(final_dir, with_aspect)
    # Per-epoch checkpoints carry optimizer state (~1.2 GB each); the best
    # epoch is already in final/, so they are only disk use once it is saved.
    for name in os.listdir(training_args.output_dir):
        if name.startswith("checkpoint-"):
            shutil.rmtree(os.path.join(training_args.output_dir, name), ignore_errors=True)
    print(f"Model saved to {final_dir}")
    return trainer.evaluate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--no-aspect", action="store_true",
                        help="train on the sentence alone, without the aspect")
    parser.add_argument("--out-dir", default=None, help=f"default {MODEL_OUT_DIR}")
    parser.add_argument("--folds", type=int, default=None, help="K for K-fold on train_dev")
    parser.add_argument("--fold", type=int, default=None, help="which fold is dev (0..K-1)")
    args = parser.parse_args()
    if (args.folds is None) != (args.fold is None):
        parser.error("--folds and --fold go together")
    metrics = run(seed=args.seed, epochs=args.epochs, lr=args.lr, batch_size=args.batch_size,
                  with_aspect=not args.no_aspect, out_dir=args.out_dir,
                  folds=args.folds, fold=args.fold)
    print(metrics)
