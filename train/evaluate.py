"""
Evaluation: fine-tuned model vs. required baselines on the FROZEN
random test set (data/labeled/candidates.csv, split='test').

Baselines are required, not optional: the claim
"fine-tuning helped" is unsupported without comparing against base FinBERT
zero-shot, a lexicon method, and a classical ML method. This script runs all
of them on the same frozen test set so the comparison is apples-to-apples.

Needs data/labeled/candidates.csv (built by train/labels.py) and, for the
fine-tuned comparison, a model trained by train/finetune.py.

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

from config.device import best_device
from train.finetune import aspect_inputs, read_input_spec
from train.labels import LABELS, check_splits

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")


def _load_test_set() -> pd.DataFrame:
    df = pd.read_csv(CANDIDATES_PATH)
    check_splits(df)
    df = df[(df["split"] == "test") & (df["label"].isin(LABELS))]
    if df.empty:
        raise ValueError("No labeled test rows found - Labeling must be complete first.")
    return df


def eval_base_finbert_zeroshot(df: pd.DataFrame) -> dict:
    """Baseline 1: base FinBERT, zero-shot, whole-sentence (not aspect-conditioned
 - base FinBERT has no mechanism to condition on the aspect at all, which is
    itself part of the case for fine-tuning)."""
    from sentiment.score import classify_sentences
    preds = [label for label, _ in classify_sentences(df["text"].tolist())]
    return _report("base_finbert_zeroshot", df["label"].tolist(), preds, df.get("source"))


def eval_lexicon(df: pd.DataFrame) -> dict:
    """Baseline 2: VADER, the rule-based floor."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except ImportError:
        print("vaderSentiment not installed (pip install vaderSentiment) - skipping lexicon baseline.")
        return {}
    analyzer = SentimentIntensityAnalyzer()
    preds = []
    for text in df["text"]:
        compound = analyzer.polarity_scores(text)["compound"]
        preds.append("positive" if compound > 0.05 else "negative" if compound < -0.05 else "neutral")
    return _report("vader_lexicon", df["label"].tolist(), preds, df.get("source"))


def eval_tfidf_logreg(train_dev_df: pd.DataFrame, test_df: pd.DataFrame) -> dict:
    """Baseline 3: TF-IDF + logistic regression, the classical ML floor."""
    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
    X_train = vec.fit_transform(train_dev_df["text"])
    X_test = vec.transform(test_df["text"])
    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(X_train, train_dev_df["label"])
    preds = clf.predict(X_test)
    return _report("tfidf_logreg", test_df["label"].tolist(), preds, test_df.get("source"))


def finetuned_probs(model_dir: str, df: pd.DataFrame) -> np.ndarray:
    """(n, 3) class probabilities in LABELS order, fed the way the model was
    trained (aspect or not, aspect key or readable label)."""
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).eval()
    device = best_device()
    model.to(device)
    spec = read_input_spec(model_dir)
    order = [{v.lower(): int(k) for k, v in model.config.id2label.items()}[l] for l in LABELS]
    out = []
    with torch.no_grad():
        for i in range(0, len(df), 32):
            batch = df.iloc[i:i + 32]
            segments = ([batch["text"].tolist(), aspect_inputs(batch, spec["aspect_text"])]
                        if spec["with_aspect"] else [batch["text"].tolist()])
            enc = tokenizer(*segments, padding=True, truncation=True, max_length=128,
                            return_tensors="pt").to(device)
            probs = torch.softmax(model(**enc).logits, dim=-1).cpu().numpy()
            out.append(probs[:, order])
    probs = np.concatenate(out)
    # The GPU once, under memory pressure, returned all-zero rows
    # without an error, which argmax turned into "negative" everywhere.
    if not np.allclose(probs.sum(axis=1), 1.0, atol=1e-3):
        raise RuntimeError(f"{model_dir}: probabilities don't sum to 1: the device returned garbage; "
                           "rerun with --cpu")
    return probs


