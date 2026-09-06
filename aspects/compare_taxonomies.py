"""
Compares candidate aspect taxonomies quantitatively, using real cluster
content from `python -m aspects.discover` (run live 2026-09-06, see
docs/data-viability.md and config/aspects.yaml's header comment) as the
source for candidate B/C's seed terms — not invented, drawn from actual
cluster exemplar sentences.

THIS DOES NOT DECIDE ANYTHING. It produces a comparison table so the team/
mentor can make the aspect-taxonomy call with evidence in front of them,
per the MVP plan's "Aspect taxonomy sign-off" open decision. Nothing here
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

USAGE:
  python -m aspects.compare_taxonomies
"""

import itertools

import numpy as np

from aspects.embed import embed_sentences
from aspects.embed_store import load_for_search

SIMILARITY_FLOOR = 0.35

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
        # Seeds drawn from real cluster 4/6/8 exemplar sentences (discover.py, 2026-09-06).
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


def evaluate_candidate(name: str, seed_dict: dict, sentence_vectors: np.ndarray) -> dict:
    centroids = _build_centroids(seed_dict)

    # Centroid separation: mean pairwise cosine distance (1 - similarity) across all aspect pairs.
    pairs = list(itertools.combinations(centroids.values(), 2))
    separations = [1 - _cosine(a, b) for a, b in pairs] if pairs else [0.0]
    avg_separation = float(np.mean(separations))

    n_matched_per_sentence = []
    top_similarities = []
    n_other = 0
    for vec in sentence_vectors:
        sims = {aspect: _cosine(vec, c) for aspect, c in centroids.items()}
        matched = [a for a, s in sims.items() if s >= SIMILARITY_FLOOR]
        top_similarities.append(max(sims.values()))
        if matched:
            n_matched_per_sentence.append(len(matched))
        else:
            n_other += 1
            n_matched_per_sentence.append(0)

    return {
        "candidate": name,
        "n_aspects": len(centroids),
        "avg_aspects_per_sentence": round(float(np.mean(n_matched_per_sentence)), 2),
        "pct_other": round(100 * n_other / len(sentence_vectors), 1),
        "avg_centroid_separation": round(avg_separation, 4),
        "avg_top_similarity": round(float(np.mean(top_similarities)), 4),
    }


def run():
    sentence_ids, vectors = load_for_search()
    if len(sentence_ids) == 0:
        print("No embedded sentences found — run `python -m aspects.embed_store` first.")
        return

    print(f"Comparing {len(CANDIDATES)} candidate taxonomies against {len(vectors)} sentences.\n")
    results = [evaluate_candidate(name, seeds, vectors) for name, seeds in CANDIDATES.items()]

    header = f"{'candidate':26s} {'#asp':>5s} {'avg/sent':>9s} {'%other':>7s} {'separation':>11s} {'top_sim':>8s}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(f"{r['candidate']:26s} {r['n_aspects']:5d} {r['avg_aspects_per_sentence']:9.2f} "
              f"{r['pct_other']:6.1f}% {r['avg_centroid_separation']:11.4f} {r['avg_top_similarity']:8.4f}")

    print("\nHow to read this:")
    print("  - avg_aspects_per_sentence closer to 1 = more discriminating (candidate A's known")
    print("    problem, quantified here — most sentences matching ~4 of 5 aspects near-equally).")
    print("  - avg_centroid_separation higher = the aspects are more distinct from each other.")
    print("  - pct_other very high or very low are both worth a second look: too high means the")
    print("    taxonomy doesn't fit the corpus; too low (~0%) means the floor never triggers.")
    print("\nThis is decision support, not a decision — see config/aspects.yaml's header comment")
    print("and the MVP plan's 'Aspect taxonomy sign-off' open decision.")


if __name__ == "__main__":
    run()
