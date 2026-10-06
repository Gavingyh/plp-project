"""
Domain-adaptive pretraining: continue FinBERT's masked-word training on the
project's own unlabelled sentences before fine-tuning.

Why: the fine-tuned model's commonest error is a neutral sentence read as
positive or negative, two thirds of them Reddit posts about retail banking
products (docs/evidence/error-analysis-2026-10-01.md). That is a vocabulary
and register gap (local product names, Reddit's style), which pretraining on
the corpus's own text addresses without labels. Slang is too rare to be the
cause (27 of 1,280 labelled train/dev rows, 6 Oct 2026).

Leakage: no labelled sentence's text enters the pretraining corpus, in any
split, and nor does any corpus sentence whose text, lower-cased with digits
and spaces collapsed, matches a labelled one (a results report repeats a
sentence each quarter with only the figures changed). The Fine-tuning lead
claim requires that no test text informs training; dropping train and dev
text too keeps the comparison clean whichever rows a seed holds out.

FinBERT (ProsusAI/finbert) is published without its masked-word head; the
head starts from bert-base-uncased's, which shares FinBERT's vocabulary. The
output is a sequence-classification checkpoint: FinBERT's own sentiment head
on the adapted encoder, so train/finetune.py --base-model fine-tunes it
exactly as it fine-tunes FinBERT.

  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m train.dapt --out models/dapt-2026-10-06
  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m train.dapt --out /tmp/x --limit 500 --epochs 1   # smoke test

Reads data/plp.db read-only; writes only under --out.
"""

import argparse
import json
import os
import re
import sqlite3
import time

import pandas as pd
import torch
from transformers import (AutoModelForSequenceClassification, AutoTokenizer, BertForMaskedLM,
                          DataCollatorForLanguageModeling, Trainer, TrainingArguments)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "plp.db")
LABELS_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
BASE_MODEL = "ProsusAI/finbert"
HEAD_MODEL = "bert-base-uncased"


def norm(text: str) -> str:
    """Lower case, digits as one mark, spaces collapsed: a repeated sentence with new figures matches."""
    return re.sub(r"\s+", " ", re.sub(r"\d+(?:[.,]\d+)*", "0", (text or "").lower())).strip()


def build_corpus(db_path: str = DB_PATH, labels_path: str = LABELS_PATH, limit: int | None = None):
    """(texts, stats): every corpus sentence except labelled ones and their near-copies."""
    labelled = pd.read_csv(labels_path)
    ids = set(labelled["sentence_id"])
    texts = {norm(t) for t in labelled["text"]}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT sentence_id, text, source FROM sentences ORDER BY sentence_id").fetchall()
    finally:
        conn.close()
    kept, by_id, by_text, by_source = [], 0, 0, {}
    for sid, text, source in rows:
        if sid in ids:
            by_id += 1
            continue
        if norm(text) in texts:
            by_text += 1
            continue
        kept.append(text)
        by_source[source] = by_source.get(source, 0) + 1
    if limit:
        kept = kept[:limit]
    stats = {"corpus_sentences": len(rows), "dropped_labelled_id": by_id,
             "dropped_matching_labelled_text": by_text, "kept": len(kept), "kept_by_source": by_source,
             "labelled_rows_excluded": len(labelled)}
    return kept, stats


class TextDataset(torch.utils.data.Dataset):
    def __init__(self, encodings):
        self.encodings = encodings

    def __len__(self):
        return len(self.encodings["input_ids"])

    def __getitem__(self, i):
        return {k: v[i] for k, v in self.encodings.items()}


def mlm_model() -> BertForMaskedLM:
    """FinBERT's encoder with bert-base-uncased's masked-word head (FinBERT ships none)."""
    model = BertForMaskedLM.from_pretrained(BASE_MODEL)
    head = BertForMaskedLM.from_pretrained(HEAD_MODEL)
    state = {k: v for k, v in head.state_dict().items() if k.startswith("cls.predictions.")
             and not k.endswith("decoder.weight")}           # the decoder is tied to FinBERT's embeddings
    missing = model.load_state_dict(state, strict=False)
    assert not missing.unexpected_keys, missing.unexpected_keys
    model.tie_weights()
    return model


def save_classifier(mlm: BertForMaskedLM, out_dir: str, tokenizer) -> str:
    """FinBERT's sentiment head on the adapted encoder, saved where finetune --base-model reads it."""
    clf = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL)
    encoder = {k[len("bert."):]: v for k, v in mlm.state_dict().items() if k.startswith("bert.")}
    result = clf.bert.load_state_dict(encoder, strict=False)
    assert not result.unexpected_keys, result.unexpected_keys
    path = os.path.join(out_dir, "classifier")
    clf.save_pretrained(path)
    tokenizer.save_pretrained(path)
    return path


def run(out_dir: str, epochs: float = 3, lr: float = 5e-5, batch_size: int = 32, max_length: int = 128,
        seed: int = 42, limit: int | None = None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    torch.manual_seed(seed)
    texts, stats = build_corpus(limit=limit)
    print(json.dumps(stats, indent=1), flush=True)
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    enc = tokenizer(texts, truncation=True, max_length=max_length, return_special_tokens_mask=True)
    data = TextDataset(enc)
    model = mlm_model()
    steps = max(1, int(len(data) / batch_size * epochs))
    args = TrainingArguments(
        output_dir=os.path.join(out_dir, "checkpoints"), num_train_epochs=epochs, learning_rate=lr,
        per_device_train_batch_size=batch_size, weight_decay=0.01, warmup_steps=int(0.06 * steps),
        logging_steps=50, save_strategy="epoch", save_total_limit=1, seed=seed, report_to=[],
        dataloader_num_workers=0,
        # Sentences are short (median 23 tokens, 6 Oct 2026); batching similar lengths
        # saves padding, which on this M1 is most of the cost.
        train_sampling_strategy="group_by_length")
    collator = DataCollatorForLanguageModeling(tokenizer, mlm_probability=0.15)
    trainer = Trainer(model=model, args=args, train_dataset=data, data_collator=collator)
    start = time.time()
    out = trainer.train()
    stats.update({"epochs": epochs, "lr": lr, "batch_size": batch_size, "max_length": max_length, "seed": seed,
                  "train_loss": out.training_loss, "seconds": round(time.time() - start),
                  "device": str(next(model.parameters()).device),
                  "loss_log": [h for h in trainer.state.log_history if "loss" in h]})
    stats["classifier_dir"] = save_classifier(trainer.model.to("cpu"), out_dir, tokenizer)
    with open(os.path.join(out_dir, "dapt_stats.json"), "w") as f:
        json.dump(stats, f, indent=1)
    return stats


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", required=True)
    p.add_argument("--epochs", type=float, default=3)
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--max-length", type=int, default=128)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit", type=int, default=None, help="use only the first N sentences (smoke test)")
    a = p.parse_args()
    s = run(a.out, a.epochs, a.lr, a.batch_size, a.max_length, a.seed, a.limit)
    print({k: v for k, v in s.items() if k != "loss_log"})
