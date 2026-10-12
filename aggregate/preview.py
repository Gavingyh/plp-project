"""
What the index looks like under two changes, measured on a random sample of
sentences without touching the database: aspects from the LLM classifier
instead of seed-centroid matching (DESIGN decision 16), and sentiment from
fine-tuned models instead of base FinBERT. Built to preview the re-score
(scripts/rescore.py). A and C read the stored aspects, so on a re-scored
database, where each sentence holds the LLM's aspect, A equals B and C equals D.

Four scenarios, each scored with the index's own `_summarize`:
  A  stored aspects  + base FinBERT        (the centroid aspects, before the re-score)
  B  LLM aspect      + base FinBERT
  C  stored aspects  + fine-tuned average
  D  LLM aspect      + fine-tuned average

Reads only. LLM answers go to the classifier's cache (data/aspect_llm/). The
fine-tuned models' averaged probabilities go to data/preview/scores.<key>.jsonl,
where <key> names the models and the device, a chunk at a time, so an
interrupted run resumes and a second view of the same pairs (another neutral
margin) costs minutes. Results go to data/preview/ (all gitignored).

`--margin` applies the dev-chosen neutral margin to C and D: a sentence is
neutral unless the stronger of negative and positive beats neutral by more
than the margin, as in docs/model-card.md. The default, 0, is the plain most
likely class used for the 11,000-sentence preview.

`--llm-only` skips C, which scores every centroid pair (about six a
sentence) with the fine-tuned models: the slow part, and beside the point
once the LLM aspects are chosen.

`--per-seed` also scores D with each model on its own (LLM aspects only, one
pair per sentence, each model in its own scores cache) and prints every
bank's headline per model and the spread, to show how far the index moves
from one seed to another.

USAGE:
  HF_HUB_OFFLINE=1 python -m aggregate.preview --n 1000 --cpu
  HF_HUB_OFFLINE=1 python -m aggregate.preview --n 44345 --cpu --margin 0.13     # the whole corpus
  HF_HUB_OFFLINE=1 python -m aggregate.preview --n 44345 --cpu --margin 0.13 --per-seed
  HF_HUB_OFFLINE=1 python -m aggregate.preview --n 2000 --models models/experiments-2026-10-01/label/seed_{42,1,7}/final
"""

import argparse
import hashlib
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd

import config.model_version as current_model
from aggregate.index import _DEFAULT_WEIGHT, _SOURCE_WEIGHT, _summarize
from config.model_version import DEFAULT_FINETUNED, FINETUNED
from train.labels import LABELS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "preview")
DEFAULT_MODELS = [os.path.join(BASE_DIR, d) for d in FINETUNED[DEFAULT_FINETUNED]["models"]]


def sample_sentences(conn, n: int, seed: int) -> pd.DataFrame:
    df = pd.read_sql("SELECT sentence_id, text, bank, source, published_at FROM sentences ORDER BY sentence_id", conn)
    return df.sample(n=min(n, len(df)), random_state=seed).reset_index(drop=True)


def stored_pairs(conn, ids: list[str]) -> pd.DataFrame:
    """The stored (sentence, aspect) pairs with base FinBERT's label and confidence,
    whichever version is served.
    Queried in batches: SQLite caps the parameters of one statement."""
    parts = []
    for i in range(0, len(ids), 10000):
        batch = ids[i:i + 10000]
        q = ",".join("?" * len(batch))
        parts.append(pd.read_sql(f"""
            SELECT sa.sentence_id, sa.aspect, ase.label, ase.confidence
            FROM sentence_aspects sa
            JOIN aspect_sentiment ase ON ase.sentence_id = sa.sentence_id AND ase.aspect = sa.aspect
            WHERE sa.sentence_id IN ({q}) AND ase.model_version = ?""",
            conn, params=batch + [current_model.BASE_VERSION]))
    return pd.concat(parts, ignore_index=True)


def scores_cache_path(model_dirs: list[str]) -> str:
    """The cache for this set of models on this device: each model's weights
    (path, size, time) and input format, so retrained or different models
    never reuse another set's probabilities."""
    import train.evaluate
    parts = [str(train.evaluate.best_device())]
    for d in model_dirs:
        st = os.stat(os.path.join(d, "model.safetensors"))
        fmt_path = os.path.join(d, "input_format.json")
        fmt = open(fmt_path).read() if os.path.exists(fmt_path) else ""
        parts.append(f"{os.path.realpath(d)}|{st.st_size}|{st.st_mtime_ns}|{fmt}")
    key = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:8]
    return os.path.join(OUT_DIR, f"scores.{key}.jsonl")


