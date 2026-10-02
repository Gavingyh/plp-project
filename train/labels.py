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

A top-up sheet (preprocess.export_topup) adds rows with `--topup`: every
row with an aspect and a label, unless marked `not_about_bank`, joins
train_dev, with `url` and `published_at` taken from the database. A top-up
sentence already in the file, in either split, is refused rather than
merged.

USAGE:
  python -m train.labels \
      --candidates data/labeled/resolved/candidates_resolved.csv \
      --blind data/labeled/test_blind.csv \
      --out data/labeled/candidates.csv
  python -m train.labels --topup data/labeled/topup/topup_sheet_resolved.csv   # plus the defaults
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


_YES = {"1", "y", "yes", "true", "x"}


def topup_rows(paths: list[str], conn) -> pd.DataFrame:
    """The labelled rows of top-up sheets, in candidates.csv's shape, all train_dev."""
    from train.agreement import aspect_keys
    sheets = [pd.read_csv(p, keep_default_na=False, dtype=str).assign(_file=os.path.basename(p)) for p in paths]
    df = pd.concat(sheets, ignore_index=True)
    for col in ("aspect", "label", "not_about_bank"):
        df[col] = (df[col] if col in df.columns else pd.Series("", index=df.index)).astype(str).str.strip().str.lower()
    df = df[(df["not_about_bank"].isin(_YES) == False) & (df["aspect"] != "") & (df["label"] != "")]  # noqa: E712
    bad_label = sorted(set(df["label"]) - set(LABELS))
    bad_aspect = sorted(set(df["aspect"]) - set(aspect_keys()) - {"other"})
    if bad_label or bad_aspect:
        raise ValueError(f"top-up sheet has invalid labels {bad_label} or aspects {bad_aspect}")
    ids = list(df["sentence_id"])
    meta = pd.read_sql(f"SELECT sentence_id, url, published_at FROM sentences WHERE sentence_id IN "
                       f"({','.join('?' * len(ids))})", conn, params=ids) if ids else \
        pd.DataFrame(columns=["sentence_id", "url", "published_at"])
    missing = set(ids) - set(meta["sentence_id"])
    if missing:
        raise KeyError(f"{len(missing)} top-up sentences are not in the database, first: {sorted(missing)[:3]}")
    out = df.merge(meta, on="sentence_id", how="left").assign(split="train_dev", sampling_method="topup")
    keep = ["sentence_id", "aspect", "text", "bank", "source", "url", "published_at", "split",
            "sampling_method", "label", "annotator"]
    return out[[c for c in keep if c in out.columns]]


def prepare(candidates_path: str, blind_path: str, out_path: str,
            topup_paths: list[str] | None = None, conn=None) -> dict:
    cand = pd.read_csv(candidates_path)
    blind = pd.read_csv(blind_path)
    report = {"input_rows": len(cand)}
    if topup_paths:
        if conn is None:
            from ingest.db import get_connection
            conn = get_connection()
        extra = topup_rows(topup_paths, conn)
        clash = set(extra["sentence_id"]) & set(cand["sentence_id"])
        if clash:
            raise ValueError(f"{len(clash)} top-up sentences are already labelled, first: {sorted(clash)[:3]}")
        report["topup_rows_added"] = len(extra)
        cand = pd.concat([cand, extra], ignore_index=True)

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
    p.add_argument("--topup", nargs="*", default=[], help="labelled top-up sheets to add to train_dev")
    args = p.parse_args()
    for k, v in prepare(args.candidates, args.blind, args.out, args.topup).items():
        print(f"{k:34s} {v}")
