"""
Fine-tune FinBERT for aspect-conditioned sentiment classification.

NOT RUNNABLE YET — requires data/labeled/candidates.csv to have its `label`
column filled in by human annotators (human-annotation-bound work
this pipeline cannot do on its own). This script is ready to run the moment
that data exists.

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
"""

import argparse
import os

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score
from sklearn.utils.class_weight import compute_class_weight
from torch.utils.data import Dataset
from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                           EarlyStoppingCallback, Trainer, TrainingArguments)

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
    df = df[df["split"] == split]
    df = df[df["label"].isin(LABELS)]  # drops unlabeled rows
    if df.empty:
        raise ValueError(
            f"No labeled rows found for split='{split}'. Labeling needs to happen "
            "before this script can run — see docs/annotation-guideline.md."
        )
    return df


def _tokenize(tokenizer, df: pd.DataFrame):
    enc = tokenizer(
        df["text"].tolist(), df["aspect"].tolist(),  # sentence-pair: [CLS] sentence [SEP] aspect [SEP]
        padding=True, truncation=True, max_length=128, return_tensors="pt",
    )
    labels = [LABEL2ID[l] for l in df["label"]]
    return enc, labels


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {
        "macro_f1": f1_score(labels, preds, average="macro"),
        "accuracy": (preds == labels).mean(),
    }


def run(seed: int = 42, epochs: int = 4, lr: float = 2e-5, batch_size: int = 16):
    torch.manual_seed(seed)
    np.random.seed(seed)

    train_dev_df = _load_labeled("train_dev")
    # Simple 85/15 split of the labeled train_dev pool for train vs. dev
    # (k-fold is the documented alternative given a small seed set — swap
    # in sklearn's StratifiedKFold here once labeling is complete and the
    # team decides which to use).
    train_dev_df = train_dev_df.sample(frac=1, random_state=seed).reset_index(drop=True)
    split_idx = int(len(train_dev_df) * 0.85)
    train_df, dev_df = train_dev_df[:split_idx], train_dev_df[split_idx:]

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    train_enc, train_labels = _tokenize(tokenizer, train_df)
    dev_enc, dev_labels = _tokenize(tokenizer, dev_df)

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
        output_dir=os.path.join(MODEL_OUT_DIR, f"seed_{seed}"),
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

    final_dir = os.path.join(MODEL_OUT_DIR, f"seed_{seed}", "final")
    trainer.save_model(final_dir)
    tokenizer.save_pretrained(final_dir)
    print(f"Model saved to {final_dir}")
    return trainer.evaluate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    metrics = run(seed=args.seed, epochs=args.epochs, lr=args.lr, batch_size=args.batch_size)
    print(metrics)
