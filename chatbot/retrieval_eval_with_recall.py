"""
Retrieval quality of FinBERT-vector search, measured on the 1,277 sentences
people labelled (Hit@K, MRR, precision@K, recall@K).

For each bank and each aspect with enough labelled sentences for that bank,
the question "What do people say about <bank>'s <aspect label>?" ranks that
bank's labelled sentences by FinBERT cosine plus a small word-overlap boost,
the score `search_evidence` used before it moved to a model built for search
(data/eval/search-models/compare.py measures the search in use). A sentence is relevant if
people gave it that aspect. Judging only the labelled pool keeps every
relevance judgement human: over the whole corpus most retrieved sentences
would have no judgement at all. A random ranking is the baseline.

Reads only. Needs the embedding cache (python -m aspects.embed_store).

USAGE:
  HF_HUB_OFFLINE=1 python -m chatbot.retrieval_eval_with_recall
"""

import argparse
import os
from math import comb

import numpy as np
import pandas as pd

from chatbot.retrieval import _LEXICAL_WEIGHT, _WORD, _cosine_sim, _lexical_overlap, ranking_query

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
KS = (1, 5, 10)
MIN_RELEVANT = 3


def rank(query_vec: np.ndarray, query: str, vecs: np.ndarray, texts: list[str]) -> np.ndarray:
    """Indices in the order search_evidence would return them (`query` feeds the word-overlap boost)."""
    words = set(_WORD.findall(query.lower()))
    score = _cosine_sim(query_vec, vecs) + _LEXICAL_WEIGHT * np.array([_lexical_overlap(words, t) for t in texts])
    return np.argsort(-score, kind="stable")


def metrics(relevant_in_order: list[bool], ks=KS) -> dict:
    """Hit@K, precision@K, recall@K and reciprocal rank for one ranked list."""
    out = {}
    total_rel = sum(relevant_in_order)
    first = next((i for i, r in enumerate(relevant_in_order) if r), None)
    out["rr"] = 0.0 if first is None else 1.0 / (first + 1)
    for k in ks:
        top = relevant_in_order[:k]
        out[f"hit@{k}"] = float(any(top))
        out[f"p@{k}"] = sum(top) / max(len(top), 1)   # a pool under k holds fewer
        out[f"recall@{k}"] = sum(top) / total_rel if total_rel else 0.0
    return out


def random_baseline(n: int, r: int, ks=KS) -> dict:
    """Expected metrics for a random ordering of n sentences, r of them relevant."""
    out = {f"hit@{k}": 1 - comb(n - r, min(k, n)) / comb(n, min(k, n)) for k in ks}
    out.update({f"p@{k}": r / n for k in ks})
    out.update({f"recall@{k}": min(k, n) / n for k in ks})
    # expected reciprocal rank of the first relevant item among n with r relevant
    out["rr"] = sum((1 / i) * (comb(n - i, r - 1) / comb(n, r)) for i in range(1, n - r + 2))
    return out


def evaluate(labels: pd.DataFrame, vec_by_id: dict, embed, aspect_label: dict,
             query_style: str = "question", stored_aspects: dict | None = None) -> pd.DataFrame:
    """One row per (bank, aspect) query. `query_style` "question" asks like a
    user; "label" uses the aspect's name alone. With `stored_aspects`
    ({sentence_id: set of stored aspects}), only sentences stored under the
    asked aspect are ranked, as search_evidence(aspect=...) does."""
    rows = []
    for bank, bank_pool in labels.groupby("bank"):
        bank_pool = bank_pool[bank_pool["sentence_id"].isin(vec_by_id)]
        for aspect, n_rel in bank_pool["aspect"].value_counts().items():
            if aspect == "other" or n_rel < MIN_RELEVANT:
                continue
            pool = bank_pool
            if stored_aspects is not None:
                pool = pool[[aspect in stored_aspects.get(s, ()) for s in pool["sentence_id"]]]
            pool = pool.reset_index(drop=True)
            r = int((pool["aspect"] == aspect).sum())
            if pool.empty or r == 0:
                rows.append({"bank": bank, "aspect": aspect, "pool": len(pool), "relevant": r,
                             **metrics([]), **{f"random_{k}": 0.0 for k in metrics([])}})
                continue
            vecs = np.stack([vec_by_id[s] for s in pool["sentence_id"]])
            label = aspect_label[aspect]
            question = f"What do people say about {bank}'s {label.lower()}?"
            query = label if query_style == "label" else question
            if query_style == "aspect-query":            # as search_evidence with CHATBOT_ASPECT_QUERY=1
                query = ranking_query(question, aspect)
            order = rank(embed(query), query, vecs, pool["text"].tolist())
            rel = (pool["aspect"].values[order] == aspect).tolist()
            rows.append({"bank": bank, "aspect": aspect, "pool": len(pool), "relevant": r,
                         **metrics(rel), **{f"random_{k}": v for k, v in random_baseline(len(pool), r).items()}})
    return pd.DataFrame(rows)


def main():
    argparse.ArgumentParser(description=__doc__.split("\n\n")[0]).parse_args()
    from aspects.embed import embed_sentences
    from aspects.embed_store import load_for_search
    from config import aspect_taxonomy
    aspect_label = aspect_taxonomy.labels()
    labels = pd.read_csv(LABELS_PATH)
    ids, vecs = load_for_search()
    wanted = set(labels["sentence_id"])
    vec_by_id = {sid: vecs[i] for i, sid in enumerate(ids) if sid in wanted}
    from ingest.db import get_connection
    conn = get_connection()
    try:
        sa = pd.read_sql("SELECT sentence_id, aspect FROM sentence_aspects", conn)
    finally:
        conn.close()
    sa = sa[sa["sentence_id"].isin(wanted)]
    stored = sa.groupby("sentence_id")["aspect"].agg(set).to_dict()
    cache = {}
    embed = lambda q: cache.setdefault(q, embed_sentences([q])[0])
    cols = ["hit@1", "hit@5", "hit@10", "p@5", "recall@5", "recall@10", "rr"]
    table, per_aspect, per_query = {}, None, []
    for name, style, filt in (("question", "question", None), ("label", "label", None),
                              ("aspect query (CHATBOT_ASPECT_QUERY)", "aspect-query", None),
                              ("question + stored-aspect filter", "question", stored),
                              ("label + stored-aspect filter", "label", stored),
                              ("aspect query + stored-aspect filter", "aspect-query", stored)):
        res = evaluate(labels, vec_by_id, embed, aspect_label, style, filt)
        per_query.append(res.assign(variant=name))
        table[name] = res[cols].mean()
        table[f"{name} (random)"] = res[[f"random_{c}" for c in cols]].mean().set_axis(cols)
        if per_aspect is None:
            per_aspect = res.groupby("aspect")[["relevant", "hit@5", "p@5", "rr", "random_p@5", "random_rr"]].mean()
    print(f"{len(res)} (bank, aspect) queries over {labels['bank'].nunique()} banks' labelled pools\n")
    print("Mean over queries:\n" + pd.DataFrame(table).T.to_string(float_format=lambda v: f"{v:.3f}"))
    print("\nBy aspect, question queries, no filter (mean over banks):\n" + per_aspect.to_string(float_format=lambda v: f"{v:.2f}"))
    out = os.path.join(BASE_DIR, "retrieval_recall_per_query.csv")
    pd.concat(per_query).to_csv(out, index=False)
    print(f"\nPer-query results written to {out}")


if __name__ == "__main__":
    main()
