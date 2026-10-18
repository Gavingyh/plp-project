"""
How sure the index scores are: bootstrap confidence intervals.

The index reports one number per bank, aspect, source and window, and says how
many sentences it rests on, but not how far chance could move it. The report
(section 4.4) says no interval has been computed. This computes them by the
bootstrap: resample the sentences a score is made of, with replacement, score
each resample with the index's own formula (weights, confidence and shrinkage,
through aggregate.index), and take the middle 95% of the results.

Two ways to resample:
  --unit document  (default) draws whole documents. Sentences from one Reddit
                   thread or one earnings release are not independent, and
                   drawing them one at a time would give intervals that are too
                   narrow.
  --unit sentence  draws sentences one at a time, the plain bootstrap.
Reporting both shows how much that dependence matters.

What the interval covers, and what it does not: the spread that comes from
which sentences happen to be in the corpus. It does not include the sentiment
model's own mistakes (about three sentences in ten), which a bootstrap of the
labels cannot see; section 4.1 of the report gives that error separately. It
also assumes the corpus is a fair sample of what is said, which collection
choices (Google News favouring recent articles, DBS's larger earnings text)
make only roughly true.

It also tests whether two banks' headline scores differ: the difference between
their scores, its interval, and the share of resamples in which the first bank
scores higher.

It reads the database read-only (set PLP_DB_PATH to use a copy) and writes
nothing to it.

USAGE:
  python -m aggregate.uncertainty                        # the model the index serves
  python -m aggregate.uncertainty --unit sentence --bootstrap 2000
Output goes to data/eval/uncertainty/ (uncertainty.md and uncertainty.json). A run
takes about a minute. Run it on the database that is submitted.
"""

import argparse
import json
import os
import sqlite3
from collections import defaultdict
from datetime import timedelta

import numpy as np

from aggregate import index as ix

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(BASE_DIR, "data", "eval", "uncertainty")
BANKS = ("DBS", "OCBC", "UOB")
DEFAULT_ASPECTS = ("retail_banking_sentiment", "wealth_business", "dividend_policy",
                   "income_profit_results", "net_interest_margin")


# --- the data ------------------------------------------------------------------------

def collect(conn, model_version: str) -> list[tuple]:
    """Every (sentence, aspect) pair the index counts for one model:
    (bank, aspect, source, published_at, sentence_id, doc_id, label, confidence)."""
    return conn.execute("""
        SELECT sa.bank, ase.aspect, sa.source, sa.published_at, ase.sentence_id, sa.doc_id,
               ase.label, ase.confidence
        FROM aspect_sentiment ase
        JOIN sentences sa ON sa.sentence_id = ase.sentence_id
        JOIN sentence_aspects asg ON asg.sentence_id = ase.sentence_id AND asg.aspect = ase.aspect
        WHERE ase.model_version = ?""", (model_version,)).fetchall()


def _item(source, doc_id, label, confidence):
    """(document, label score, weight): the weight is the index's own, confidence
    times the source's weight."""
    return (doc_id, ix._LABEL_SCORE[label], confidence * ix._SOURCE_WEIGHT.get(source, ix._DEFAULT_WEIGHT))


def headline_items(records, bank, source=None, cutoff=None) -> list[tuple]:
    """The items of a bank's headline: one per sentence, the pair with the highest
    confidence, as the stored index counts it."""
    best: dict = {}
    for b, aspect, src, published_at, sid, doc_id, label, conf in records:
        if b != bank or (source and src != source):
            continue
        if cutoff is not None:
            t = ix._utc(published_at)
            if t is None or t < cutoff:
                continue
        if sid not in best or conf > best[sid][0]:
            best[sid] = (conf, _item(src, doc_id, label, conf))
    return [v[1] for v in best.values()]


def aspect_items(records, bank, aspect, cutoff=None) -> list[tuple]:
    out = []
    for b, a, src, published_at, sid, doc_id, label, conf in records:
        if b != bank or a != aspect:
            continue
        if cutoff is not None:
            t = ix._utc(published_at)
            if t is None or t < cutoff:
                continue
        out.append(_item(src, doc_id, label, conf))
    return out


