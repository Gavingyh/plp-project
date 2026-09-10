# Status: what's done, what isn't, what to improve

Written to be usable directly as source material for the project report —
the sections map onto methodology, results, limitations and future work.

For reasoning behind design choices, see [DESIGN.md](DESIGN.md). For how to
run anything mentioned here, see [RUNBOOK.md](RUNBOOK.md).

---

## Before you trust any number

| claim you might make | why you can't, yet |
|---|---|
| "DBS/OCBC show more positive sentiment than UOB" | No longer an artifact of missing UOB data — all three banks now have earnings coverage (DBS 9,093 sentences, UOB 1,600, OCBC 1,561). DBS still carries ~6x the earnings volume of the other two, so check the per-source breakdown before making a blended claim. |
| "The fine-tuned FinBERT classifier achieves X" | No fine-tuned model exists. All scores are base FinBERT, zero-shot. |
| "The aspect breakdown shows NIM sentiment is Y" | **Measured and failing for Reddit.** The 20 highest-similarity Reddit sentences assigned to `net_interest_margin` are all retail banking products (fees, cards, fixed deposits) and none are about margins. Earnings-only rows for that aspect are defensible; Reddit-only and blended ones are not. |
| "The chatbot cites its sources" | Local models fabricate citations — 43–48% of answers on the default model, across two runs. A code check flags this, but it detects rather than prevents. See the evaluation below. |
| "GPT / Gemini backends work" | Never run against their real APIs — no keys were available. |

**The Reddit-only rows remain the cleanest cross-bank comparison** (DBS
-0.0015, OCBC -0.0107, UOB -0.0106 — no meaningful difference). The blended
rows are now defensible too, but read them alongside the per-source
breakdown: earnings text scores far higher than retail chatter for every bank
(DBS +0.168, OCBC +0.206, UOB +0.229), so blended scores track earnings
coverage as much as sentiment.

---

## Current corpus

| | count |
|---|---|
| documents | 21,924 |
| sentences | 36,884 |
| (sentence, aspect) pairs scored | 79,987 |
| date range | Jan 2020 – Sep 2026 |

By source:

| source | documents | sentences |
|---|---|---|
| Reddit (`r/singaporefi`) | 21,726 | 24,591 |
| Earnings PDFs (DBS, OCBC, UOB) | 178 | 12,254 |
| NewsAPI | 20 | 39 |

By bank: DBS 20,907 · UOB 10,601 · OCBC 5,376 sentences.

Earnings sentences by bank: DBS 9,093 · UOB 1,600 · OCBC 1,561.

Codebase: 9,270 lines of Python (6,542 excluding tests), 246 tests.

Every figure on this page was re-taken from `data/plp.db` on 2026-09-11 and
is recorded with its query in [verification-ledger.md](verification-ledger.md).
The previous version of this table under-reported documents by source — it
listed 18,620 / 177 / 18, which summed to 18,815 against its own stated total
of 21,924.

---

## Done

**Ingestion.** Reddit (Arctic Shift, 2020–present), earnings PDFs auto-fetched
from DBS and OCBC IR sites and, for WAF-blocked UOB, from the Wayback
Machine; NewsAPI; Yahoo Finance analyst consensus. All
idempotent — re-running any adapter inserts nothing new.

**Preprocessing.** Sentence segmentation with financial-abbreviation handling,
per-source cleaning, per-sentence bank attribution, near-duplicate removal.

**Aspects.** FinBERT embeddings, offline clustering for taxonomy discovery,
frozen-centroid assignment per batch, and a tool for comparing candidate
taxonomies quantitatively.

**Sentiment & aggregation.** Base FinBERT scoring, per-bank/aspect index with
volume shrinkage, 7d/30d/all-time windows, per-source breakdown.

**Interfaces.** Streamlit dashboard (including a Chat tab), FastAPI REST API,
chatbot with four pluggable model backends and RAG evidence retrieval.
Suggested starter questions are generated from the index rather than
hardcoded, so the UI never offers a question the data cannot answer.

**Engineering.** 246 tests (external APIs mocked with captured payloads),
central logging with debug configuration, resumable overnight backfill script,
start/stop/status scripts for the dashboard and API.

