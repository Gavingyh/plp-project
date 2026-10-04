# Does the readable aspect label help? Cross-validation on two more seeds

On 1 October the fine-tuning configuration was chosen by 5-fold
cross-validation on seed 42 alone. The readable aspect label
(`--aspect-text label`) beat the aspect key by +0.016 dev macro-F1, better in
4 folds of 5, but that gain was smaller than the noise between two runs of
one configuration (sd 0.024), so it was reported as a lean, not a measured
improvement ([finetune-fixes-2026-10-01.md](finetune-fixes-2026-10-01.md)).
This repeats the same comparison with seeds 1 and 7. Run 2026-10-01 23:46
to 2026-10-02 03:04 on the M1's GPU; fold models deleted after scoring;
nothing written to the database.

```bash
for seed in 1 7; do for f in 0 1 2 3 4; do
  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m train.finetune --seed $seed --epochs 8 --folds 5 --fold $f \
      --out-dir models/experiments-2026-10-02/cv [--aspect-text label]
done; done
```

The seed sets both the fold partition (`StratifiedKFold(random_state=seed)`)
and the training seed, so each seed is a fresh draw of both. Within a seed,
the two inputs see identical folds, so their fold-by-fold differences are
paired. Everything else is the 1 October baseline: 8 epochs with early
stopping (patience 2), plain cross-entropy, per-batch padding. All 20 runs
exited cleanly; scores range from 0.603 to 0.678, with no sign of the GPU
failure seen in the index preview.

## Results

Dev macro-F1 per fold:

| seed | input | fold 0 | fold 1 | fold 2 | fold 3 | fold 4 | mean ± sd |
|---|---|---|---|---|---|---|---|
| 42 (1 Oct) | aspect key | 0.704 | 0.604 | 0.587 | 0.605 | 0.605 | 0.621 ± 0.047 |
| 42 (1 Oct) | readable label | 0.682 | 0.610 | 0.652 | 0.627 | 0.617 | 0.638 ± 0.029 |
| 1 | aspect key | 0.622 | 0.655 | 0.649 | 0.646 | 0.639 | 0.642 ± 0.013 |
| 1 | readable label | 0.652 | 0.636 | 0.678 | 0.613 | 0.616 | 0.639 ± 0.027 |
| 7 | aspect key | 0.613 | 0.640 | 0.608 | 0.647 | 0.663 | 0.634 ± 0.023 |
| 7 | readable label | 0.603 | 0.668 | 0.616 | 0.637 | 0.654 | 0.635 ± 0.027 |

(Seed 42's rows are copied from the 1 October file, which gives the label
mean as 0.637 and its lead as +0.016 from unrounded fold scores; the rounded
scores here give 0.638 and +0.017.)

Readable label minus aspect key, fold by fold:

| seed | differences | mean | folds better |
|---|---|---|---|
| 42 | −0.022, +0.006, +0.065, +0.022, +0.012 | +0.017 | 4 of 5 |
| 1 | +0.031, −0.018, +0.028, −0.033, −0.023 | −0.003 | 2 of 5 |
| 7 | −0.010, +0.027, +0.008, −0.010, −0.009 | +0.001 | 2 of 5 |
| **all 15** | sd 0.026 | **+0.005** | **8 of 15** |

## What it shows

**The readable label's lead does not replicate.** Seed 42's +0.017 becomes
−0.003 and +0.001 on the two new seeds. Over all 15 paired folds the mean
difference is +0.005 with a standard deviation of 0.026 (paired t = 0.73,
14 degrees of freedom; 8 of 15 folds better, which is what chance gives).
A 95% t-interval for the effect is −0.010 to +0.020. That interval treats
the 15 folds as independent, which they aren't (folds within a seed share
four fifths of their training data), so the true uncertainty is wider. The
honest statement is: **no measurable difference between the two inputs.**

**How big is the noise?** Two ways to see it:

- Paired fold differences between two inputs vary with a standard deviation
  of 0.026, the same size as the 0.024 measured on 1 October between two
  runs of one configuration. Differences between configurations of about
  0.02 or less can't be separated from noise with one seed's 5 folds.
- The same configuration's cross-validated mean moves between seeds: the
  aspect key scored 0.621, 0.642 and 0.634 (sd 0.011); the readable label
  0.638, 0.639 and 0.635. Seed 42's baseline, against which every 1 October
  change was compared, was the lowest of the three.

**What this changes.**

1. The final models stand. They were trained with the readable label, and
   nothing here says it is worse; their test results (0.604 ± 0.035 over
   three seeds, 0.615 averaged, 0.624 with the neutral margin) are
   unaffected. But the report must not credit the readable label for the
   gain over the 30 September models (test macro-F1 0.577 to 0.604). That
   gain is about one seed standard deviation, and with no measurable effect
   from the label, run-to-run variation is its simplest explanation.
2. The other seed-42 leans (balanced class weights +0.009, source weights
   +0.012) are smaller than this noise too. They remain unproven either way.
3. **The procedure, not the choice, is the lesson.** Choosing by one seed's
   cross-validation was within the noise, as the 1 October evidence warned.
   Three seeds × five folds roughly rules out an effect larger than 0.02
   (less certainly than the interval suggests, given the dependence between
   folds), and is the least any future choice between configurations should
   use.

## Caveats

- Training on the Apple GPU is not bit-for-bit reproducible.
- The dev folds come from the labelled pool, which is stratified and 38%
  neutral, not sampled like the corpus.
- Three seeds give three cross-validated means; their spread (sd 0.011) is
  itself a rough estimate.
- Time: 3 h 18 min for 20 folds (7.7–12.8 minutes each) on a MacBook Air
  under memory pressure (swap about 10 GB used).