# --- the statistics (pure, tested) -------------------------------------------------------

def point_score(items, k: int = ix.SHRINKAGE_K) -> float:
    """The index's score for these items: weighted mean label, shrunk by n/(n+k)."""
    n = len(items)
    if n == 0:
        return 0.0
    num = sum(l * w for _, l, w in items)
    den = sum(w for _, _, w in items) or 1e-9
    return (num / den) * (n / (n + k))


def bootstrap_scores(items, unit: str = "document", boot: int = 1000, seed: int = 2026,
                     k: int = ix.SHRINKAGE_K, chunk: int = 200) -> np.ndarray:
    """The score of `boot` resamples. `unit` is "document" (draw whole documents)
    or "sentence" (draw items one at a time)."""
    rng = np.random.default_rng(seed)
    if not items:
        return np.zeros(boot)
    if unit == "sentence":
        groups = [(l * w, w, 1) for _, l, w in items]
    elif unit == "document":
        by_doc = defaultdict(lambda: [0.0, 0.0, 0])
        for doc, l, w in items:
            by_doc[doc][0] += l * w
            by_doc[doc][1] += w
            by_doc[doc][2] += 1
        groups = [tuple(v) for v in by_doc.values()]
    else:
        raise ValueError(f"unit must be 'document' or 'sentence', got {unit!r}")
    num = np.array([g[0] for g in groups]); den = np.array([g[1] for g in groups])
    cnt = np.array([g[2] for g in groups], dtype=float)
    out = np.empty(boot)
    for start in range(0, boot, chunk):
        size = min(chunk, boot - start)
        idx = rng.integers(0, len(groups), size=(size, len(groups)))
        n_ = cnt[idx].sum(axis=1)
        raw = num[idx].sum(axis=1) / np.maximum(den[idx].sum(axis=1), 1e-9)
        out[start:start + size] = raw * (n_ / (n_ + k))
    return out