---

## Chatbot evaluation

A 23-question gold set (`chatbot/eval_gold_set.py`) run against five local
models via `chatbot/run_eval.py`. Tool selection, advice-declining behaviour
and citation fabrication are checked automatically; whether a stated number
is correct is not (see the note at the end of this section).

| model | params | errors | tool selection | behaviour | citation fabrication |
|---|---|---|---|---|---|
| `llama3.2:3b` (default) | 3B | 0 | 12/16 | 3/7 | **10–11/23 (43–48%)** |
| `phi4-mini` | 3.8B | 0 | 0/16 | 1/7 | 19/23 (83%) |
| `gemma3:4b` | 4B | 23 | 0/16 | 0/7 | 0/23 — *artifact, see below* |
| `qwen3:4b` | 4B | 23 | 0/16 | 0/7 | 0/23 — *artifact, see below* |
| `llama3.1:8b` | 8B | 3 | 12/16 | 3/7 | **3/23 (13%)** |

Six things worth carrying into the report:

**The default model's fabrication rate is a range because it was run twice.**
11/23 on 2026-09-07 and 10/23 on 2026-09-10, same model, same gold set. That
is a one-question difference, and on 23 questions one question is 4.3
percentage points. Every other rate in this table rests on a single run and
carries the same uncertainty without showing it. Treat these as approximate
to within roughly one question, and do not report a change of a few points
between two models as a real difference unless it survives a re-run. The
gap that does survive is `llama3.2:3b` against `llama3.1:8b`, which is
roughly eight questions wide.

**Scale cuts fabrication sharply, and fixes nothing else.** Going from 3B to
8B drops citation fabrication from 43–48% to 13%, a gap far wider than the
run-to-run noise above. Tool selection (12/16) and advice-declining behaviour
(3/7) are *identical* across the two. So fabrication is a capability limit
that scale relieves, while the behavioural failures are design problems that a
bigger model does not touch.

**Two models score 0% fabrication and neither result means anything.**
`gemma3:4b` has no Ollama tool-calling support, so all 23 questions failed
with HTTP 400. `qwen3:4b` (added 2026-09-11) failed all 23 differently: every
call exceeded the 120-second read timeout, because it emits a long hidden
reasoning chain before answering and the agent loop needs several calls per
question. Both produced 23 empty answers, so there were no citations to
fabricate. **A fabrication rate is only meaningful alongside its error
count**, which is why the table carries both — read either 0% as "produced no
output", not "stayed grounded".

The qwen result is consistent with what `train/llm_prelabel.py` already
records: on a far simpler single-turn labelling task the same model took
65–97 seconds per call, against 3–5 seconds for `llama3.2:3b`. It is not
viable for an agent loop at any reasonable timeout. One caveat on this
particular run: it shared the machine with other work, which will have made
the timeouts worse, so treat "unusably slow here" rather than a specific
latency as the finding.

**phi4-mini is the worst case and the most instructive one.** It called a
tool in 0 of 16 questions yet fabricated citations in 83% of answers — it
answered entirely from parametric knowledge while producing text that looks
sourced. This is the strongest single argument in the project for enforcing
grounding in code rather than in the prompt.

**Advice-declining is the weakest area regardless of model.** 3/7 at best,
and `advice-1`/`advice-2` fail on every model tested. For a tool carrying a
not-financial-advice disclaimer this is the most report-relevant gap, and it
is a prompt/design fix rather than a model choice.

Per-model transcripts are in `data/eval/chatbot_eval_results_*.jsonl`,
summaries in `data/eval/chatbot_eval_summary_*.md`. Reproduce with
`scripts/compare_chatbot_models.sh`.

**Not automated:** whether the numbers a model states are actually correct,
and whether cited evidence is relevant. That needs a human reading the
transcripts — verifying a number by extracting it with another model is less
trustworthy than the check itself.

---

## Not done

### 1. Labelling — the critical blocker

Zero examples human-labelled. This blocks the fine-tuned classifier, which
blocks the deep-learning deliverable the proposal commits to.

