"""
Aspect assignment: deterministic nearest-centroid assignment against
the FROZEN taxonomy in config/aspects.yaml. Runs every batch - unlike
discover.py's clustering, this does NOT change the taxonomy, only which
bucket each sentence falls into. See docs/DESIGN.md, "The key
architectural point".

Bootstrap note: until aspects/discover.py has been run on a large enough
corpus and its cluster centroids substituted into config/aspects.yaml,
centroids here come from embedding each aspect's seed_terms and averaging -
a reasonable starting point, not the final data-driven taxonomy the plan
calls for.

A sentence may be assigned to more than one aspect if it clears the
similarity floor for more than one non-OTHER aspect - docs/DESIGN.md, step 6:
"NIM held up but provisions rose" is about two aspects.

USAGE:
  python -m aspects.assign
"""

import os

import numpy as np
import yaml

from aspects.embed import embed_sentences
from aspects.embed_store import load_for_search, update as update_embeddings
from ingest.db import get_connection, init_db, now_iso

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "aspects.yaml")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sentence_aspects (
    sentence_id  TEXT NOT NULL REFERENCES sentences(sentence_id),
    aspect       TEXT NOT NULL,
    similarity   REAL NOT NULL,
    assigned_at  TEXT NOT NULL,
    PRIMARY KEY (sentence_id, aspect)
);
CREATE INDEX IF NOT EXISTS idx_sentence_aspects_aspect ON sentence_aspects(aspect);
"""


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _build_centroids(config: dict) -> dict[str, np.ndarray]:
    centroids = {}
    for key, cfg in config["aspects"].items():
        if key == "other":
            continue
        vecs = embed_sentences(cfg["seed_terms"])
        centroids[key] = vecs.mean(axis=0)
    return centroids


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def run() -> dict:
    config = _load_config()
    floor = config.get("similarity_floor", 0.35)
    centroids = _build_centroids(config)

    logger.info("Ensuring all sentences are embedded...")
    logger.info("Embedding cache: %s", update_embeddings())
    sentence_ids, vectors = load_for_search()

    init_db()
    conn = get_connection()
    conn.executescript(_SCHEMA)

    already = {r[0] for r in conn.execute("SELECT DISTINCT sentence_id FROM sentence_aspects").fetchall()}
    todo_idx = [i for i, sid in enumerate(sentence_ids) if sid not in already]

    stats = {"already_assigned": len(already), "newly_assigned": 0, "assignments_written": 0,
              "fell_to_other": 0}
    rows = []
    for i in todo_idx:
        sid, vec = sentence_ids[i], vectors[i]
        sims = {aspect: _cosine(vec, centroid) for aspect, centroid in centroids.items()}
        matched = {a: s for a, s in sims.items() if s >= floor}
        ts = now_iso()
        if matched:
            for aspect, sim in matched.items():
                rows.append((sid, aspect, sim, ts))
        else:
            best_aspect, best_sim = max(sims.items(), key=lambda x: x[1])
            rows.append((sid, "other", best_sim, ts))
            stats["fell_to_other"] += 1
        stats["newly_assigned"] += 1

    if rows:
        conn.executemany(
            "INSERT OR IGNORE INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) "
            "VALUES (?,?,?,?)", rows,
        )
        conn.commit()
    stats["assignments_written"] = len(rows)
    conn.close()
    return stats


if __name__ == "__main__":
    setup_logging()
    stats = run()
    logger.info("=" * 50)
    for k, v in stats.items():
        logger.info(f"  {k:22s} {v}")
    logger.info("=" * 50)
