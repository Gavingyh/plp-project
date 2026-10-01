# What the two pending changes would do to the index: a preview

Two changes wait for a team decision: aspects from the LLM classifier
instead of seed-centroid matching (DESIGN decision 16), and sentiment from
the fine-tuned models instead of base FinBERT. This previews both on a
random sample, scored with the index's own function, without touching the
database. Run 2026-10-01.

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.preview --n 1000 --cpu
```

1,000 sentences drawn at random (seed 2026) from the 44,345; for each, its
stored centroid aspects (6,332 pairs, 6.3 per sentence) and base FinBERT
label, its `llama3.1:8b` aspect (one per sentence), and the average of the
three readable-label fine-tuned models
([finetune-fixes-2026-10-01.md](finetune-fixes-2026-10-01.md)) on each
(sentence, aspect) pair. Four scenarios, each summarised with
`aggregate.index._summarize` (confidence- and source-weighted, shrunk, the
headline counting each sentence once by its most confident pair):

| | aspects | sentiment |
|---|---|---|
| A | centroid (what the database holds) | base FinBERT |
| B | LLM | base FinBERT |
| C | centroid | fine-tuned average |
| D | LLM | fine-tuned average |

## The headline per bank

| bank | sentences | A | B | C | D |
|---|---|---|---|---|---|
| DBS | 541 | +0.090 | +0.090 | +0.182 | +0.147 |
| OCBC | 181 | +0.215 | +0.215 | +0.328 | +0.281 |
| UOB | 278 | +0.076 | +0.076 | +0.266 | +0.171 |

Labels per sentence: base FinBERT 68.6% neutral, 21.3% positive, 10.1%
negative; fine-tuned (C) 47.6%, 37.1%, 15.3%; (D) 48.4%, 34.6%, 17.0%.

**How far the sample is from the corpus.** Scenario A is what the stored
index computes on all sentences: DBS +0.122, OCBC +0.136, UOB +0.074
(STATUS.md). The sample gives +0.090, +0.215 and +0.076: within about 0.03
for DBS and UOB, 0.08 off for OCBC, whose sample holds 181 sentences. Read
the columns against each other (same sentences), not against the stored
figures.

**What it shows.**

1. **Changing the aspects doesn't move the headline** (A = B exactly). With
   base FinBERT every pair of a sentence carries the same label, and the
   headline counts each sentence once, so which aspect a sentence gets
   can't change it. Aspects matter only for the per-aspect rows.
2. **Changing the sentiment model moves every headline up, by 0.06 to 0.19**,
   because the fine-tuned models call about 20 points fewer sentences
   neutral and most of those become positive. It also **reorders the
   banks**: on base FinBERT DBS and UOB are level (+0.090, +0.076) behind
   OCBC; on the fine-tuned models UOB is clearly ahead of DBS (C: +0.266
   against +0.182; D: +0.171 against +0.147).
3. Part of that shift is the fine-tuned model's known bias: on the test
   split it calls neutral sentences positive or negative more often than
   people do ([error-analysis-2026-10-01.md](error-analysis-2026-10-01.md)).
   The dev-chosen neutral margin, not applied here, would pull it back
   partly. Whoever decides should look at the margin version too.

## Per aspect

Under centroid assignment every named aspect (all but `other`) of every bank scores positive (the
lowest is UOB retail banking, +0.059). With LLM aspects several turn
negative: DBS asset quality −0.255 (A: +0.258), UOB NIM −0.240 (A: +0.367),
OCBC NIM −0.188 (A: +0.463), DBS retail banking −0.072 (A: +0.078). The
centroid method files generic positive earnings prose under every aspect
(6.3 per sentence), so each aspect inherits the bank's overall tone; the
LLM files a sentence under the one aspect it is about.

The spread of aspect scores within a bank is similar either way (standard
deviation 0.17–0.19 under A, 0.19–0.24 under B); the difference is where
the scores sit, not how far apart they are.

**These per-aspect numbers are thin under B.** One aspect per sentence
leaves a median of 17 sentences per bank-aspect cell in this sample (A:
170), and 21 of the 30 cells have fewer than 30. The full corpus has 44
times as many; the sign changes above are what to check first when the
classifier runs on it.

| aspect (LLM, one per sentence) | sentences in the sample | centroid pairs in the sample |
|---|---|---|
| retail_banking_sentiment | 423 | 820 |
| investor_stock_sentiment | 132 | 878 |
| other | 99 | 43 |
| wealth_business | 88 | 736 |
| income_profit_results | 83 | 236 |
| management_guidance | 50 | 791 |
| macro_market_environment | 31 | 119 |
| asset_quality | 29 | 700 |
| capital_liquidity | 27 | 757 |
| net_interest_margin | 25 | 423 |
| dividend_policy | 13 | 829 |

## A device failure, caught

The first run scored the fine-tuned models on the GPU while the Mac was
swapping heavily. Scenario C came back plausible, but D came back with
every probability 0, which `argmax` turns into "negative" for all 1,000
sentences, and no error. The rerun on the CPU (the command above) is the
one reported. Between the two runs, C's headlines differ by 0.011 to 0.019,
so the GPU's C was nearly right too; the CPU figures are used throughout.
`finetuned_labels` now refuses probabilities that don't sum to 1
(`tests/test_preview.py`).

## Caveats

One random sample of 1,000; the sampling error is visible in the A column
above. The per-sentence results are in `data/preview/` (gitignored); the
LLM answers in the classifier's cache. Nothing was written to the database.