The candidate set is exported (`data/labeled/candidates.csv`, 998 rows: 798
`train_dev` and 200 `test`). `train/llm_prelabel.py` has run a local model
over it to propose a label and rationale for each row, so labelling becomes
correction rather than starting from scratch: 997 rows carry an
`llm_prelabel` from `llama3.2:3b` (999 succeeded, 1 failed).
`train/finetune.py` / `train/evaluate.py` are written and smoke-tested. Only
the human correction step is missing.

**The test split was pre-labelled before anyone noticed it shouldn't be.**
199 of the 200 `test` rows received an `llm_prelabel`, and every row also
carries `base_finbert_label` — base FinBERT being one of the two models the
test set exists to compare. An annotator working from that sheet would have
been measuring agreement with a model rather than establishing ground truth,
and anchoring on the baseline's answer would have biased the comparison in
the baseline's favour.

`preprocess/export_blind_test.py` is the repair: it writes
`data/labeled/test_blind.csv` carrying the sentence, its aspect and its
provenance and nothing else, and merges the filled sheet back afterwards.
What this does and does not fix is worth being precise about. It does prevent
the leak for anyone who labels from the blind sheet, which is nobody so far
since zero rows are labelled. It does not undo the model's exposure to those
rows, and it cannot help if someone opens `candidates.csv` and labels the
test rows there instead. **Label the test split from `test_blind.csv` only.**

**Class balance is a live risk for two aspects.** The proposal asks for
200–300 examples per sentiment class. The candidate pool is not distributed
to make that reachable per aspect:

| aspect | candidate rows |
|---|---|
| other | 524 |
| dividend_policy | 200 |
| net_interest_margin | 119 |
| management_guidance | 97 |
| asset_quality | 58 |

`asset_quality` and `management_guidance` cannot yield 200 per class no
matter how the labels fall, and `other` — the fallback bucket, not a real
aspect — is the majority of the sheet. The model's own proposed labels split
positive 464 / negative 310 / neutral 223, which is far less neutral-heavy
than the base-FinBERT distribution over the whole corpus (87% neutral) and is
a consequence of the deliberate non-neutral oversampling in the `train_dev`
sampler. Human labels may not follow it.

Running pre-labelling for real surfaced something worth knowing before
correcting: some candidates are off-topic for the aspect they were assigned
(a product description assigned to `management_guidance`, for instance) —
exactly the "incidental mentions" case `docs/annotation-guideline.md`
already anticipated. Expect to flag/discard some rows rather than correct
their label.

The sampling design matters and shouldn't be shortcut: the test split is
drawn at random *before* any model-assisted selection. If the test set were
drawn from model-screened candidates, the fine-tuned model's reported F1
would be inflated relative to the baseline it's compared against.

### 2. UOB earnings coverage — resolved

Was the project's biggest validity problem: DBS 9,093 earnings sentences,
OCBC 1,561, **UOB 4**. UOB's IR site sits behind an F5 WAF that answers
scripted requests with a challenge stub, so the direct fetch used for DBS and
OCBC could not reach it.

Resolved by fetching the same PDFs from the Wayback Machine, which is not
behind that WAF (`ingest/uob_wayback_fetch.py`): 66 quarterly documents,
2020–2025, giving UOB 1,600 earnings sentences. UOB's blended all-time score
moved from -0.011 to +0.020 as a direct result — a clean illustration of how
much a coverage gap had been distorting the comparison.

Residual caveat: DBS still carries ~6x the earnings volume of either other
bank, because it publishes full analyst-call transcripts and they are long.
The per-source breakdown remains the honest way to read blended figures.

### 3. Aspect taxonomy not validated

The taxonomy is still the proposal's four a-priori aspects. The earlier
finding — that clustering found only a coarse consumer-banking versus
investment-discussion split — was drawn from a Reddit-only corpus of 2,888
sentences and **no longer holds**.

**Discovery re-run, 2026-09-11, on all 36,884 sentences.** This could not be
run before today: `aspects.discover` bound one SQL parameter per embedding
and SQLite caps that at 32,766, so it had been failing outright since the
corpus passed that size. Fixed on this branch.

