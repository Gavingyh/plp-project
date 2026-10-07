"""
A per-source labelling round, from the model's suggestions to a training file.

`preprocess/export_source_round.py` draws the sentences (data/labeled/<source>/
candidates.csv and test_blind.csv). This module covers the two steps either
side of the people:

  prelabel   Put an LLM's suggested aspect, not-about-bank flag and sentiment
             into the TRAIN/DEV rows of the sheet the annotators will correct.
             The test rows are never touched: they stay blind (DESIGN decision
             22, guideline "The test split is frozen").
  label-test Put an LLM's labels for the BLIND test rows in a separate file
             (claude_test_labels.csv). The blind sheet itself is never written to.
  silver     Build resolved files from the LLM's labels instead of the annotators'
             (prefix `silver_`), for training and scoring while people have not
             labelled yet. Every such row carries the LLM as its `annotator`.
  merge      Take the annotators' filled sheets and write the resolved files in
             the formats train.labels expects. Rows an annotator marked
             not_about_bank are left out, as the guideline says ("stop").
  combine    Add a source's resolved rows to the existing rounds' resolved
             files and run train.labels.prepare, writing a NEW labelled file
             under data/labeled/combined/. The existing candidates.csv and its
             sources are not modified.

The suggestions are suggestions. Nothing here turns an LLM label into a gold
label: `merge` reads the annotators' columns (`aspect`, `label`,
`not_about_bank`), and an unfilled row is dropped, never filled from the model.

USAGE:
  python -m train.source_round prelabel --round data/labeled/sgx_research
  python -m train.source_round label-test --round data/labeled/sgx_research
  python -m train.source_round silver   --round data/labeled/sgx_research
  python -m train.source_round combine  --round data/labeled/sgx_research --prefix silver \
        --out-dir data/labeled/combined_silver
  python -m train.source_round merge    --round data/labeled/sgx_research \
        --candidates filled_candidates.csv --blind filled_test_blind.csv
  python -m train.source_round combine  --round data/labeled/sgx_research
  python -m train.finetune --labels data/labeled/combined/candidates.csv ...
"""

import argparse
import os

import pandas as pd
import yaml

from train.labels import KEY, LABELED_DIR, LABELS, check_splits, prepare

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASPECTS_CONFIG = os.path.join(BASE_DIR, "config", "aspects.yaml")

# Compact keys the raw suggestion files use, to keep a few hundred lines readable.
ASPECT_KEYS = {"AQ": "asset_quality", "CL": "capital_liquidity", "DP": "dividend_policy",
               "NIM": "net_interest_margin", "MG": "management_guidance",
               "IPR": "income_profit_results", "WB": "wealth_business",
               "ISS": "investor_stock_sentiment", "RB": "retail_banking_sentiment",
               "MME": "macro_market_environment", "OT": "other"}
SENTIMENT_KEYS = {"+": "positive", "0": "neutral", "-": "negative"}

RESOLVED_COLUMNS = ["sentence_id", "aspect", "text", "bank", "source", "url", "published_at", "split",
                    "sampling_method", "base_finbert_label", "base_finbert_confidence", "label",
                    "annotator", "labeled_at", "llm_prelabel", "was_corrected", "original_aspect"]
BLIND_RESOLVED_COLUMNS = ["sentence_id", "aspect", "text", "bank", "source", "published_at", "url",
                          "label", "flag", "annotator", "original_aspect"]


def valid_aspects() -> set[str]:
    with open(ASPECTS_CONFIG, encoding="utf-8") as f:
        return set(yaml.safe_load(f)["aspects"]) | {"other"}


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "x"}


# ----- prelabel -----------------------------------------------------------------

