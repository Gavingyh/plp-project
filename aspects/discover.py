"""
Phase 3 aspect discovery — run ONCE offline to derive the aspect taxonomy,
then freeze it into config/aspects.yaml. This is the unsupervised text-mining
deliverable: letting the data propose the aspect set rather than assuming it.

After this, aspects/assign.py does the per-batch, deterministic nearest-
centroid assignment against the frozen taxonomy — clustering itself does NOT
re-run every batch (see docs/DESIGN.md, "The key architectural point":
users can't be shown a renumbered cluster on Tuesday).

USAGE:
  python -m aspects.discover                 # cluster + print inspection report
  python -m aspects.discover --min-cluster-size 8
"""

import argparse
from collections import Counter

import hdbscan
import numpy as np
import umap
from sklearn.feature_extraction.text import TfidfVectorizer

from aspects.embed_store import load_for_search, update as update_embeddings
from config.logging_config import get_logger, setup_logging
from ingest.db import get_connection

logger = get_logger(__name__)

_STOPWORDS_EXTRA = {"dbs", "ocbc", "uob", "bank", "banks", "singapore", "sgx"}


def _top_terms(texts: list[str], n: int = 8) -> list[str]:
    """TF-IDF top terms for a cluster, bank names excluded since they'd
    dominate every cluster without being aspect-discriminating."""
    if len(texts) < 2:
        return []
    vec = TfidfVectorizer(stop_words="english", max_features=200, ngram_range=(1, 2))
    try:
        X = vec.fit_transform(texts)
    except ValueError:
        return []
    scores = np.asarray(X.sum(axis=0)).ravel()
    terms = vec.get_feature_names_out()
    ranked = sorted(zip(terms, scores), key=lambda x: -x[1])
    return [t for t, _ in ranked if t not in _STOPWORDS_EXTRA][:n]


def run(min_cluster_size: int = 10) -> None:
    logger.info("Updating embedding cache for any un-embedded sentences...")
    logger.info("Embedding cache: %s", update_embeddings())

    sentence_ids, vectors = load_for_search()
    if len(sentence_ids) < min_cluster_size * 2:
        print(f"\nOnly {len(sentence_ids)} sentences embedded — too few to cluster "
              f"meaningfully yet (need several times min_cluster_size={min_cluster_size}). "
              "Run more ingestion/preprocessing first.")
        return

    # One full scan, filtered in Python, rather than an `IN (?,?,...)` over
    # every cached sentence_id. That form binds one SQL variable per id and
    # dies with "too many SQL variables" once the corpus passes SQLite's
    # SQLITE_MAX_VARIABLE_NUMBER (32,766 here) — which it did at 36,884
    # sentences, making this whole script unrunnable exactly when the corpus
    # finally got big enough to cluster meaningfully.
    wanted = set(sentence_ids)
    conn = get_connection()
    try:
        rows = conn.execute("SELECT sentence_id, text, bank FROM sentences").fetchall()
    finally:
        conn.close()
    text_by_id = {r[0]: r[1] for r in rows if r[0] in wanted}
    bank_by_id = {r[0]: r[2] for r in rows if r[0] in wanted}

    # An embedded sentence whose row has since been deleted would otherwise
    # KeyError below. embed_store prunes these, but a mid-run deletion is
    # cheap to survive: drop the vector alongside the id so the two stay
    # aligned.
    missing = [i for i, sid in enumerate(sentence_ids) if sid not in text_by_id]
    if missing:
        logger.warning("%d embedded sentence(s) no longer in the sentences table — dropping",
                       len(missing))
        keep = [i for i in range(len(sentence_ids)) if i not in set(missing)]
        sentence_ids = [sentence_ids[i] for i in keep]
        vectors = vectors[keep]

    texts = [text_by_id[sid] for sid in sentence_ids]

    logger.info("Reducing %d x %d embeddings with UMAP...", vectors.shape[0], vectors.shape[1])
    reducer = umap.UMAP(n_neighbors=15, min_dist=0.0, n_components=10, metric="cosine",
                         random_state=42)
    reduced = reducer.fit_transform(vectors)

    logger.info("Clustering with HDBSCAN (min_cluster_size=%d)...", min_cluster_size)
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean")
    labels = clusterer.fit_predict(reduced)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int(np.sum(labels == -1))
    print(f"\n{'=' * 70}\nFound {n_clusters} clusters, {n_noise} noise points "
          f"({100 * n_noise / len(labels):.0f}% of sentences)\n{'=' * 70}")

    for cluster_id in sorted(set(labels)):
        if cluster_id == -1:
            continue
        idxs = np.where(labels == cluster_id)[0]
        cluster_texts = [texts[i] for i in idxs]
        cluster_banks = Counter(bank_by_id[sentence_ids[i]] for i in idxs)
        print(f"\n--- Cluster {cluster_id} (n={len(idxs)}) ---")
        print(f"  Bank mix: {dict(cluster_banks)}")
        print(f"  Top terms: {', '.join(_top_terms(cluster_texts))}")
        print("  Sample sentences:")
        for i in idxs[:5]:
            print(f"    - {texts[i][:110]}")

    print(f"\n{'=' * 70}")
    print("NEXT STEP (manual): inspect the clusters above, name them, and write")
    print("the frozen taxonomy to config/aspects.yaml (see aspects/assign.py).")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-cluster-size", type=int, default=10)
    args = parser.parse_args()
    run(min_cluster_size=args.min_cluster_size)
