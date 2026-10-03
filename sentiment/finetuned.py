"""
Fine-tuned scores for assigned pairs that don't have them yet.

scripts/rescore.py scores the whole corpus with the fine-tuned models once.
After that, while config/model_version.py serves a fine-tuned version, new
sentences need its scores too, or they drop out of every served number
without an error; sentiment/score.py calls this after its base FinBERT pass.
The models and margin come from FINETUNED in config/model_version.py. The
probabilities go through aggregate.preview's checked, cached scorer: the
three seeds averaged, refusing probabilities that don't sum to 1.
"""

import os

import pandas as pd

from config.model_version import FINETUNED

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def missing_pairs(conn, version: str) -> pd.DataFrame:
    """(sentence_id, aspect, text) for assigned pairs with no row for this version."""
    return pd.read_sql("""
        SELECT asg.sentence_id, asg.aspect, s.text
        FROM sentence_aspects asg
        JOIN sentences s ON s.sentence_id = asg.sentence_id
        WHERE NOT EXISTS (SELECT 1 FROM aspect_sentiment ase
                          WHERE ase.sentence_id = asg.sentence_id AND ase.aspect = asg.aspect
                            AND ase.model_version = ?)""", conn, params=(version,))


def score_missing(conn, version: str, now: str) -> int:
    """Score and write every missing pair for this version; returns how many."""
    if version not in FINETUNED:
        raise ValueError(f"{version!r} is served but has no models in FINETUNED (config/model_version.py)")
    pairs = missing_pairs(conn, version)
    if pairs.empty:
        return 0
    import aggregate.preview as pv
    spec = FINETUNED[version]
    models = [os.path.join(BASE_DIR, m) for m in spec["models"]]
    labels = pv.finetuned_labels(pairs, models, pv.scores_cache_path(models), spec["margin"])
    with conn:
        conn.executemany("INSERT OR IGNORE INTO aspect_sentiment "
                         "(sentence_id, aspect, label, confidence, model_version, scored_at) VALUES (?,?,?,?,?,?)",
                         [(r.sentence_id, r.aspect, r.label, round(float(r.confidence), 4), version, now)
                          for r in labels.itertuples(index=False)])
    return len(labels)
