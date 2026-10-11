### first round 299 ({'neutral': np.int64(166), 'positive': np.int64(94), 'negative': np.int64(39)})

| model | accuracy | macro-F1 | negative P / R | neutral P / R | positive P / R |
|---|---|---|---|---|---|
| Base FinBERT, no fine-tuning | 0.699 | 0.571 | 0.53 / 0.21 | 0.68 / 0.91 | 0.79 / 0.53 |
| FinBERT fine-tuned on people's labels (4 Oct retrain): mean of three seeds (macro-F1 sd 0.027) | 0.693 | 0.621 | 0.51 / 0.41 | 0.73 / 0.81 | 0.70 / 0.61 |
| FinBERT fine-tuned on people's labels (4 Oct retrain): the three averaged | 0.702 | 0.634 | 0.49 / 0.44 | 0.73 / 0.81 | 0.73 / 0.63 |
| FinBERT fine-tuned on people's labels, broker rows included (7 Oct): mean of three seeds (macro-F1 sd 0.017) | 0.689 | 0.617 | 0.52 / 0.37 | 0.75 / 0.76 | 0.64 / 0.70 |
| FinBERT fine-tuned on people's labels, broker rows included (7 Oct): the three averaged | 0.676 | 0.597 | 0.46 / 0.33 | 0.75 / 0.74 | 0.62 / 0.70 |
| FinBERT fine-tuned on Opus's labels (11 Oct): mean of three seeds (macro-F1 sd 0.020) | 0.682 | 0.631 | 0.49 / 0.49 | 0.77 / 0.72 | 0.62 / 0.70 |
| FinBERT fine-tuned on Opus's labels (11 Oct): the three averaged | 0.702 | 0.641 | 0.52 / 0.44 | 0.78 / 0.75 | 0.64 / 0.73 |
| Adapted encoder fine-tuned on Opus's labels (11 Oct): mean of three seeds (macro-F1 sd 0.018) | 0.689 | 0.649 | 0.48 / 0.61 | 0.77 / 0.71 | 0.67 / 0.68 |
| Adapted encoder fine-tuned on Opus's labels (11 Oct): the three averaged | 0.716 | 0.670 | 0.48 / 0.59 | 0.81 / 0.73 | 0.69 / 0.73 |

### broker research 100 ({'positive': np.int64(42), 'neutral': np.int64(35), 'negative': np.int64(23)})

| model | accuracy | macro-F1 | negative P / R | neutral P / R | positive P / R |
|---|---|---|---|---|---|
| Base FinBERT, no fine-tuning | 0.690 | 0.687 | 0.70 / 0.83 | 0.68 / 0.49 | 0.69 / 0.79 |
| FinBERT fine-tuned on people's labels (4 Oct retrain): mean of three seeds (macro-F1 sd 0.065) | 0.670 | 0.659 | 0.75 / 0.61 | 0.62 / 0.54 | 0.67 / 0.81 |
| FinBERT fine-tuned on people's labels (4 Oct retrain): the three averaged | 0.690 | 0.690 | 0.80 / 0.70 | 0.66 / 0.54 | 0.67 / 0.81 |
| FinBERT fine-tuned on people's labels, broker rows included (7 Oct): mean of three seeds (macro-F1 sd 0.016) | 0.693 | 0.692 | 0.76 / 0.74 | 0.66 / 0.54 | 0.69 / 0.79 |
| FinBERT fine-tuned on people's labels, broker rows included (7 Oct): the three averaged | 0.700 | 0.698 | 0.75 / 0.78 | 0.69 / 0.51 | 0.68 / 0.81 |
| FinBERT fine-tuned on Opus's labels (11 Oct): mean of three seeds (macro-F1 sd 0.008) | 0.710 | 0.705 | 0.67 / 0.87 | 0.70 / 0.52 | 0.75 / 0.78 |
| FinBERT fine-tuned on Opus's labels (11 Oct): the three averaged | 0.690 | 0.683 | 0.66 / 0.91 | 0.67 / 0.46 | 0.73 / 0.76 |
| Adapted encoder fine-tuned on Opus's labels (11 Oct): mean of three seeds (macro-F1 sd 0.021) | 0.740 | 0.740 | 0.69 / 0.88 | 0.71 / 0.64 | 0.80 / 0.75 |
| Adapted encoder fine-tuned on Opus's labels (11 Oct): the three averaged | 0.770 | 0.770 | 0.70 / 0.91 | 0.77 / 0.69 | 0.82 / 0.76 |

