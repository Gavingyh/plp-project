"""
What the index would look like under the two pending changes, measured on a
random sample of sentences without touching the database: aspects from the
LLM classifier instead of seed-centroid matching (DESIGN decision 16), and
sentiment from the fine-tuned models instead of base FinBERT.

Four scenarios, each scored with the index's own `_summarize`:
  A  centroid aspects + base FinBERT        (what the database holds today)
  B  LLM aspect      + base FinBERT
  C  centroid aspects + fine-tuned average
  D  LLM aspect      + fine-tuned average

Reads only. LLM answers go to the classifier's cache (data/aspect_llm/), and
the per-sentence results to data/preview/ (gitignored) so a re-run resumes.

USAGE:
  HF_HUB_OFFLINE=1 python -m aggregate.preview --n 1000 --cpu
  HF_HUB_OFFLINE=1 python -m aggregate.preview --n 2000 --models models/experiments-2026-10-01/label/seed_{42,1,7}/final
"""

import argparse
import os
from collections import defaultdict

import numpy as np
import pandas as pd

from aggregate.index import _SOURCE_WEIGHT, _summarize

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "preview")
DEFAULT_MODELS = [os.path.join(BASE_DIR, "models", "experiments-2026-10-01", "label", f"seed_{s}", "final")
                  for s in (42, 1, 7)]
LABELS = ["negative", "neutral", "positive"]


def sample_sentences(conn, n: int, seed: int) -> pd.DataFrame:
    df = pd.read_sql("SELECT sentence_id, text, bank, source, published_at FROM sentences ORDER BY sentence_id", conn)
    return df.sample(n=min(n, len(df)), random_state=seed).reset_index(drop=True)


def stored_pairs(conn, ids: list[str]) -> pd.DataFrame:
    """Today's (sentence, aspect) pairs with base FinBERT's label and confidence."""
    q = ",".join("?" * len(ids))
    return pd.read_sql(f"""
        SELECT sa.sentence_id, sa.aspect, ase.label, ase.confidence
        FROM sentence_aspects sa
        JOIN aspect_sentiment ase ON ase.sentence_id = sa.sentence_id AND ase.aspect = sa.aspect
        WHERE sa.sentence_id IN ({q})""", conn, params=ids)


def finetuned_labels(pairs: pd.DataFrame, model_dirs: list[str]) -> pd.DataFrame:
    """The average of the models' probabilities for each (sentence, aspect) pair: label and its probability."""
    from train.evaluate import finetuned_probs
    probs = np.mean([finetuned_probs(d, pairs) for d in model_dirs], axis=0)
    # On 2026-10-01 the GPU, under memory pressure, returned all-zero rows
    # without an error, which argmax turned into "negative" everywhere.
    if not np.allclose(probs.sum(axis=1), 1.0, atol=1e-3):
        raise RuntimeError("model probabilities don't sum to 1: the device returned garbage; "
                           "rerun with --cpu")
    out = pairs[["sentence_id", "aspect"]].copy()
    out["label"] = [LABELS[i] for i in probs.argmax(axis=1)]
    out["confidence"] = probs.max(axis=1)
    return out