With earnings text in the corpus, clusters of exactly the kind the proposal
anticipated appear unprompted: leverage ratio against the regulatory minimum,
final Basel III reforms and their CET-1 effect, fee income by line, return on
equity and return on tangible equity. None of these existed in the
Reddit-only run. **This is the clearest evidence the project has that
ingesting earnings material closed a real vocabulary gap rather than merely
adding volume.**

It does not settle the taxonomy. The run produced 281 clusters with a median
size of 23 and 67% of the corpus left as noise, which is a topic list rather
than an aspect set, and the fundamental clusters are finer than
`asset_quality` or `management_guidance` and cut across them. Noise rose from
52%, so a bigger corpus did not buy cleaner structure at the default
`min_cluster_size`. Full write-up:
[evidence/aspect-discovery-2026-09-11.md](evidence/aspect-discovery-2026-09-11.md).

**A side finding worth acting on:** several clusters are extraction artifacts
rather than topics — character-spaced PDF text, chart axis labels, earnings
boilerplate, Reddit markdown table fragments. Measured across the corpus these
are 2.6% of sentences (2.7% of earnings, 2.5% of Reddit), so they are not
distorting the index, but they will undermine any cluster listing reproduced
in the report. Crude filters in `preprocess/clean.py` would remove most of
them.

The evidence that assignment is not yet trustworthy: Reddit sentences are
assigned to `net_interest_margin` by centroid similarity, but the Reddit
corpus contains **zero** occurrences of "net interest margin" and 4 of the
abbreviation `NIM`. The earnings corpus contains 375 and 300. Adding earnings
data closed the vocabulary gap; it did not fix assignment.

**Now measured, not just suspected (2026-09-11).** The twenty Reddit sentences
with the *highest* similarity to the `net_interest_margin` centroid are, in
order: "No fees for ocbc", "DBS Fixed deposit interest.", "DBS My Account: no
minimum balance and fees.", "UOB one savings terms and conditions", "UOB
Absolute Amex, 1.7% unlimited cashback", and so on. **Not one is about net
interest margin.** All twenty are retail banking products — fees, cards,
fixed deposits, transfers. These are the best matches, so the rest are worse.

Worse, the polarity inverts on the ones that do mention interest. "UOB One
(5.2% interest)" is a *deposit rate paid to a customer*, which is a funding
cost to the bank and compresses its margin. A depositor's enthusiasm is scored
as positive sentiment on a metric it actually damages.

**Practical consequence: do not report Reddit-sourced `net_interest_margin`
rows.** They measure retail enthusiasm for deposit products. The earnings-only
rows for that aspect are defensible; the blended and Reddit-only ones are not.
Whether the other three aspects fail the same way has not been checked, and
`dividend_policy` may well be fine given Reddit discusses dividends in 561
sentences. Reproduce with the query in
`learning/02-sentiment-mining/aspect-based-sentiment-analysis.md`.

**Re-run on the full corpus, 2026-09-11.** `aspects/compare_taxonomies.py`
was itself measuring at the wrong threshold: it hardcoded the pre-calibration
floor of 0.35 while `config/aspects.yaml` had moved to 0.65 five days
earlier and `aspects/assign.py` reads the config. The tool now reads the live
floor and can sweep a range. Results at the production floor, over all 36,884
sentences:

| candidate | aspects | avg matched/sentence | % other | centroid separation |
|---|---|---|---|---|
| A — the proposal's four | 4 | 1.80 | 37.3% | 0.1125 |
| B — data-derived coarse | 2 | 1.69 | 7.7% | 0.1695 |
| C — data-derived fine | 3 | 2.38 | 8.5% | 0.2222 |

Centroid separation is the column that matters most, because it is computed
from the seed embeddings alone and therefore cannot be changed by tuning the
floor. The proposal's four aspects are the least distinct of the three
candidates. Sweeping the floor from 0.35 to 0.80 shows candidate A has no
usable operating point: at 0.60 it still matches 2.55 of 4 aspects per
sentence, at 0.65 it discards 37.3% of the corpus to `other`, and at 0.70 it
discards 57.9%. The data-derived candidates hold their shape across the whole
range.

Full table, caveats and the argument against over-reading it are in
[evidence/taxonomy-comparison-2026-09-11.md](evidence/taxonomy-comparison-2026-09-11.md).
The short version of the caveat: coarser taxonomies separate more easily
partly as arithmetic, and none of this measures whether assignments are
*correct*. This remains a judgement call for the team and supervisor, not
something to settle in code.

