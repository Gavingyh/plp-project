"""How sure the index's scores are. Two kinds of uncertainty, measured apart:

1. Sampling: the corpus is one sample of what was written. Each score is
   recomputed on 2,000 bootstrap resamples of its own sentences (the index's
   formula: confidence- and source-weighted mean of +1/0/-1, shrunk by
   n/(n+5)), giving a 95% interval, and the same for the gaps between banks.
2. Measurement: the scores come from a model that is wrong on about three
   sentences in ten. On the 399 test sentences people labelled, the net
   balance (share positive minus share negative) by the model's labels is
   compared with the balance by people's labels, with a paired bootstrap
   interval for the difference.

Reads data/plp.db and the test labels; scores the test sentences with the
served models on the CPU. Writes results.json beside this file.

  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 data/eval/index-uncertainty/intervals.py
"""
import json, os, sqlite3, sys
from datetime import timedelta
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
import numpy as np, pandas as pd
import aggregate.index as ix
from config.model_version import MODEL_VERSION, FINETUNED

B, SEED = 2000, 2026
rng = np.random.default_rng(SEED)
HERE = os.path.dirname(os.path.abspath(__file__))
conn = sqlite3.connect("file:data/plp.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT s.sentence_id, s.bank, s.source, s.published_at, a.aspect, a.label, a.confidence
                    FROM sentences s JOIN aspect_sentiment a USING (sentence_id) WHERE a.model_version = ?""", conn, params=(MODEL_VERSION,))
stored = {(b, a, w): (sc, n) for b, a, w, sc, n in conn.execute(
    "SELECT bank, aspect, window, score, n FROM sentiment_index WHERE source='ALL' AND model_version=?", (MODEL_VERSION,))}
anchor = ix.newest_sentence_time(conn)
conn.close()
df["s"] = df.label.map(ix._LABEL_SCORE); df["cw"] = df.confidence * df.source.map(lambda x: ix._SOURCE_WEIGHT.get(x, ix._DEFAULT_WEIGHT))
t = df.published_at.map(ix._utc)
df["in_30d"] = [x is not None and x >= anchor - timedelta(days=30) for x in t]
df["in_7d"] = [x is not None and x >= anchor - timedelta(days=7) for x in t]

def point(s, cw):
    n = len(s); return float((s * cw).sum() / cw.sum() * n / (n + ix.SHRINKAGE_K))

def boot(s, cw):
    n = len(s); out = []
    for _ in range(0, B, 200):
        idx = rng.integers(0, n, size=(200, n))
        out.append((s[idx] * cw[idx]).sum(1) / cw[idx].sum(1) * n / (n + ix.SHRINKAGE_K))
    return np.concatenate(out)

cells, reps = [], {}
for bank, g in df.groupby("bank"):
    for aspect, h in [("ALL", g)] + list(g.groupby("aspect")):
        for window, m in (("all_time", None), ("30d", "in_30d"), ("7d", "in_7d")):
            if aspect != "ALL" and window != "all_time":
                continue
            k = h if m is None else h[h[m]]
            if len(k) < ix.MIN_N:
                continue
            s, cw = k.s.to_numpy(), k.cw.to_numpy()
            p = point(s, cw); r = boot(s, cw); lo, hi = np.percentile(r, [2.5, 97.5])
            st = stored.get((bank, aspect, window))
            cells.append({"bank": bank, "aspect": aspect, "window": window, "n": len(k), "score": round(p, 4),
                          "stored_score": st[0] if st else None, "low": round(float(lo), 4), "high": round(float(hi), 4),
                          "half_width": round(float(hi - lo) / 2, 4)})
            reps[(bank, aspect, window)] = r
cells = pd.DataFrame(cells)
mismatch = cells[(cells.stored_score - cells.score).abs() > 0.00051]
print(f"{len(cells)} cells; recomputed scores that differ from the stored index: {len(mismatch)}")
gaps = []
for w in ("all_time", "30d", "7d"):
    for a, b in (("DBS", "OCBC"), ("DBS", "UOB"), ("OCBC", "UOB")):
        d = reps[(a, "ALL", w)] - reps[(b, "ALL", w)]
        gaps.append({"window": w, "gap": f"{a} - {b}", "point": round(float(cells.query("bank==@a and aspect=='ALL' and window==@w").score.iloc[0] - cells.query("bank==@b and aspect=='ALL' and window==@w").score.iloc[0]), 4),
                     "low": round(float(np.percentile(d, 2.5)), 4), "high": round(float(np.percentile(d, 97.5)), 4), "share_above_zero": round(float((d > 0).mean()), 3)})
gaps = pd.DataFrame(gaps)

# ---- measurement: the model against people on the test sentences
import train.evaluate as ev
ev.best_device = lambda: "cpu"
ts = pd.read_csv("data/labeled/llm_rater/rules-2026-10-10/training_set.csv"); first = ts[ts.split == "test"]
broker = pd.read_csv("data/labeled/sgx_research/resolved_test_blind.csv")
test = pd.concat([first[["sentence_id", "aspect", "text", "bank", "source", "label"]], broker[["sentence_id", "aspect", "text", "bank", "source", "label"]]], ignore_index=True)
probs = sum(ev.finetuned_probs(os.path.realpath(d), test) for d in FINETUNED[MODEL_VERSION]["models"]) / 3
pred = np.array(["negative", "neutral", "positive"])[probs.argmax(1)]
val = {"negative": -1, "neutral": 0, "positive": 1}
hm = test.label.map(val).to_numpy(); mm = np.vectorize(val.get)(pred)
meas = []
for name, mask in (("all 399", np.ones(len(test), bool)), ("Reddit", (test.source == "arctic_shift").to_numpy()),
                   ("earnings", (test.source == "earnings").to_numpy()), ("broker research", (test.source == "sgx_research").to_numpy())):
    h, m = hm[mask], mm[mask]; n = len(h)
    idx = rng.integers(0, n, size=(B, n)); d = m[idx].mean(1) - h[idx].mean(1)
    meas.append({"test sentences": name, "n": n, "net balance, people": round(float(h.mean()), 3), "net balance, model": round(float(m.mean()), 3),
                 "difference": round(float(m.mean() - h.mean()), 3), "low": round(float(np.percentile(d, 2.5)), 3), "high": round(float(np.percentile(d, 97.5)), 3)})
meas = pd.DataFrame(meas)

pd.set_option("display.width", 220)
print("\nHeadlines:\n" + cells[cells.aspect == "ALL"].to_string(index=False))
print("\nGaps between banks:\n" + gaps.to_string(index=False))
print("\nPer aspect, all time (widest intervals first):\n" + cells[cells.aspect != "ALL"].sort_values("half_width", ascending=False).to_string(index=False))
print("\nMeasurement, model against people on the test sentences:\n" + meas.to_string(index=False))
json.dump({"bootstrap_resamples": B, "seed": SEED, "cells": cells.to_dict("records"), "gaps": gaps.to_dict("records"),
           "measurement": meas.to_dict("records")}, open(os.path.join(HERE, "results.json"), "w"), indent=1)
