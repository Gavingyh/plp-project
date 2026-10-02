# What the two pending changes would do to the index: a preview

*Updated 2026-10-02: a second preview on 11,000 sentences (below) overturns
two findings of this 1,000-sentence one: UOB does not move ahead of DBS, and
DBS asset quality does not turn negative. Read the second section first.*

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

## Second preview: 11,000 sentences (2 Oct)

Run 2026-10-02 12:51–15:52 on the CPU, on the first 11,000 sentences of the
same random order (seed 2026), all of them already classified by
`llama3.1:8b` in the corpus cache, so the LLM made no new calls. 70,002
centroid pairs (6.4 a sentence).

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.preview --n 11000 --cpu
```

**The headline per bank**

| bank | sentences | A: centroid, base | B: LLM, base | C: centroid, fine-tuned | D: LLM, fine-tuned |
|---|---|---|---|---|---|
| DBS | 6,032 | +0.134 | +0.134 | +0.253 | +0.214 |
| OCBC | 1,848 | +0.142 | +0.142 | +0.245 | +0.180 |
| UOB | 3,120 | +0.068 | +0.068 | +0.257 | +0.161 |

Column A is close to the stored index over the whole corpus (DBS +0.122,
OCBC +0.136, UOB +0.074), so this sample stands for the corpus far better
than the first one did (OCBC was 0.08 off there).

**What changes from the first preview.**

1. **The ranking does not flip.** On 1,000 sentences UOB moved clearly ahead
   of DBS under the fine-tuned models. On 11,000, under C the three are level
   (+0.245 to +0.257), and under D, the combination of the two pending
   changes, the order is DBS, OCBC, UOB, as it is today.
2. **The headlines rise less.** The fine-tuned models raise them by 0.10–0.19
   with centroid aspects (C) and by 0.04–0.09 with LLM aspects (D), not by
   0.06–0.19 as first reported.
3. **The per-aspect sign changes are smaller and different.** DBS asset
   quality falls from +0.273 to +0.068 with LLM aspects (B), but stays
   positive (the first preview had −0.255). Under B five of the 30 named
   cells are negative, all slightly: retail banking for all three banks
   (−0.016 to −0.059), OCBC asset quality −0.039, UOB investor stock
   −0.009. Under D, retail banking for DBS and OCBC, NIM for OCBC (−0.323,
   31 sentences) and UOB (−0.096), and UOB macro (−0.026).

**What still holds.** Changing the aspect method leaves the headline exactly
unchanged (A = B), because each sentence counts once. Under centroid
assignment every named aspect of every bank is positive (A and C), since each
aspect inherits the bank's overall tone; LLM aspects separate them, and retail
banking, which holds 43% of sentences under the LLM, sits just below zero.
The fine-tuned models call 47–48% of sentences neutral against base
FinBERT's 70%.

**Cell sizes.** Under LLM aspects the median bank-aspect cell holds 182
sentences (centroid pairs: 1,817), and 3 of 30 cells hold fewer than 30.

**The lesson.** The first preview's two most quotable results were sampling
noise from 1,000 sentences, at most a few hundred per bank. Both appeared in
the team to-do page, the findings document, HANDOFF and the examiner's
assessment before this run, and are corrected there.

