"""
Compares candidate aspect taxonomies quantitatively, using real cluster
content from `python -m aspects.discover` (see
docs/data-viability.md and config/aspects.yaml's header comment) as the
source for candidate B/C's seed terms — not invented, drawn from actual
cluster exemplar sentences.

THIS DOES NOT DECIDE ANYTHING. It produces a comparison table so the team/
mentor can make the aspect-taxonomy call with evidence in front of them,
per the design notes' "Aspect taxonomy sign-off" open decision. Nothing here
overwrites config/aspects.yaml.

Candidates:
  A — proposal-aligned (current config/aspects.yaml): dividend_policy,
      asset_quality, net_interest_margin, management_guidance, other.
      Known issue (measured): centroids barely separate on the current
      corpus, most sentences match ~4 of 5 aspects near-equally.
  B — data-derived coarse: the two real clusters that DID emerge cleanly
      (investment_discussion vs. consumer_banking_service), plus other.
  C — data-derived fine: B split further using the finer real clusters
      (dividend_and_valuation, service_and_trust, banking_utility), plus other.

Metrics reported per candidate:
  - avg_aspects_per_sentence: how many aspects (excl. other) each sentence
    clears the similarity floor for. Lower = more discriminating. Candidate
    A's real problem, quantified: most sentences match nearly everything.
  - pct_other: fraction assigned to the fallback bucket.
  - avg_centroid_separation: mean pairwise cosine DISTANCE between aspect
    centroids (higher = aspects are more distinct from each other in
    embedding space, a proxy for how separable the taxonomy actually is).
  - avg_top_similarity: mean best-match similarity score — how confidently
    sentences fit their top aspect.

THE FLOOR MATTERS AS MUCH AS THE TAXONOMY. Every metric except centroid
separation depends on the similarity floor, so this reads the live floor from
config/aspects.yaml by default rather than carrying its own. It previously
hardcoded 0.35 while the config had been recalibrated to 0.65, which made
every candidate look equally undiscriminating and quietly reproduced the
original "0.35 separates nothing" result as though it were a new finding.

USAGE:
  python -m aspects.compare_taxonomies              # at the configured floor
  python -m aspects.compare_taxonomies --sweep      # across a range of floors
  python -m aspects.compare_taxonomies --floor 0.7  # at one specific floor
"""

import argparse
import itertools
import os

import numpy as np
import yaml

from config.logging_config import get_logger, setup_logging
from aspects.embed import embed_sentences
from aspects.embed_store import load_for_search

logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "aspects.yaml")

# The floor this comparison is measured at MUST default to the one the
# pipeline actually uses, or the table silently answers a different question
# than the reader thinks. This was hardcoded to 0.35 while
# config/aspects.yaml had been recalibrated to 0.65, so every candidate
# matched nearly every aspect and candidate A looked no worse than it had
# before the recalibration - reproducing the known "0.35 does not
# discriminate" result and presenting it as a fresh finding.
DEFAULT_SWEEP = (0.35, 0.50, 0.60, 0.65, 0.70, 0.75, 0.80)


def configured_floor() -> float:
    """The floor aspects/assign.py will really use, read from the same file."""
    with open(CONFIG_PATH) as f:
        return float(yaml.safe_load(f)["similarity_floor"])

CANDIDATES = {
    "A_proposal_aligned": {
        "dividend_policy": ["dividend payout ratio", "special dividend", "dividend yield",
                             "capital return to shareholders", "share buyback"],
        "asset_quality": ["non-performing loans", "credit provisions", "asset quality",
                           "loan loss allowance", "NPL ratio"],
        "net_interest_margin": ["net interest margin", "interest rate spread", "NIM compression",
                                 "funding costs", "loan growth"],
        "management_guidance": ["management guidance", "full year outlook", "CEO commentary",
                                 "forward guidance", "strategic priorities"],
    },
    "B_data_derived_coarse": {
        # Seeds drawn from real cluster 4/6/8 exemplar sentences (from discover.py output).
        "investment_discussion": [
            "DBS beats VWRA over the past 5 years including dividend yield",
            "DBS Group Research raised its year-end target for the Straits Times Index",
            "DBS said Singapore equities remained supported by attractive dividend yields",
            "OCBC accounted for a large share of the projected upside in the target",
            "buy dbs equals buying the country",
            "at what age should one start buying dividend stocks like DBS",
        ],
        # Seeds drawn from real cluster 0/2/5/7 exemplar sentences.
        "consumer_banking_service": [
            "waived if you are DBS Treasures",
            "scam call impersonating DBS, caller knew my full name and NRIC",
            "I have a DBS multicurrency account for transfers",
            "DBS Multiplier or POSB SAYE as a high yield savings account",
            "I met my DBS relationship manager today",
            "UOB ONE card cashback on quarterly spend",
        ],
    },
    "C_data_derived_fine": {
        "dividend_and_valuation": [
            "DBS beats VWRA over the past 5 years including dividend yield",
            "DBS Group Research raised its year-end target for the Straits Times Index",
            "at what age should one start buying dividend stocks like DBS",
            "OCBC accounted for a large share of the projected upside in the target",
        ],
        "service_and_trust": [
            "scam call impersonating DBS, caller knew my full name and NRIC",
            "I met my DBS relationship manager today",
            "widespread criticism that UOB is run like a SME",
        ],
        "banking_utility": [
            "I have a DBS multicurrency account for transfers to IBKR",
            "DBS Multiplier or POSB SAYE as a high yield savings account",
            "UOB ONE card cashback on quarterly spend",
            "transfer USD from DBS to Interactive Brokers free of charge",
        ],
    },
}


