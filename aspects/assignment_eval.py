"""
How well seed-centroid assignment (aspects/assign.py) matches the human
aspect labels, across similarity floors. Read-only: it builds the centroids
exactly as assign.py does, reads the cached sentence embeddings, and writes
nothing.

For the labelled rows in data/labeled/candidates.csv, at each floor:
  - top-1 accuracy: the most similar centroid is the human aspect, where a
    sentence that clears no floor counts as `other`;
  - recall: the human aspect is among the aspects the sentence matches
    (for a human `other`, that nothing matches);
  - mean aspects matched per sentence, and the share falling to `other`.
The last two are also reported for the whole corpus.

USAGE:
  HF_HUB_OFFLINE=1 python -m aspects.assignment_eval
  HF_HUB_OFFLINE=1 python -m aspects.assignment_eval --floors 0.6 0.65 0.7
"""

import argparse
import os
from collections import Counter

import numpy as np
import pandas as pd

from aspects.assign import _build_centroids, _load_config
from aspects.embed_store import load_for_search

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
DEFAULT_FLOORS = [round(0.55 + 0.05 * i, 2) for i in range(8)]   # 0.55 .. 0.90
OTHER = "other"


def cosine_matrix(vectors: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    """(n_sentences, n_aspects) cosine similarities."""
    v = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9)
    c = centroids / (np.linalg.norm(centroids, axis=1, keepdims=True) + 1e-9)
    return v @ c.T


def assign_at(sims: np.ndarray, aspects: list[str], floor: float):
    """What assign.py would produce at this floor: the matched set per
    sentence, and the top-1 aspect (or `other` when nothing clears it)."""
    matched = sims >= floor
    best = sims.argmax(axis=1)
    top1 = [aspects[b] if matched[i].any() else OTHER for i, b in enumerate(best)]
    return matched, top1


def label_metrics(sims: np.ndarray, aspects: list[str], human: list[str], floor: float) -> dict:
    matched, top1 = assign_at(sims, aspects, floor)
    index = {a: i for i, a in enumerate(aspects)}
    recall_hits = [(not matched[i].any()) if h == OTHER else bool(h in index and matched[i, index[h]])
                   for i, h in enumerate(human)]
    return {"floor": floor,
            "top1_accuracy": float(np.mean([t == h for t, h in zip(top1, human)])),
            "recall": float(np.mean(recall_hits)),
            "mean_matched": float(matched.sum(axis=1).mean()),
            "pct_other": float(np.mean([t == OTHER for t in top1]))}


def corpus_metrics(sims: np.ndarray, floor: float) -> dict:
    matched = sims >= floor
    return {"floor": floor, "mean_matched": float(matched.sum(axis=1).mean()),
            "pct_other": float((~matched.any(axis=1)).mean())}


def confusion(sims: np.ndarray, aspects: list[str], human: list[str], floor: float) -> pd.DataFrame:
    _, top1 = assign_at(sims, aspects, floor)
    return pd.crosstab(pd.Series(human, name="human"), pd.Series(top1, name="centroid top-1"))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--floors", type=float, nargs="+", default=DEFAULT_FLOORS)
    p.add_argument("--confusion-floor", type=float, default=None,
                   help="floor for the confusion table (default: the config's)")
    args = p.parse_args()

    config = _load_config()
    centroids = _build_centroids(config)
    aspects = list(centroids)
    ids, vectors = load_for_search()
    sims = cosine_matrix(vectors, np.stack([centroids[a] for a in aspects]))
    row = {sid: i for i, sid in enumerate(ids)}

    labels = pd.read_csv(LABELS_PATH).drop_duplicates("sentence_id")
    labels = labels[labels["sentence_id"].isin(row)]
    lab_sims = sims[[row[s] for s in labels["sentence_id"]]]
    human = labels["aspect"].tolist()
    print(f"Aspects ({len(aspects)}): {', '.join(aspects)}")
    print(f"Labelled sentences with an embedding: {len(human)}; corpus sentences: {len(ids)}")
    print(f"Human aspect distribution: {dict(Counter(human).most_common())}\n")

    print("| floor | top-1 accuracy | recall | mean matched (labelled) | % other (labelled) "
          "| mean matched (corpus) | % other (corpus) |")
    print("|---|---|---|---|---|---|---|")
    for f in args.floors:
        m, c = label_metrics(lab_sims, aspects, human, f), corpus_metrics(sims, f)
        print(f"| {f:.2f} | {m['top1_accuracy']:.3f} | {m['recall']:.3f} | {m['mean_matched']:.2f} "
              f"| {100 * m['pct_other']:.1f}% | {c['mean_matched']:.2f} | {100 * c['pct_other']:.1f}% |")

    cf = args.confusion_floor if args.confusion_floor is not None else config.get("similarity_floor", 0.65)
    print(f"\nTop-1 confusion at floor {cf:.2f} (rows: human aspect, columns: centroid top-1):\n")
    print(confusion(lab_sims, aspects, human, cf).to_string())


if __name__ == "__main__":
    main()
