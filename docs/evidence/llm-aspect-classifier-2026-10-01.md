# LLM aspect classifier against the human aspect labels

DESIGN decision 16 (PLAN D1): a local LLM reads each sentence and chooses one
aspect, replacing seed-centroid assignment. Built and evaluated 2026-10-01 on
the 1,277 labelled sentences of the 27 Sep round, against their human aspect
(10-aspect taxonomy plus `other`, DESIGN 21). **Nothing was written to the
database**; applying it to the corpus is a separate decision.

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.llm_classify --eval                              # llama3.1:8b
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.llm_classify --eval --model qwen3:4b --no-think
```

## How it classifies

`aspects/llm_classify.py` sends one sentence per request to Ollama
(`/api/chat`, temperature 0) with a fixed prompt in the course's zero-shot
ABSA pattern (NMSM Day 2): the role (analyst classifying sentences about DBS,
OCBC and UOB), the task (the one aspect the sentence is mainly about; if two,
the one its sentiment is about; topic, not polarity), the eleven keys with a
one-line definition each (from
[aspect-taxonomy-2026-09-25.md](aspect-taxonomy-2026-09-25.md)), the
constraint (JSON, one key), eleven invented example sentences (none from the
data), then the sentence. Ollama's structured output constrains the answer to
JSON whose `aspect` is one of the keys. An invalid answer is retried once,
then recorded as `other` and counted. Answers are cached in
`data/aspect_llm/<model>.jsonl` (gitignored), so a run resumes; since 2 Oct
the name also carries a hash of the prompt, `<model>.96efe244.jsonl` for
this one, so a changed prompt can't reuse these answers. The prompt
was written once and not tuned on these labels.

`--no-think` sends Ollama's `think: false`. qwen3:4b is a reasoning model:
with thinking on, the first three sentences took 95, 92 and 216 s (about 47
hours for the 1,277); with it off, the same three took 1.1–1.3 s and gave the
same answers.

## Result

1,277 sentences; the test split (299) is the purely random sample, so it is
the closest estimate of how the classifier would do on the corpus:

| method | top-1, all | macro-F1, all | top-1, test | macro-F1, test | s per sentence |
|---|---|---|---|---|---|
| always `retail_banking_sentiment` | 0.374 | 0.049 | 0.495 | 0.060 | — |
| seed-centroid, floor 0.65 (current) | 0.413 | 0.296 | 0.465 | 0.250 | — |
| **llama3.1:8b** | **0.729** | **0.679** | **0.736** | **0.647** | 1.98 |
| qwen3:4b, no thinking | 0.719 | 0.671 | 0.746 | 0.630 | 1.33 |

Neither model gave an invalid answer or needed a retry: the structured
output makes an invalid key impossible in practice. Centroid figures are
recomputed with `aspects/assignment_eval.py`'s own functions on the same
rows (all-rows top-1 0.413, as in
[aspect-assignment-calibration-2026-09-30.md](aspect-assignment-calibration-2026-09-30.md)).
On the random test split the centroid method does worse than always
answering the commonest aspect; the LLMs beat it by 0.27 and 0.28.

**Per aspect** (centroid: recall only; P/R/F1 per model):

| human aspect | rows | centroid R | llama P | llama R | llama F1 | qwen P | qwen R | qwen F1 |
|---|---|---|---|---|---|---|---|---|
| retail_banking_sentiment | 477 | 0.62 | 0.85 | 0.86 | 0.85 | 0.86 | 0.86 | 0.86 |
| income_profit_results | 149 | 0.53 | 0.84 | 0.85 | 0.84 | 0.91 | 0.70 | 0.80 |
| wealth_business | 129 | 0.20 | 0.49 | 0.51 | 0.50 | 0.70 | 0.36 | 0.48 |
| other | 100 | 0.05 | 0.46 | 0.36 | 0.40 | 0.36 | 0.69 | 0.47 |
| management_guidance | 93 | 0.30 | 0.63 | 0.46 | 0.53 | 0.66 | 0.40 | 0.50 |
| investor_stock_sentiment | 89 | 0.39 | 0.54 | 0.85 | 0.66 | 0.61 | 0.74 | 0.67 |
| asset_quality | 78 | 0.28 | 0.92 | 0.76 | 0.83 | 0.91 | 0.81 | 0.86 |
| net_interest_margin | 58 | 0.21 | 0.69 | 0.76 | 0.72 | 0.53 | 0.86 | 0.66 |
| capital_liquidity | 49 | 0.16 | 0.82 | 0.76 | 0.79 | 0.87 | 0.55 | 0.68 |
| dividend_policy | 33 | 0.39 | 0.86 | 0.55 | 0.67 | 0.85 | 0.85 | 0.85 |
| macro_market_environment | 22 | 0.23 | 0.59 | 0.77 | 0.67 | 0.46 | 0.77 | 0.58 |

Every aspect's recall is higher than the centroid method's, under both
models.

**Where llama3.1:8b goes wrong** (human → model, rows): wealth → retail
banking 36; retail banking → investor stock 31; `other` → wealth 24; retail
banking → wealth 24; `other` → retail banking 22; management guidance →
`other` 18, → wealth 13; wealth → investor stock 13. The weak aspects are
the ones whose boundary the guideline itself draws loosely: wealth against
retail banking (investment products bought at a bank), `other`, and
management guidance. It over-uses investor stock sentiment (141 predicted,
89 by people).

**By source** (top-1): Reddit 617 rows, centroid 0.519, llama 0.754, qwen
0.726; earnings 477, 0.363, 0.748, 0.706; Google News 166, 0.181, 0.566,
0.717. llama is weakest on news headlines, where qwen is not.

**The two models as a check on each other.** They agree on 965 of 1,277
sentences (76%); where they agree, the answer matches the human label 83.5%
of the time; where they disagree, llama is right 40% and qwen 36%. Agreement
is the closest thing to a confidence score this design has (temperature 0,
one answer, no probability).

## Time for the full corpus

44,345 sentences, one request each, on this MacBook Air (M1, 16 GB):
llama3.1:8b at a mean of 1.98 s (median 1.92, p95 2.74) is about **24
hours**; qwen3:4b without thinking at 1.33 s (median 1.27, p95 1.72) about
**16 hours**; both, for the agreement check, about 40. The qwen mean leaves
out one request that took 5,312 s because the Mac slept during it (battery,
15:51–17:20); its run's printed mean, 5.49 s, includes it.

*Measured on the corpus run itself (2 Oct):* llama3.1:8b takes about 2.7 s a
sentence there, slower than on the labelled set (the cause wasn't checked),
so the whole corpus is about **33 hours**, not 24.

## Caveats

- The human aspect is one rater's: the two annotators shared one corrected
  aspect column, so aspect agreement was never measured
  ([annotation guideline](../annotation-guideline.md), "Agreement"). An
  accuracy of 0.73 can't be set against a human ceiling yet.
- The train/dev rows were stratified, not random; the test split is the
  fair sample; its top-1 is 0.007 (llama) and 0.027 (qwen) above the
  all-rows figure.
- One prompt, one run per model, temperature 0. Changing the prompt using
  these results would need a held-out part of the labels to report on.
- The first minutes of the llama run shared the machine with a CPU
  evaluation job, which slows it slightly; the time estimates are
  conservative rather than optimistic.

## What needs deciding

Whether to replace seed-centroid assignment with this classifier on the
corpus (DESIGN 16), with which model, and what to do where the two models
disagree (about a quarter of sentences, where either is right less than
half the time): keep llama's answer, send them to `other`, or leave them
unassigned. Applying it rewrites `sentence_aspects`, which DESIGN decisions
4 and 5 fill from the centroids today, and needs re-scoring and
re-aggregation after.
