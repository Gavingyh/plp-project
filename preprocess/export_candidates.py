"""
Export (sentence, aspect) candidates for human labeling.

Implements the sampling design ("The sampling problem, and
the trap in solving it") - this is NOT optional detail, it's the difference
between a valid and an inflated evaluation:

  - TRAIN/DEV split: model-assisted stratified sampling, oversampling what
    base FinBERT calls non-neutral, to avoid a 60-70% neutral training set
    starving the positive/negative classes.
  - TEST split: sampled PURELY AT RANDOM, independent of any model
    screening, and frozen once exported. All headline metrics are
    reported on this set. This cannot be retrofitted after the fact - if the
    test set is drawn from model-screened candidates, the fine-tuned model's
    reported F1 is inflated relative to the base-model baseline it's meant to
    be compared against.

Requires sentence_aspects (aspects/assign.py) and, for stratification,
aspect_sentiment (sentiment/score.py, which currently holds base-FinBERT
zero-shot predictions - exactly the "model-assisted" signal this step wants).

USAGE:
  python -m preprocess.export_candidates --train-dev 800 --test 200
"""

import argparse
import csv
import os
import random

from ingest.db import get_connection

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "labeled")

_CSV_COLUMNS = ["sentence_id", "aspect", "text", "bank", "source", "url", "published_at",
                "split", "sampling_method", "base_finbert_label", "base_finbert_confidence",
                "label", "annotator", "labeled_at", "llm_prelabel", "was_corrected"]


def _all_candidates(conn) -> list[dict]:
    rows = conn.execute("""
        SELECT sa.sentence_id, sa.aspect, s.text, s.bank, s.source, s.url, s.published_at,
               ase.label, ase.confidence
        FROM sentence_aspects sa
        JOIN sentences s ON s.sentence_id = sa.sentence_id
        LEFT JOIN aspect_sentiment ase ON ase.sentence_id = sa.sentence_id AND ase.aspect = sa.aspect
    """).fetchall()
    cols = ["sentence_id", "aspect", "text", "bank", "source", "url", "published_at",
            "base_finbert_label", "base_finbert_confidence"]
    return [dict(zip(cols, r)) for r in rows]


def export(train_dev_target: int, test_target: int, seed: int = 42) -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = get_connection()
    try:
        candidates = _all_candidates(conn)
    finally:
        conn.close()

    rng = random.Random(seed)
    rng.shuffle(candidates)

    if len(candidates) < train_dev_target + test_target:
        logger.warning(f"WARNING: only {len(candidates)} candidates available, "
              f"requested {train_dev_target + test_target}. Exporting what exists — "
              "run more ingestion before treating this as the real labeling set.")

    # TEST FIRST, purely at random, before any model-assisted selection touches
    # the pool - see module docstring. This is the frozen evaluation set.
    test_rows = candidates[:test_target]
    remaining = candidates[test_target:]

    # TRAIN/DEV: stratify by base FinBERT's own call, oversampling non-neutral
    # so the labeled set isn't 60-70% neutral by default.
    by_label = {"positive": [], "neutral": [], "negative": [], None: []}
    for c in remaining:
        by_label.setdefault(c["base_finbert_label"], []).append(c)

    target_per_class = train_dev_target // 3
    train_dev_rows = []
    for label in ("positive", "negative", "neutral"):
        pool = by_label.get(label, [])
        train_dev_rows.extend(pool[:target_per_class])
    # Top up from whatever's left (including unscored candidates) if any class was short.
    used_ids = {c["sentence_id"] + c["aspect"] for c in train_dev_rows}
    leftover = [c for c in remaining if c["sentence_id"] + c["aspect"] not in used_ids]
    shortfall = train_dev_target - len(train_dev_rows)
    if shortfall > 0:
        train_dev_rows.extend(leftover[:shortfall])

    def to_csv_row(c, split, sampling_method):
        return {
            "sentence_id": c["sentence_id"], "aspect": c["aspect"], "text": c["text"],
            "bank": c["bank"], "source": c["source"], "url": c["url"],
            "published_at": c["published_at"], "split": split, "sampling_method": sampling_method,
            "base_finbert_label": c["base_finbert_label"] or "",
            "base_finbert_confidence": c["base_finbert_confidence"] or "",
            "label": "", "annotator": "", "labeled_at": "", "llm_prelabel": "", "was_corrected": "",
        }

    all_rows = (
        [to_csv_row(c, "test", "random") for c in test_rows] +
        [to_csv_row(c, "train_dev", "stratified") for c in train_dev_rows]
    )

    out_path = os.path.join(OUT_DIR, "candidates.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    return {
        "total_candidates_available": len(candidates),
        "test_exported": len(test_rows),
        "train_dev_exported": len(train_dev_rows),
        "output": out_path,
    }


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dev", type=int, default=800)
    parser.add_argument("--test", type=int, default=200)
    args = parser.parse_args()
    stats = export(args.train_dev, args.test)
    logger.info("=" * 50)
    for k, v in stats.items():
        logger.info(f"  {k:28s} {v}")
    logger.info("=" * 50)
    logger.info("Next: open data/labeled/candidates.csv, fill in the `label` column")
    logger.info("(positive/neutral/negative) per docs/annotation-guideline.md.")