def averaged_probs(pairs: pd.DataFrame, model_dirs: list[str], cache_path: str | None = None,
                   chunk: int = 5000) -> np.ndarray:
    """(n, 3) probabilities averaged over the models, one row per pair. With a
    cache, only pairs not yet in it are scored, a chunk at a time, and each
    chunk is appended once it is checked, so an interrupted run resumes."""
    import train.evaluate

    def score(df):
        probs = np.mean([train.evaluate.finetuned_probs(d, df) for d in model_dirs], axis=0)
        # The GPU once, under memory pressure, returned all-zero rows
        # without an error, which argmax turned into "negative" everywhere.
        if not np.allclose(probs.sum(axis=1), 1.0, atol=1e-3):
            raise RuntimeError("model probabilities don't sum to 1: the device returned garbage; "
                               "rerun with --cpu")
        return probs

    if cache_path is None:
        return score(pairs)
    done = {}
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            for line in f:
                r = json.loads(line)
                done[(r["sentence_id"], r["aspect"])] = r["probs"]
    keys = list(zip(pairs["sentence_id"], pairs["aspect"]))
    todo = pairs[[k not in done for k in keys]].drop_duplicates(["sentence_id", "aspect"])
    if len(todo):
        print(f"scoring {len(todo)} of {len(pairs)} pairs ({len(pairs) - len(todo)} cached) "
              f"into {cache_path}", flush=True)
    with open(cache_path, "a") as f:
        for i in range(0, len(todo), chunk):
            part = todo.iloc[i:i + chunk]
            for sid, aspect, p in zip(part["sentence_id"], part["aspect"], score(part)):
                done[(sid, aspect)] = [float(x) for x in p]
                f.write(json.dumps({"sentence_id": sid, "aspect": aspect, "probs": done[(sid, aspect)]}) + "\n")
            f.flush()
            print(f"scored {min(i + chunk, len(todo))}/{len(todo)}", flush=True)
    return np.array([done[k] for k in keys])


def finetuned_labels(pairs: pd.DataFrame, model_dirs: list[str], cache_path: str | None = None,
                     margin: float = 0.0) -> pd.DataFrame:
    """Label and its probability for each (sentence, aspect) pair, from the
    models' averaged probabilities. With a margin, the pair is neutral unless
    the stronger of negative and positive beats neutral by more than it."""
    probs = averaged_probs(pairs, model_dirs, cache_path)
    out = pairs[["sentence_id", "aspect"]].copy()
    idx = probs.argmax(axis=1)
    if margin > 0:
        neg, neu, pos = probs[:, 0], probs[:, 1], probs[:, 2]
        polar = np.where(pos >= neg, 2, 0)
        idx = np.where(np.maximum(pos, neg) - neu > margin, polar, 1)
    out["label"] = [LABELS[i] for i in idx]
    out["confidence"] = probs[np.arange(len(probs)), idx]
    return out


