# The model re-run on Opus's labels (2026-10-11)

On 10 Oct 2026 the team decided that every model is re-run, that the
evaluation gives precision and recall for each class beside macro-F1 and
accuracy, and that the dashboard and chatbot use the fine-tuned FinBERT with
the best results. This is that run: 11 Oct 15:51 to 12 Oct 00:07 on the
MacBook's GPU, about eight hours, no step failed. Nothing was written to the
database.

## What was trained, and on what

- **Training rows: 1,563**, on Opus 5.5's labels under the rules of 10 Oct
  (616 positive, 586 neutral, 361 negative): 917 from the first round, 275
  broker research, 240 top-up and 131 active-learning. Left out: 112 rows
  Opus flagged as not about the bank, and 1 row that was a near-copy of a
  test sentence.
- **Test rows:** the first round's 299, on the labels people gave them, and
  the broker research round's 100 blind rows (annotator recorded on 11 Oct).
  No test row or near-copy of one is among the training rows, in either
  scope.
- **Pretraining:** FinBERT's masked-word training continued for 3 epochs on
  42,822 of the corpus's 45,844 sentences. Left out by the leakage filter:
  2,270 labelled sentences, 37 with the same text as one, 147 holding one or
  held in one, and 568 sharing most of their words with one. About 1 hour 40
  minutes.
- **Fine-tuning:** the standing configuration (8 epochs with early stopping,
  the readable aspect label as input, plain cross-entropy), from FinBERT and
  from the adapted encoder, seeds 42, 1 and 7. Nothing was tuned in this run.

## Cross-validation on the training rows

Dev macro-F1 against Opus's labels, 5 folds, each seed's folds trained from
both starting points so the differences are paired.

| fold | seed 42: FinBERT | adapted | seed 1: FinBERT | adapted | seed 7: FinBERT | adapted |
|---|---|---|---|---|---|---|
| 0 | 0.651 | 0.673 | 0.682 | 0.713 | 0.636 | 0.667 |
| 1 | 0.731 | 0.748 | 0.666 | 0.681 | 0.713 | 0.722 |
| 2 | 0.683 | 0.677 | 0.719 | 0.703 | 0.705 | 0.691 |
| 3 | 0.687 | 0.680 | 0.673 | 0.715 | 0.704 | 0.724 |
| 4 | 0.692 | 0.693 | 0.683 | 0.698 | 0.660 | 0.708 |
| mean | 0.689 | 0.694 | 0.685 | 0.702 | 0.684 | 0.702 |

Over the 15 paired folds: FinBERT 0.686, adapted 0.700; difference +0.014
(sd 0.020), adapted better in 11 of 15; paired t = 2.75, p = 0.016; Wilcoxon
p = 0.015; 95% interval +0.003 to +0.025.

## The test rows

Mean of the three seeds, with the seeds' standard deviation of macro-F1, and
the three models averaged (mean probabilities, then the most likely class).
P / R is precision and recall.

**First round, 299 rows** (166 neutral, 94 positive, 39 negative)

| model | accuracy | macro-F1 | negative P / R | neutral P / R | positive P / R |
|---|---|---|---|---|---|
| Base FinBERT, no fine-tuning | 0.699 | 0.571 | 0.53 / 0.21 | 0.68 / 0.91 | 0.79 / 0.53 |
| Fine-tuned on people's labels, 1 Oct: mean (sd 0.035) | 0.651 | 0.604 | 0.44 / 0.48 | 0.76 / 0.64 | 0.60 / 0.73 |
| Fine-tuned on people's labels, 4 Oct retrain: mean (sd 0.027) | 0.693 | 0.621 | 0.51 / 0.41 | 0.73 / 0.81 | 0.70 / 0.61 |
| Fine-tuned on Opus's labels, 11 Oct: mean (sd 0.020) | 0.682 | 0.631 | 0.49 / 0.49 | 0.77 / 0.72 | 0.62 / 0.70 |
| the three averaged | 0.702 | 0.641 | 0.52 / 0.44 | 0.78 / 0.75 | 0.64 / 0.73 |
| **Adapted encoder, fine-tuned on Opus's labels, 11 Oct: mean (sd 0.018)** | 0.689 | **0.649** | 0.48 / 0.61 | 0.77 / 0.71 | 0.67 / 0.68 |
| **the three averaged** | 0.716 | **0.670** | 0.48 / 0.59 | 0.81 / 0.73 | 0.69 / 0.73 |