### all 399 ({'neutral': np.int64(201), 'positive': np.int64(136), 'negative': np.int64(62)})

| model | accuracy | macro-F1 | negative P / R | neutral P / R | positive P / R |
|---|---|---|---|---|---|
| Base FinBERT, no fine-tuning | 0.697 | 0.648 | 0.64 / 0.44 | 0.68 / 0.84 | 0.75 / 0.61 |
| FinBERT fine-tuned on people's labels (4 Oct retrain): mean of three seeds (macro-F1 sd 0.020) | 0.688 | 0.647 | 0.60 / 0.48 | 0.71 / 0.76 | 0.69 / 0.67 |
| FinBERT fine-tuned on people's labels (4 Oct retrain): the three averaged | 0.699 | 0.666 | 0.60 / 0.53 | 0.72 / 0.76 | 0.70 / 0.68 |
| FinBERT fine-tuned on people's labels, broker rows included (7 Oct): mean of three seeds (macro-F1 sd 0.014) | 0.690 | 0.658 | 0.62 / 0.51 | 0.73 / 0.72 | 0.66 / 0.73 |
| FinBERT fine-tuned on people's labels, broker rows included (7 Oct): the three averaged | 0.682 | 0.649 | 0.60 / 0.50 | 0.74 / 0.70 | 0.64 / 0.74 |
| FinBERT fine-tuned on Opus's labels (11 Oct): mean of three seeds (macro-F1 sd 0.010) | 0.689 | 0.669 | 0.57 / 0.63 | 0.76 / 0.68 | 0.66 / 0.73 |
| FinBERT fine-tuned on Opus's labels (11 Oct): the three averaged | 0.699 | 0.677 | 0.58 / 0.61 | 0.77 / 0.70 | 0.67 / 0.74 |
| Adapted encoder fine-tuned on Opus's labels (11 Oct): mean of three seeds (macro-F1 sd 0.013) | 0.702 | 0.685 | 0.56 / 0.71 | 0.76 / 0.70 | 0.71 / 0.70 |
| Adapted encoder fine-tuned on Opus's labels (11 Oct): the three averaged | 0.729 | 0.709 | 0.56 / 0.71 | 0.80 / 0.73 | 0.73 / 0.74 |

Accuracy by source, FinBERT fine-tuned on Opus's labels (11 Oct), the three averaged: arctic_shift 0.66 (n=184), sgx_research 0.69 (n=100), earnings 0.80 (n=79), google_news 0.71 (n=34), yahoo_news 0.50 (n=2)

Accuracy by source, Adapted encoder fine-tuned on Opus's labels (11 Oct), the three averaged: arctic_shift 0.68 (n=184), sgx_research 0.77 (n=100), earnings 0.81 (n=79), google_news 0.68 (n=34), yahoo_news 0.50 (n=2)

### Cross-validation, adapted encoder against FinBERT (15 paired folds, dev macro-F1 against Opus's labels)

FinBERT 0.686, adapted 0.700; difference +0.014 (sd 0.020), better in 11 of 15; paired t = 2.75, p = 0.016; Wilcoxon p = 0.015; 95% interval +0.003 to +0.025.
By seed: seed 1: 0.685 against 0.702; seed 7: 0.684 against 0.702; seed 42: 0.689 against 0.694
