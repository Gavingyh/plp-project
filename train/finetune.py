"""
Fine-tune FinBERT for aspect-conditioned sentiment classification.

Reads data/labeled/candidates.csv, built from the resolved annotation
sheets by train/labels.py, and refuses to train if the file has duplicate
pairs or a sentence in both splits (see check_splits there).

Sentence-pair (NLI-style) input formulation:
  [CLS] {sentence} [SEP] {aspect} [SEP]  ->  3-way softmax
One model for all aspects (aspect supplied as context), NOT a model-per-aspect
- splitting ~1,000 examples across 6-10 aspects would leave ~100 each, too
few to fine-tune anything.

Training config: LR 2e-5, batch 16, max_len 128, warmup 10%, early stopping
on dev macro-F1, fixed seed (report mean +/- std across >=3 seeds - a single
run's F1 can be seed noise at this data size). Each batch is padded to its own
longest sentence.

Loss weighting (--class-weights): `none` (the default) is plain cross-entropy.
Every model trained before 2026-10-01 was trained this way: class weights were
computed and printed but never reached the loss, although this docstring said
"class-weighted loss". `balanced` applies sklearn's balanced weights; `prior`
reweights classes from the training mix towards the corpus mix (base FinBERT's
per-sentence labels), because the train/dev rows were drawn to over-represent
polarity. --source-weights does the same for the source mix.

USAGE:
  python -m train.finetune --seed 42
  python -m train.finetune --seed 42 --no-aspect          # sentence only, to test the aspect input
  python -m train.finetune --seed 42 --folds 5 --fold 0   # cross-validation fold, dev score only
  python -m train.finetune --seed 42 --out-dir models/experiments
  python -m train.finetune --seed 42 --class-weights prior --source-weights --aspect-text label
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
                          DataCollatorWithPadding, EarlyStoppingCallback, Trainer,
                          TrainingArguments)

from train.labels import check_splits

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
MODEL_OUT_DIR = os.path.join(BASE_DIR, "models", "finbert-absa")
BASE_MODEL = "ProsusAI/finbert"
LABELS = ["negative", "neutral", "positive"]
LABEL2ID = {l: i for i, l in enumerate(LABELS)}


def head_label2id(model_name: str = None) -> dict[str, int]:
    """The label ids to train with: the pretrained head's own order when it
    names the three sentiment classes (ProsusAI/finbert: positive 0,
    negative 1, neutral 2), else LABEL2ID for a head with no class meaning.

    Fine-tuning keeps the pretrained head, whose shape matches. Training with
    a different order, as every model up to 3 Oct 2026 did, starts each
    output answering for the wrong class, which the model must then unlearn."""
    from transformers import AutoConfig
    cfg = AutoConfig.from_pretrained(model_name or BASE_MODEL)
    order = {str(k).lower(): int(v) for k, v in (cfg.label2id or {}).items()}
    return order if set(order) == set(LABELS) else dict(LABEL2ID)




class PairDataset(Dataset):
    """Unpadded encodings; the collator pads each batch. Optional per-row
    weights travel with the row as `sample_weight`."""

    def __init__(self, encodings, labels, weights=None):
        self.encodings = encodings
        self.labels = labels
        self.weights = weights

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = int(self.labels[idx])
        if self.weights is not None:
            item["sample_weight"] = float(self.weights[idx])
        return item


class WeightedCollator:
    """Pads with DataCollatorWithPadding, carrying sample_weight alongside."""

    def __init__(self, tokenizer):
        self._pad = DataCollatorWithPadding(tokenizer)

    def __call__(self, features):
        weights = [f.pop("sample_weight", 1.0) for f in features]
        batch = self._pad(features)
        batch["sample_weight"] = torch.tensor(weights, dtype=torch.float)
        return batch


class WeightedTrainer(Trainer):
    """Cross-entropy weighted per class and per row, normalised by the total
    weight so the loss scale doesn't depend on the weighting."""

    def __init__(self, *args, class_weights=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = None if class_weights is None else torch.tensor(class_weights, dtype=torch.float)

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        labels = inputs.pop("labels")
        row_w = inputs.pop("sample_weight", None)
        outputs = model(**inputs)
        logits = outputs.logits
        per_row = torch.nn.functional.cross_entropy(logits, labels, reduction="none")
        w = torch.ones_like(per_row) if row_w is None else row_w.to(per_row.device)
        if self.class_weights is not None:
            w = w * self.class_weights.to(per_row.device)[labels]
        loss = (per_row * w).sum() / w.sum()
        return (loss, outputs) if return_outputs else loss


def aspect_labels() -> dict[str, str]:
    """Aspect key -> readable label from config/aspects.yaml."""
    from config import aspect_taxonomy
    return aspect_taxonomy.labels()


def corpus_shares(column: str) -> dict[str, float]:
    """Corpus share of each label (base FinBERT, one per sentence) or source,
    read from the database (read-only)."""
    from ingest.db import get_connection
    conn = get_connection()
    try:
        if column == "label":
            rows = conn.execute("SELECT label, COUNT(*) FROM (SELECT sentence_id, MIN(label) AS label "
                                "FROM aspect_sentiment GROUP BY sentence_id) GROUP BY label").fetchall()
        elif column == "source":
            rows = conn.execute("SELECT source, COUNT(*) FROM sentences GROUP BY source").fetchall()
        else:
            raise ValueError(column)
    finally:
        conn.close()
    total = sum(n for _, n in rows) or 1
    return {k: n / total for k, n in rows}


def ratio_weights(train_values: list[str], target_share: dict[str, float]) -> dict[str, float]:
    """Per-value weight = target share / training share, normalised so the
    training rows' mean weight is 1. Values absent from the target get 1."""
    counts = pd.Series(train_values).value_counts(normalize=True).to_dict()
    raw = {v: (target_share.get(v, counts[v]) / counts[v]) for v in counts}
    mean = sum(raw[v] * counts[v] for v in counts)
    return {v: w / mean for v, w in raw.items()}


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
            "before this script can run - see docs/annotation-guideline.md."
        )
    return df


