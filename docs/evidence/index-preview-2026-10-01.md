# What the two pending changes would do to the index: a preview

*Updated 2026-10-03: the full corpus (44,345 sentences), in the last section,
supersedes both samples; read it first. The 11,000-sentence preview overturned
two findings of this 1,000-sentence one (UOB does not move ahead of DBS; DBS
asset quality does not turn negative), and itself wrongly said its order
matched today's index: see the last section.*

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
   changes, the order is DBS, OCBC, UOB. (Corrected 3 Oct: this said "as it
   is today", but today's index puts OCBC just ahead of DBS; the full-corpus
   run below confirms the swap.)
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

## Full corpus: 44,345 sentences (3 Oct)

Run 2026-10-03 14:04–19:19 on the CPU, on every sentence, after the
`llama3.1:8b` corpus run finished (all 44,345 answered, none invalid). 281,744
centroid pairs (6.4 a sentence); the fine-tuned models' probabilities are
saved in `data/preview/scores.1a38d71a.jsonl`, so the margin version reused
them. Scenario A reproduces the stored index exactly (DBS +0.122, OCBC
+0.136, UOB +0.074), as it should with every sentence in.

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.preview --n 44345 --cpu
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.preview --n 44345 --cpu --margin 0.13
```

**The headline per bank**

| bank | sentences | A: centroid, base | B: LLM, base | C: centroid, fine-tuned | D: LLM, fine-tuned | D with margin 0.13 |
|---|---|---|---|---|---|---|
| DBS | 24,431 | +0.122 | +0.122 | +0.242 | +0.204 | **+0.192** |
| OCBC | 7,412 | +0.136 | +0.136 | +0.268 | +0.188 | **+0.174** |
| UOB | 12,502 | +0.074 | +0.074 | +0.250 | +0.151 | **+0.137** |

Labels per sentence: base FinBERT 70.0% neutral, 20.3% positive, 9.7%
negative; fine-tuned with LLM aspects 47.0%, 35.4%, 17.6%; with the margin
51.9%, 32.0%, 16.1%.

**What it shows.**

1. **The aspect method still doesn't move the headline** (A = B): each
   sentence counts once.
2. **The two changes together raise every headline by 0.04–0.07** with the
   recommended scoring (D with the margin; 0.05–0.08 without it), and **swap
   the top two banks**: today OCBC is just ahead of DBS (+0.136 against
   +0.122); with both changes DBS is just ahead of OCBC (+0.192 against
   +0.174). Both gaps are under 0.02; UOB is last either way. The
   11,000-sentence preview had the same order under D but wrongly called it
   unchanged.
3. **With centroid aspects the fine-tuned models raise the headlines more**
   (0.12–0.18, C) and put all three banks within 0.03 of each other, because
   every pair of a sentence is scored and the most confident wins.
4. **Per aspect, LLM aspects separate what centroids blur.** Under centroids
   (A and C) every named aspect of every bank is positive. With LLM aspects
   and base FinBERT (B), four cells are negative: retail banking for all
   three banks (−0.020 to −0.049) and OCBC asset quality (−0.026). DBS asset
   quality falls from +0.265 to +0.065. With LLM aspects and the fine-tuned
   models (D, margin), six are negative: retail banking for all three (DBS
   −0.086, OCBC −0.118, UOB −0.005), net interest margin for OCBC (−0.110)
   and UOB (−0.046), and OCBC macro (−0.040, 95 sentences); dividends turn
   strongly positive (+0.70 to +0.80).
5. **The 11,000-sentence sample held up on the headlines**: its D headlines
   were within 0.01 of these. Some smaller cells moved: in column B, UOB
   investor sentiment is +0.010 here (sample −0.009); in column D without
   the margin, UOB macro is +0.046 (sample −0.026) and OCBC macro −0.030
   (sample +0.127 on 23 sentences), and OCBC NIM is −0.113 on 141 sentences,
   not −0.323 on 31.

**Cell sizes.** Under LLM aspects the median of the 30 named bank-aspect
cells holds 699 sentences (smallest: UOB dividends, 59); none has fewer than
30. Centroid pairs: median 7,361.

**Caveats.** All-time scores, so the six misdated UOB earnings documents
(fixed in the parser, repair pending) don't affect this table. The
fine-tuned models are the 1 Oct seeds, trained from a relabelled head
([training-review-2026-10-03.md](training-review-2026-10-03.md)); retrained
models could move column D. Columns C and D come from one average of three
seeds; the next section measures how far each seed alone moves the index.

## How far the index moves from seed to seed (3 Oct)

The same 44,345 LLM-aspect pairs scored by each of the three fine-tuned
models alone, with the same 0.13 margin (chosen on dev for the average; a
single seed's best margin may differ). Run 3 Oct on the CPU:

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.preview --n 44345 --cpu --margin 0.13 --per-seed
```

| bank | base FinBERT | seed 1 | seed 42 | seed 7 | the average (D, margin) |
|---|---|---|---|---|---|
| DBS | +0.122 | +0.113 | +0.216 | +0.235 | +0.192 |
| OCBC | +0.136 | +0.116 | +0.198 | +0.210 | +0.174 |
| UOB | +0.074 | +0.105 | +0.135 | +0.149 | +0.137 |

**What it shows.**

1. **The seeds disagree by more than the effects reported above.** The
   spread between seeds is 0.122 for DBS, 0.094 for OCBC and 0.044 for UOB,
   far more than the 0.018 between DBS and OCBC. With seed 1 alone, OCBC
   stays just ahead of DBS (+0.116 against +0.113) and both fall below base
   FinBERT; with seed 42 or seed 7, DBS leads and every headline rises by
   0.06–0.11. UOB is last under every seed. "DBS moves ahead of OCBC" and
   "every headline rises" are properties of the three-seed average, not of
   fine-tuning as such.
2. **Test macro-F1 doesn't predict the level.** Seed 1 (test macro-F1
   0.617) gives the lowest headlines and seed 7 (0.565, below base) the
   highest ([finetune-fixes](finetune-fixes-2026-10-01.md)).
3. **Per aspect, signs are settled only where the evidence is strong.**
   Across the 30 named bank-aspect cells the median spread is 0.183 (the
   largest 0.438, DBS NIM). Eight cells change sign between seeds: NIM for
   all three banks (positive under seed 42, negative under the other two),
   macro for all three, OCBC asset quality, and UOB retail banking (−0.038
   to +0.002). Retail banking is negative for DBS and OCBC under every seed
   (spreads 0.058 and 0.053), and dividends and wealth are strongly
   positive under every seed.
4. **What to report.** The average, which is the setting chosen, with the
   per-seed range beside each headline; the DBS–OCBC order as unsettled;
   NIM and macro signs as unsettled. The seeds were trained from a
   relabelled head (training review, 3 Oct); retrained seeds may spread
   differently, which only a retrain can show.