**Broker research, 100 rows** (42 positive, 35 neutral, 23 negative)

| model | accuracy | macro-F1 | negative P / R | neutral P / R | positive P / R |
|---|---|---|---|---|---|
| Base FinBERT, no fine-tuning | 0.690 | 0.687 | 0.70 / 0.83 | 0.68 / 0.49 | 0.69 / 0.79 |
| Fine-tuned on people's labels, 4 Oct retrain: mean (sd 0.065) | 0.670 | 0.659 | 0.75 / 0.61 | 0.62 / 0.54 | 0.67 / 0.81 |
| Fine-tuned on people's labels with broker rows, 7 Oct: mean (sd 0.016) | 0.693 | 0.692 | 0.76 / 0.74 | 0.66 / 0.54 | 0.69 / 0.79 |
| Fine-tuned on Opus's labels, 11 Oct: mean (sd 0.008) | 0.710 | 0.705 | 0.67 / 0.87 | 0.70 / 0.52 | 0.75 / 0.78 |
| the three averaged | 0.690 | 0.683 | 0.66 / 0.91 | 0.67 / 0.46 | 0.73 / 0.76 |
| **Adapted encoder, fine-tuned on Opus's labels, 11 Oct: mean (sd 0.021)** | 0.740 | **0.740** | 0.69 / 0.88 | 0.71 / 0.64 | 0.80 / 0.75 |
| **the three averaged** | 0.770 | **0.770** | 0.70 / 0.91 | 0.77 / 0.69 | 0.82 / 0.76 |

**Both, 399 rows** (201 neutral, 136 positive, 62 negative)

| model | accuracy | macro-F1 | negative P / R | neutral P / R | positive P / R |
|---|---|---|---|---|---|
| Base FinBERT, no fine-tuning | 0.697 | 0.648 | 0.64 / 0.44 | 0.68 / 0.84 | 0.75 / 0.61 |
| Fine-tuned on people's labels, 4 Oct retrain: mean (sd 0.020) | 0.688 | 0.647 | 0.60 / 0.48 | 0.71 / 0.76 | 0.69 / 0.67 |
| Fine-tuned on Opus's labels, 11 Oct: mean (sd 0.010) | 0.689 | 0.669 | 0.57 / 0.63 | 0.76 / 0.68 | 0.66 / 0.73 |
| the three averaged | 0.699 | 0.677 | 0.58 / 0.61 | 0.77 / 0.70 | 0.67 / 0.74 |
| **Adapted encoder, fine-tuned on Opus's labels, 11 Oct: mean (sd 0.013)** | 0.702 | **0.685** | 0.56 / 0.71 | 0.76 / 0.70 | 0.71 / 0.70 |
| **the three averaged** | 0.729 | **0.709** | 0.56 / 0.71 | 0.80 / 0.73 | 0.73 / 0.74 |

Accuracy by source, the three adapted models averaged: Reddit 0.68 (184
rows), broker research 0.77 (100), earnings 0.81 (79), Google News 0.68
(34).

## What it shows

1. **The best set is the adapted encoder fine-tuned on Opus's labels.** By
   the rule fixed before the run (test macro-F1 over three seeds,
   cross-validation as the tie-breaker) it leads on the first round's rows
   (0.649), on the broker research rows (0.740) and on both (0.685), and
   cross-validation agrees (+0.014, better in 11 of 15 folds, p = 0.016).
2. **Its lead over FinBERT fine-tuned the same way is small.** 0.649 against
   0.631 on the first round's rows is about one seed standard deviation.
   What makes it the choice is that every measure points the same way, not
   the size of any one gap.
3. **Against base FinBERT the gain is clear on the first round's rows**:
   0.649 against 0.571, about four seed standard deviations, and negative
   recall rises from 0.21 to 0.61.
4. **On broker research text, fine-tuning on people's labels did not beat
   base FinBERT** (0.659 and 0.692 against 0.687). The adapted encoder on
   Opus's labels does (0.740).
5. **Training on Opus's labels did not cost anything on people's test
   labels.** The models are tested on labels made under the older rules and
   still score above those trained on people's labels (0.631 and 0.649
   against 0.621).
6. **Reddit is still the weak source**: 0.68 accuracy, the same as on
   6 Oct.

## Two gaps closed on 12 Oct

