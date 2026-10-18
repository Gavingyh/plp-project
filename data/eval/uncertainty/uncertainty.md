# Confidence intervals for the index

Model `finbert-adapted-finetuned-2026-10-11-3seed-m0`; 2,000 resamples; windows end at 2026-09-25 10:37:46+00:00. Intervals are the middle 95% of resampled scores.

Check: the headline score computed here, the same score from the index's own formula (aggregate.index), and the stored index table. The first two must match; the stored table matches only if the index was rebuilt after the last scoring.

| bank | computed here | index formula | stored index |
|---|---|---|---|
| DBS | 0.143 | 0.143 | 0.143 |
| OCBC | 0.1285 | 0.1285 | 0.1285 |
| UOB | 0.1069 | 0.1069 | 0.1069 |

## Resampling documents

| group | window | sentences | documents | score | 95% interval | half-width |
|---|---|---|---|---|---|---|
| DBS headline | all_time | 24,978 | 12,560 | +0.143 | +0.122 to +0.165 | 0.021 |
| DBS arctic_shift | all_time | 12,226 | 9,840 | +0.058 | +0.046 to +0.070 | 0.011 |
| DBS earnings | all_time | 9,093 | 75 | +0.276 | +0.236 to +0.317 | 0.041 |
| DBS headline | 30d | 371 | 300 | +0.044 | -0.031 to +0.122 | 0.077 |
| DBS retail_banking_sentiment | all_time | 9,099 | 7,077 | -0.028 | -0.047 to -0.009 | 0.019 |
| DBS wealth_business | all_time | 839 | 418 | +0.459 | +0.409 to +0.507 | 0.049 |
| DBS dividend_policy | all_time | 414 | 179 | +0.455 | +0.379 to +0.527 | 0.074 |
| DBS income_profit_results | all_time | 2,360 | 234 | +0.429 | +0.362 to +0.509 | 0.073 |
| DBS net_interest_margin | all_time | 1,068 | 140 | +0.163 | +0.091 to +0.231 | 0.070 |
| OCBC headline | all_time | 7,774 | 4,820 | +0.129 | +0.103 to +0.154 | 0.025 |
| OCBC arctic_shift | all_time | 3,936 | 3,230 | -0.009 | -0.030 to +0.012 | 0.021 |
| OCBC earnings | all_time | 1,561 | 39 | +0.343 | +0.302 to +0.386 | 0.042 |
| OCBC headline | 30d | 115 | 95 | +0.271 | +0.130 to +0.391 | 0.130 |
| OCBC retail_banking_sentiment | all_time | 3,598 | 2,930 | -0.029 | -0.055 to -0.003 | 0.026 |
| OCBC wealth_business | all_time | 271 | 206 | +0.542 | +0.465 to +0.615 | 0.075 |
| OCBC dividend_policy | all_time | 138 | 70 | +0.453 | +0.339 to +0.545 | 0.103 |
| OCBC income_profit_results | all_time | 776 | 144 | +0.481 | +0.423 to +0.543 | 0.060 |
| OCBC net_interest_margin | all_time | 169 | 54 | -0.035 | -0.202 to +0.119 | 0.161 |
| UOB headline | all_time | 13,092 | 8,933 | +0.107 | +0.090 to +0.124 | 0.017 |
| UOB arctic_shift | all_time | 9,371 | 7,293 | +0.058 | +0.044 to +0.071 | 0.014 |
| UOB earnings | all_time | 1,600 | 66 | +0.332 | +0.265 to +0.396 | 0.065 |
| UOB headline | 30d | 136 | 118 | +0.185 | +0.095 to +0.279 | 0.092 |
| UOB retail_banking_sentiment | all_time | 8,180 | 6,446 | +0.064 | +0.048 to +0.079 | 0.015 |
| UOB wealth_business | all_time | 313 | 276 | +0.400 | +0.339 to +0.463 | 0.062 |
| UOB dividend_policy | all_time | 62 | 43 | +0.340 | +0.179 to +0.485 | 0.153 |
| UOB income_profit_results | all_time | 698 | 155 | +0.282 | +0.175 to +0.375 | 0.100 |
| UOB net_interest_margin | all_time | 188 | 109 | -0.071 | -0.222 to +0.074 | 0.148 |

