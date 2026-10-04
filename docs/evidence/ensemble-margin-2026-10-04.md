# The averaged model's neutral margin, chosen on dev: 4 Oct seeds

The margin used for the retrained models' preview (0.12) is the mean of the
three seeds' own dev-chosen margins (0.20, 0.10, 0.05), not a margin tuned
on the averaged model. This page tunes it on the averaged model, with the
same procedure as `train/error_analysis.py` (`best_margin`: the grid 0 to
0.60 in steps of 0.05, highest dev macro-F1, ties to the smaller margin),
and reports the test split only after the dev choice was fixed. Models:
`models/experiments-2026-10-03/label/seed_{42,1,7}/final`
([retrain-2026-10-04.md](retrain-2026-10-04.md)). Run 4 Oct on the CPU;
nothing written but this page.

## There is no shared dev set

Each seed held out its own 147 dev rows (`dev_ids.json`), and the three
sets barely overlap: one row is held out by all three seeds, 59 by two, 320
by one (380 in all). Every dev row but that one was training data for at
least one of the other seeds, so the averaged model has a single row that
none of its members trained on, and can't be tuned on clean dev data. Two
ways round it, the first fixed as the result before any test score was
computed:

- **Out-of-fold (the result).** Each of the 380 rows is scored by the
  average of only the seeds that held it out: 320 rows by one seed, 59 by
  two, one by all three. No row is scored by a model that trained on it,
  but most rows are scored by a single seed, not the three-seed average.
- **Full average (for comparison).** All three seeds on all 380 rows. It is
  the averaged model, but two of its three members trained on most rows, so
  its dev scores are inflated.

The cached corpus probabilities (`data/preview/scores.*.jsonl`) can't be
used: they hold corpus pairs with the LLM's aspect, not the labelled pairs,
and probabilities depend on the aspect fed in. The dev and test rows were
scored afresh, in memory.

## Dev

| margin | 0 | 0.05 | 0.10 | 0.15 | 0.20 | 0.25 | 0.30 | 0.40 | 0.50 | 0.60 |
|---|---|---|---|---|---|---|---|---|---|---|
| out-of-fold macro-F1 | 0.636 | 0.632 | **0.644** | 0.642 | 0.640 | 0.629 | 0.624 | 0.600 | 0.581 | 0.556 |
| full average macro-F1 | 0.758 | 0.757 | 0.759 | **0.763** | 0.763 | 0.754 | 0.740 | 0.718 | 0.702 | 0.660 |

Margins 0.35, 0.45 and 0.55 are left out of the table; none scores higher.

Chosen: **0.10** out-of-fold (dev macro-F1 0.644 against 0.636 at argmax, a
gain of 0.008 on 380 rows); 0.15 on the full average.

## Test (frozen random split, 299 rows), after the dev choice

| rule | margin | macro-F1 | accuracy | neutral called polar | polar called neutral |
|---|---|---|---|---|---|
| argmax | 0 | **0.634** | 0.702 | 32 | 49 |
| dev-chosen, out-of-fold (the result) | 0.10 | 0.612 | 0.702 | 27 | 54 |
| dev-chosen, full average | 0.15 | 0.620 | 0.712 | 24 | 54 |
| mean of the seeds' margins | 0.12 | 0.618 | 0.709 | 25 | 54 |

Base FinBERT on the same split: 0.571, accuracy 0.699.

## What it shows

1. **The dev-chosen margin is 0.10, reported with argmax beside it.**
   It is close to the 0.12 used so far. It is a stand-in, not the averaged
   model's own margin: 320 of the 380 out-of-fold rows are scored by one
   seed alone, so 0.10 is in effect a single-model margin. Averaging three
   models flattens their probabilities: on the 380 dev rows the strongest
   polar class beats neutral by 0.51 on average under the three-seed
   average, against 0.57 for a single seed (0.45 to 0.66), and 9.5% of rows
   fall within 0.10 of neutral against 6.7%. A given margin therefore moves
   more of the average's sentences to neutral, so its true best margin is
   likely smaller. No clean dev set
   exists for the three-seed average; only a retrain with a shared held-out
   set would give one. The dev gain that chooses 0.10, 0.008, is small for
   380 rows.
2. **On test the margin makes no measurable difference.** Paired bootstrap
   over the 299 test rows (10,000 resamples, seed 2026): macro-F1 at 0.10
   minus macro-F1 at argmax is −0.022 (bootstrap mean −0.022), 95%
   interval −0.058 to +0.009, which includes 0. The two rules disagree on
   10 of the 299 rows.
3. **The test result can't be used to drop the margin.** Keeping the
   dev-chosen 0.10 is what the procedure says; reporting argmax beside it is
   allowed; choosing argmax because of this table is choosing on test. A
   rule fixed now (for example, a margin only if its dev gain exceeds the
   noise) has seen this table and must be recorded as such.
4. **A correction to the 4 Oct write-up.** Its "0.12" test figures (0.612,
   accuracy 0.702) were computed by `train/error_analysis.py` at the
   unrounded mean of the seeds' margins, 0.1167, while printing 0.12. At
   exactly 0.12, which the full-corpus preview used, test macro-F1 is 0.618
   and accuracy 0.709 (above).

## The bootstrap

```python
# test: ev._load_test_set(); avg: the three seeds' averaged probabilities on it
gold = test["label"].to_numpy()
a, m = np.array(apply_margin(avg, 0.0)), np.array(apply_margin(avg, 0.10))
f = lambda g, p: f1_score(g, p, labels=LABELS, average="macro", zero_division=0)
rng = np.random.default_rng(2026)
diffs = []
for _ in range(10_000):
    idx = rng.integers(0, len(gold), len(gold))
    diffs.append(f(gold[idx], m[idx]) - f(gold[idx], a[idx]))
print(np.mean(diffs), np.percentile(diffs, [2.5, 97.5]))   # -0.0222 [-0.0579  0.0086]
```

## To reproduce

```python
import numpy as np, pandas as pd
import train.evaluate as ev
from train.error_analysis import best_margin, apply_margin, dev_split
from train.labels import LABELS
ev.best_device = lambda: "cpu"
models = {s: f"models/experiments-2026-10-03/label/seed_{s}/final" for s in (42, 1, 7)}
full = pd.read_csv(ev.CANDIDATES_PATH)
train_dev = full[(full["split"] == "train_dev") & full["label"].isin(LABELS)]
devs = {s: dev_split(train_dev, s, models[s]) for s in models}
union = pd.concat(devs.values()).drop_duplicates(["sentence_id", "aspect"]).reset_index(drop=True)
keys = list(zip(union["sentence_id"], union["aspect"]))
held = {s: set(zip(devs[s]["sentence_id"], devs[s]["aspect"])) for s in models}
probs = {s: ev.finetuned_probs(models[s], union) for s in models}
oof = np.array([np.mean([probs[s][i] for s in models if keys[i] in held[s]], axis=0) for i in range(len(keys))])
print(best_margin(oof, union["label"].tolist()))          # (0.1, 0.6439...)
```
