"""
The labelled data, made safe to train and evaluate on.

Annotators label aspect and sentiment together (DESIGN decision 17), and
correcting an aspect can turn two candidate rows into the same (sentence,
aspect) pair. The 2026-09-27 round did exactly that: 21 pairs appear two or
three times, and in 5 of them one copy sits in train_dev and the other in the
frozen test split. A sentence on both sides of the split leaks the answer into
training, and a duplicated row counts twice in both training and scoring.

`prepare()` builds data/labeled/candidates.csv from the resolved sheets:

  1. one row per (sentence_id, aspect), refusing to continue if duplicates
     disagree on the label;
  2. no sentence in train_dev that is also in test (the test copy stays: the
     test split is frozen);
  3. test labels taken from the resolved blind sheet, which was labelled
     without model output in view, rather than from the candidates sheet.

`check_splits()` is what train.finetune and train.evaluate call before using
the file, so a future labelling round that reintroduces either problem fails
loudly instead of inflating a score.

USAGE:
  python -m train.labels \
      --candidates data/labeled/resolved/candidates_resolved.csv \
      --blind data/labeled/test_blind.csv \
      --out data/labeled/candidates.csv
"""

import argparse
import os

import pandas as pd

LABELS = ["negative", "neutral", "positive"]
KEY = ["sentence_id", "aspect"]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELED_DIR = os.path.join(BASE_DIR, "data", "labeled")


def check_splits(df: pd.DataFrame) -> None:
    """Raise ValueError if the labelled file would inflate a score."""
    problems = []
    dups = df[df.duplicated(KEY, keep=False)]
    if not dups.empty:
        problems.append(f"{dups.groupby(KEY).ngroups} (sentence_id, aspect) pairs appear more than once")
    leaked = set(df.loc[df["split"] == "train_dev", "sentence_id"]) & set(df.loc[df["split"] == "test", "sentence_id"])
    if leaked:
        problems.append(f"{len(leaked)} sentences are in both train_dev and test")
    if problems:
        raise ValueError("labelled data is not safe to use: " + "; ".join(problems)
                         + ". Rebuild it with `python -m train.labels`.")


def _dedupe(df: pd.DataFrame, what: str) -> tuple[pd.DataFrame, int]:
    groups = df[df.duplicated(KEY, keep=False)].groupby(KEY)["label"].nunique()
    conflicts = groups[groups > 1]
    if not conflicts.empty:
        raise ValueError(f"{len(conflicts)} duplicated pairs in {what} disagree on the label; "
                         f"resolve them by hand first, e.g. {list(conflicts.index[:3])}")
    out = df.drop_duplicates(KEY, keep="first")
    return out, len(df) - len(out)


def prepare(candidates_path: str, blind_path: str, out_path: str) -> dict:
    cand = pd.read_csv(candidates_path)
    blind = pd.read_csv(blind_path)
    report = {"input_rows": len(cand)}

    # Leakage first: a sentence whose copies sit in both splits keeps only its test copy.
    test_ids = set(cand.loc[cand["split"] == "test", "sentence_id"])
    leaked = (cand["split"] == "train_dev") & cand["sentence_id"].isin(test_ids)
    report["train_dev_rows_dropped_as_leaked"] = int(leaked.sum())
    cand = cand[~leaked]

    cand, report["duplicate_rows_dropped"] = _dedupe(cand, candidates_path)
    blind, report["duplicate_blind_rows_dropped"] = _dedupe(blind, blind_path)

    # Test labels come from the blind sheet.
    test = cand["split"] == "test"
    blind_labels = blind.set_index(KEY)["label"]
    keys = pd.MultiIndex.from_frame(cand.loc[test, KEY])
    missing = [k for k in keys if k not in blind_labels.index]
    if missing:
        raise KeyError(f"{len(missing)} test rows are not in the blind sheet, first: {missing[:3]}")
    new = blind_labels.reindex(keys).to_numpy()
    report["test_labels_changed_to_blind"] = int((cand.loc[test, "label"].to_numpy() != new).sum())
    cand.loc[test, "label"] = new

    check_splits(cand)
    bad = set(cand["label"].dropna()) - set(LABELS)
    if bad:
        raise ValueError(f"invalid labels {sorted(bad)}")
    cand.to_csv(out_path, index=False)
    report.update({"output_rows": len(cand),
                   "train_dev": int((cand["split"] == "train_dev").sum()),
                   "test": int((cand["split"] == "test").sum()),
                   "out": out_path})
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Build data/labeled/candidates.csv from the resolved sheets.")
    p.add_argument("--candidates", default=os.path.join(LABELED_DIR, "resolved", "candidates_resolved.csv"))
    p.add_argument("--blind", default=os.path.join(LABELED_DIR, "test_blind.csv"))
    p.add_argument("--out", default=os.path.join(LABELED_DIR, "candidates.csv"))
    args = p.parse_args()
    for k, v in prepare(args.candidates, args.blind, args.out).items():
        print(f"{k:34s} {v}")
