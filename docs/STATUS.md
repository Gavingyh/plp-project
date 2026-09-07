# Status: what's done, what isn't, what to improve

Written to be usable directly as source material for the project report —
the sections map onto methodology, results, limitations and future work.

For reasoning behind design choices, see [DESIGN.md](DESIGN.md). For how to
run anything mentioned here, see [RUNBOOK.md](RUNBOOK.md).

---

## Before you trust any number

| claim you might make | why you can't, yet |
|---|---|
| "DBS/OCBC show more positive sentiment than UOB" | Artifact. DBS and OCBC have earnings text in the corpus; UOB has almost none. Earnings text is far more positive than any other source. |
| "The fine-tuned FinBERT classifier achieves X" | No fine-tuned model exists. All scores are base FinBERT, zero-shot. |
| "The aspect breakdown shows NIM sentiment is Y" | Aspect assignment is not yet validated. Reddit sentences are assigned to `net_interest_margin` despite the Reddit corpus containing zero instances of that phrase. |
| "The chatbot cites its sources" | Local models fabricate citations. A code check flags this, but it detects rather than prevents. |
| "GPT / Gemini backends work" | Never run against their real APIs — no keys were available. |

**The defensible cross-bank comparison today is the Reddit-only rows**, which
show no meaningful difference between the three banks.

---

## Current corpus

| | count |
|---|---|
| documents | 21,861 |
| sentences | 35,288 |
| (sentence, aspect) pairs scored | 77,070 |
| date range | Jan 2020 – Sep 2026 |

By source:

| source | documents | sentences |
|---|---|---|
| Reddit (`r/singaporefi`) | 21,726 | 24,591 |
| Earnings PDFs (DBS, OCBC) | 115 | 10,658 |
| NewsAPI | 20 | 39 |

By bank: DBS 20,907 · UOB 9,005 · OCBC 5,376 sentences.

Codebase: ~6,800 lines of Python, 144 tests.

---

## Done

**Ingestion.** Reddit (Arctic Shift, 2020–present), earnings PDFs auto-fetched
from DBS and OCBC IR sites, NewsAPI, Yahoo Finance analyst consensus. All
idempotent — re-running any adapter inserts nothing new.

**Preprocessing.** Sentence segmentation with financial-abbreviation handling,
per-source cleaning, per-sentence bank attribution, near-duplicate removal.

**Aspects.** FinBERT embeddings, offline clustering for taxonomy discovery,
frozen-centroid assignment per batch, and a tool for comparing candidate
taxonomies quantitatively.

**Sentiment & aggregation.** Base FinBERT scoring, per-bank/aspect index with
volume shrinkage, 7d/30d/all-time windows, per-source breakdown.

**Interfaces.** Streamlit dashboard, FastAPI REST API, chatbot with four
pluggable model backends and RAG evidence retrieval.

**Engineering.** 144 tests (external APIs mocked with captured payloads),
central logging with debug configuration, resumable overnight backfill script.

---

## Not done

### 1. Labelling — the critical blocker

Zero examples labelled. This blocks the fine-tuned classifier, which blocks
the deep-learning deliverable the proposal commits to.

Everything needed is ready: `preprocess/export_candidates.py` produces a
correctly-sampled candidate set, `docs/annotation-guideline.md` defines the
scheme, and `train/finetune.py` / `train/evaluate.py` are written and
smoke-tested. Only the human labelling is missing.

The sampling design matters and shouldn't be shortcut: the test split is
drawn at random *before* any model-assisted selection. If the test set were
drawn from model-screened candidates, the fine-tuned model's reported F1
would be inflated relative to the baseline it's compared against.

### 2. UOB earnings coverage

DBS 9,093 earnings sentences, OCBC 1,561, **UOB 4**. UOB's IR site blocks
automated access, so its PDFs need manual download into
`data/earnings_pdfs/UOB/`.

Until then the blended cross-bank comparison is invalid. Mitigations already
applied (earnings weight reduced 3.0 → 1.0, per-source breakdown exposed)
reduce the distortion but cannot remove it, because the cause is coverage
asymmetry rather than weighting.

### 3. Aspect taxonomy not validated

The taxonomy is still the proposal's four a-priori aspects. Clustering the
real corpus found a different structure — a split between consumer-banking
discussion and investment discussion, rather than dividend / asset-quality /
NIM / guidance.

The evidence that assignment is not yet trustworthy: Reddit sentences are
assigned to `net_interest_margin` by centroid similarity, but the Reddit
corpus contains **zero** occurrences of "net interest margin". The earnings
corpus contains 298. Adding earnings data closed the vocabulary gap; it did
not fix assignment.

`aspects/compare_taxonomies.py` produces the comparison needed to decide.
This is a judgement call for the team and supervisor, not something to settle
in code.

### 4. Model backends never verified

GPT and Gemini backends are written to documented API contracts but have
never received a real response. Gemini carries more risk — its schema `type`
field expects uppercase proto-enum values, unlike the JSON-Schema lowercase
used everywhere else in this codebase.

### 5. Smaller gaps

- `get_trend` compares two discrete windows, not a continuous series.
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
2. **Add UOB earnings.** ~10 PDFs, manual download. Restores cross-bank
   comparability.
3. **Settle the aspect taxonomy.** Re-run discovery on the enriched corpus,
   review with the supervisor, freeze the decision.
4. **Build the chatbot evaluation set.** A 30–40 question gold set measuring
   tool-selection accuracy, numerical fidelity and citation validity. Given
   the fabrication problem, this is report-worthy evidence rather than
   routine testing.
5. **Verify GPT/Gemini backends** with one real call each.
6. **Continuous time series** for `get_trend`, replacing discrete windows.
7. **Improve relevance filtering.** Sentences mentioning a bank incidentally
   ("paid via DBS PayNow") still enter the corpus.
8. **Reconsider blending.** Whether management commentary and retail chatter
   belong in a single index at all is a legitimate methodological question,
   currently resolved in favour of the proposal's design with the
   composition made visible.
