"""
HDBSCAN against the human aspect labels, side by side with LDA.

aspects/topic_model.py fits LDA (and NMF) on word counts. aspects/discover.py
clusters FinBERT sentence embeddings with UMAP and HDBSCAN. This script scores
the second family the same way as the first, so the two can be compared:
the same human-labelled sentences, the same NMI, ARI and purity, the same shuffled-
label chance level, and NPMI coherence of each cluster's top words.

HDBSCAN leaves some sentences as noise. The scores are given two ways: with
all noise sentences as one extra group (penalises leaving sentences out), and
on the clustered sentences only (with the share covered).

Nothing here reads human labels to choose a setting: every min_cluster_size
tried is reported. Read-only on the database; uses the embedding cache.

USAGE:
  python -m aspects.hdbscan_compare --min-cluster-size 10 100 200
"""

import argparse
import json
import os
import sqlite3
from collections import Counter

import numpy as np
import pandas as pd

from aspects.topic_model import (DEFAULT_LABELS, DEFAULT_OUT, SEED, chance_level, contingency,
                                 load_labelled, nmi_ari, npmi_coherence, purity, topic_summary)

TOKEN = r"(?u)\b[a-zA-Z][a-zA-Z']{2,}\b"


def cluster_top_words(counts, labels: np.ndarray, vocab: np.ndarray, n: int = 10) -> dict[int, list[int]]:
    """Top word ids per cluster by class-based TF-IDF: a word scores high when it is
    frequent in the cluster and rare in the rest of the corpus."""
    ids = sorted(set(labels.tolist()) - {-1})
    total = np.asarray(counts.sum(axis=0)).ravel() + 1
    avg = total.sum() / max(len(ids), 1)
    out = {}
    for c in ids:
        tf = np.asarray(counts[labels == c].sum(axis=0)).ravel()
        score = (tf / max(tf.sum(), 1)) * np.log(1 + avg / total)
        out[c] = list(np.argsort(score)[::-1][:n])
    return out


def score_run(labels: np.ndarray, lab_idx: np.ndarray, aspects: list[str]) -> dict:
    topic_of = labels[lab_idx].tolist()
    table = contingency(topic_of, aspects)
    nmi, ari = nmi_ari(topic_of, aspects)
    ch = chance_level(topic_of, aspects)
    clustered = [i for i, t in enumerate(topic_of) if t != -1]
    res = {"noise_as_group": {"nmi": nmi, "ari": ari, "purity": purity(table), "chance": ch}}
    if len(set(topic_of[i] for i in clustered)) > 1:
        t2 = [topic_of[i] for i in clustered]
        a2 = [aspects[i] for i in clustered]
        n2, r2 = nmi_ari(t2, a2)
        res["clustered_only"] = {"nmi": n2, "ari": r2, "purity": purity(contingency(t2, a2)),
                                 "chance": chance_level(t2, a2), "labelled_covered": len(clustered)}
    else:
        res["clustered_only"] = None
    res["alignment"] = topic_summary(table)
    return res


def run(sizes: list[int], labels_path: str, out_dir: str) -> dict:
    import hdbscan
    import umap
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

    from aspects.embed_store import load_for_search
    from ingest.db import DB_PATH

    ids, vectors = load_for_search()
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        text_by_id = dict(conn.execute("SELECT sentence_id, text FROM sentences").fetchall())
        n_db = len(text_by_id)
    finally:
        conn.close()
    keep = [i for i, s in enumerate(ids) if s in text_by_id]
    ids = [ids[i] for i in keep]
    vectors = vectors[keep]
    texts = [text_by_id[s] for s in ids]
    pos = {s: i for i, s in enumerate(ids)}

    labelled = load_labelled(labels_path)
    labelled = labelled[labelled["sentence_id"].isin(pos)].reset_index(drop=True)
    lab_idx = np.array([pos[s] for s in labelled["sentence_id"]])
    aspects = labelled["aspect"].tolist()

    stop = list(ENGLISH_STOP_WORDS | {"dbs", "ocbc", "uob", "bank", "banks", "posb"})
    vec = CountVectorizer(stop_words=stop, min_df=5, max_df=0.5, token_pattern=TOKEN)
    counts = vec.fit_transform(texts)
    vocab = np.array(vec.get_feature_names_out())
    binary = CountVectorizer(vocabulary=vec.vocabulary_, binary=True, token_pattern=TOKEN).fit_transform(texts)

    print(f"UMAP on {vectors.shape[0]:,} embeddings ...", flush=True)
    reduced = umap.UMAP(n_neighbors=15, min_dist=0.0, n_components=10, metric="cosine",
                        random_state=42).fit_transform(vectors)

    results = {"embedded": len(ids), "database_sentences": n_db, "labelled": len(labelled), "runs": []}
    for size in sizes:
        labels = hdbscan.HDBSCAN(min_cluster_size=size, metric="euclidean").fit_predict(reduced)
        tops = cluster_top_words(counts, labels, vocab)
        coh = {c: npmi_coherence(binary, w) for c, w in tops.items()}
        sizes_c = Counter(labels.tolist())
        n_clusters = len(tops)
        run_res = {"min_cluster_size": size, "clusters": n_clusters,
                   "noise_share": round(float((labels == -1).mean()), 4),
                   "coherence_mean": round(float(np.mean(list(coh.values()))), 4) if coh else None,
                   "scores": score_run(labels, lab_idx, aspects),
                   "largest": [{"cluster": c, "sentences": n, "top_words": [str(vocab[w]) for w in tops[c]],
                                "coherence": round(coh[c], 4)}
                               for c, n in sizes_c.most_common(40) if c != -1][:15]}
        results["runs"].append(run_res)
        print(f"min_cluster_size {size}: {n_clusters} clusters, noise {run_res['noise_share']:.0%}", flush=True)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "hdbscan_vs_lda.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=float)
    with open(os.path.join(out_dir, "hdbscan_vs_lda.md"), "w", encoding="utf-8") as f:
        f.write(render(results, out_dir))
    return results


