# Fine-tuning fixes: class weights, source weights, readable aspect labels

Follows [finetune-experiments-2026-09-30.md](finetune-experiments-2026-09-30.md)
(8 epochs, sentence + aspect: test macro-F1 0.577 ± 0.027, 5-fold CV dev
0.622 ± 0.028). Its error analysis of seed 42 on test found the model calls
neutral sentences positive or negative too often (48 of its 102 errors) and is
weakest on Reddit (accuracy 0.64, base FinBERT 0.70), and the labelled
training set doesn't look like the corpus it will score. Run 2026-10-01 on
this MacBook Air (M1, 16 GB, MPS), same cleaned labels (978 train/dev, 299
test).

## A bug found first: the class weights were never applied

`train/finetune.py` computed balanced class weights
(`compute_class_weight("balanced")`) and printed them, but the `Trainer` was
never given them: every model up to 30 Sep, including E1 to E3, trained
with plain cross-entropy. The docstring, the technical spec and
[finetune-2026-09-30.md](finetune-2026-09-30.md) said "class-weighted"; they
now say what ran. Weighting is now a real option, default `none`, so the
earlier results still reproduce.

## What changed in the code

| change | option | what it does |
|---|---|---|
| per-batch padding | always | pads each batch to its own longest pair instead of the whole set to 128 tokens; speed only |
| class weights | `--class-weights {none,balanced,prior}` | `balanced`: inverse class frequency in the training rows. `prior`: corpus share ÷ training share per class, the corpus share being base FinBERT's per-sentence distribution (negative 9.7%, neutral 70.0%, positive 20.3%) |
| source weights | `--source-weights` | weights each training row by corpus share ÷ training share of its source, so the training mix matches the corpus |
| readable aspect | `--aspect-text label` | feeds the aspect's `label` from `config/aspects.yaml` ("Dividend Policy") instead of its key (`dividend_policy`); recorded in the model's `input_format.json` so evaluation feeds the same |
| several models | `train.evaluate --model-dir d1 d2 d3` | reports each model and their average (mean of the softmax probabilities) |
| accuracy by source | always | `train.evaluate` prints accuracy per source for every model and baseline |

Class and source weights multiply into one weight per row; the loss is the
weighted mean of per-row cross-entropy.

Source weights over the whole train/dev pool (in the CV folds, computed on
each fold's 782 or 783 training rows: Reddit 1.26–1.33, earnings 0.68–0.73,
google_news 0.91–0.99; the two tiny sources vary more):

| source | train/dev rows | corpus share | weight |
|---|---|---|---|
| arctic_shift (Reddit) | 433 (44%) | 55.6% | 1.30 |
| earnings | 398 (41%) | 27.6% | 0.70 |
| google_news | 132 | 12.3% | 0.94 |
| yahoo_news | 14 | 0.8% | 0.56 |
| newsapi | 1 | 0.1% | 0.59 |

(The test split is 184 of 299 Reddit, 62%.)

Class weights as applied (fold 0): `balanced` negative 1.38, neutral 0.87,
positive 0.89; `prior` negative 0.40, neutral 1.82, positive 0.54.

## Padding check

Seed 42, 8 epochs, the 30 Sep train/dev split, dev macro-F1 per epoch:

| padding | epoch 1 | 2 | 3 | 4 | 5 | best |
|---|---|---|---|---|---|---|
| whole set to 128 (E1, 30 Sep) | 0.389 | 0.569 | **0.641** | 0.635 | 0.630 | 0.641, epoch 3 |
| per batch (1 Oct) | 0.464 | 0.500 | **0.626** | 0.608 | 0.619 | 0.626, epoch 3 |

Both stop after epoch 5 with the best at epoch 3. On 147 dev rows a 0.015
gap is within run-to-run noise (MPS training isn't bit-for-bit
reproducible), and the 5-fold baseline below agrees: 0.621 against 0.622.
Training took 367 s against 834 s, but the machine's other load differed, so
the speed-up is indicative only.

## Cross-validation: one change at a time

```bash
.venv-plp/bin/python3 -m train.finetune --seed 42 --epochs 8 --folds 5 --fold $f \
    --out-dir models/experiments-2026-10-01/cv [--class-weights balanced|prior] [--source-weights] [--aspect-text label]
```

(`HF_HUB_OFFLINE=1`; folds 0–4, each 782 or 783 training and 195 or 196 dev
rows; fold models deleted after scoring.) Each variant is the 30 Sep
configuration (8 epochs, sentence + aspect key) with one change. Dev
macro-F1:

| variant | fold 0 | fold 1 | fold 2 | fold 3 | fold 4 | mean ± sd | vs none, mean of fold differences | folds better |
|---|---|---|---|---|---|---|---|---|
| none (baseline, per-batch padding) | 0.704 | 0.604 | 0.587 | 0.605 | 0.605 | 0.621 ± 0.047 | — | — |
| `--class-weights balanced` | 0.713 | 0.596 | 0.591 | 0.611 | 0.641 | 0.630 ± 0.050 | +0.009 | 4 |
| `--class-weights prior` | 0.398 | 0.555 | 0.530 | 0.623 | 0.517 | 0.525 ± 0.082 | −0.096 | 1 |
| `--source-weights` | 0.690 | 0.638 | 0.604 | 0.625 | 0.606 | 0.633 ± 0.035 | +0.012 | 4 |
| `--aspect-text label` | 0.682 | 0.610 | 0.652 | 0.627 | 0.617 | **0.637 ± 0.029** | +0.016 | 4 |
| *none, whole-set padding (E3, 30 Sep)* | *0.667* | *0.614* | *0.601* | *0.628* | *0.598* | *0.622 ± 0.028* | | |

**How big is noise?** The first and last rows are the same configuration
apart from padding, which doesn't change what the model computes. Their
fold-by-fold differences are +0.037, −0.010, −0.014, −0.023 and +0.007 (sd
0.024). Every gain above is smaller than that. Balanced class weights,
source weights and readable labels each beat the baseline in four folds of
five, which is a consistent lean, but none is a measured improvement on its
own.

**Why `prior` collapses, and why CV can't judge it.** Prior weights make
neutral 1.8 times as costly to miss and negative 0.4 times, so the model
leans to neutral (fold 0 stopped after 3 epochs at 0.398). The dev folds are
drawn from the same labelled pool as training (38% neutral), so CV punishes
a correction aimed at a population that is 56% neutral in the test split and
an estimated 70% in the corpus. Judging it fairly needs dev data sampled
like the corpus, which doesn't exist; the test split must not be used for
selection. It is reported, not chosen.

## Choosing the final configuration

The rule, fixed before the combined run started: combine every change whose
CV mean beat the baseline (balanced, source, label; `prior` can't join
`balanced` anyway, both being class weights); cross-validate the
combination; train three seeds on whichever has the higher CV mean, the
combination or the best single change.

| | fold 0 | fold 1 | fold 2 | fold 3 | fold 4 | mean ± sd | vs none | folds better |
|---|---|---|---|---|---|---|---|---|
| balanced + source + label | 0.669 | 0.615 | 0.640 | 0.617 | 0.634 | 0.635 ± 0.022 | +0.014 | 4 |
| label alone | 0.682 | 0.610 | 0.652 | 0.627 | 0.617 | **0.637 ± 0.029** | +0.016 | 4 |

The weightings add nothing on top of the readable label, so the final
configuration is **8 epochs, sentence + readable aspect label, plain
cross-entropy**: one option different from 30 Sep (`--aspect-text label`).

## Test result

```bash
.venv-plp/bin/python3 -m train.finetune --seed $s --epochs 8 --aspect-text label --out-dir models/experiments-2026-10-01/label
.venv-plp/bin/python3 -m train.evaluate --model-dir models/experiments-2026-10-01/label/seed_{42,1,7}/final
```

Seeds 42, 1, 7 ran 6, 8 and 6 epochs (early stopping ended 42 and 7). Test split, n = 299 (39
negative, 166 neutral, 94 positive):

| configuration | CV dev | test macro-F1 (seeds 42, 1, 7) | mean ± sd | average of the 3 models | negative F1 | neutral F1 | positive F1 | accuracy |
|---|---|---|---|---|---|---|---|---|
| base FinBERT, zero-shot | — | 0.571 | — | — | 0.30 | 0.78 | 0.64 | 0.70 |
| E1, 30 Sep: aspect key | 0.622 | 0.607, 0.560, 0.563 | 0.577 ± 0.027 | 0.573 | 0.44 | 0.66 | 0.63 | 0.66, 0.60, 0.60 |
| **1 Oct: readable aspect label** | **0.637** | **0.630, 0.617, 0.565** | **0.604 ± 0.035** | **0.615** | 0.45 | 0.70 | 0.66 | 0.68, 0.67, 0.61 |
| TF-IDF + logistic regression | — | 0.515 | — | — | 0.35 | 0.65 | 0.55 | 0.57 |
| VADER lexicon | — | 0.427 | — | — | 0.24 | 0.50 | 0.54 | 0.49 |

Per-class F1 is the mean over the three seeds. Each seed trains on the same
85/15 split as the E1 model with that seed, so the pairs compare directly:
+0.022, +0.057 and +0.002.

**Where the errors are** (counts out of 299; the 3-model average in the
last column of each group):