def percentile_interval(samples: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    tail = (1 - level) / 2 * 100
    lo, hi = np.percentile(samples, [tail, 100 - tail])
    return float(lo), float(hi)


def compare_banks(items_a, items_b, unit: str, boot: int, seed: int) -> dict:
    """Score of bank A minus bank B over independent resamples of each (their
    sentences do not overlap)."""
    a = bootstrap_scores(items_a, unit, boot, seed)
    b = bootstrap_scores(items_b, unit, boot, seed + 1)
    diff = a - b
    lo, hi = percentile_interval(diff)
    return {"difference": point_score(items_a) - point_score(items_b), "low": lo, "high": hi,
            "share_a_higher": float((diff > 0).mean())}


# --- run -----------------------------------------------------------------------------

def _row(label, items, unit, boot, seed, window=None):
    scores = bootstrap_scores(items, unit, boot, seed)
    lo, hi = percentile_interval(scores)
    return {"group": label, "window": window or "all_time", "n": len(items),
            "documents": len({d for d, _, _ in items}), "score": round(point_score(items), 4),
            "low": round(lo, 4), "high": round(hi, 4), "half_width": round((hi - lo) / 2, 4)}


def run(model_version: str, units: list[str], boot: int, seed: int, aspects, out_dir: str) -> dict:
    from ingest.db import DB_PATH
    os.makedirs(out_dir, exist_ok=True)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        records = collect(conn, model_version)
        anchor = ix.newest_sentence_time(conn)
        stored = {r[0]: r[1] for r in conn.execute(
            "SELECT bank, score FROM sentiment_index WHERE aspect='ALL' AND window='all_time' "
            "AND source='ALL' AND model_version=?", (model_version,))}
        # The index's own formula on the same rows: the check that this module scores as the index does.
        formula = {r[0]: r[4] for r in ix._compute_rows_for_window(
            [r for r in ix._fetch_all_rows(conn) if r[4] == model_version], "all_time", None)
            if r[1] == "ALL" and r[3] == ix.SOURCE_ALL}
    finally:
        conn.close()
    if not records:
        raise SystemExit(f"No scores for model version {model_version!r} in {DB_PATH}")
    cutoff30 = anchor - timedelta(days=30) if anchor else None

    results = {"model_version": model_version, "bootstrap": boot, "seed": seed, "anchor": str(anchor),
               "check_against_index": {}, "by_unit": {}}
    for bank in BANKS:
        mine = round(point_score(headline_items(records, bank)), 4)
        results["check_against_index"][bank] = {"computed": mine, "index_formula": formula.get(bank),
                                                "stored": stored.get(bank)}
    for unit in units:
        rows = []
        for bank in BANKS:
            rows.append(_row(f"{bank} headline", headline_items(records, bank), unit, boot, seed))
            for src in ("arctic_shift", "earnings"):
                items = headline_items(records, bank, source=src)
                if len(items) >= ix.MIN_N:
                    rows.append(_row(f"{bank} {src}", items, unit, boot, seed))
            if cutoff30 is not None:
                items = headline_items(records, bank, cutoff=cutoff30)
                if len(items) >= ix.MIN_N:
                    rows.append(_row(f"{bank} headline", items, unit, boot, seed, window="30d"))
            for aspect in aspects:
                items = aspect_items(records, bank, aspect)
                if len(items) >= ix.MIN_N:
                    rows.append(_row(f"{bank} {aspect}", items, unit, boot, seed))
        pairs = {}
        for a, b in (("DBS", "OCBC"), ("DBS", "UOB"), ("OCBC", "UOB")):
            pairs[f"{a} minus {b}"] = compare_banks(headline_items(records, a), headline_items(records, b),
                                                    unit, boot, seed)
        results["by_unit"][unit] = {"rows": rows, "pairs": pairs}
    with open(os.path.join(out_dir, "uncertainty.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    with open(os.path.join(out_dir, "uncertainty.md"), "w", encoding="utf-8") as f:
        f.write(render(results))
    return results


def render(results: dict) -> str:
    lines = ["# Confidence intervals for the index", "",
             f"Model `{results['model_version']}`; {results['bootstrap']:,} resamples; windows end at "
             f"{results['anchor']}. Intervals are the middle 95% of resampled scores.", "",
             "Check: the headline score computed here, the same score from the index's own formula "
             "(aggregate.index), and the stored index table. The first two must match; the stored "
             "table matches only if the index was rebuilt after the last scoring.", "",
             "| bank | computed here | index formula | stored index |", "|---|---|---|---|"]
    lines += [f"| {b} | {v['computed']} | {v['index_formula']} | {v['stored']} |"
              for b, v in results["check_against_index"].items()]
    lines.append("")
    for unit, block in results["by_unit"].items():
        lines += [f"## Resampling {unit}s", "",
                  "| group | window | sentences | documents | score | 95% interval | half-width |",
                  "|---|---|---|---|---|---|---|"]
        for r in block["rows"]:
            lines.append(f"| {r['group']} | {r['window']} | {r['n']:,} | {r['documents']:,} | {r['score']:+.3f} "
                         f"| {r['low']:+.3f} to {r['high']:+.3f} | {r['half_width']:.3f} |")
        lines += ["", "| banks | difference | 95% interval | resamples where the first is higher |",
                  "|---|---|---|---|"]
        for name, p in block["pairs"].items():
            lines.append(f"| {name} | {p['difference']:+.3f} | {p['low']:+.3f} to {p['high']:+.3f} "
                         f"| {p['share_a_higher']:.0%} |")
        lines.append("")
    return "\n".join(lines)


def main():
    from config import model_version as mv
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--model-version", default=mv.MODEL_VERSION)
    p.add_argument("--unit", choices=["document", "sentence", "both"], default="both")
    p.add_argument("--bootstrap", type=int, default=1000)
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--aspects", nargs="+", default=list(DEFAULT_ASPECTS))
    p.add_argument("--out", default=DEFAULT_OUT)
    args = p.parse_args()
    units = ["document", "sentence"] if args.unit == "both" else [args.unit]
    results = run(args.model_version, units, args.bootstrap, args.seed, args.aspects, args.out)
    print(render(results))
    print(f"Full output in {args.out}")


if __name__ == "__main__":
    main()