def summarize(pairs: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """The index's all-time, all-source rows: one per (bank, aspect), plus the
    headline (aspect 'ALL'), which counts each sentence once (its most
    confident pair), as aggregate.index does."""
    m = pairs.merge(meta[["sentence_id", "bank", "source"]], on="sentence_id")
    groups, best = defaultdict(list), {}
    for r in m.itertuples(index=False):
        item = (r.label, float(r.confidence), _SOURCE_WEIGHT.get(r.source, 1.0))
        groups[(r.bank, r.aspect)].append(item)
        key = (r.bank, r.sentence_id)
        if key not in best or item[1] > best[key][1]:
            best[key] = item
    for (bank, _sid), item in best.items():
        groups[(bank, "ALL")].append(item)
    rows = []
    for (bank, aspect), items in groups.items():
        score, n, pos, neu, neg, _conf = _summarize(items)
        rows.append({"bank": bank, "aspect": aspect, "score": score, "n": n, "pos": pos, "neu": neu, "neg": neg})
    return pd.DataFrame(rows)


def compare(scenarios: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per (bank, aspect): each scenario's score and n side by side."""
    out = None
    for name, df in scenarios.items():
        part = df[["bank", "aspect", "score", "n"]].rename(columns={"score": f"score_{name}", "n": f"n_{name}"})
        out = part if out is None else out.merge(part, on=["bank", "aspect"], how="outer")
    return out.sort_values(["bank", "aspect"]).reset_index(drop=True)


def _md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    def cell(col, v):
        if pd.isna(v):
            return ""
        if col.startswith("n") or not isinstance(v, float):
            return str(int(v)) if isinstance(v, float) else str(v)
        return f"{v:+.3f}"
    for r in df.itertuples(index=False):
        lines.append("| " + " | ".join(cell(c, v) for c, v in zip(cols, r)) + " |")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--n", type=int, default=2000)
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--llm", default="llama3.1:8b")
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    p.add_argument("--cpu", action="store_true", help="run the fine-tuned models on the CPU")
    args = p.parse_args()
    if args.cpu:
        import train.evaluate
        train.evaluate.best_device = lambda: "cpu"

    from aspects.llm_classify import classify_rows
    from ingest.db import get_connection

    conn = get_connection()
    try:
        meta = sample_sentences(conn, args.n, args.seed)
        stored = stored_pairs(conn, meta["sentence_id"].tolist())
    finally:
        conn.close()
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"sample: {len(meta)} sentences (seed {args.seed}); centroid pairs {len(stored)} "
          f"({len(stored) / len(meta):.1f} per sentence)", flush=True)

    llm = classify_rows(meta[["sentence_id", "text"]], args.llm)[["sentence_id", "aspect"]]
    texts = meta[["sentence_id", "text"]]
    base_by_sentence = stored.drop_duplicates("sentence_id")[["sentence_id", "label", "confidence"]]

    a = stored[["sentence_id", "aspect", "label", "confidence"]]
    b = llm.merge(base_by_sentence, on="sentence_id")                     # base FinBERT is per sentence
    c = finetuned_labels(stored[["sentence_id", "aspect"]].merge(texts, on="sentence_id"), args.models)
    d = finetuned_labels(llm.merge(texts, on="sentence_id"), args.models)
    for name, df in (("A", a), ("B", b), ("C", c), ("D", d)):
        df.to_csv(os.path.join(OUT_DIR, f"pairs_{name}.csv"), index=False)

    table = compare({k: summarize(v, meta) for k, v in (("A", a), ("B", b), ("C", c), ("D", d))})
    table.to_csv(os.path.join(OUT_DIR, "index_preview.csv"), index=False)
    print("\nHeadline (aspect ALL), per bank:\n" + _md(table[table["aspect"] == "ALL"]))
    print("\nPer bank and aspect:\n" + _md(table[table["aspect"] != "ALL"]))

    print("\nAspect distribution: centroid pairs vs LLM (one per sentence)")
    dist = pd.DataFrame({"centroid_pairs": a["aspect"].value_counts(), "llm_sentences": llm["aspect"].value_counts()}).fillna(0).astype(int)
    print(_md(dist.reset_index().rename(columns={"index": "aspect"})))
    for name, df in (("A", a), ("B", b), ("C", c), ("D", d)):
        one = df.sort_values("confidence", ascending=False).drop_duplicates("sentence_id")
        shares = one["label"].value_counts(normalize=True).reindex(LABELS, fill_value=0)
        print(f"labels per sentence, {name}: " + ", ".join(f"{k} {v:.1%}" for k, v in shares.items()))


if __name__ == "__main__":
    main()
