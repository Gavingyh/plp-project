"""
Export a labelling round for ONE source, the way the first round was drawn but
without touching the existing labelled files.

`export_candidates.py` samples the whole corpus and writes data/labeled/
candidates.csv, which would overwrite a labelled file. A new source (the first
user is `sgx_research`, DESIGN decision 17's version-2 sheet) needs the same
sampling design on its own sentences, written to its own folder:

  - TEST: drawn purely at random from the source's usable sentences FIRST, before
    any model screening, and exported on a blind sheet with no model output
    (no base FinBERT, no LLM suggestion, not even the pipeline's aspect).
  - TRAIN/DEV: from what is left, stratified on base FinBERT's own call so the
    set is not 60-70% neutral, topped up from the rest if a class runs short.
    These rows carry the pipeline's aspect and base FinBERT for reference.

One row is one SENTENCE (guideline v2): the annotator chooses the aspect and
the sentiment and sets `not_about_bank`. `original_aspect` holds the aspect the
pipeline's nearest-centroid assignment ranked first.

Near-copies of a test sentence are removed from train (analyst reports repeat
themselves with small edits). Sentences that are plainly extraction debris (chart legends, legal boilerplate,
table rows, run-ons) are left out before sampling so annotators' time goes on
prose. The rules are in `junk_reason` and are listed in the report.

USAGE:
  python -m preprocess.export_source_round --source sgx_research --train-dev 300 --test 100
"""

import argparse
import csv
import os
import random
import re

import pandas as pd

from ingest.db import get_connection
from preprocess.fragments import fragment_reason

from config.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELED_DIR = os.path.join(BASE_DIR, "data", "labeled")

CANDIDATE_COLUMNS = ["sentence_id", "aspect", "text", "bank", "source", "url", "published_at",
                     "split", "sampling_method", "base_finbert_label", "base_finbert_confidence",
                     "label", "annotator", "labeled_at", "llm_prelabel", "was_corrected",
                     "original_aspect", "not_about_bank", "llm_not_about_bank", "doc_title"]
BLIND_COLUMNS = ["sentence_id", "aspect", "text", "bank", "source", "doc_title", "published_at",
                 "url", "label", "not_about_bank", "annotator"]

_LEGAL_OR_CHART = re.compile(
    r"Please refer to|Ratings History|Disclaimer|disclosures|Share Price vs\.|Insights Direct|"
    r"\s--\s|TikTok|Sign Up|prior written consent|Major Shareholders|Free float|Source:", re.IGNORECASE)
MIN_WORDS, MAX_WORDS, MAX_CHARS = 8, 70, 450
NEAR_DUP_VS_TEST, NEAR_DUP_WITHIN = 0.6, 0.8      # word-set Jaccard


def jaccard(a: str, b: str) -> float:
    """Overlap of the two sentences' lower-cased word sets, 0..1."""
    wa, wb = set(re.findall(r"[a-z0-9]+", a.lower())), set(re.findall(r"[a-z0-9]+", b.lower()))
    return len(wa & wb) / max(len(wa | wb), 1)


def junk_reason(text: str, source: str) -> str | None:
    """Why a sentence is not worth a person's time, or None."""
    words = text.split()
    if len(words) < MIN_WORDS:
        return "too short"
    if len(words) > MAX_WORDS or len(text) > MAX_CHARS:
        return "run-on (several sentences or a table joined)"
    if _LEGAL_OR_CHART.search(text):
        return "legal text, chart legend or page furniture"
    return fragment_reason(text, source)       # 'garbled' or 'table' for PDF sources


def load_pool(conn, source: str) -> pd.DataFrame:
    """One row per sentence: its text, base FinBERT call, and the pipeline's top aspect."""
    return pd.read_sql_query("""
        SELECT s.sentence_id, s.text, s.bank, s.source, s.url, s.published_at, d.title AS doc_title,
               (SELECT sa.aspect FROM sentence_aspects sa WHERE sa.sentence_id = s.sentence_id
                ORDER BY sa.similarity DESC LIMIT 1) AS original_aspect,
               (SELECT ase.label FROM aspect_sentiment ase WHERE ase.sentence_id = s.sentence_id LIMIT 1)
                   AS base_finbert_label,
               (SELECT ase.confidence FROM aspect_sentiment ase WHERE ase.sentence_id = s.sentence_id LIMIT 1)
                   AS base_finbert_confidence
        FROM sentences s JOIN documents d ON d.doc_id = s.doc_id
        WHERE s.source = ?
        ORDER BY s.sentence_id""", conn, params=(source,))