The comparison left two things untested. Both were run on 12 Oct; neither
changes the choice.

**A neutral threshold for the chosen model.** Chosen as on 4 Oct
([ensemble-margin-2026-10-04.md](ensemble-margin-2026-10-04.md)): each of
the 601 dev rows the three seeds held out (504 by one seed, 90 by two, 7 by
all three) is scored by the average of only the seeds that held it out, and
the margin with the highest macro-F1 there is taken before any test row is
scored. Against the LLM's labels macro-F1 is 0.710 with no margin and 0.680
to 0.704 with any margin from 0.05 to 0.60, so the chosen margin is 0: the
averaged model is used as it is. Reported only: on the 299 test rows the
same margins score 0.664 to 0.676.

**The weighting techniques on the chosen setup.** On 1 Oct they were tested
on plain FinBERT with people's labels. Here each runs on the adapted encoder
with the LLM's labels, on the same seeds and folds as the chosen model, so
the differences are paired. The rule was written into the run script before
it started: a weighted variant replaces the chosen model only if its gain
has p < 0.05 and its test macro-F1 over three seeds is higher.

| variant | dev macro-F1 | chosen model | difference (sd) | folds better | paired t, p | 95% interval |
|---|---|---|---|---|---|---|
| balanced class weights and source weights | 0.697 | 0.700 | −0.003 (0.015) | 6 of 15 | −0.65, 0.52 | −0.011 to +0.006 |
| balanced class weights | 0.697 | 0.700 | −0.002 (0.011) | 7 of 15 | −0.85, 0.41 | −0.009 to +0.004 |
| source weights | 0.696 | 0.700 | −0.004 (0.017) | 6 of 15 | −0.89, 0.39 | −0.014 to +0.006 |

None gains. Three final models were trained with both weightings, to give
the comparison a test row:

| test rows | chosen: mean (sd), averaged | both weightings: mean (sd), averaged |
|---|---|---|
| first round, 299 | 0.649 (0.018), 0.670 | 0.651 (0.020), 0.664 |
| broker research, 100 | 0.740 (0.021), 0.770 | 0.739 (0.027), 0.746 |
| both, 399 | 0.685 (0.013), 0.709 | 0.689 (0.008), 0.699 |

Row by row the two averaged models disagree on 29 of the 399 test
sentences (the chosen one right on 17, the other on 12; exact test
p = 0.46). The chosen model stands.

**The index balance, checked both ways.** On all 399 test rows the weighted
model's net balance, (positive − negative) / all, is closer to the labels:
+0.188 against +0.185, where the chosen model reads +0.153. On the 601
held-out training rows it is closer overall (+0.140 against +0.131; chosen
+0.108) but far off on broker research (+0.180 against +0.054; chosen
+0.009): the source weights give broker research rows 0.08 and Reddit rows
1.52. Neither model is reliably closer, so the balance is not a reason to
change the choice.

Files: `neutral_margin.py`, `margin_adapted.json`, `margin_weighted.json`,
`dev_balance.json`, `run_weighting.sh`, `cv_weighting.jsonl` and
`progress_weighting.log` in `data/eval/model-rerun-2026-10-11/`. The
weighted models are in `models/experiments-2026-10-11/dapt-weighted/` (not
in git).

## Limits

- One run of three seeds. The gaps between fine-tuned sets are of the size
  of the seed spread.
- The cross-validation folds are scored against Opus's labels, the test
  rows against people's. The first round's test labels were made with a
  model's suggestion in view (89% match it) and under the older retail rule.
- The 7 Oct adapted models are not in the tables: their pretraining had read
  sentences related to test sentences. The earlier 0.751 on the broker
  research rows was theirs.
- Averaging three models helps the adapted set (0.670 from 0.649) more than
  the FinBERT set (0.641 from 0.631); with three seeds that difference is
  not established.

## Files

- Scripts, the 30 cross-validation scores, the progress log, both result
  tables as written by the run, the pretraining statistics and the models'
  SHA-256 values: `data/eval/model-rerun-2026-10-11/`.
- Label file: `data/labeled/llm_rater/rules-2026-10-10/training_set.csv`;
  broker test rows: `data/labeled/sgx_research/resolved_test_blind.csv`.
- Models (not in git): `models/dapt-2026-10-11/` and
  `models/experiments-2026-10-11/{finbert,dapt}/seed_{42,1,7}/final`.