def eval_finetuned(model_dir: str, df: pd.DataFrame, name: str = "finetuned_finbert_absa") -> dict:
    probs = finetuned_probs(model_dir, df)
    return _report(name, df["label"].tolist(), [LABELS[i] for i in probs.argmax(axis=1)], df.get("source"))


def eval_ensemble(model_dirs: list[str], df: pd.DataFrame) -> dict:
    """Average the models' probabilities, then take the most likely class."""
    probs = np.mean([finetuned_probs(d, df) for d in model_dirs], axis=0)
    return _report(f"finetuned_average_of_{len(model_dirs)}", df["label"].tolist(),
                   [LABELS[i] for i in probs.argmax(axis=1)], df.get("source"))


def accuracy_by_source(y_true: list, y_pred: list, sources: list) -> dict[str, tuple[float, int]]:
    """{source: (accuracy, n)}, largest source first."""
    df = pd.DataFrame({"ok": [t == p for t, p in zip(y_true, y_pred)], "source": list(sources)})
    g = df.groupby("source")["ok"].agg(["mean", "size"]).sort_values("size", ascending=False)
    return {s: (float(r["mean"]), int(r["size"])) for s, r in g.iterrows()}


def _report(name: str, y_true: list, y_pred: list, sources=None) -> dict:
    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    print(f"\n=== {name} ===")
    print(f"Macro-F1: {macro_f1:.4f}")
    print(classification_report(y_true, y_pred, labels=LABELS, zero_division=0))
    if sources is not None:
        by_source = accuracy_by_source(y_true, y_pred, sources)
        print("Accuracy by source: " + ", ".join(f"{s} {a:.2f} (n={n})" for s, (a, n) in by_source.items()))
    return {"name": name, "macro_f1": macro_f1}


def run(model_dir: str | list[str] | None):
    model_dirs = [model_dir] if isinstance(model_dir, str) else list(model_dir or [])
    test_df = _load_test_set()
    full_df = pd.read_csv(CANDIDATES_PATH)
    train_dev_df = full_df[(full_df["split"] == "train_dev") & (full_df["label"].isin(LABELS))]

    results = [eval_base_finbert_zeroshot(test_df)]
    lex = eval_lexicon(test_df)
    if lex:
        results.append(lex)
    if not train_dev_df.empty:
        results.append(eval_tfidf_logreg(train_dev_df, test_df))
    for i, d in enumerate(model_dirs):
        results.append(eval_finetuned(d, test_df, "finetuned_finbert_absa" if len(model_dirs) == 1
                                      else f"finetuned_{i + 1}"))
    if len(model_dirs) > 1:
        results.append(eval_ensemble(model_dirs, test_df))

    print("\n" + "=" * 50)
    print("SUMMARY (frozen random test set, n={})".format(len(test_df)))
    print("=" * 50)
    for r in results:
        print(f"  {r['name']:28s} macro-F1 = {r['macro_f1']:.4f}")

    if len(model_dirs) == 1:
        fine = next(r for r in results if r["name"] == "finetuned_finbert_absa")
        base = results[0]
        if fine["macro_f1"] <= base["macro_f1"]:
            print("\nWARNING: fine-tuned model did NOT beat base FinBERT zero-shot. Per the plan, "
                  "this is a reportable finding, not a defect to hide - investigate label quality "
                  "(kappa), training set size, and whether aspect-conditioning is actually helping "
                  "before concluding the approach failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", nargs="+", default=None,
                        help="one or more fine-tuned models; with several, their average is reported too")
    parser.add_argument("--labels", default=None,
                        help=f"labelled file to score on, default {CANDIDATES_PATH}")
    parser.add_argument("--cpu", action="store_true", help="run every model on the CPU instead of the GPU")
    args = parser.parse_args()
    if args.labels:
        CANDIDATES_PATH = args.labels
    if args.cpu:
        import sentiment.score
        best_device = sentiment.score.best_device = lambda: "cpu"  # noqa: E731  (read at call time)
    run(model_dir=args.model_dir)