| banks | difference | 95% interval | resamples where the first is higher |
|---|---|---|---|
| DBS minus OCBC | +0.014 | -0.018 to +0.048 | 81% |
| DBS minus UOB | +0.036 | +0.007 to +0.062 | 99% |
| OCBC minus UOB | +0.022 | -0.010 to +0.053 | 91% |

## Resampling sentences

| group | window | sentences | documents | score | 95% interval | half-width |
|---|---|---|---|---|---|---|
| DBS headline | all_time | 24,978 | 12,560 | +0.143 | +0.134 to +0.152 | 0.009 |
| DBS arctic_shift | all_time | 12,226 | 9,840 | +0.058 | +0.047 to +0.070 | 0.011 |
| DBS earnings | all_time | 9,093 | 75 | +0.276 | +0.263 to +0.290 | 0.014 |
| DBS headline | 30d | 371 | 300 | +0.044 | -0.029 to +0.114 | 0.071 |
| DBS retail_banking_sentiment | all_time | 9,099 | 7,077 | -0.028 | -0.043 to -0.013 | 0.015 |
| DBS wealth_business | all_time | 839 | 418 | +0.459 | +0.421 to +0.498 | 0.038 |
| DBS dividend_policy | all_time | 414 | 179 | +0.455 | +0.404 to +0.506 | 0.051 |
| DBS income_profit_results | all_time | 2,360 | 234 | +0.429 | +0.397 to +0.460 | 0.031 |
| DBS net_interest_margin | all_time | 1,068 | 140 | +0.163 | +0.114 to +0.216 | 0.051 |
| OCBC headline | all_time | 7,774 | 4,820 | +0.129 | +0.113 to +0.144 | 0.016 |
| OCBC arctic_shift | all_time | 3,936 | 3,230 | -0.009 | -0.029 to +0.011 | 0.020 |
| OCBC earnings | all_time | 1,561 | 39 | +0.343 | +0.307 to +0.378 | 0.035 |
| OCBC headline | 30d | 115 | 95 | +0.271 | +0.157 to +0.394 | 0.118 |
| OCBC retail_banking_sentiment | all_time | 3,598 | 2,930 | -0.029 | -0.053 to -0.006 | 0.024 |
| OCBC wealth_business | all_time | 271 | 206 | +0.542 | +0.474 to +0.611 | 0.068 |
| OCBC dividend_policy | all_time | 138 | 70 | +0.453 | +0.349 to +0.550 | 0.100 |
| OCBC income_profit_results | all_time | 776 | 144 | +0.481 | +0.427 to +0.534 | 0.053 |
| OCBC net_interest_margin | all_time | 169 | 54 | -0.035 | -0.167 to +0.091 | 0.129 |
| UOB headline | all_time | 13,092 | 8,933 | +0.107 | +0.095 to +0.118 | 0.011 |
| UOB arctic_shift | all_time | 9,371 | 7,293 | +0.058 | +0.045 to +0.071 | 0.013 |
| UOB earnings | all_time | 1,600 | 66 | +0.332 | +0.297 to +0.368 | 0.036 |
| UOB headline | 30d | 136 | 118 | +0.185 | +0.093 to +0.282 | 0.094 |
| UOB retail_banking_sentiment | all_time | 8,180 | 6,446 | +0.064 | +0.049 to +0.078 | 0.015 |
| UOB wealth_business | all_time | 313 | 276 | +0.400 | +0.339 to +0.463 | 0.062 |
| UOB dividend_policy | all_time | 62 | 43 | +0.340 | +0.183 to +0.480 | 0.149 |
| UOB income_profit_results | all_time | 698 | 155 | +0.282 | +0.215 to +0.350 | 0.067 |
| UOB net_interest_margin | all_time | 188 | 109 | -0.071 | -0.196 to +0.053 | 0.124 |

| banks | difference | 95% interval | resamples where the first is higher |
|---|---|---|---|
| DBS minus OCBC | +0.014 | -0.004 to +0.031 | 94% |
| DBS minus UOB | +0.036 | +0.022 to +0.051 | 100% |
| OCBC minus UOB | +0.022 | +0.003 to +0.042 | 99% |
