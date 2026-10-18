"""
Topic modelling as a second route to the aspects, compared with the ones used.

Aspect discovery (aspects/discover.py) clusters FinBERT embeddings with UMAP and
HDBSCAN. The Text Analytics module teaches a second family for finding themes in
text, probabilistic and matrix topic models (LDA and NMF). This runs both on the
corpus's sentences and asks two questions of each:

  1. Are the topics coherent? NPMI coherence over the corpus's sentences: do a
     topic's top words appear together more than chance? Higher is better;
     above about 0.05 reads as a topic a person can name.
  2. Do they find the aspects people labelled? Each human-labelled sentence is
     given its dominant topic, and the topics are compared with the human aspect
     labels (normalised mutual information, adjusted Rand index and purity),
     with a shuffled-label run for the level chance gives.

It reads the database read-only (set PLP_DB_PATH to use a copy) and writes
nothing to it. The labelled sentences are in the corpus, so the models are fitted
without any labels: the labels are used only to compare.

USAGE:
  python -m aspects.topic_model                     # NMF and LDA at 11 topics
  python -m aspects.topic_model --k 11 25 --methods nmf
  python -m aspects.topic_model --sample 15000      # quicker, on a random sample
Output goes to data/eval/topic_model/ (topic_model.md and topic_model.json). A full
run takes a few minutes on a laptop CPU, LDA being the slower. Run it on the
database that is submitted: every figure in the report must come from that file.
"""

import argparse
import json
import math
import os
import random
import sqlite3
from collections import Counter

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(BASE_DIR, "data", "eval", "topic_model")
DEFAULT_LABELS = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
SEED = 2026


# --- measures (pure, tested) ---------------------------------------------------------

def npmi_coherence(binary_docs, top_word_ids: list[int], eps: float = 1e-12) -> float:
    """Mean normalised pointwise mutual information over the pairs of a topic's
    top words, with probabilities taken from how many sentences contain the
    words (a binary document-term matrix, scipy sparse or numpy). 1 means the words
    always occur together, 0 as often as chance, -1 never together."""
    n_docs = binary_docs.shape[0]
    cols = [np.asarray(binary_docs[:, w].todense()).ravel() if hasattr(binary_docs, "todense")
            else np.asarray(binary_docs[:, w]).ravel() for w in top_word_ids]
    p = [c.sum() / n_docs for c in cols]
    scores = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            p_ij = float((cols[i] * cols[j]).sum()) / n_docs
            if p_ij <= 0 or p[i] <= 0 or p[j] <= 0:
                scores.append(-1.0)
                continue
            pmi = math.log(p_ij / (p[i] * p[j]))
            scores.append(pmi / (-math.log(p_ij + eps)))
    return float(np.mean(scores)) if scores else 0.0


def contingency(topics: list, aspects: list) -> pd.DataFrame:
    return pd.crosstab(pd.Series(topics, name="topic"), pd.Series(aspects, name="aspect"))


def purity(table: pd.DataFrame) -> float:
    """Share of sentences that sit with their topic's commonest aspect."""
    return float(table.max(axis=1).sum() / table.values.sum())


def nmi_ari(topics: list, aspects: list) -> tuple[float, float]:
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
    return (float(normalized_mutual_info_score(aspects, topics)),
            float(adjusted_rand_score(aspects, topics)))


def chance_level(topics: list, aspects: list, rounds: int = 200, seed: int = SEED) -> dict:
    """The agreement a random assignment gives, by shuffling the aspect labels."""
    rng = random.Random(seed)
    nmi, ari, pur = [], [], []
    labels = list(aspects)
    for _ in range(rounds):
        rng.shuffle(labels)
        n, a = nmi_ari(topics, labels)
        nmi.append(n); ari.append(a); pur.append(purity(contingency(topics, labels)))
    return {"nmi": float(np.mean(nmi)), "ari": float(np.mean(ari)), "purity": float(np.mean(pur))}


def topic_summary(table: pd.DataFrame) -> list[dict]:
    """For each topic: its size, its commonest human aspect and that aspect's share."""
    out = []
    for topic, row in table.iterrows():
        n = int(row.sum())
        best = row.idxmax()
        out.append({"topic": int(topic), "labelled_sentences": n, "best_aspect": str(best),
                    "share": round(float(row.max() / n), 3) if n else 0.0})
    return out


# --- data ----------------------------------------------------------------------------

def load_sentences(sample: int | None, seed: int = SEED) -> pd.DataFrame:
    from ingest.db import DB_PATH
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        df = pd.read_sql_query("SELECT sentence_id, text FROM sentences", conn)
    finally:
        conn.close()
    if sample and sample < len(df):
        df = df.sample(sample, random_state=seed).reset_index(drop=True)
    return df


def load_labelled(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["aspect"].notna() & df["text"].notna()]
    return df.drop_duplicates(["sentence_id", "aspect"]).reset_index(drop=True)


# --- models --------------------------------------------------------------------------