### 4. Model backends never verified

GPT and Gemini backends are written to documented API contracts but have
never received a real response. Gemini carries more risk — its schema `type`
field expects uppercase proto-enum values, unlike the JSON-Schema lowercase
used everywhere else in this codebase.

### 5. Smaller gaps

- `get_trend`'s headline direction is still a two-window comparison (7d vs
  30d); it now also returns up to 12 monthly points alongside it, so the
  shape behind the direction is visible. The two-window figure remains what
  the `direction` field is computed from.
- The news-derived analyst proxy (`ingest/analyst_tag.py`) matches zero
  documents; largely superseded by Yahoo consensus but retained since the
  zero result is itself a finding.
- Alpha Vantage contributes nothing (no SGX coverage) but remains in the
  codebase.
- NewsAPI's free tier gives ~1 month of lookback and title+description only.

---

## Where the original plan was wrong

Useful for the report's methodology discussion — these are cases where
implementation contradicted the plan.

**SGX was the wrong target.** The plan assumed analyst reports could come
from SGX. They cannot: SGX hosts company announcements, not third-party
analyst reports, which are brokerage IP behind entitlements. The banks' own
IR sites turned out to be open and to carry the same earnings material —
including DBS's quarterly analyst call transcripts, which are closer to the
original goal than anything SGX would have provided.

**The aspect taxonomy did not emerge as predicted.** The plan assumed
clustering would surface the four proposed aspects. It surfaced a
consumer-banking vs. investment-discussion split instead, because the
dominant corpus (`r/singaporefi`) discusses banking products rather than
equity fundamentals.

**Adding a data source made a metric worse.** Earnings ingestion closed a
real vocabulary gap and simultaneously broke cross-bank comparability, since
it arrived for two banks out of three. Worth reporting: more data is not
automatically better if it arrives unevenly.

**Prompt instructions were insufficient for grounding.** The plan assumed
system-prompt rules would keep the chatbot honest. A local model fabricated
citations twice, in two different formats, after the prompt was tightened.
The rules had to move into code.

---

## How to improve it

Roughly in order of value.

1. **Label the data.** Unblocks the fine-tuned classifier and the DNN
   deliverable. LLM-assisted pre-labelling followed by human correction is
   viable and can run free on the local Ollama model.
2. ~~**Add UOB earnings.**~~ Done — 66 quarterly PDFs (2020–2025) fetched
   from the Wayback Machine, which is not behind the WAF that blocks UOB's
   IR site. See `ingest/uob_wayback_fetch.py`.
3. **Settle the aspect taxonomy.** Re-run discovery on the enriched corpus,
   review with the supervisor, freeze the decision.
4. **Fix advice-declining, and switch the default local model.** The
   evaluation above has been run; two actions fall out of it. Advice-seeking
   questions are declined only 3/7 of the time on every model tested, which
   is a prompt/design fix, not a model-choice one. And `llama3.1:8b`
   fabricates citations at 13% against `llama3.2:3b`'s 43–48%, so it is the
   better default for anyone whose machine can run it — at the cost of being
   noticeably slower. Reading the transcripts for numerical fidelity is still
   outstanding and still human work.
5. **Verify GPT/Gemini backends** with one real call each.
6. ~~**Continuous time series** for `get_trend`.~~ Done — `compute_time_series`
   in `aggregate/index.py` buckets by week, month or quarter through the same
   `_summarize` the stored index uses, so a chart cannot disagree with the
   headline number. Exposed at `GET /sentiment/series`, on the dashboard's
   Time Series tab, and as `monthly_series` inside `get_trend`. Thin buckets
   are returned with `sufficient=false` rather than dropped, so a gap in a
   line means missing data rather than neutral sentiment.
7. **Improve relevance filtering.** Sentences mentioning a bank incidentally
   ("paid via DBS PayNow") still enter the corpus.
8. **Reconsider blending.** Whether management commentary and retail chatter
   belong in a single index at all is a legitimate methodological question,
   currently resolved in favour of the proposal's design with the
   composition made visible.