def render(results: dict, out_dir: str) -> str:
    lines = ["# HDBSCAN and LDA against the human aspect labels", "",
             f"HDBSCAN clusters UMAP-reduced FinBERT embeddings of {results['embedded']:,} of the "
             f"{results['database_sentences']:,} sentences in the database (the embedding cache is not up to date "
             f"for the rest), compared on {results['labelled']:,} human-labelled sentences. "
             "Chance is the level a shuffled labelling gives. No setting was chosen using the human labels.", ""]
    lda = None
    p = os.path.join(out_dir, "topic_model.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            lda = next((r for r in json.load(f)["runs"] if r["method"] == "lda"), None)
    lines += ["| method | groups | sentences left as noise | mean coherence | NMI (chance) | ARI (chance) | purity (chance) |",
              "|---|---|---|---|---|---|---|"]
    if lda:
        c = lda["chance"]
        lines.append(f"| LDA, {lda['k']} topics | {lda['k']} | 0% | {lda['coherence_mean']:.3f} | "
                     f"{lda['nmi']:.3f} ({c['nmi']:.3f}) | {lda['ari']:.3f} ({c['ari']:.3f}) | "
                     f"{lda['purity']:.3f} ({c['purity']:.3f}) |")
    for r in results["runs"]:
        s = r["scores"]["noise_as_group"]; c = s["chance"]
        coh = f"{r['coherence_mean']:.3f}" if r["coherence_mean"] is not None else "n/a"
        lines.append(f"| HDBSCAN, min cluster {r['min_cluster_size']} (noise as one group) | {r['clusters']} | "
                     f"{r['noise_share']:.0%} | {coh} | {s['nmi']:.3f} ({c['nmi']:.3f}) | "
                     f"{s['ari']:.3f} ({c['ari']:.3f}) | {s['purity']:.3f} ({c['purity']:.3f}) |")
    lines += ["", "Clustered sentences only (noise left out):", "",
              "| min cluster size | labelled sentences covered | NMI (chance) | ARI (chance) | purity (chance) |",
              "|---|---|---|---|---|"]
    for r in results["runs"]:
        s = r["scores"]["clustered_only"]
        if not s:
            lines.append(f"| {r['min_cluster_size']} | too few clusters | | | |"); continue
        c = s["chance"]
        lines.append(f"| {r['min_cluster_size']} | {s['labelled_covered']} of {results['labelled']} | "
                     f"{s['nmi']:.3f} ({c['nmi']:.3f}) | {s['ari']:.3f} ({c['ari']:.3f}) | "
                     f"{s['purity']:.3f} ({c['purity']:.3f}) |")
    for r in results["runs"]:
        align = {a["topic"]: a for a in r["scores"]["alignment"]}
        lines += ["", f"### HDBSCAN, min cluster size {r['min_cluster_size']}: largest clusters", "",
                  "| cluster | sentences | top words | coherence | commonest human aspect (share) |",
                  "|---|---|---|---|---|"]
        for t in r["largest"]:
            a = align.get(t["cluster"])
            best = f"{a['best_aspect']} ({a['share']:.2f}, n={a['labelled_sentences']})" if a else "no labelled sentence"
            lines.append(f"| {t['cluster']} | {t['sentences']:,} | {', '.join(t['top_words'][:8])} | "
                         f"{t['coherence']:.3f} | {best} |")
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--min-cluster-size", type=int, nargs="+", default=[10, 100, 200])
    p.add_argument("--labels", default=DEFAULT_LABELS)
    p.add_argument("--out", default=DEFAULT_OUT)
    a = p.parse_args()
    run(a.min_cluster_size, a.labels, a.out)
    print(f"Full output in {a.out}")


if __name__ == "__main__":
    main()