def summarize(pairs: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """The index's all-time, all-source rows: one per (bank, aspect), plus the
    headline (aspect 'ALL'), which counts each sentence once (its most
    confident pair), as aggregate.index does."""
    m = pairs.merge(meta[["sentence_id", "bank", "source"]], on="sentence_id")
    groups, best = defaultdict(list), {}
    for r in m.itertuples(index=False):
        item = (r.label, float(r.confidence), _SOURCE_WEIGHT.get(r.source, _DEFAULT_WEIGHT))
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


def _models_tag(model_dirs: list[str]) -> str:
    """A file-name tag for a non-default set of models: their experiment
    folder (experiments-2026-10-03 -> 2026-10-03), else a short hash."""
    parts = os.path.normpath(model_dirs[0]).split(os.sep)
    exp = next((p.removeprefix("experiments-") for p in parts if p.startswith("experiments-")), None)
    return exp or hashlib.sha256("|".join(model_dirs).encode()).hexdigest()[:8]


def per_seed(pairs: pd.DataFrame, meta: pd.DataFrame, model_dirs: list[str], margin: float = 0.0,
             cache: bool = True) -> pd.DataFrame:
    """Each model's own index on these (sentence, aspect, text) pairs: one row
    per (model, bank, aspect), the model named by its directory (`seed_42`
    for `.../seed_42/final`). Each model has its own scores cache."""
    def short(d):
        path = os.path.normpath(d)
        return os.path.basename(os.path.dirname(path) if os.path.basename(path) == "final" else path)
    names = [short(d) for d in model_dirs]
    if len(set(names)) < len(names):           # e.g. seed_1 from two experiments: keep them apart
        names = [os.path.normpath(d) for d in model_dirs]
    rows = []
    for d, name in zip(model_dirs, names):
        labelled = finetuned_labels(pairs, [d], scores_cache_path([d]) if cache else None, margin)
        rows.append(summarize(labelled, meta).assign(model=name))
    return pd.concat(rows, ignore_index=True)[["model", "bank", "aspect", "score", "n"]]


def seed_spread(table: pd.DataFrame) -> pd.DataFrame:
    """Per (bank, aspect): each model's score side by side, then the lowest,
    the highest and the spread between them."""
    wide = table.pivot_table(index=["bank", "aspect"], columns="model", values="score").reset_index()
    models = [c for c in wide.columns if c not in ("bank", "aspect")]
    wide["min"] = wide[models].min(axis=1)
    wide["max"] = wide[models].max(axis=1)
    wide["spread"] = wide["max"] - wide["min"]
    n = table.groupby(["bank", "aspect"])["n"].first().rename("n").reset_index()
    return wide.merge(n, on=["bank", "aspect"]).sort_values(["bank", "aspect"]).reset_index(drop=True)


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
    from aspects.llm_classify import DEFAULT_MODEL as LLM_MODEL
    p.add_argument("--llm", default=LLM_MODEL)
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    p.add_argument("--cpu", action="store_true", help="run the fine-tuned models on the CPU")
    p.add_argument("--margin", type=float, default=0.0,
                   help="neutral margin for the fine-tuned models (0: the most likely class)")
    p.add_argument("--llm-only", action="store_true",
                   help="skip C (centroid pairs with the fine-tuned models), the slow scenario")
    p.add_argument("--per-seed", action="store_true",
                   help="also score D with each model on its own and print the spread between them")
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
    cache = scores_cache_path(args.models)
    d = finetuned_labels(llm.merge(texts, on="sentence_id"), args.models, cache, args.margin)
    scenarios = {"A": a, "B": b, "D": d}
    if not args.llm_only:
        scenarios["C"] = finetuned_labels(stored[["sentence_id", "aspect"]].merge(texts, on="sentence_id"),
                                          args.models, cache, args.margin)
    scenarios = {k: scenarios[k] for k in sorted(scenarios)}
    tag = f"_margin{args.margin:g}" if args.margin else ""
    if args.models != DEFAULT_MODELS:            # don't overwrite the default models' files
        tag += "_" + _models_tag(args.models)
    for name, df in scenarios.items():
        df.to_csv(os.path.join(OUT_DIR, f"pairs_{name}{tag}.csv"), index=False)

    table = compare({k: summarize(v, meta) for k, v in scenarios.items()})
    table.to_csv(os.path.join(OUT_DIR, f"index_preview{tag}.csv"), index=False)
    print(f"\nsample {len(meta)} sentences, neutral margin {args.margin:g}")
    print("\nHeadline (aspect ALL), per bank:\n" + _md(table[table["aspect"] == "ALL"]))
    print("\nPer bank and aspect:\n" + _md(table[table["aspect"] != "ALL"]))

    print("\nAspect distribution: centroid pairs vs LLM (one per sentence)")
    dist = pd.DataFrame({"centroid_pairs": a["aspect"].value_counts(), "llm_sentences": llm["aspect"].value_counts()}).fillna(0).astype(int)
    print(_md(dist.reset_index().rename(columns={"index": "aspect"})))
    for name, df in scenarios.items():
        one = df.sort_values("confidence", ascending=False).drop_duplicates("sentence_id")
        shares = one["label"].value_counts(normalize=True).reindex(LABELS, fill_value=0)
        print(f"labels per sentence, {name}: " + ", ".join(f"{k} {v:.1%}" for k, v in shares.items()))

    if args.per_seed:
        seeds = per_seed(llm.merge(texts, on="sentence_id"), meta, args.models, args.margin)
        spread = seed_spread(seeds)
        spread.to_csv(os.path.join(OUT_DIR, f"index_preview_per_seed{tag}.csv"), index=False)
        print("\nD per model (LLM aspects, each model alone), headline per bank:\n"
              + _md(spread[spread["aspect"] == "ALL"]))
        print("\nD per model, per bank and aspect:\n" + _md(spread[spread["aspect"] != "ALL"]))


if __name__ == "__main__":
    main()
