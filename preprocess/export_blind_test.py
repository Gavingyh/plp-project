"""
Export the held-out test split for blind human labelling, and merge the
filled sheet back.

WHY BLIND: the test split is the only thing that makes the eventual
"fine-tuned FinBERT beats base FinBERT" claim meaningful, and it stops being
that the moment an annotator can see a model's opinion while labelling.
Two columns in candidates.csv leak exactly that:

  - `llm_prelabel` / `llm_rationale` - a local model's proposed label. 199 of
    the 200 test rows have one. Labelling next to them measures agreement
    with that model, not ground truth.
  - `base_finbert_label` / `base_finbert_confidence` - worse, because base
    FinBERT is one of the two models the test set exists to compare. An
    annotator anchored on the baseline's answer biases the comparison
    directly in the baseline's favour.

So the blind sheet carries the sentence, its aspect and its provenance, and
nothing else. Fill in `label` (and `flag` for rows that shouldn't be scored
at all), then merge back.

USAGE:
  python -m preprocess.export_blind_test                 # write the blind sheet
  python -m preprocess.export_blind_test --merge         # merge the filled sheet back
  python -m preprocess.export_blind_test --check-leakage # group-separation report only
"""

import argparse
import csv
import os
import shutil
from datetime import datetime, timezone

import pandas as pd

from config.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELED_DIR = os.path.join(BASE_DIR, "data", "labeled")
CANDIDATES_PATH = os.path.join(LABELED_DIR, "candidates.csv")
BLIND_PATH = os.path.join(LABELED_DIR, "test_blind.csv")

# Anything a model produced is withheld - see the module docstring.
WITHHELD_COLUMNS = ["llm_prelabel", "llm_rationale",
                    "base_finbert_label", "base_finbert_confidence"]

BLIND_COLUMNS = ["sentence_id", "aspect", "text", "bank", "source", "published_at",
                 "url", "label", "flag", "annotator"]

VALID_LABELS = {"positive", "negative", "neutral"}

# A row is keyed by (sentence_id, aspect), not sentence_id: the same sentence
# can be sampled under two different aspects, and merging on sentence_id
# alone would write one aspect's label onto both.
KEY = ["sentence_id", "aspect"]


def find_split_leakage(df: pd.DataFrame) -> list[str]:
    """sentence_ids present in both test and train_dev.

    Splitting per row rather than per sentence lets one sentence land in both
    sides under different aspects. The fine-tuned model would then be
    evaluated on text it was trained on.
    """
    test_ids = set(df[df.split == "test"].sentence_id)
    train_ids = set(df[df.split == "train_dev"].sentence_id)
    return sorted(test_ids & train_ids)


def repair_split_leakage(candidates_path: str = CANDIDATES_PATH) -> dict:
    """Drop the *train_dev* side of any sentence that straddles the split.

    Dropping the train side rather than the test side is deliberate: the test
    split is 200 randomly-drawn rows and every one is expensive, while
    train_dev has 800 and losing a couple costs nothing. Only ever run this
    before labelling - it rewrites candidates.csv.
    """
    df = pd.read_csv(candidates_path)
    leaked = find_split_leakage(df)
    if not leaked:
        return {"leaked_sentence_ids": 0, "rows_dropped": 0}

    if df["label"].notna().any():
        raise RuntimeError(
            "candidates.csv already contains human labels - refusing to drop rows. "
            "Repair the split before labelling starts, not after.")

    backup = candidates_path + ".pre-leakage-repair.bak"
    shutil.copy2(candidates_path, backup)

    drop_mask = (df.split == "train_dev") & (df.sentence_id.isin(leaked))
    kept = df[~drop_mask]
    kept.to_csv(candidates_path, index=False)

    logger.info("dropped %d train_dev row(s) sharing a sentence with the test split",
                int(drop_mask.sum()))
    logger.info("backup written to %s", backup)
    return {"leaked_sentence_ids": len(leaked), "rows_dropped": int(drop_mask.sum()),
            "backup": backup}


def export_blind(candidates_path: str = CANDIDATES_PATH,
                 out_path: str = BLIND_PATH) -> dict:
    """Write the test split with every model-produced column withheld."""
    df = pd.read_csv(candidates_path)
    test = df[df.split == "test"].copy()

    for col in ["label", "flag", "annotator"]:
        if col not in test.columns:
            test[col] = ""
    test["label"] = ""
    test["flag"] = ""
    test["annotator"] = ""

    blind = test[BLIND_COLUMNS]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    blind.to_csv(out_path, index=False, quoting=csv.QUOTE_MINIMAL)

    withheld = [c for c in WITHHELD_COLUMNS if c in df.columns]
    logger.info("wrote %d blind test rows to %s", len(blind), out_path)
    logger.info("withheld columns: %s", ", ".join(withheld))
    return {"rows": len(blind), "path": out_path, "withheld": withheld}


def merge_labels(blind_path: str = BLIND_PATH,
                 candidates_path: str = CANDIDATES_PATH) -> dict:
    """Merge a filled blind sheet back into candidates.csv on (sentence_id, aspect)."""
    blind = pd.read_csv(blind_path)
    df = pd.read_csv(candidates_path)

    filled = blind[blind["label"].notna() & (blind["label"].astype(str).str.strip() != "")]
    if filled.empty:
        raise RuntimeError(f"no labels filled in {blind_path} - nothing to merge")

    bad = sorted(set(filled["label"].astype(str).str.strip().str.lower()) - VALID_LABELS)
    if bad:
        raise ValueError(f"invalid label(s) {bad}; allowed: {sorted(VALID_LABELS)}")

    backup = candidates_path + ".pre-merge.bak"
    shutil.copy2(candidates_path, backup)

    df = df.set_index(KEY)
    src = filled.set_index(KEY)
    now = datetime.now(timezone.utc).isoformat()

    # An entirely-empty column reads back as float64, and assigning a string
    # into it raises. Every column written below is text, so make that explicit.
    for col in ["label", "flag", "annotator", "labeled_at"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(object)

    missing = [k for k in src.index if k not in df.index]
    if missing:
        raise KeyError(f"{len(missing)} labelled row(s) not found in candidates.csv, "
                       f"first: {missing[:3]}")

    df.loc[src.index, "label"] = src["label"].astype(str).str.strip().str.lower()
    if "flag" in src.columns:
        df.loc[src.index, "flag"] = src["flag"].fillna("")
    if "annotator" in src.columns:
        df.loc[src.index, "annotator"] = src["annotator"].fillna("")
    df.loc[src.index, "labeled_at"] = now

    df.reset_index().to_csv(candidates_path, index=False)
    logger.info("merged %d label(s); backup at %s", len(src), backup)
    return {"merged": len(src), "backup": backup, "candidates_path": candidates_path}


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--merge", action="store_true",
                        help="merge a filled blind sheet back into candidates.csv")
    parser.add_argument("--check-leakage", action="store_true",
                        help="report sentences straddling the train/test split and exit")
    parser.add_argument("--repair-leakage", action="store_true",
                        help="drop train_dev rows sharing a sentence with the test split")
    args = parser.parse_args()

    if args.check_leakage:
        leaked = find_split_leakage(pd.read_csv(CANDIDATES_PATH))
        print(f"sentences in both splits: {len(leaked)}")
        for sid in leaked:
            print(f"  {sid}")
    elif args.repair_leakage:
        print(repair_split_leakage())
    elif args.merge:
        print(merge_labels())
    else:
        print(export_blind())
