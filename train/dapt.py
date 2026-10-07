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
split or sheet (by default every labelling file under data/labeled), and nor
does any corpus sentence that copies one closely: the same text once figures,
case and spacing are ignored, a sentence holding a labelled one or held in
one (letters only, from 30 letters: a test sentence split in two by another
machine's extraction), or one sharing 60% or more of its words with one. The
Fine-tuning lead claim requires that no test text informs training; leaving
out train and dev text too keeps the comparison clean whichever rows a seed
holds out. (Until 7 Oct 2026 only the id and the exact text were checked; a
validation found 151 test-related sentences in the 6 Oct run's text.)

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
                          DataCollatorForLanguageModeling, Trainer, TrainerCallback, TrainingArguments)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "plp.db")
LABELS_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
BASE_MODEL = "ProsusAI/finbert"
HEAD_MODEL = "bert-base-uncased"


def norm(text: str) -> str:
    """Lower case, digits as one mark, spaces collapsed: a repeated sentence with new figures matches."""
    return re.sub(r"\s+", " ", re.sub(r"\d+(?:[.,]\d+)*", "0", (text or "").lower())).strip()


_WORD = re.compile(r"[a-z0]+")
NEAR = 0.6          # word-set Jaccard, all words: the broker research round's threshold against test rows
HELD = 30           # letters: a sentence holding a labelled one, or held in one, from this length


def letters(text: str) -> str:
    """Letters and the digit mark only: a sentence extracted with a stray bullet, a sidebar
    line or other spacing on another machine still matches."""
    return re.sub(r"[^a-z0]", "", norm(text))


def labelled_files(root: str = os.path.join(BASE_DIR, "data", "labeled")) -> list[str]:
    """Every CSV under data/labeled with sentence ids and text: every round, split and sheet,
    labelled or still to be labelled. The default for what pretraining leaves out, so a
    labels file can't be forgotten (7 Oct 2026: --db with the default labels kept the
    broker research test rows)."""
    out = []
    for dirpath, _, names in os.walk(root):
        for name in sorted(names):
            if name.endswith(".csv"):
                path = os.path.join(dirpath, name)
                try:
                    cols = pd.read_csv(path, nrows=0).columns
                except Exception:
                    continue
                if {"sentence_id", "text"} <= set(cols):
                    out.append(path)
    return sorted(out)


class NearCopies:
    """Labelled sentences a corpus sentence copies closely: it shares NEAR of their words or
    more (Jaccard on all words, computed exactly with sparse matrices), or it holds a
    labelled sentence, or is held in one, letters only, from HELD letters. The second
    catches a test sentence split in two by another machine's extraction, and one quoted
    inside a longer headline (validation, 7 Oct 2026: both reached pretraining)."""

    def __init__(self, labelled_texts):
        from sklearn.feature_extraction.text import CountVectorizer
        self.labelled_letters = sorted({l for l in (letters(t) for t in labelled_texts) if len(l) >= HELD})
        self.vectorizer = CountVectorizer(token_pattern=r"[a-z0]+", binary=True, preprocessor=norm)
        self.labelled = self.vectorizer.fit_transform(list(labelled_texts))
        self.labelled_sizes = self.labelled.sum(axis=1).A1

    def held(self, text: str) -> bool:
        t = letters(text)
        if len(t) < HELD:
            return False
        return any(l in t or t in l for l in self.labelled_letters)

    def overlapping(self, texts: list[str], batch: int = 4000) -> list[bool]:
        """Whether each text shares NEAR of its words with some labelled sentence."""
        import numpy as np
        out = []
        for i in range(0, len(texts), batch):
            m = self.vectorizer.transform(texts[i:i + batch])
            sizes = m.sum(axis=1).A1
            inter = (m @ self.labelled.T).tocoo()
            best = np.zeros(m.shape[0])
            union = sizes[inter.row] + self.labelled_sizes[inter.col] - inter.data
            jac = np.where(union > 0, inter.data / np.maximum(union, 1), 0)
            np.maximum.at(best, inter.row, jac)
            out.extend((best >= NEAR) & (sizes >= 3))
        return out

    def near(self, text: str) -> bool:
        return self.held(text) or self.overlapping([text])[0]