def export(source: str, train_dev: int, test: int, seed: int = 42, out_dir: str | None = None) -> dict:
    out_dir = out_dir or os.path.join(LABELED_DIR, source)
    os.makedirs(out_dir, exist_ok=True)
    conn = get_connection()
    try:
        pool = load_pool(conn, source)
    finally:
        conn.close()

    reasons = pool["text"].map(lambda t: junk_reason(t, source))
    dropped = reasons.value_counts().to_dict()
    usable = pool[reasons.isna()].reset_index(drop=True)
    logger.info("%d sentences, %d usable, dropped: %s", len(pool), len(usable), dropped)

    rows = usable.to_dict("records")
    random.Random(seed).shuffle(rows)
    if len(rows) < train_dev + test:
        logger.warning("only %d usable sentences for %d requested", len(rows), train_dev + test)

    # TEST FIRST, purely at random: this is the evaluation set.
    test_rows, rest = rows[:test], rows[test:]

    by_label: dict = {}
    for r in rest:
        by_label.setdefault(r["base_finbert_label"], []).append(r)
    per_class = train_dev // 3
    train_rows = [r for label in ("positive", "negative", "neutral") for r in by_label.get(label, [])[:per_class]]
    used = {r["sentence_id"] for r in train_rows}
    train_rows += [r for r in rest if r["sentence_id"] not in used][:max(train_dev - len(train_rows), 0)]

    # Broker reports repeat themselves with small edits ("We believe there are downside risks to
    # earnings in an escalating trade war environment given the huge and broad US tariffs"), which
    # the pipeline's exact-text dedup misses. A near-copy of a test sentence in train would leak
    # the answer, so the TRAIN side is dropped (as with split leakage, never the test side), and
    # near-copies inside train are collapsed to the first. Dropped rows are not refilled.
    kept, dropped_vs_test, dropped_within = [], 0, 0
    for r in train_rows:
        if any(jaccard(r["text"], t["text"]) >= NEAR_DUP_VS_TEST for t in test_rows):
            dropped_vs_test += 1
        elif any(jaccard(r["text"], k["text"]) >= NEAR_DUP_WITHIN for k in kept):
            dropped_within += 1
        else:
            kept.append(r)
    train_rows = kept

    def candidate(r: dict, split: str, method: str, blind: bool) -> dict:
        row = {c: "" for c in CANDIDATE_COLUMNS}
        row.update({k: r[k] for k in ("sentence_id", "text", "bank", "source", "url", "published_at", "doc_title")})
        row.update({"split": split, "sampling_method": method})
        if not blind:
            row.update({"aspect": r["original_aspect"], "original_aspect": r["original_aspect"],
                        "base_finbert_label": r["base_finbert_label"],
                        "base_finbert_confidence": r["base_finbert_confidence"]})
        return row

    cand = [candidate(r, "test", "random", True) for r in test_rows] + \
           [candidate(r, "train_dev", "stratified", False) for r in train_rows]
    cand_path = os.path.join(out_dir, "candidates.csv")
    pd.DataFrame(cand, columns=CANDIDATE_COLUMNS).to_csv(cand_path, index=False, quoting=csv.QUOTE_MINIMAL)

    blind = pd.DataFrame([{**{c: "" for c in BLIND_COLUMNS},
                           **{k: r[k] for k in ("sentence_id", "text", "bank", "source", "doc_title",
                                                "published_at", "url")}} for r in test_rows],
                         columns=BLIND_COLUMNS)
    blind_path = os.path.join(out_dir, "test_blind.csv")
    blind.to_csv(blind_path, index=False, quoting=csv.QUOTE_MINIMAL)

    return {"pool": len(pool), "usable": len(usable), "dropped": dropped, "test": len(test_rows),
            "train_dev": len(train_rows), "train_dropped_near_copy_of_test": dropped_vs_test,
            "train_dropped_near_copy_in_train": dropped_within, "candidates": cand_path, "blind": blind_path,
            "train_dev_base_finbert": pd.Series([r["base_finbert_label"] for r in train_rows]).value_counts().to_dict()}


if __name__ == "__main__":
    setup_logging()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", required=True)
    ap.add_argument("--train-dev", type=int, default=300)
    ap.add_argument("--test", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    for k, v in export(args.source, args.train_dev, args.test, args.seed).items():
        logger.info("  %-22s %s", k, v)
