# Full evaluation of the retrained models on the SGX and original test rows (6 Oct 2026)

Companion to [sgx-research-round-2026-10-04.md](sgx-research-round-2026-10-04.md), which gives the
headline macro-F1 figures. This file lists every metric `train.evaluate` computes (accuracy,
per-class precision, recall and F1, macro and weighted averages, accuracy by source) and the error
breakdown of [finetune-fixes-2026-10-01.md](finetune-fixes-2026-10-01.md) (neutral sentences called
polar, polar sentences called neutral, positive and negative swapped), for the same predictors on
three test scopes: the original 299 rows, the 100 human-labelled SGX rows (blind sheet) and the
combined 399. All figures are from one scoring run per model; nothing was selected on them.

- **old** = the 1 Oct models from the Hugging Face repo `plp-bank-sentiment/plp-finbert-absa`
  (trained without SGX data, with the head-order flaw). **new** = the three retrained seeds
  (`models/sgx-retrain/label`), trained on the original 978 plus 280 SGX train/dev rows with the
  fixed training code. Seeds are listed 42, 1, 7; "3 averaged" averages the three models'
  probabilities, then takes the most likely class.
- **TF-IDF + logistic regression** was trained on the train/dev rows of its scope (the original 978
  for the original 299; the combined 1,258 for the other two), as in `train.evaluate`.
- Precision / recall / F1 are per class, in the order negative, neutral, positive. Macro averages
  weight the three classes equally; weighted F1 weights them by support.
- Rounding: the 1 Oct report's 0.565 (old seed 7) and 0.615 (old averaged) are 0.5645 and 0.6145 here,
  printed to three decimals as 0.564 and 0.614.
- The original-299 rows reproduce the 1 Oct report (base FinBERT 90 errors: 15 neutral called polar,
  70 polar called neutral, 5 swapped; old averaged model 101: 57, 32, 12).
