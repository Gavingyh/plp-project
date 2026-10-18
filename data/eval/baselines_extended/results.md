# Baselines and fine-tuned FinBERT on the extended test set

Baselines trained on 1,563 labelled pairs; scored on 399 test rows (299 frozen random rows plus 100 broker research rows). 95% bootstrap intervals over rows.

## all_399 (399 rows)

| model | macro-F1 (95% interval) | FinBERT minus this model (95% interval) |
|---|---|---|
| finbert | 0.697 (0.649 to 0.743) |  |
| naive_bayes | 0.583 (0.523 to 0.639) | +0.114 (+0.047 to +0.182) |
| complement_nb | 0.606 (0.555 to 0.655) | +0.092 (+0.033 to +0.149) |
| linear_svm | 0.556 (0.505 to 0.606) | +0.141 (+0.083 to +0.200) |
| logistic_regression | 0.550 (0.497 to 0.600) | +0.147 (+0.091 to +0.204) |
| bilstm | 0.524 (0.473 to 0.572) | +0.173 (+0.119 to +0.228) |
| cnn | 0.464 (0.416 to 0.514) | +0.233 (+0.175 to +0.290) |

## original_299 (299 rows)

| model | macro-F1 (95% interval) | FinBERT minus this model (95% interval) |
|---|---|---|
| finbert | 0.669 (0.608 to 0.725) |  |
| naive_bayes | 0.547 (0.477 to 0.613) | +0.122 (+0.041 to +0.203) |
| complement_nb | 0.576 (0.509 to 0.634) | +0.093 (+0.020 to +0.163) |
| linear_svm | 0.540 (0.473 to 0.600) | +0.129 (+0.061 to +0.200) |
| logistic_regression | 0.530 (0.465 to 0.588) | +0.139 (+0.071 to +0.207) |
| bilstm | 0.519 (0.458 to 0.576) | +0.150 (+0.088 to +0.215) |
| cnn | 0.455 (0.400 to 0.509) | +0.214 (+0.145 to +0.281) |

## sgx_100 (100 rows)

| model | macro-F1 (95% interval) | FinBERT minus this model (95% interval) |
|---|---|---|
| finbert | 0.722 (0.632 to 0.805) |  |
| naive_bayes | 0.646 (0.541 to 0.742) | +0.075 (-0.046 to +0.195) |
| complement_nb | 0.635 (0.538 to 0.725) | +0.087 (-0.031 to +0.204) |
| linear_svm | 0.569 (0.466 to 0.663) | +0.153 (+0.038 to +0.282) |
| logistic_regression | 0.570 (0.470 to 0.666) | +0.152 (+0.039 to +0.271) |
| bilstm | 0.510 (0.409 to 0.603) | +0.212 (+0.088 to +0.336) |
| cnn | 0.459 (0.354 to 0.550) | +0.263 (+0.135 to +0.388) |

The stored FinBERT label was made under the pipeline's aspect, which differs from the human aspect on 114 of 399 rows.
