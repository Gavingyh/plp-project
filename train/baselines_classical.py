"""
Classical baselines for the sentiment classifier: Naive Bayes, a linear SVM and
logistic regression on TF-IDF features (Text Processing using ML).

Why: the report compares FinBERT with VADER and one TF-IDF logistic regression.
Adding Naive Bayes and an SVM completes the classical comparison and shows what
the fine-tuned model buys over cheap models trained on the same labels.

Protocol (the same labels and splits as train.finetune, so the numbers compare):
  - the labelled file's `split` column: train_dev for fitting, test for scoring;
  - train.labels.check_splits first, so a leaking file fails loudly;
  - the input is the aspect key plus the sentence (as the FinBERT input is);
  - 5-fold stratified CV on train_dev picks nothing but reports the spread;
  - each model is then fitted on all of train_dev and scored ONCE on test;
  - test macro-F1 gets a 95% bootstrap interval over test rows.
Test predictions are saved so a paired comparison with FinBERT can be made on
the same rows (see paired_bootstrap).

USAGE:
  python -m train.baselines_classical
  python -m train.baselines_classical --labels data/labeled/llm_rater/rules-2026-10-10/training_set.csv
  python -m train.baselines_classical --no-aspect
"""

import argparse
import json
import os

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.naive_bayes import ComplementNB, MultinomialNB
from sklearn.pipeline import make_pipeline
from sklearn.svm import LinearSVC

from train.labels import LABELS, check_splits

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LABELS = os.path.join(BASE_DIR, "data", "labeled", "llm_rater", "rules-2026-10-10", "training_set.csv")
OUT_DIR = os.path.join(BASE_DIR, "data", "eval", "baselines")


def model_input(df: pd.DataFrame, with_aspect: bool = True) -> list[str]:
    """The aspect key as a leading token, then the sentence."""
    if not with_aspect:
        return df["text"].astype(str).tolist()
    return ("aspect_" + df["aspect"].astype(str) + " " + df["text"].astype(str)).tolist()


def models(seed: int = 42) -> dict:
    def tfidf():
        return TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, lowercase=True)
    return {
        "naive_bayes": make_pipeline(tfidf(), MultinomialNB(alpha=0.5)),
        "complement_nb": make_pipeline(tfidf(), ComplementNB(alpha=0.5)),
        "linear_svm": make_pipeline(tfidf(), LinearSVC(C=0.5, class_weight="balanced", random_state=seed)),
        "logistic_regression": make_pipeline(tfidf(), LogisticRegression(
            C=4.0, max_iter=2000, class_weight="balanced", random_state=seed)),
    }


def load_split(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(path)
    df = df[df["label"].isin(LABELS)].reset_index(drop=True)
    check_splits(df)
    return df[df["split"] == "train_dev"].reset_index(drop=True), df[df["split"] == "test"].reset_index(drop=True)


def macro_f1_interval(y_true, y_pred, boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Macro-F1 with a 95% percentile bootstrap interval over rows."""
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    rng = np.random.default_rng(seed)
    n = len(y_true)
    stats = []
    for _ in range(boot):
        idx = rng.integers(0, n, n)
        stats.append(f1_score(y_true[idx], y_pred[idx], average="macro", labels=LABELS))
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(f1_score(y_true, y_pred, average="macro", labels=LABELS)), float(lo), float(hi)


def paired_bootstrap(y_true, pred_a, pred_b, boot: int = 2000, seed: int = 0) -> dict:
    """Macro-F1(A) - macro-F1(B) on the same rows, with a 95% interval."""
    y_true, pred_a, pred_b = map(np.asarray, (y_true, pred_a, pred_b))
    rng = np.random.default_rng(seed)
    n = len(y_true)
    diffs = []
    for _ in range(boot):
        idx = rng.integers(0, n, n)
        diffs.append(f1_score(y_true[idx], pred_a[idx], average="macro", labels=LABELS)
                     - f1_score(y_true[idx], pred_b[idx], average="macro", labels=LABELS))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    obs = f1_score(y_true, pred_a, average="macro", labels=LABELS) - f1_score(y_true, pred_b, average="macro", labels=LABELS)
    return {"diff": float(obs), "lo": float(lo), "hi": float(hi), "excludes_zero": bool(lo > 0 or hi < 0)}


def cross_validate(pipe, X, y, folds: int = 5, seed: int = 42) -> list[float]:
    from sklearn.base import clone
    scores = []
    for tr, dv in StratifiedKFold(folds, shuffle=True, random_state=seed).split(X, y):
        m = clone(pipe).fit([X[i] for i in tr], [y[i] for i in tr])
        scores.append(f1_score([y[i] for i in dv], m.predict([X[i] for i in dv]), average="macro", labels=LABELS))
    return scores


def run(labels_path: str = DEFAULT_LABELS, with_aspect: bool = True, folds: int = 5, seed: int = 42,
        out_dir: str = OUT_DIR) -> pd.DataFrame:
    train, test = load_split(labels_path)
    Xtr, ytr = model_input(train, with_aspect), train["label"].tolist()
    Xte, yte = model_input(test, with_aspect), test["label"].tolist()
    rows, preds = [], {"sentence_id": test["sentence_id"], "aspect": test["aspect"], "label": yte}
    for name, pipe in models(seed).items():
        cv = cross_validate(pipe, Xtr, ytr, folds, seed)
        pipe.fit(Xtr, ytr)
        p = pipe.predict(Xte)
        f1, lo, hi = macro_f1_interval(yte, p)
        rows.append({"model": name, "cv_macro_f1_mean": np.mean(cv), "cv_macro_f1_sd": np.std(cv, ddof=1),
                     "test_macro_f1": f1, "test_ci_low": lo, "test_ci_high": hi,
                     "test_accuracy": accuracy_score(yte, p), "n_train": len(train), "n_test": len(test),
                     "with_aspect": with_aspect})
        preds[name] = p
    os.makedirs(out_dir, exist_ok=True)
    result = pd.DataFrame(rows)
    suffix = "" if with_aspect else "_noaspect"
    result.to_csv(os.path.join(out_dir, f"classical{suffix}.csv"), index=False)
    pd.DataFrame(preds).to_csv(os.path.join(out_dir, f"classical_test_predictions{suffix}.csv"), index=False)
    with open(os.path.join(out_dir, f"classical{suffix}.json"), "w") as f:
        json.dump({"labels": labels_path, "folds": folds, "seed": seed, "rows": rows}, f, indent=1, default=float)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", default=DEFAULT_LABELS)
    ap.add_argument("--no-aspect", action="store_true")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=OUT_DIR)
    a = ap.parse_args()
    res = run(a.labels, not a.no_aspect, a.folds, a.seed, a.out)
    print(res.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