| | errors | neutral called polar | polar called neutral | positive ↔ negative |
|---|---|---|---|---|
| base FinBERT | 90 | 15 | 70 | 5 |
| E1 seeds 42, 1, 7 / average | 102, 120, 120 / 114 | 48, 82, 73 / 70 | 41, 23, 35 / 31 | 13, 15, 12 / 13 |
| label seeds 42, 1, 7 / average | 96, 99, 118 / 101 | 52, 50, 75 / 57 | 34, 37, 29 / 32 | 10, 12, 14 / 12 |

**Accuracy by source** (seeds 42, 1, 7 / average of the three):

| source (test rows) | base FinBERT | E1, 30 Sep | readable label, 1 Oct |
|---|---|---|---|
| Reddit (184) | 0.70 | 0.64, 0.51, 0.58 / 0.56 | 0.66, 0.63, 0.55 / 0.63 |
| earnings (79) | 0.73 | 0.72, 0.78, 0.67 / 0.76 | 0.73, 0.75, 0.72 / 0.73 |
| google_news (34) | 0.65 | 0.65, 0.68, 0.59 / 0.65 | 0.71, 0.74, 0.68 / 0.71 |
| yahoo_news (2) | 0.50 | 0.00 for all | 0.00 for all |

The error and per-source tables come from re-scoring the saved models on the
CPU (`train.evaluate`'s functions with the device set to CPU, while the GPU
ran J2); every macro-F1 matched the GPU evaluation to four decimals.

## What it shows

1. **The readable aspect label is the one change that helped, on CV and on
   test.** It led CV (0.637 against 0.621), and on test every seed scored at
   least as well as the 30 Sep model trained on the same split (mean 0.604
   against 0.577). Against base FinBERT (0.571) the mean is ahead by 0.033,
   about one seed standard deviation: two seeds and the 3-model average are
   ahead, seed 7 is behind. Why the label helps is untested. It isn't
   tokenization: FinBERT already splits `dividend_policy` into the same
   words with `_` between them. Five labels carry words the keys don't
   ("Other / Not an investment aspect", "Retail Banking Products & Customer
   Experience", "Wealth Management / Private Banking", "Investor / Retail
   Stock Sentiment", "Asset Quality / Provisioning"), which may be what the
   model uses.
2. **The three-model average is the safer model**: 0.615, close to the
   better seeds, without depending on which seed is picked. It costs three
   times the inference.
3. **The weightings didn't help.** Balanced class weights and source
   weights each leaned slightly positive on CV (within noise) and added
   nothing on top of the readable label. Prior weights can't be judged on
   this data (above).
4. **The main error is unchanged in kind.** Neutral sentences called
   positive or negative fell from 68 to 59 per model on average, but base
   FinBERT makes only 15 such errors and errs the other way (70 polar
   sentences called neutral). Base FinBERT still has the higher accuracy
   (0.70 against 0.66 for the average) and the higher Reddit accuracy
   (0.70 against 0.63); the fine-tuned models win macro-F1 because they find
   more of the negative and positive sentences.

Whether this model should replace base FinBERT for scoring the corpus is a
team decision (PLAN section 5), not taken here. If it does, the scores'
character changes: fewer sentences called neutral, more called positive or
negative.

## Caveats

As before: test labels weren't independent of the LLM's suggestion; 39
negative test rows, so one sentence moves negative F1 by about 0.02; MPS
training isn't bit-for-bit reproducible. Here also: the configuration was
chosen by CV with one seed (42), and the dev fold that stops training early
is the one scored, which flatters every CV number equally; the 1 Oct and 30
Sep models differ in padding as well as the aspect text, a difference the
padding check puts within noise; the 2 yahoo_news test rows are too few to
read.

## Model weights

Saved on the MacBook that ran them under `models/experiments-2026-10-01/`
(not in git; 437,961,724 bytes each). Each `final/` folder holds the
tokenizer, config and `input_format.json`
(`{"with_aspect": true, "aspect_text": "label"}`), which `train.evaluate`
reads. Cross-validation fold models were not kept.

| model | SHA-256 of `model.safetensors` |
|---|---|
| `models/experiments-2026-10-01/label/seed_42/final` | `e536ffe3af5694c1a15625202cf292542a2f7c0e0517fbd9455c285715729633` |
| `models/experiments-2026-10-01/label/seed_1/final` | `116a79d79f2a27953ff50fdfa19cc3129a6b23f4b1de2f9fba25e9a481f01dda` |
| `models/experiments-2026-10-01/label/seed_7/final` | `d2f0ef04f768991a601222775c79ce3188fa0ec2b538756603b8eb28ad10909c` |
