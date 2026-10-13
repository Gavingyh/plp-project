# Validation of the report draft's figures (13 Oct 2026)

**What this is.** `docs/report/report.html` is the draft of the practice module
report. An audit earlier the same day compared its text with the evidence
notes. This validation goes one step further back: it recomputes the report's
figures from primary data (the database, the label files, the trained models
scored again on the test sentences, the chatbot transcripts) and compares each
with the value the report prints.

**Result.** 100 of 100 recomputed figures match the report. The checks
found three things, all corrected in the report before this note was written:

- **Bank recognition scores had moved.** The report quoted 200 and 154 of
  201, scored on 4 Oct. With the code as it stands, after the rules added on
  11 Oct, the recogniser is right on all 201 and alias matching on 161 (F1
  0.89). The report now gives these, and says the perfect score is not a
  held-out result: the last rules were written after reading this sheet's
  errors.
- **One agreement figure needed its source named.** The LLM rater's macro-F1
  of 0.789 on aspects is its first run's, made under the guideline people
  used; the second run, under the rules of 10 Oct, gives 0.791. The report
  keeps 0.789 and says which run it is.
- **The first-round test labels are not blind.** The agreement note records
  that each annotator's test labels equal the labels they gave with a
  model's suggestion in view. The report now says so beside the kappa of
  0.93.

## What was recomputed, and from what

`data/eval/report-validation-2026-10-13/validate.py` (output in
`output.txt`, every check in `checks.json`). Nothing was written to the
database or the label files.

- **Corpus and index** (sections 2.1 and 4.4, Tables 1, 6 and 7): read from
  `data/plp.db`.
- **Labels** (section 2.2, Table 2): counted from the label files; the LLM
  rater's and the two annotators' agreement recomputed from them.
- **Sentiment models** (Tables 3 and 4): base FinBERT and the three seeds of
  the chosen model were scored again on the 399 test sentences, on the CPU.
  The other fine-tuned rows were read from the stored results
  (`report_data.json`). Cross-validation was recomputed from the 30 fold
  results, and the two classical baselines were run again.
- **Aspects** (Table 5 and the wealth trial): the two local models' cached
  answers and the LLM rater's labels against people's aspects; the trial
  from its `answers.csv`.
- **Bank recognition** (section 4.3): the scorer and the corpus comparison
  run again.
- **Chatbot** (Table 8, section 4.5): the three runs' transcripts, summaries
  and timing files; the evidence-search figures from the run's log.

## Not recomputed

These figures were checked against their evidence notes only (by the audit),
because recomputing them needs a run that was not repeated or a source
outside the repository:

- the similarity method's row of Table 5 (41.3%, macro-F1 0.296);
- aspect discovery: 338 and 358 clusters, 65% and 52% unclustered, 25
  clusters at the coarser setting;
- evidence-search precision under the earlier aspects (0.33);
- the counts of invented citations by kind in the run before the code
  checks, beyond the 11 of 32 answers;
- the survey figures and the index share in section 1, which come from the
  proposal and still need checking against the original reports;
- the examples in the GenAI declaration, which come from the project's log.

## Every check

