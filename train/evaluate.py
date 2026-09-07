"""
Evaluation: fine-tuned model vs. required baselines on the FROZEN
random test set (data/labeled/candidates.csv, split='test').

Baselines are required, not optional: the claim
"fine-tuning helped" is unsupported without comparing against base FinBERT
zero-shot, a lexicon method, and a classical ML method. This script runs all
of them on the same frozen test set so the comparison is apples-to-apples.

NOT RUNNABLE YET — same blocker as train/finetune.py: needs labeled test
data, and for the fine-tuned-model comparison, needs a model already trained
by train/finetune.py.

USAGE:
  python -m train.evaluate --model-dir models/finbert-absa/seed_42/final
"""

import argparse
import os

import numpy as np
import pandas as pd
import torch
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from transformers import AutoModelForSequenceClassification, AutoTokenizer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
LABELS = ["negative", "neutral", "positive"]


def _load_test_set() -> pd.DataFrame:
    df = pd.read_csv(CANDIDATES_PATH)
    df = df[(df["split"] == "test") & (df["label"].isin(LABELS))]
    if df.empty:
        raise ValueError("No labeled test rows found — Labeling must be complete first.")
    return df


def eval_base_finbert_zeroshot(df: pd.DataFrame) -> dict:
    """Baseline 1: base FinBERT, zero-shot, whole-sentence (not aspect-conditioned
    — base FinBERT has no mechanism to condition on the aspect at all, which is
    itself part of the case for fine-tuning)."""
    from sentiment.score import classify_sentences
    preds = [label for label, _ in classify_sentences(df["text"].tolist())]
    return _report("base_finbert_zeroshot", df["label"].tolist(), preds)


def eval_lexicon(df: pd.DataFrame) -> dict:
    """Baseline 2: VADER, the rule-based floor."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except ImportError:
        print("vaderSentiment not installed (pip install vaderSentiment) — skipping lexicon baseline.")
        return {}
    analyzer = SentimentIntensityAnalyzer()
    preds = []
    for text in df["text"]:
        compound = analyzer.polarity_scores(text)["compound"]
        preds.append("positive" if compound > 0.05 else "negative" if compound < -0.05 else "neutral")
    return _report("vader_lexicon", df["label"].tolist(), preds)


def eval_tfidf_logreg(train_dev_df: pd.DataFrame, test_df: pd.DataFrame) -> dict:
    """Baseline 3: TF-IDF + logistic regression, the classical ML floor."""
    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
    X_train = vec.fit_transform(train_dev_df["text"])
    X_test = vec.transform(test_df["text"])
    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(X_train, train_dev_df["label"])
    preds = clf.predict(X_test)
    return _report("tfidf_logreg", test_df["label"].tolist(), preds)


def eval_finetuned(model_dir: str, df: pd.DataFrame) -> dict:
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).eval()
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    preds = []
    with torch.no_grad():
        for i in range(0, len(df), 32):
            batch = df.iloc[i:i + 32]
            enc = tokenizer(batch["text"].tolist(), batch["aspect"].tolist(),
                             padding=True, truncation=True, max_length=128,
                             return_tensors="pt").to(device)
            logits = model(**enc).logits
            idx = logits.argmax(dim=-1).cpu().tolist()
            preds.extend(model.config.id2label[i].lower() for i in idx)
    return _report("finetuned_finbert_absa", df["label"].tolist(), preds)


def _report(name: str, y_true: list, y_pred: list) -> dict:
    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    print(f"\n=== {name} ===")
    print(f"Macro-F1: {macro_f1:.4f}")
    print(classification_report(y_true, y_pred, labels=LABELS, zero_division=0))
    return {"name": name, "macro_f1": macro_f1}


def run(model_dir: str | None):
    test_df = _load_test_set()
    full_df = pd.read_csv(CANDIDATES_PATH)
    train_dev_df = full_df[(full_df["split"] == "train_dev") & (full_df["label"].isin(LABELS))]

    results = [eval_base_finbert_zeroshot(test_df)]
    lex = eval_lexicon(test_df)
    if lex:
        results.append(lex)
    if not train_dev_df.empty:
        results.append(eval_tfidf_logreg(train_dev_df, test_df))
    if model_dir:
        results.append(eval_finetuned(model_dir, test_df))

    print("\n" + "=" * 50)
    print("SUMMARY (frozen random test set, n={})".format(len(test_df)))
    print("=" * 50)
    for r in results:
        print(f"  {r['name']:28s} macro-F1 = {r['macro_f1']:.4f}")

    if model_dir:
        fine = next(r for r in results if r["name"] == "finetuned_finbert_absa")
        base = results[0]
        if fine["macro_f1"] <= base["macro_f1"]:
            print("\nWARNING: fine-tuned model did NOT beat base FinBERT zero-shot. Per the plan, "
                  "this is a reportable finding, not a defect to hide — investigate label quality "
                  "(kappa), training set size, and whether aspect-conditioning is actually helping "
                  "before concluding the approach failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default=None, help="Path to a fine-tuned model from train.finetune")
    args = parser.parse_args()
    run(model_dir=args.model_dir)