def build_corpus(db_path: str = DB_PATH, labels_path: str | list[str] | None = None, limit: int | None = None):
    """(texts, stats): every corpus sentence except labelled ones and their near-copies.
    labels_path defaults to every labelling file (labelled_files)."""
    paths = labelled_files() if labels_path is None else (
        [labels_path] if isinstance(labels_path, str) else list(labels_path))
    labelled = pd.concat([pd.read_csv(p) for p in paths]).drop_duplicates("sentence_id")
    ids = set(labelled["sentence_id"])
    texts = {norm(t) for t in labelled["text"]}
    near = NearCopies(labelled["text"].tolist())
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT sentence_id, text, source FROM sentences ORDER BY sentence_id").fetchall()
    finally:
        conn.close()
    by_id = by_text = by_held = by_overlap = 0
    left = []
    for sid, text, source in rows:
        if sid in ids:
            by_id += 1
        elif norm(text) in texts:
            by_text += 1
        elif near.held(text):
            by_held += 1
        else:
            left.append((text, source))
    overlapping = near.overlapping([t for t, _ in left])
    kept, by_source = [], {}
    for (text, source), over in zip(left, overlapping):
        if over:
            by_overlap += 1
            continue
        kept.append(text)
        by_source[source] = by_source.get(source, 0) + 1
    if limit:
        kept = kept[:limit]
    stats = {"corpus_sentences": len(rows), "dropped_labelled_id": by_id,
             "dropped_matching_labelled_text": by_text, "dropped_holding_or_held_in_labelled_text": by_held,
             "dropped_sharing_most_words_with_labelled_text": by_overlap,
             "kept": len(kept), "kept_by_source": by_source, "labels_files": paths,
             "labelled_rows_excluded": len(labelled)}
    return kept, stats


class ReleaseMemory(TrainerCallback):
    """Every 50 steps, give the Mac GPU's cached memory back and log how much is held.

    On 6 Oct 2026 the first full run slowed from about 1 s a step to 100 s
    after 200 steps, with swap nearly full: on MPS each new batch shape keeps
    its own cached buffers. Batches are padded to a multiple of 32 tokens (two
    shapes up to the 64-token cap) and the cache is emptied here."""

    def on_step_end(self, args, state, control, **kwargs):
        if state.global_step % 50 == 0 and torch.backends.mps.is_available():
            torch.mps.empty_cache()
            print(f"step {state.global_step}: mps allocated {torch.mps.current_allocated_memory() / 2**30:.2f} GB, "
                  f"driver {torch.mps.driver_allocated_memory() / 2**30:.2f} GB", flush=True)


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


def run(out_dir: str, epochs: float = 3, lr: float = 5e-5, batch_size: int = 32, max_length: int = 64,
        seed: int = 42, limit: int | None = None, db_path: str = DB_PATH,
        labels: str | list[str] | None = None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    torch.manual_seed(seed)
    texts, stats = build_corpus(db_path, labels, limit=limit)
    print(json.dumps(stats, indent=1), flush=True)
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    enc = tokenizer(texts, truncation=True, max_length=max_length, return_special_tokens_mask=True)
    data = TextDataset(enc)
    model = mlm_model()
    # Two half-batches a step: on a 16 GB M1 a 32-sentence batch held 7 GB, mostly the scores
    # for every vocabulary word at every position (6 Oct 2026); the step is the same.
    accumulate = 2 if batch_size >= 2 else 1
    steps = max(1, int(len(data) / batch_size * epochs))
    args = TrainingArguments(
        output_dir=os.path.join(out_dir, "checkpoints"), num_train_epochs=epochs, learning_rate=lr,
        per_device_train_batch_size=batch_size // accumulate, gradient_accumulation_steps=accumulate,
        weight_decay=0.01, warmup_steps=int(0.06 * steps),
        logging_steps=50, save_strategy="epoch", save_total_limit=1, seed=seed, report_to=[],
        dataloader_num_workers=0,
        # Sentences are short (median 23 tokens, 6 Oct 2026); batching similar lengths
        # saves padding, which on this M1 is most of the cost.
        train_sampling_strategy="group_by_length")
    collator = DataCollatorForLanguageModeling(tokenizer, mlm_probability=0.15, pad_to_multiple_of=32)
    trainer = Trainer(model=model, args=args, train_dataset=data, data_collator=collator,
                      callbacks=[ReleaseMemory()])
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
    p.add_argument("--max-length", type=int, default=64)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit", type=int, default=None, help="use only the first N sentences (smoke test)")
    p.add_argument("--db", default=DB_PATH, help="the database whose sentences to read (read-only)")
    p.add_argument("--labels", nargs="+", default=None,
                   help="labelled files whose sentences are left out (all splits); default every "
                        "labelling file under data/labeled")
    a = p.parse_args()
    s = run(a.out, a.epochs, a.lr, a.batch_size, a.max_length, a.seed, a.limit, a.db, a.labels)
    print({k: v for k, v in s.items() if k != "loss_log"})