INPUT_FORMAT_FILE = "input_format.json"
DEV_IDS_FILE = "dev_ids.json"


def write_input_format(model_dir: str, with_aspect: bool, aspect_text: str = "key") -> None:
    """Record how the model was fed, so evaluation tokenizes the same way."""
    with open(os.path.join(model_dir, INPUT_FORMAT_FILE), "w") as f:
        json.dump({"with_aspect": with_aspect, "aspect_text": aspect_text}, f)


def read_input_spec(model_dir: str) -> dict:
    """{"with_aspect": bool, "aspect_text": "key" | "label"}. Models saved
    before the marker existed were all trained on (sentence, aspect key) pairs."""
    path = os.path.join(model_dir, INPUT_FORMAT_FILE)
    spec = {"with_aspect": True, "aspect_text": "key"}
    if os.path.exists(path):
        with open(path) as f:
            spec.update(json.load(f))
    return spec


def read_input_format(model_dir: str) -> bool:
    """True when the model takes (sentence, aspect) pairs."""
    return bool(read_input_spec(model_dir)["with_aspect"])


def aspect_inputs(df: pd.DataFrame, aspect_text: str = "key") -> list[str]:
    if aspect_text == "label":
        labels = aspect_labels()
        return [labels.get(a, a) for a in df["aspect"]]
    return df["aspect"].tolist()


def _tokenize(tokenizer, df: pd.DataFrame, with_aspect: bool = True, aspect_text: str = "key",
              label2id: dict[str, int] | None = None):
    """Unpadded encodings (the collator pads per batch), with labels as ids in
    `label2id`'s order (LABEL2ID if not given)."""
    texts = df["text"].tolist()
    if with_aspect:   # sentence-pair: [CLS] sentence [SEP] aspect [SEP]
        enc = tokenizer(texts, aspect_inputs(df, aspect_text), truncation=True, max_length=128)
    else:             # sentence alone: [CLS] sentence [SEP]
        enc = tokenizer(texts, truncation=True, max_length=128)
    labels = [(label2id or LABEL2ID)[l] for l in df["label"]]
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
        folds: int | None = None, fold: int | None = None,
        class_weights: str = "none", source_weights: bool = False, aspect_text: str = "key"):
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
    label2id = head_label2id()
    id2label = {i: l for l, i in label2id.items()}
    train_enc, train_labels = _tokenize(tokenizer, train_df, with_aspect, aspect_text, label2id)
    dev_enc, dev_labels = _tokenize(tokenizer, dev_df, with_aspect, aspect_text, label2id)

    if class_weights == "balanced":
        cw = compute_class_weight("balanced", classes=np.arange(len(LABELS)), y=train_labels).tolist()
    elif class_weights == "prior":
        by_label = ratio_weights(train_df["label"].tolist(), corpus_shares("label"))
        cw = [by_label.get(id2label[i], 1.0) for i in range(len(LABELS))]   # in the head's order
    elif class_weights == "none":
        cw = None
    else:
        raise ValueError(f"class_weights must be none, balanced or prior, got {class_weights!r}")
    row_weights = None
    if source_weights:
        by_source = ratio_weights(train_df["source"].tolist(), corpus_shares("source"))
        row_weights = [by_source[s] for s in train_df["source"]]
    print(f"Class weights ({'/'.join(id2label[i][:3] for i in range(len(LABELS)))}): "
          f"{cw if cw is not None else 'none'}; "
          f"source weights: {'on' if source_weights else 'off'}; aspect text: {aspect_text}")

    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=len(LABELS), id2label=id2label, label2id=label2id,
    )

    # transformers 5.x has no warmup_ratio in TrainingArguments, so compute the
    # step count for a 10% warmup here.
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
        # Keep sample_weight in the batch: WeightedTrainer.compute_loss removes
        # it before the model sees the inputs.
        remove_unused_columns=False,
    )

    trainer = WeightedTrainer(
        model=model,
        args=training_args,
        train_dataset=PairDataset(train_enc, train_labels, row_weights),
        eval_dataset=PairDataset(dev_enc, dev_labels),
        data_collator=WeightedCollator(tokenizer),
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
        class_weights=cw,
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
    write_input_format(final_dir, with_aspect, aspect_text)
    # The exact dev rows, so a later step that tunes on dev (the neutral margin
    # in train/error_analysis.py) uses these rows, not a reshuffle of a file
    # that may have grown since.
    with open(os.path.join(final_dir, DEV_IDS_FILE), "w") as f:
        json.dump(dev_df[["sentence_id", "aspect"]].values.tolist(), f)
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
    parser.add_argument("--class-weights", choices=["none", "balanced", "prior"], default="none")
    parser.add_argument("--source-weights", action="store_true",
                        help="weight rows so the source mix matches the corpus")
    parser.add_argument("--aspect-text", choices=["key", "label"], default="key",
                        help="feed the aspect key or its readable label")
    args = parser.parse_args()
    if (args.folds is None) != (args.fold is None):
        parser.error("--folds and --fold go together")
    metrics = run(seed=args.seed, epochs=args.epochs, lr=args.lr, batch_size=args.batch_size,
                  with_aspect=not args.no_aspect, out_dir=args.out_dir,
                  folds=args.folds, fold=args.fold, class_weights=args.class_weights,
                  source_weights=args.source_weights, aspect_text=args.aspect_text)
    print(metrics)