- **Not recomputed:** the neutral-margin results of `train.error_analysis` (a threshold chosen per
  seed on that seed's dev rows). That script has no `--labels` option and reads only the original
  labelled file. On 4 Oct the team found the margin made no measurable difference on test
  ([retrain-2026-10-04.md](retrain-2026-10-04.md)).
- Regenerate with `python -m train.evaluation_report <output.md>` (model paths are constants at the
  top of `train/evaluation_report.py`).

### original 299 (n=299: 39 negative, 166 neutral, 94 positive)

| model | accuracy | macro-F1 | macro precision | macro recall | weighted F1 | negative P / R / F1 | neutral P / R / F1 | positive P / R / F1 |
|---|---|---|---|---|---|---|---|---|
| base FinBERT (zero-shot) | 0.699 | 0.571 | 0.670 | 0.549 | 0.672 | 0.53 / 0.21 / 0.30 | 0.68 / 0.91 / 0.78 | 0.79 / 0.53 / 0.64 |
| VADER | 0.488 | 0.427 | 0.453 | 0.453 | 0.478 | 0.30 / 0.21 / 0.24 | 0.64 / 0.41 / 0.50 | 0.42 / 0.74 / 0.54 |
| TF-IDF + logistic regression | 0.565 | 0.515 | 0.520 | 0.536 | 0.578 | 0.27 / 0.49 / 0.35 | 0.68 / 0.62 / 0.65 | 0.61 / 0.50 / 0.55 |
| old seed 42 | 0.679 | 0.630 | 0.632 | 0.635 | 0.679 | 0.51 / 0.46 / 0.49 | 0.77 / 0.69 / 0.73 | 0.61 / 0.76 / 0.68 |
| old seed 1 | 0.669 | 0.617 | 0.610 | 0.626 | 0.672 | 0.44 / 0.49 / 0.46 | 0.76 / 0.70 / 0.73 | 0.63 / 0.69 / 0.66 |
| old seed 7 | 0.605 | 0.564 | 0.559 | 0.597 | 0.610 | 0.35 / 0.49 / 0.41 | 0.76 / 0.55 / 0.64 | 0.57 / 0.76 / 0.65 |
| old, 3 averaged | 0.662 | 0.614 | 0.608 | 0.629 | 0.665 | 0.44 / 0.49 / 0.46 | 0.77 / 0.66 / 0.71 | 0.61 / 0.74 / 0.67 |
| new seed 42 | 0.696 | 0.631 | 0.649 | 0.621 | 0.692 | 0.55 / 0.41 / 0.47 | 0.75 / 0.77 / 0.76 | 0.65 / 0.68 / 0.66 |
| new seed 1 | 0.645 | 0.589 | 0.589 | 0.601 | 0.647 | 0.42 / 0.41 / 0.42 | 0.77 / 0.64 / 0.70 | 0.58 / 0.76 / 0.65 |
| new seed 7 | 0.679 | 0.611 | 0.655 | 0.602 | 0.673 | 0.62 / 0.33 / 0.43 | 0.75 / 0.72 / 0.73 | 0.60 / 0.76 / 0.67 |
| new, 3 averaged | 0.696 | 0.631 | 0.655 | 0.622 | 0.691 | 0.58 / 0.38 / 0.46 | 0.76 / 0.75 / 0.75 | 0.63 / 0.73 / 0.68 |

Errors of 299 (neutral called polar, polar called neutral, positive and negative swapped):

| model | errors | neutral called polar | polar called neutral | positive <-> negative |
|---|---|---|---|---|
| base FinBERT (zero-shot) | 90 | 15 | 70 | 5 |
| VADER | 153 | 98 | 38 | 17 |
| TF-IDF + logistic regression | 130 | 63 | 49 | 18 |
| old seed 42 | 96 | 52 | 34 | 10 |
| old seed 1 | 99 | 50 | 37 | 12 |
| old seed 7 | 118 | 75 | 29 | 14 |
| old, 3 averaged | 101 | 57 | 32 | 12 |
| new seed 42 | 91 | 38 | 43 | 10 |
| new seed 1 | 106 | 60 | 32 | 14 |
| new seed 7 | 96 | 47 | 40 | 9 |
| new, 3 averaged | 91 | 42 | 40 | 9 |

### SGX 100 (n=100: 23 negative, 35 neutral, 42 positive)

| model | accuracy | macro-F1 | macro precision | macro recall | weighted F1 | negative P / R / F1 | neutral P / R / F1 | positive P / R / F1 |
|---|---|---|---|---|---|---|---|---|
| base FinBERT (zero-shot) | 0.690 | 0.687 | 0.690 | 0.699 | 0.681 | 0.70 / 0.83 / 0.76 | 0.68 / 0.49 / 0.57 | 0.69 / 0.79 / 0.73 |
| VADER | 0.550 | 0.523 | 0.561 | 0.516 | 0.540 | 0.57 / 0.35 / 0.43 | 0.59 / 0.49 / 0.53 | 0.53 / 0.71 / 0.61 |
| TF-IDF + logistic regression | 0.560 | 0.558 | 0.576 | 0.576 | 0.565 | 0.41 / 0.70 / 0.52 | 0.68 / 0.49 / 0.57 | 0.64 / 0.55 / 0.59 |
| old seed 42 | 0.590 | 0.540 | 0.588 | 0.546 | 0.560 | 0.60 / 0.39 / 0.47 | 0.57 / 0.34 / 0.43 | 0.59 / 0.90 / 0.72 |
| old seed 1 | 0.650 | 0.643 | 0.640 | 0.651 | 0.649 | 0.59 / 0.70 / 0.64 | 0.61 / 0.54 / 0.58 | 0.71 / 0.71 / 0.71 |
| old seed 7 | 0.610 | 0.577 | 0.606 | 0.588 | 0.588 | 0.57 / 0.57 / 0.57 | 0.63 / 0.34 / 0.44 | 0.62 / 0.86 / 0.72 |
| old, 3 averaged | 0.630 | 0.596 | 0.621 | 0.596 | 0.613 | 0.65 / 0.48 / 0.55 | 0.56 / 0.43 / 0.48 | 0.66 / 0.88 / 0.76 |
| new seed 42 | 0.700 | 0.696 | 0.702 | 0.694 | 0.698 | 0.73 / 0.70 / 0.71 | 0.68 / 0.60 / 0.64 | 0.70 / 0.79 / 0.74 |
| new seed 1 | 0.670 | 0.665 | 0.712 | 0.651 | 0.663 | 0.88 / 0.61 / 0.72 | 0.63 / 0.49 / 0.55 | 0.63 / 0.86 / 0.73 |
| new seed 7 | 0.700 | 0.687 | 0.732 | 0.673 | 0.693 | 0.87 / 0.57 / 0.68 | 0.65 / 0.57 / 0.61 | 0.69 / 0.88 / 0.77 |
| new, 3 averaged | 0.740 | 0.735 | 0.768 | 0.721 | 0.736 | 0.88 / 0.65 / 0.75 | 0.71 / 0.63 / 0.67 | 0.71 / 0.88 / 0.79 |

Errors of 100 (neutral called polar, polar called neutral, positive and negative swapped):

| model | errors | neutral called polar | polar called neutral | positive <-> negative |
|---|---|---|---|---|
| base FinBERT (zero-shot) | 31 | 18 | 8 | 5 |
| VADER | 45 | 18 | 12 | 15 |
| TF-IDF + logistic regression | 44 | 18 | 8 | 18 |
| old seed 42 | 41 | 23 | 9 | 9 |
| old seed 1 | 35 | 16 | 12 | 7 |
| old seed 7 | 39 | 23 | 7 | 9 |
| old, 3 averaged | 37 | 20 | 12 | 5 |
| new seed 42 | 30 | 14 | 10 | 6 |
| new seed 1 | 33 | 18 | 10 | 5 |
| new seed 7 | 30 | 15 | 11 | 4 |
| new, 3 averaged | 26 | 13 | 9 | 4 |

### combined 399 (n=399: 62 negative, 201 neutral, 136 positive)

| model | accuracy | macro-F1 | macro precision | macro recall | weighted F1 | negative P / R / F1 | neutral P / R / F1 | positive P / R / F1 |
|---|---|---|---|---|---|---|---|---|
| base FinBERT (zero-shot) | 0.697 | 0.648 | 0.691 | 0.627 | 0.688 | 0.64 / 0.44 / 0.52 | 0.68 / 0.84 / 0.75 | 0.75 / 0.61 / 0.67 |
| VADER | 0.504 | 0.458 | 0.489 | 0.472 | 0.493 | 0.39 / 0.26 / 0.31 | 0.63 / 0.42 / 0.51 | 0.45 / 0.74 / 0.56 |
| TF-IDF + logistic regression | 0.581 | 0.546 | 0.549 | 0.561 | 0.591 | 0.33 / 0.52 / 0.40 | 0.68 / 0.64 / 0.66 | 0.64 / 0.53 / 0.58 |
| old seed 42 | 0.657 | 0.618 | 0.630 | 0.621 | 0.653 | 0.54 / 0.44 / 0.48 | 0.75 / 0.63 / 0.68 | 0.61 / 0.80 / 0.69 |
| old seed 1 | 0.664 | 0.636 | 0.630 | 0.645 | 0.666 | 0.50 / 0.56 / 0.53 | 0.73 / 0.67 / 0.70 | 0.66 / 0.70 / 0.68 |
| old seed 7 | 0.607 | 0.579 | 0.580 | 0.605 | 0.605 | 0.42 / 0.52 / 0.46 | 0.74 / 0.51 / 0.61 | 0.58 / 0.79 / 0.67 |
| old, 3 averaged | 0.654 | 0.620 | 0.621 | 0.629 | 0.653 | 0.50 / 0.48 / 0.49 | 0.74 / 0.62 / 0.67 | 0.63 / 0.79 / 0.70 |
| new seed 42 | 0.697 | 0.665 | 0.676 | 0.657 | 0.695 | 0.63 / 0.52 / 0.57 | 0.74 / 0.74 / 0.74 | 0.66 / 0.71 / 0.69 |
| new seed 1 | 0.652 | 0.622 | 0.632 | 0.628 | 0.650 | 0.56 / 0.48 / 0.52 | 0.75 / 0.61 / 0.67 | 0.59 / 0.79 / 0.68 |
| new seed 7 | 0.684 | 0.647 | 0.693 | 0.635 | 0.679 | 0.72 / 0.42 / 0.53 | 0.73 / 0.69 / 0.71 | 0.62 / 0.79 / 0.70 |
| new, 3 averaged | 0.707 | 0.674 | 0.702 | 0.663 | 0.704 | 0.70 / 0.48 / 0.57 | 0.75 / 0.73 / 0.74 | 0.66 / 0.78 / 0.71 |

Errors of 399 (neutral called polar, polar called neutral, positive and negative swapped):

| model | errors | neutral called polar | polar called neutral | positive <-> negative |
|---|---|---|---|---|
| base FinBERT (zero-shot) | 121 | 33 | 78 | 10 |
| VADER | 198 | 116 | 50 | 32 |
| TF-IDF + logistic regression | 167 | 73 | 61 | 33 |
| old seed 42 | 137 | 75 | 43 | 19 |
| old seed 1 | 134 | 66 | 49 | 19 |
| old seed 7 | 157 | 98 | 36 | 23 |
| old, 3 averaged | 138 | 77 | 44 | 17 |
| new seed 42 | 121 | 52 | 53 | 16 |
| new seed 1 | 139 | 78 | 42 | 19 |
| new seed 7 | 126 | 62 | 51 | 13 |
| new, 3 averaged | 117 | 55 | 49 | 13 |

### Accuracy by source (combined 399)

| model | arctic_shift (n=184) | sgx_research (n=100) | earnings (n=79) | google_news (n=34) | yahoo_news (n=2) |
|---|---|---|---|---|---|
| base FinBERT (zero-shot) | 0.70 | 0.69 | 0.73 | 0.65 | 0.50 |
| VADER | 0.44 | 0.55 | 0.62 | 0.47 | 0.00 |
| TF-IDF + logistic regression | 0.56 | 0.56 | 0.68 | 0.53 | 0.50 |
| old seed 42 | 0.66 | 0.59 | 0.73 | 0.71 | 0.00 |
| old seed 1 | 0.63 | 0.65 | 0.75 | 0.74 | 0.00 |
| old seed 7 | 0.55 | 0.61 | 0.72 | 0.68 | 0.00 |
| old, 3 averaged | 0.63 | 0.63 | 0.73 | 0.71 | 0.00 |
| new seed 42 | 0.66 | 0.70 | 0.80 | 0.65 | 0.50 |
| new seed 1 | 0.60 | 0.67 | 0.80 | 0.56 | 0.50 |
| new seed 7 | 0.64 | 0.70 | 0.80 | 0.65 | 0.50 |
| new, 3 averaged | 0.66 | 0.74 | 0.81 | 0.65 | 0.50 |
