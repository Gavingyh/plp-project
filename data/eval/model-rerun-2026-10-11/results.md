Test rows: 299 ({'neutral': 166, 'positive': 94, 'negative': 39}). Training rows: 1563.

| model | accuracy | macro-F1 | negative P / R | neutral P / R | positive P / R |
|---|---|---|---|---|---|
| Base FinBERT, no fine-tuning | 0.699 | 0.571 | 0.53 / 0.21 | 0.68 / 0.91 | 0.79 / 0.53 |
| FinBERT fine-tuned on people's labels (1 Oct): mean of three seeds (macro-F1 sd 0.035) | 0.651 | 0.604 | 0.44 / 0.48 | 0.76 / 0.64 | 0.60 / 0.73 |
| FinBERT fine-tuned on people's labels (1 Oct): the three averaged | 0.662 | 0.614 | 0.44 / 0.49 | 0.77 / 0.66 | 0.61 / 0.74 |
| FinBERT fine-tuned on people's labels (4 Oct retrain): mean of three seeds (macro-F1 sd 0.027) | 0.693 | 0.621 | 0.51 / 0.41 | 0.73 / 0.81 | 0.70 / 0.61 |
| FinBERT fine-tuned on people's labels (4 Oct retrain): the three averaged | 0.702 | 0.634 | 0.49 / 0.44 | 0.73 / 0.81 | 0.73 / 0.63 |
| FinBERT fine-tuned on Opus's labels (11 Oct): mean of three seeds (macro-F1 sd 0.020) | 0.682 | 0.631 | 0.49 / 0.49 | 0.77 / 0.72 | 0.62 / 0.70 |
| FinBERT fine-tuned on Opus's labels (11 Oct): the three averaged | 0.702 | 0.641 | 0.52 / 0.44 | 0.78 / 0.75 | 0.64 / 0.73 |
| Adapted encoder fine-tuned on Opus's labels (11 Oct): mean of three seeds (macro-F1 sd 0.018) | 0.689 | 0.649 | 0.48 / 0.61 | 0.77 / 0.71 | 0.67 / 0.68 |
| Adapted encoder fine-tuned on Opus's labels (11 Oct): the three averaged | 0.716 | 0.670 | 0.48 / 0.59 | 0.81 / 0.73 | 0.69 / 0.73 |

Cross-validation on the training rows (dev macro-F1 against Opus's labels, 5 folds, seeds 42, 1 and 7):

- dapt: mean 0.700, sd 0.022, 15 folds
- finbert: mean 0.686, sd 0.026, 15 folds
- adapted minus FinBERT, paired: mean +0.014, sd 0.020, better in 11 of 15 folds