def fit_topics(method: str, k: int, texts: list[str], labelled_texts: list[str], seed: int = SEED):
    """Fit one topic model on the sentences. Returns (top-word lists, coherence per
    topic, dominant topic of each labelled sentence, topic sizes on the corpus)."""
    from sklearn.decomposition import NMF, LatentDirichletAllocation
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer, TfidfVectorizer

    stop = list(ENGLISH_STOP_WORDS | {"dbs", "ocbc", "uob", "bank", "banks", "posb"})
    if method == "nmf":
        vec = TfidfVectorizer(stop_words=stop, min_df=5, max_df=0.5, sublinear_tf=True,
                              token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z']{2,}\b")
        X = vec.fit_transform(texts)
        model = NMF(n_components=k, init="nndsvda", random_state=seed, max_iter=300)
    elif method == "lda":
        vec = CountVectorizer(stop_words=stop, min_df=5, max_df=0.5,
                              token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z']{2,}\b")
        X = vec.fit_transform(texts)
        model = LatentDirichletAllocation(n_components=k, learning_method="online", random_state=seed,
                                          max_iter=10, batch_size=2048, n_jobs=1)
    else:
        raise ValueError(method)
    doc_topic = model.fit_transform(X)
    vocab = np.array(vec.get_feature_names_out())
    binary = (CountVectorizer(vocabulary=vec.vocabulary_, binary=True,
                              token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z']{2,}\b", lowercase=True)
              .fit_transform(texts))
    tops, coh = [], []
    for comp in model.components_:
        ids = np.argsort(comp)[::-1][:10]
        tops.append(list(vocab[ids]))
        coh.append(npmi_coherence(binary, list(ids)))
    labelled_topic = model.transform(vec.transform(labelled_texts)).argmax(axis=1)
    sizes = Counter(doc_topic.argmax(axis=1).tolist())
    return tops, coh, labelled_topic.tolist(), sizes


def run(ks: list[int], methods: list[str], sample: int | None, labels_path: str, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    corpus = load_sentences(sample)
    labelled = load_labelled(labels_path)
    aspects = labelled["aspect"].tolist()
    results = {"sentences": len(corpus), "labelled": len(labelled), "runs": []}
    for method in methods:
        for k in ks:
            tops, coh, topic_of, sizes = fit_topics(method, k, corpus["text"].tolist(), labelled["text"].tolist())
            table = contingency(topic_of, aspects)
            nmi, ari = nmi_ari(topic_of, aspects)
            results["runs"].append({
                "method": method, "k": k, "coherence_mean": round(float(np.mean(coh)), 4),
                "nmi": round(nmi, 4), "ari": round(ari, 4), "purity": round(purity(table), 4),
                "chance": {m: round(v, 4) for m, v in chance_level(topic_of, aspects).items()},
                "topics": [{"topic": i, "top_words": tops[i], "coherence": round(coh[i], 4),
                            "corpus_sentences": int(sizes.get(i, 0))} for i in range(k)],
                "alignment": topic_summary(table)})
    with open(os.path.join(out_dir, "topic_model.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    with open(os.path.join(out_dir, "topic_model.md"), "w", encoding="utf-8") as f:
        f.write(render(results))
    return results


def render(results: dict) -> str:
    lines = ["# Topic models against the human aspect labels", "",
             f"Fitted on {results['sentences']:,} sentences; compared on {results['labelled']:,} "
             "human-labelled sentences. Chance is the level a shuffled labelling gives.", "",
             "| method | topics | mean coherence | NMI (chance) | ARI (chance) | purity (chance) |",
             "|---|---|---|---|---|---|"]
    for r in results["runs"]:
        c = r["chance"]
        lines.append(f"| {r['method'].upper()} | {r['k']} | {r['coherence_mean']:.3f} | {r['nmi']:.3f} ({c['nmi']:.3f}) "
                     f"| {r['ari']:.3f} ({c['ari']:.3f}) | {r['purity']:.3f} ({c['purity']:.3f}) |")
    for r in results["runs"]:
        lines += ["", f"### {r['method'].upper()}, {r['k']} topics", "",
                  "| topic | top words | coherence | corpus sentences | commonest human aspect (share) |",
                  "|---|---|---|---|---|"]
        align = {a["topic"]: a for a in r["alignment"]}
        for t in r["topics"]:
            a = align.get(t["topic"])
            best = f"{a['best_aspect']} ({a['share']:.2f}, n={a['labelled_sentences']})" if a else "no labelled sentence"
            lines.append(f"| {t['topic']} | {', '.join(t['top_words'][:8])} | {t['coherence']:.3f} "
                         f"| {t['corpus_sentences']:,} | {best} |")
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--k", type=int, nargs="+", default=[11], help="numbers of topics (11 = the ten aspects plus other)")
    p.add_argument("--methods", nargs="+", choices=["nmf", "lda"], default=["nmf", "lda"])
    p.add_argument("--sample", type=int, default=None, help="fit on a random sample of this many sentences")
    p.add_argument("--labels", default=DEFAULT_LABELS)
    p.add_argument("--out", default=DEFAULT_OUT)
    args = p.parse_args()
    results = run(args.k, args.methods, args.sample, args.labels, args.out)
    print(render(results)[:3500])
    print(f"Full output in {args.out}")


if __name__ == "__main__":
    main()