def parse_suggestions(raw_dir: str) -> pd.DataFrame:
    """Raw lines "<row number> <ASPECT KEY> <+|0|-> [x]" -> one row per sentence,
    numbered in the order of `order.csv`. `x` flags not-about-the-bank."""
    order = pd.read_csv(os.path.join(raw_dir, "order.csv"))["sentence_id"].tolist()
    rows = {}
    for name in sorted(f for f in os.listdir(raw_dir) if f.startswith("labels_") and f.endswith(".txt")):
        with open(os.path.join(raw_dir, name), encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if not parts:
                    continue
                n, aspect, sentiment, flag = int(parts[0]), parts[1], parts[2], len(parts) > 3
                if aspect not in ASPECT_KEYS or sentiment not in SENTIMENT_KEYS:
                    raise ValueError(f"{name}: cannot read {line.strip()!r}")
                if n in rows:
                    raise ValueError(f"{name}: row {n} is labelled twice")
                rows[n] = {"sentence_id": order[n - 1], "claude_aspect": ASPECT_KEYS[aspect],
                           "claude_not_about_bank": flag, "claude_label": SENTIMENT_KEYS[sentiment]}
    missing = sorted(set(range(1, len(order) + 1)) - set(rows))
    if missing:
        raise ValueError(f"{len(missing)} rows have no suggestion, first: {missing[:5]}")
    return pd.DataFrame(rows.values())


def prelabel(round_dir: str, rater: str, labelled_on: str) -> dict:
    cand_path = os.path.join(round_dir, "candidates.csv")
    cand = pd.read_csv(cand_path, dtype=str)
    sugg = parse_suggestions(os.path.join(round_dir, "claude_prelabels"))

    train = cand["split"] == "train_dev"
    ids = set(cand.loc[train, "sentence_id"])
    if not ids <= set(sugg["sentence_id"]):
        raise ValueError(f"{len(ids - set(sugg['sentence_id']))} train_dev rows have no suggestion")
    sugg = sugg[sugg["sentence_id"].isin(ids)]      # rows the export later dropped need none
    sugg.assign(rater=rater, labelled_on=labelled_on).to_csv(
        os.path.join(round_dir, "claude_prelabels.csv"), index=False)
    if cand.loc[~train, ["aspect", "llm_prelabel"]].notna().any().any():
        raise ValueError("test rows already carry model output; they must stay blind")

    by_id = sugg.set_index("sentence_id")
    cand.loc[train, "aspect"] = cand.loc[train, "sentence_id"].map(by_id["claude_aspect"])
    cand.loc[train, "llm_prelabel"] = cand.loc[train, "sentence_id"].map(by_id["claude_label"])
    cand.loc[train, "llm_not_about_bank"] = cand.loc[train, "sentence_id"].map(
        by_id["claude_not_about_bank"]).map(lambda v: "true" if v else "false")
    cand.to_csv(cand_path, index=False)
    return {"rows_prelabelled": int(train.sum()),
            "aspects": sugg["claude_aspect"].value_counts().to_dict(),
            "labels": sugg["claude_label"].value_counts().to_dict(),
            "flagged_not_about_bank": int(sugg["claude_not_about_bank"].sum())}


# ----- LLM labels for the blind test rows, and the silver files -----------------

def label_test(round_dir: str, rater: str, labelled_on: str) -> dict:
    """Parse the LLM's answers for the blind test rows into claude_test_labels.csv.
    The sheets the annotators use are not touched."""
    test_ids = pd.read_csv(os.path.join(round_dir, "test_blind.csv"), dtype=str)["sentence_id"]
    sugg = parse_suggestions(os.path.join(round_dir, "claude_test_labels"))
    if set(sugg["sentence_id"]) != set(test_ids):
        raise ValueError("the labels do not cover exactly the blind test rows")
    sugg.assign(rater=rater, labelled_on=labelled_on).to_csv(
        os.path.join(round_dir, "claude_test_labels.csv"), index=False)
    return {"test_rows_labelled": len(sugg), "aspects": sugg["claude_aspect"].value_counts().to_dict(),
            "labels": sugg["claude_label"].value_counts().to_dict(),
            "flagged_not_about_bank": int(sugg["claude_not_about_bank"].sum())}


def silver(round_dir: str, rater: str) -> dict:
    """Resolved files built from the LLM's labels (train suggestions and test labels),
    written with the prefix `silver`. Not gold: the annotator column says who labelled."""
    cand = pd.read_csv(os.path.join(round_dir, "candidates.csv"), dtype=str)
    train = cand[cand["split"] == "train_dev"].assign(
        label=lambda d: d["llm_prelabel"], not_about_bank=lambda d: d["llm_not_about_bank"], annotator=rater)
    tests = pd.read_csv(os.path.join(round_dir, "claude_test_labels.csv"), dtype=str)
    blind = pd.read_csv(os.path.join(round_dir, "test_blind.csv"), dtype=str)[["sentence_id"]].merge(
        tests.rename(columns={"claude_aspect": "aspect", "claude_label": "label",
                              "claude_not_about_bank": "not_about_bank"}), on="sentence_id").assign(annotator=rater)
    blind["not_about_bank"] = blind["not_about_bank"].map({"True": "true", "False": "false"})
    out = os.path.join(round_dir, "silver")
    os.makedirs(out, exist_ok=True)
    train.to_csv(os.path.join(out, "filled_candidates.csv"), index=False)
    blind.to_csv(os.path.join(out, "filled_test_blind.csv"), index=False)
    report = merge(round_dir, os.path.join(out, "filled_candidates.csv"),
                   os.path.join(out, "filled_test_blind.csv"), prefix="silver")
    return {**report, "annotator": rater}


# ----- merge --------------------------------------------------------------------

def _filled(df: pd.DataFrame, what: str) -> pd.DataFrame:
    """Rows the annotator completed and kept: a valid aspect and label, and not
    flagged not_about_bank. Anything else is reported, not guessed."""
    aspects = valid_aspects()
    flagged = df["not_about_bank"].map(_truthy) if "not_about_bank" in df else pd.Series(False, index=df.index)
    label = df["label"].astype(str).str.strip().str.lower()
    bad_label = df["label"].notna() & ~label.isin(LABELS) & ~flagged
    bad_aspect = ~df["aspect"].isin(aspects) & ~flagged & df["label"].notna()
    if bad_label.any() or bad_aspect.any():
        raise ValueError(f"{what}: {int(bad_label.sum())} invalid labels and {int(bad_aspect.sum())} invalid "
                         f"aspects, first rows: {df.index[bad_label | bad_aspect][:5].tolist()}")
    keep = df["label"].notna() & ~flagged
    out = df[keep].copy()
    out["label"] = label[keep]
    return out


def _was_corrected(round_dir: str, train: pd.DataFrame) -> pd.Series:
    """Whether the annotator changed the LLM's suggestion: its sentiment, or its aspect
    (from claude_prelabels.csv). Until 7 Oct 2026 this compared the aspect with the
    pipeline's nearest-centroid guess, which says nothing about the suggestion. Empty
    where the row had no suggestion."""
    suggested = train["llm_prelabel"].fillna("").astype(str).str.strip().str.lower()
    changed = train["label"] != suggested
    path = os.path.join(round_dir, "claude_prelabels.csv")
    if os.path.exists(path):
        aspects = pd.read_csv(path, dtype=str).set_index("sentence_id")["claude_aspect"]
        changed = changed | (train["aspect"] != train["sentence_id"].map(aspects))
    return changed.where(suggested != "", "")


def merge(round_dir: str, filled_candidates: str, filled_blind: str, prefix: str = "resolved") -> dict:
    cand = pd.read_csv(os.path.join(round_dir, "candidates.csv"), dtype=str)
    train_done = _filled(pd.read_csv(filled_candidates, dtype=str), "candidates sheet")
    train_done = train_done[train_done["sentence_id"].isin(cand.loc[cand["split"] == "train_dev", "sentence_id"])]
    blind_done = _filled(pd.read_csv(filled_blind, dtype=str), "blind sheet")

    unnamed = [what for what, df in (("candidates sheet", train_done), ("blind sheet", blind_done))
               if "annotator" not in df or df["annotator"].fillna("").str.strip().eq("").any()]
    if unnamed:
        # The report says people labelled these rows; the file must say who (7 Oct 2026: the
        # broker research round's 100 test rows came through with a blank annotator).
        raise ValueError(f"labelled rows without an annotator in the {' and the '.join(unnamed)}: "
                         "fill in who labelled each row (a code such as A)")

    train = train_done.assign(split="train_dev", sampling_method="stratified")
    train["llm_prelabel"] = train["llm_prelabel"] if "llm_prelabel" in train else ""
    train["was_corrected"] = _was_corrected(round_dir, train)

    test_base = cand[cand["split"] == "test"].drop(columns=["aspect", "label", "annotator"])
    test = test_base.merge(blind_done[["sentence_id", "aspect", "label", "annotator"]], on="sentence_id")
    test["original_aspect"] = ""

    resolved = pd.concat([train, test])[RESOLVED_COLUMNS]
    blind = test.assign(flag="")[BLIND_RESOLVED_COLUMNS]
    resolved.to_csv(os.path.join(round_dir, f"{prefix}_candidates.csv"), index=False)
    blind.to_csv(os.path.join(round_dir, f"{prefix}_test_blind.csv"), index=False)
    return {"train_dev": len(train), "test": len(test),
            "dropped_unfilled_or_not_about_bank": int(len(cand) - len(train) - len(test))}


# ----- combine ------------------------------------------------------------------

def combine(round_dirs: list[str], out_dir: str | None = None, prefix: str = "resolved") -> dict:
    out_dir = out_dir or os.path.join(LABELED_DIR, "combined")
    os.makedirs(out_dir, exist_ok=True)
    cands = [pd.read_csv(os.path.join(LABELED_DIR, "resolved", "candidates_resolved.csv"))]
    blinds = [pd.read_csv(os.path.join(LABELED_DIR, "test_blind.csv"))]
    for d in round_dirs:
        cands.append(pd.read_csv(os.path.join(d, f"{prefix}_candidates.csv")))
        blinds.append(pd.read_csv(os.path.join(d, f"{prefix}_test_blind.csv")))
    cand_path, blind_path = os.path.join(out_dir, "candidates_resolved.csv"), os.path.join(out_dir, "test_blind.csv")
    pd.concat(cands, ignore_index=True)[RESOLVED_COLUMNS].to_csv(cand_path, index=False)
    pd.concat(blinds, ignore_index=True)[BLIND_RESOLVED_COLUMNS].to_csv(blind_path, index=False)
    out_path = os.path.join(out_dir, "candidates.csv")
    report = prepare(cand_path, blind_path, out_path)
    check_splits(pd.read_csv(out_path))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prelabel")
    p.add_argument("--round", required=True)
    p.add_argument("--rater", default="claude-sonnet-5-5")
    p.add_argument("--date", default=pd.Timestamp.now().strftime("%Y-%m-%d"))
    p = sub.add_parser("label-test")
    p.add_argument("--round", required=True)
    p.add_argument("--rater", default="claude-sonnet-5-5")
    p.add_argument("--date", default=pd.Timestamp.now().strftime("%Y-%m-%d"))
    p = sub.add_parser("silver")
    p.add_argument("--round", required=True)
    p.add_argument("--rater", default="claude-sonnet-5-5")
    p = sub.add_parser("merge")
    p.add_argument("--round", required=True)
    p.add_argument("--candidates", required=True)
    p.add_argument("--blind", required=True)
    p = sub.add_parser("combine")
    p.add_argument("--round", required=True, nargs="+")
    p.add_argument("--out-dir")
    p.add_argument("--prefix", default="resolved", help="`silver` to combine the LLM-labelled files")
    args = ap.parse_args()
    if args.cmd == "prelabel":
        result = prelabel(args.round, args.rater, args.date)
    elif args.cmd == "label-test":
        result = label_test(args.round, args.rater, args.date)
    elif args.cmd == "silver":
        result = silver(args.round, args.rater)
    elif args.cmd == "merge":
        result = merge(args.round, args.candidates, args.blind)
    else:
        result = combine(args.round, args.out_dir, args.prefix)
    for k, v in result.items():
        print(f"{k:34s} {v}")