def _build_centroids(seed_dict: dict[str, list[str]]) -> dict[str, np.ndarray]:
    return {aspect: embed_sentences(seeds).mean(axis=0) for aspect, seeds in seed_dict.items()}


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _unit(m: np.ndarray) -> np.ndarray:
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


def evaluate_candidate(name: str, seed_dict: dict, sentence_vectors: np.ndarray,
                        floors: tuple[float, ...]) -> list[dict]:
    """One row per floor. Similarities are computed once and thresholded
    repeatedly - the floor changes which matches count, not the geometry, so
    re-embedding per floor would only make a sweep slow enough to skip."""
    centroids = _build_centroids(seed_dict)
    names = list(centroids)

    # Centroid separation: mean pairwise cosine distance (1 - similarity) across all aspect pairs.
    pairs = list(itertools.combinations(centroids.values(), 2))
    separations = [1 - _cosine(a, b) for a, b in pairs] if pairs else [0.0]
    avg_separation = float(np.mean(separations))

    sims = _unit(sentence_vectors) @ _unit(np.stack([centroids[a] for a in names])).T
    top_similarities = sims.max(axis=1)

    rows = []
    for floor in floors:
        matched = (sims >= floor).sum(axis=1)
        rows.append({
            "candidate": name,
            "floor": floor,
            "n_aspects": len(centroids),
            "avg_aspects_per_sentence": round(float(matched.mean()), 2),
            "pct_other": round(100 * float((matched == 0).mean()), 1),
            "avg_centroid_separation": round(avg_separation, 4),
            "avg_top_similarity": round(float(top_similarities.mean()), 4),
        })
    return rows


def _print_table(rows: list[dict], show_floor: bool) -> None:
    head = f"{'candidate':26s} {'#asp':>5s}"
    if show_floor:
        head += f" {'floor':>6s}"
    head += f" {'avg/sent':>9s} {'%other':>7s} {'separation':>11s} {'top_sim':>8s}"
    print(head)
    print("-" * len(head))
    last = None
    for r in rows:
        if show_floor and last is not None and r["candidate"] != last:
            print()
        last = r["candidate"]
        line = f"{r['candidate']:26s} {r['n_aspects']:5d}"
        if show_floor:
            line += f" {r['floor']:6.2f}"
        line += (f" {r['avg_aspects_per_sentence']:9.2f} {r['pct_other']:6.1f}%"
                 f" {r['avg_centroid_separation']:11.4f} {r['avg_top_similarity']:8.4f}")
        print(line)


def run(floors: tuple[float, ...] | None = None, sweep: bool = False):
    sentence_ids, vectors = load_for_search()
    if len(sentence_ids) == 0:
        print("No embedded sentences found — run `python -m aspects.embed_store` first.")
        return

    live = configured_floor()
    floors = floors or (DEFAULT_SWEEP if sweep else (live,))

    logger.info("Comparing %d candidate taxonomies against %d sentences at floor(s) %s "
                "(config/aspects.yaml similarity_floor = %.2f).",
                len(CANDIDATES), len(vectors), ", ".join(f"{f:.2f}" for f in floors), live)

    rows = []
    for name, seeds in CANDIDATES.items():
        rows.extend(evaluate_candidate(name, seeds, vectors, floors))

    _print_table(rows, show_floor=len(floors) > 1)

    print(f"\nMeasured at the floor in config/aspects.yaml ({live:.2f}) unless --floor/--sweep "
          f"says otherwise.")
    print("\nHow to read this:")
    print("  - avg_aspects_per_sentence closer to 1 = more discriminating (candidate A's known")
    print("    problem, quantified here — most sentences matching ~4 of 5 aspects near-equally).")
    print("  - avg_centroid_separation higher = the aspects are more distinct from each other.")
    print("    It does NOT move with the floor: it describes the taxonomy's geometry, so it is")
    print("    the one column a floor change cannot flatter.")
    print("  - pct_other very high or very low are both worth a second look: too high means the")
    print("    taxonomy doesn't fit the corpus; too low (~0%) means the floor never triggers.")
    print("\nThis is decision support, not a decision — see config/aspects.yaml's header comment")
    print("and the design notes' 'Aspect taxonomy sign-off' open decision.")


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--floor", type=float, action="append", dest="floors",
                        help="evaluate at this floor (repeatable); default is "
                             "config/aspects.yaml's similarity_floor")
    parser.add_argument("--sweep", action="store_true",
                        help=f"evaluate across {DEFAULT_SWEEP}")
    args = parser.parse_args()
    run(floors=tuple(args.floors) if args.floors else None, sweep=args.sweep)
