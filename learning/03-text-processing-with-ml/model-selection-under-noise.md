# Model selection under noise

Subject: Text Processing with Machine Learning (module 3) · Bloom target: Analyze / Evaluate / Create
Prerequisites: [evaluation-splits-and-leakage](evaluation-splits-and-leakage.md),
[transfer-learning-and-finbert](transfer-learning-and-finbert.md).

---

## 1. Why it matters here (Understand)

With 978 labelled training rows, the difference between two reasonable
fine-tuning configurations is often smaller than the difference between two
runs of the *same* configuration. Choosing on noise produces a "best" model
that isn't, and a report that claims an improvement that won't replicate.
On 1 October this project tested four changes to the sentiment model and
had to decide which, if any, were real
([finetune-fixes-2026-10-01.md](../../docs/evidence/finetune-fixes-2026-10-01.md)).

---

## 2. The concept (Understand / Apply)

**Three splits, three jobs.** Training data fits the weights; validation
data (dev, or cross-validation folds) chooses between configurations; the
test split measures the chosen one, once. Choosing on test turns it into a
second dev set and inflates the reported score.

**k-fold cross-validation.** Split the train/dev pool into k folds; train k
times, each time holding one fold out; average the k held-out scores. Every
row is used for validation once, so the estimate is steadier than one 15%
dev slice. Stratifying the folds keeps each fold's class mix the same.

**Paired comparison.** Two configurations run on the same folds can be
compared fold by fold. The mean of the differences, and how many folds
favour one, says more than the two means side by side, because fold
difficulty cancels out.

**The noise floor.** Run the same configuration twice with something that
shouldn't matter changed, and look at the fold-by-fold differences. Any
"improvement" smaller than that spread is indistinguishable from noise.

**Post-hoc thresholds.** A classifier's decision rule can be tuned
separately from its weights, e.g. "predict neutral unless a polar class
beats neutral by more than a margin m". The margin is a hyperparameter:
choose it on dev, never on test.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| one CV fold (`--folds 5 --fold F`) | `train/finetune.py` `fold_split` |
| class and source weighting | `train/finetune.py` `WeightedTrainer`, `ratio_weights` |
| the margin rule, chosen per seed on its own dev split | `train/error_analysis.py` `apply_margin`, `best_margin` |
| several models averaged | `train/evaluate.py` `eval_ensemble` |
| the results | `docs/evidence/finetune-fixes-2026-10-01.md`, `error-analysis-2026-10-01.md` |

---

## 4. Analyze

**The noise floor here.** The baseline was cross-validated twice, on 30
September and 1 October, identical except for how batches were padded
(which changes no computation). Fold-by-fold the two runs differed by
+0.037, −0.010, −0.014, −0.023 and +0.007: a standard deviation of 0.024.

**The four changes, against that floor** (mean of fold differences from the
baseline, folds better):

| change | mean difference | folds better | larger than the floor? |
|---|---|---|---|
| balanced class weights | +0.009 | 4 of 5 | no |
| source weights | +0.012 | 4 of 5 | no |
| readable aspect name | +0.016 | 4 of 5 | no |
| prior class weights | −0.096 | 1 of 5 | yes, worse |

Each of the first three leans the same way in four folds, but no single
gain exceeds what re-running the baseline produced. Combining all three
scored 0.635, below the readable name alone (0.637): the weightings added
nothing.

**Why "prior" weights collapsed, and why CV couldn't judge them.** Prior
weights scale each class by corpus share ÷ training share (neutral ×1.8,
negative ×0.4), aiming the model at the corpus, which is 70% neutral by
base FinBERT. But the CV dev folds are drawn from the training pool, 38%
neutral, so CV punishes exactly the shift the weights were for. Judging
them needs dev data sampled like the corpus.

**The margin rule.** Seed 42's dev split chose m = 0.15, seed 7's 0.25,
seed 1's 0 (no change). On test the mean over seeds moved from 0.604 to
0.619, and for the three-model average from 0.614 to 0.624, trading 13
neutral-called-polar errors for 7 polar-called-neutral ones.

---

## 5. Evaluate

The selection was sound in procedure: the rule for combining changes was
fixed before the combined run, CV chose, and test was scored once. Its
weakness is power. Five folds of about 196 rows, one seed, and gains below
the noise floor mean the chosen configuration is "no worse, probably a
little better", not "better". The test result points the same way (every
seed at least as good as its 30 September counterpart), which is
reassuring but not independent proof, since the 299 test rows are few and
their labels were anchored on a model's suggestion.

What the evidence does *not* show: that class or source weighting is
useless (the dev folds can't reward a shift towards the corpus), or that
the readable aspect name works for the reason one might guess (FinBERT
already splits `dividend_policy` into the same words; five labels add
words such as "Not an investment aspect").

When the opposite choice would be right: with a dev set sampled like the
corpus, prior weights could be judged fairly and might win; with ten times
the labels, a single CV run would have the power to call +0.016 real.

---

## 6. Create

**Exercise (≈ 90 minutes, mostly waiting).** Measure the noise floor
properly: cross-validate the baseline with seeds 1 and 7 as well as 42
(`train.finetune --seed S --epochs 8 --folds 5 --fold F`), and compute the
spread of fold scores for the same fold across seeds.

*Expected outcome:* a seed-to-seed spread of the same order as the 0.024
measured from padding (two seeds' test scores already differ by up to
0.065), which would confirm that none of the 1 October gains can be called
real from one seed's CV.

---

## 7. Self-check

1. Why may the margin be chosen on dev but not on test?
2. Two configurations score 0.630 and 0.621 in CV. What else do you need
   before calling the first better?
3. Why did combining three individually positive changes not help?
4. Why can't cross-validation evaluate a correction aimed at the corpus's
   class mix?
5. The test score agrees with CV. Why is that weaker evidence than it looks?

<details>
<summary>Answers</summary>

1. Choosing on test makes the test score the best of several tries, so it
   overstates how the chosen rule would do on new data.
2. The paired fold differences and a noise floor: if re-running either
   configuration moves folds by more than 0.009, the gap is noise.
3. They overlap in what they change (two are loss weightings) and each gain
   was within noise; adding noise to noise doesn't make a signal.
4. Its dev folds are drawn from the training pool, so they share the
   training class mix, not the corpus's.
5. 299 rows, 39 of them negative, labels anchored on a model's suggestion,
   and the same direction is what random variation produces half the time.

</details>

---

## 8. Sources

**Repository**

- `train/finetune.py`, `train/error_analysis.py`, `train/evaluate.py`
- `docs/evidence/finetune-experiments-2026-09-30.md` (the first CV run),
  `finetune-fixes-2026-10-01.md`, `error-analysis-2026-10-01.md`

**Measured in this repository (2026-10-01)**

- Every figure in sections 4 and 5, from the evidence files above.

**External**

- Kohavi, R. (1995), "A Study of Cross-Validation and Bootstrap for
  Accuracy Estimation and Model Selection", IJCAI. **Not fetched during
  this pass**; cite the paper directly.
- Dietterich, T. G. (1998), "Approximate Statistical Tests for Comparing
  Supervised Classification Learning Algorithms", *Neural Computation*
  10(7). On why fold-level comparisons need care. **Not fetched.**

**Not verified**

- The seed-to-seed spread in CV (exercise 6) has not been measured.