| Section | Figure | In the report | Recomputed | Source |
|---|---|---|---|---|
| 2.1 | documents | 28852 | 28852 | data/plp.db |
| 2.1 | sentences | 45844 | 45844 | data/plp.db |
| 2.1 | first and last date | ['2020-01-06', '2026-09-25'] | ['2020-01-06', '2026-09-25'] | data/plp.db |
| Table 1 | arctic_shift documents / sentences | [22630, 25533] | [22630, 25533] | data/plp.db |
| Table 1 | earnings documents / sentences | [178, 12254] | [178, 12254] | data/plp.db |
| Table 1 | google_news documents / sentences | [5685, 5447] | [5685, 5447] | data/plp.db |
| Table 1 | cna documents / sentences | [207, 1599] | [207, 1599] | data/plp.db |
| Table 1 | sgx_research documents / sentences | [25, 641] | [25, 641] | data/plp.db |
| Table 1 | yahoo_news documents / sentences | [114, 344] | [114, 344] | data/plp.db |
| Table 1 | newsapi documents / sentences | [13, 26] | [13, 26] | data/plp.db |
| 2.1 | sentences DBS / UOB / OCBC | [24978, 13092, 7774] | [24978, 13092, 7774] | data/plp.db |
| 2.1 | earnings sentences DBS / OCBC / UOB | [9093, 1561, 1600] | [9093, 1561, 1600] | data/plp.db |
| 2.1 | Reddit share of sentences, % | 56 | 56 | data/plp.db |
| 2.1 | earnings share of sentences, % | 27 | 27 | data/plp.db |
| 2.1 | late additions: Reddit documents, broker reports | [825, 25] | [825, 25] | data/plp.db |
| 4.4 | Reddit share of UOB's / DBS's sentences, % | [72, 49] | [72, 49] | data/plp.db |
| 2.2 | labelled sentences | 2075 | 2075 | data/labeled/llm_rater/rules-2026-10-10/rater_labels.csv |
| Table 2 | first round / top-up / active / broker | [1277, 268, 150, 380] | [1277, 268, 150, 380] | data/labeled/llm_rater/rules-2026-10-10/rater_labels.csv |
| 2.2 | LLM labels positive / neutral / negative | [757, 879, 439] | [757, 879, 439] | data/labeled/llm_rater/rules-2026-10-10/rater_labels.csv |
| 2.2 | flagged as not about the bank | 134 | 134 | data/labeled/llm_rater/rules-2026-10-10/rater_labels.csv |
| 2.2 | training rows | 1563 | 1563 | data/labeled/llm_rater/rules-2026-10-10/training_set.csv |
| 2.2 | training positive / neutral / negative | [616, 586, 361] | [616, 586, 361] | data/labeled/llm_rater/rules-2026-10-10/training_set.csv |
| 2.2 | first-round test neutral / positive / negative | [166, 94, 39] | [166, 94, 39] | data/labeled/llm_rater/rules-2026-10-10/training_set.csv |
| 2.2 | broker test positive / neutral / negative | [42, 35, 23] | [42, 35, 23] | data/labeled/sgx_research/test_blind.csv |
| Table 2 | first round train / test | [978, 299] | [978, 299] | data/labeled/candidates.csv |
| 2.2 | LLM rater against people, aspect kappa | 0.8 | 0.8 | candidates.csv x rater_labels.csv |
| 2.2 | LLM rater against people, sentiment kappa | 0.79 | 0.79 | candidates.csv x rater_labels.csv |
| Table 5 | LLM rater right aspect, % | 84.2 | 84.2 | candidates.csv x rater_labels.csv |
| 2.2 | first-round labels matching the shown suggestion, % | 91.6 | 91.6 | data/labeled/candidates.csv |
| 3.5 | pretraining sentences kept; epochs | [42822, 3] | [42822, 3] | data/eval/model-rerun-2026-10-11/report_data.json |
| 3.5 | left out: labelled / same text / containing / sharing words | [2270, 37, 147, 568] | [2270, 37, 147, 568] | data/eval/model-rerun-2026-10-11/report_data.json |
| 4.1 | cross-validation lead; folds better; p | [0.014, 11, 0.016] | [0.014, 11, 0.016] | data/eval/model-rerun-2026-10-11/report_data.json |
| 4.1 | the same, recomputed from the 30 fold results | [0.014, 11, 0.016] | [0.014, 11, 0.016] | data/eval/model-rerun-2026-10-11/cv_results.jsonl |
| 4.1 | weighting variants against the chosen model, lowest and highest | [-0.004, -0.002] | [-0.004, -0.002] | data/eval/model-rerun-2026-10-11/cv_weighting.jsonl |
| 3.5 | held-out rows; threshold chosen | [601, 0.0] | [601, 0.0] | data/eval/model-rerun-2026-10-11/margin_adapted.json |
| Table 4 note | accuracy earnings / broker / Reddit / Google News, % | [81, 77, 68, 68] | [81, 77, 68, 68] | data/eval/model-rerun-2026-10-11/report_data.json |
| Table 4 note | rows earnings / broker / Reddit / Google News | [79, 100, 184, 34] | [79, 100, 184, 34] | data/eval/model-rerun-2026-10-11/report_data.json |
| Table 3 | FinBERT, no fine-tuning: accuracy, macro-F1, P/R negative, neutral, positive | [0.699, 0.571, 0.53, 0.21, 0.68, 0.91, 0.79, 0.53] | [0.699, 0.571, 0.53, 0.21, 0.68, 0.91, 0.79, 0.53] | models re-scored on the test sentences |
| Table 3 | model in use (three averaged): the same | [0.716, 0.67, 0.48, 0.59, 0.81, 0.73, 0.69, 0.73] | [0.716, 0.67, 0.48, 0.59, 0.81, 0.73, 0.69, 0.73] | models re-scored on the test sentences |
| Table 3 | adapted encoder, mean of 3 seeds: accuracy, macro-F1, sd | [0.689, 0.649, 0.018] | [0.689, 0.649, 0.018] | models re-scored on the test sentences |
| Table 3 | the same: mean P/R negative, neutral, positive | [0.48, 0.61, 0.77, 0.71, 0.67, 0.68] | [0.48, 0.61, 0.77, 0.71, 0.67, 0.68] | models re-scored on the test sentences |
| Table 4 | first round: FinBERT macro-F1 | 0.571 | 0.571 | models re-scored on the test sentences |
| Table 4 | first round: model in use macro-F1, accuracy | [0.67, 0.716] | [0.67, 0.716] | models re-scored on the test sentences |
| Table 4 | broker research: FinBERT macro-F1 | 0.687 | 0.687 | models re-scored on the test sentences |
| Table 4 | broker research: model in use macro-F1, accuracy | [0.77, 0.77] | [0.77, 0.77] | models re-scored on the test sentences |
| Table 4 | both: FinBERT macro-F1 | 0.648 | 0.648 | models re-scored on the test sentences |
| Table 4 | both: model in use macro-F1, accuracy | [0.709, 0.729] | [0.709, 0.729] | models re-scored on the test sentences |
| Table 3 | fine-tuned on people's labels, mean of 3: accuracy, macro-F1, sd, P/R | [0.693, 0.621, 0.027, 0.51, 0.41, 0.73, 0.81, 0.7, 0.61] | [0.693, 0.621, 0.027, 0.51, 0.41, 0.73, 0.81, 0.7, 0.61] | data/eval/model-rerun-2026-10-11/report_data.json |
| Table 3 | fine-tuned on LLM labels, mean of 3: the same | [0.682, 0.631, 0.02, 0.49, 0.49, 0.77, 0.72, 0.62, 0.7] | [0.682, 0.631, 0.02, 0.49, 0.49, 0.77, 0.72, 0.62, 0.7] | data/eval/model-rerun-2026-10-11/report_data.json |
| 4.1 | steps: fine-tuning, LLM labels, pretraining, averaging | [0.05, 0.01, 0.018, 0.021] | [0.05, 0.01, 0.018, 0.021] | Table 3 |
| Table 6 | DBS FinBERT: score, sentences, % pos/neu/neg | [0.122, 24978, 22, 67, 10] | [0.122, 24978, 22, 67, 10] | data/plp.db |
| Table 6 | DBS model in use: the same | [0.155, 24978, 33, 51, 16] | [0.155, 24978, 33, 51, 16] | data/plp.db |
| Table 6 | OCBC FinBERT: score, sentences, % pos/neu/neg | [0.136, 7774, 23, 67, 11] | [0.136, 7774, 23, 67, 11] | data/plp.db |
| Table 6 | OCBC model in use: the same | [0.143, 7774, 32, 50, 18] | [0.143, 7774, 32, 50, 18] | data/plp.db |
| Table 6 | UOB FinBERT: score, sentences, % pos/neu/neg | [0.074, 13092, 15, 76, 9] | [0.074, 13092, 15, 76, 9] | data/plp.db |
| Table 6 | UOB model in use: the same | [0.117, 13092, 30, 53, 17] | [0.117, 13092, 30, 53, 17] | data/plp.db |
| Table 6 note | 30d DBS, OCBC, UOB: score, sentences | [[0.054, 371], [0.281, 115], [0.196, 136]] | [[0.054, 371], [0.281, 115], [0.196, 136]] | data/plp.db |
| Table 6 note | 7d DBS, OCBC, UOB: score, sentences | [[0.171, 90], [0.151, 42], [0.309, 60]] | [[0.171, 90], [0.151, 42], [0.309, 60]] | data/plp.db |
| 4.4 | labels changed; of them from neutral; % changed | [13154, 10219, 29] | [13154, 10219, 29] | data/plp.db |
| 4.4 | Reddit neutral %, FinBERT (lowest, highest) | [88, 89] | [88, 89] | data/plp.db |
| 4.4 | Reddit neutral %, model in use (lowest, highest) | [57, 58] | [57, 58] | data/plp.db |
| 4.4 | Reddit score, model in use (lowest, highest) | [0.0, 0.07] | [0.0, 0.07] | data/plp.db |
| 4.4 | earnings DBS, OCBC, UOB: FinBERT to model in use | [[0.286, 0.287], [0.375, 0.344], [0.406, 0.335]] | [[0.286, 0.287], [0.375, 0.344], [0.406, 0.335]] | data/plp.db |
| 4.4 | earnings score, model in use (lowest, highest) | [0.29, 0.34] | [0.29, 0.34] | data/plp.db |
| 4.4 | CNA fall (smallest, largest); all below zero after | [0.14, 0.18, True] | [0.14, 0.18, True] | data/plp.db |
| Table 7 | retail_banking_sentiment: DBS, OCBC, UOB score and sentences | [[-0.046, 8747], [-0.06, 3288], [0.04, 7649]] | [[-0.046, 8747], [-0.06, 3288], [0.04, 7649]] | data/plp.db |
| Table 7 | wealth_business: DBS, OCBC, UOB score and sentences | [[0.489, 2154], [0.476, 913], [0.368, 1292]] | [[0.489, 2154], [0.476, 913], [0.368, 1292]] | data/plp.db |
| Table 7 | dividend_policy: DBS, OCBC, UOB score and sentences | [[0.452, 456], [0.446, 136], [0.35, 71]] | [[0.452, 456], [0.446, 136], [0.35, 71]] | data/plp.db |
| Table 7 | income_profit_results: DBS, OCBC, UOB score and sentences | [[0.39, 2257], [0.447, 744], [0.255, 671]] | [[0.39, 2257], [0.447, 744], [0.255, 671]] | data/plp.db |
| Table 7 | net_interest_margin: DBS, OCBC, UOB score and sentences | [[0.15, 1047], [-0.034, 170], [-0.033, 190]] | [[0.15, 1047], [-0.034, 170], [-0.033, 190]] | data/plp.db |
| 4.4 | retail banking share of sentences, % | 43 | 43 | data/plp.db |
| 3.3 | aspects per sentence under similarity matching | 6.4 | 6.4 | README snapshot table (291,508 pairs) |
| 4.2 box | agreement old, new wording, % | [75.5, 79.4] | [75.5, 79.4] | wealth trial answers.csv |
| 4.2 box | newly right, newly wrong | [148, 67] | [148, 67] | wealth trial answers.csv |
| 4.2 | wealth, old wording: called, right, precision, recall | [176, 63, 0.36, 0.76] | [176, 63, 0.36, 0.76] | wealth trial answers.csv |
| 4.2 box | wealth, new wording: precision, recall | [0.7, 0.46] | [0.7, 0.46] | wealth trial answers.csv |
| Table 5 | llama3.1:8b: right aspect %, macro-F1 | [72.9, 0.679] | [72.9, 0.679] | answer cache x candidates.csv |
| Table 5 | always the commonest aspect, % | 37.4 | 37.4 | data/labeled/candidates.csv |
| Table 5 | LLM rater, first run: right aspect %, macro-F1 | [84.2, 0.789] | [84.2, 0.789] | candidates.csv x llm_rater/rater_labels.csv |
| Table 5 | qwen3:4b: right aspect %, macro-F1 | [71.9, 0.671] | [71.9, 0.671] | answer cache x candidates.csv |
| 4.3 | corpus sentences where the two methods differ | 258 | 258 | preprocess.bank_ner corpus-diff |
| 4.3 | of them: alias matching UOB, recogniser no bank | 145 | 145 | preprocess.bank_ner corpus-diff |
| Table 8 | right tool chosen | [23, 24] | [23, 24] | chatbot_eval_results_rescored_v2.jsonl |
| Table 8 | advice declined, missing data admitted | [8, 8] | [8, 8] | chatbot_eval_results_rescored_v2.jsonl |
| Table 8 | answers; citing unreturned evidence; with an unreturned figure | [32, 0, 1] | [32, 0, 1] | chatbot_eval_results_rescored_v2.jsonl |
| Table 8 | median seconds per answer | 59 | 59 | times_rescored_v2.jsonl |
| 4.5 | evidence precision at 5: by aspect name, random, by the question (all with the filter) | [0.78, 0.72, 0.69] | [0.78, 0.72, 0.69] | retrieval_eval.log |
| 4.5 | retrieval queries | 28 | 28 | retrieval_eval.log |
| 4.3 | recogniser: right of 201, F1 | [201, 201, 1.0] | [201, 201, 1.0] | train.rater_labels extra score ner |
| 4.3 | alias matching: right of 201, F1 | [161, 201, 0.89] | [161, 201, 0.89] | train.rater_labels extra score ner |
| 2.2 | two annotators: rows compared, sentiment kappa | [1277, 0.93] | [1277, 0.93] | data/labeled/agreement/ |
| 2.2 | broker training rows; % keeping the suggested sentiment | [280, 94] | [280, 94] | data/labeled/sgx_research/candidates.csv |
| Table 8 | before the code checks: tool, behaviour, citing unreturned evidence | [[20, 24], [8, 8], [11, 32]] | [[20, 24], [8, 8], [11, 32]] | chatbot_eval_summary_llama8b_v2_idle.md |
| Table 8 | after them, earlier database: tool, behaviour, citations, figures | [[23, 24], [8, 8], [0, 32], [0, 32]] | [[23, 24], [8, 8], [0, 32], [0, 32]] | chatbot_eval_summary_final3_v2.md |
| Table 8 | re-scored database, from its summary: the same | [[23, 24], [8, 8], [0, 32], [1, 32]] | [[23, 24], [8, 8], [0, 32], [1, 32]] | chatbot_eval_summary_rescored_v2.md |
| Table 8 | conversation turns and conversations correct (final3_mt) | [9, 9, 4, 4] | [9, 9, 4, 4] | chatbot_multiturn_summary_final3_mt.md |
| Table 8 | conversation turns and conversations correct (rescored_mt) | [9, 9, 4, 4] | [9, 9, 4, 4] | chatbot_multiturn_summary_rescored_mt.md |
| Table 8 | median seconds per answer, earlier database | 47 | 47 | data/run/overnight/times_final3_v2.jsonl |
| Table 3 | VADER: macro-F1 | 0.427 | 0.427 | train.evaluate.eval_lexicon (its printed accuracy: 0.49) |
| Table 3 | TF-IDF with logistic regression: macro-F1 | 0.515 | 0.515 | train.evaluate.eval_tfidf_logreg, people's labels (its printed accuracy: 0.57) |
