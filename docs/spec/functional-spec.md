# Functional Specification

What the system does, for whom, and how you would tell whether it works.

This is the document a teammate joining now still lacks. The others cover
adjacent ground and are not repeated here: [DESIGN.md](../DESIGN.md) explains
*why* each choice was made, [RUNBOOK.md](../RUNBOOK.md) how to run things, and
[STATUS.md](../STATUS.md) what is and is not finished. Where this document
states a limitation, STATUS is the authority and this is a summary.

Current as of 2026-09-11. Figures trace to
[verification-ledger.md](../verification-ledger.md).

---

## 1. Purpose and users

### The problem

Singapore retail investors are heavily concentrated in DBS, OCBC and UOB and
have poor access to research on them. From the project proposal, citing the
SIAS-Beansprout Singapore Retail Investor Pulse Survey (March 2025, n=1,011)
and an MDRT survey (April 2025, n=2,000):

| finding | figure |
|---|---|
| Interested in or open to Singapore stocks | over 80% |
| Cite lack of guidance and research as a barrier | 24% |
| Cite lack of familiarity as a barrier | 19% |
| Of those with a small Singapore allocation, read an analyst report before investing | 81% |
| Rate their own financial literacy "good" | 34% |

*These figures are carried as cited in the proposal. They were not
independently re-verified against the original survey publications during the
documentation pass, and the report should cite the surveys directly.* The
same applies to the proposal's ">S$180B combined market cap, roughly half the
Straits Times Index" claim.

The gap this system addresses is the one between "81% read an analyst report
first" and the fact that analyst reports are brokerage IP behind
entitlements. The system does not replace research. It offers a regularly
refreshed, evidence-linked read of what is being said about the three banks.

### Users

| user | what they need | served by |
|---|---|---|
| **Retail reader** | A quick read on sentiment per bank and aspect, with the evidence behind it and an honest signal when data is thin | Streamlit dashboard, chatbot |
| **Frontend or API consumer** | The same numbers as JSON, for a non-Streamlit interface | FastAPI REST API |
| **Teammate, marker, supervisor** | To reproduce every number, see what is unfinished, and judge what the numbers support | Docs, evidence files, verification ledger, test suite |

The third user is not an afterthought. This is a graded practice module whose
deliverables include a report, a demo video and source code, so
reproducibility is a functional requirement rather than an engineering
nicety.

---

## 2. Scope and non-goals

**In scope.** Batch ingestion of public text about the three banks;
sentence-level aspect assignment and sentiment scoring; a per-bank, per-aspect
index with time windows and a continuous series; a dashboard, a REST API and a
grounded chatbot; a labelling workflow for the fine-tuning dataset.

**Explicit non-goals**, each a deliberate decision rather than an omission:

| non-goal | why |
|---|---|
| Investment advice | The chatbot must decline buy/sell framing. The system reports sentiment, not recommendations. |
| Real-time streaming | The proposal specifies scheduled batches. Sources are polled on demand or by cron. |
| Full analyst report text | Brokerage IP behind entitlements. Yahoo Finance consensus *aggregates* are the substitute, disclosed as such. |
| Price prediction or backtesting | No claim is made that sentiment predicts returns. Price data is reference only. |
| Beating a WAF | UOB's IR site signals refusal to scripted clients; the Wayback Machine is used instead of fingerprint spoofing. |
| Multi-user accounts, auth, deployment | Single-user local tool for a practice module. The API has no authentication and must not be exposed publicly. |

---

## 3. Data sources

| source | provides | cadence | key | caveats |
|---|---|---|---|---|
| **Reddit** via Arctic Shift | `r/singaporefi` posts and comments, 2020 to present. 21,726 documents, 24,591 sentences | Incremental 7-day pull; resumable multi-year backfill | none | Reddit declined the API application, so PRAW is unavailable. Keyword search times out, so whole subreddits are harvested by date window and filtered locally. `r/singapore` and `r/investing` returned zero bank-mentioning items and were dropped. |
| **Earnings PDFs** | Results releases, CEO presentations, and DBS analyst-call transcripts. 178 documents, 12,254 sentences | Manual, quarterly | none | DBS and OCBC fetched directly from IR sites; UOB via the Wayback Machine because its site is WAF-blocked. Archive coverage thins for recent quarters. Tables are not extracted, only prose. |
| **Yahoo Finance consensus** | Analyst counts, rating distribution, mean and median price targets | Daily, safe to re-run | none | **Unofficial API.** No published terms bless it; it needs a cookie and crumb handshake. Provides aggregates, not analyst reasoning. Must not be described as "analyst reports". |
| **NewsAPI** | Article title and description. 20 documents, 39 sentences | On demand | `NEWSAPI_KEY` | Free tier gives roughly one month of lookback and truncates body text, so usable text is title plus description. Contributes marginally at current volume. |
| **Alpha Vantage** | Nothing | — | `ALPHAVANTAGE_KEY` | Does not index SGX-listed tickers at all, confirmed live across three ticker formats for all three banks. Adapter retained in case coverage is added. |

The proposal committed to four streams. All four exist, but their weights are
very unequal: Reddit and earnings carry the corpus, consensus is structured
data rather than text, and news is marginal. That is a finding for the report,
not a gap to paper over.

---

## 4. Functional requirements

Each requirement has acceptance criteria that can be checked against the code,
a test, or a running instance. Status values: **Done**, **Partial**,
**Blocked**.

### 4.1 Dashboard

The dashboard has five tabs, defined in `dashboard/app.py`.

| # | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| D1 | As a retail reader, I see an overall sentiment score per bank so I can compare the three at a glance | Overview tab shows a score and its sample size `n` for each of DBS, OCBC, UOB. No score is ever displayed without `n`. | Done |
| D2 | I see sentiment broken down by aspect so I can drill into what drives the headline | Aspect Heatmap tab shows a bank-by-aspect grid | Done |
| D3 | I see how sentiment moved over time, not just a snapshot | Time Series tab plots a continuous series with a week/month/quarter selector. Buckets below the volume floor appear as gaps, never interpolated. Underlying counts are expandable. | Done |
| D4 | I can read the actual sentences behind a score | Evidence tab returns sentences with `sentence_id`, source URL and date | Done |
| D5 | I can ask questions in natural language | Chat tab runs the same agent as the CLI, offers generated starter questions, and shows the verification warning when it fires | Done |
| D6 | I am told when the data cannot support a number | Any cell with `n` below 5 reads "insufficient data" rather than a score | Done |
| D7 | I can see which sources produced a blended figure | Per-source breakdown available alongside blended rows | Done |

### 4.2 REST API

Thirteen endpoints in `api/main.py`. No authentication; localhost only.

| # | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| A1 | A frontend can fetch the same numbers the dashboard shows | `/sentiment`, `/sentiment/compare`, `/sentiment/index`, `/sentiment/trend`, `/sentiment/series` return JSON matching the stored index | Done |
| A2 | Invalid input is rejected, not guessed at | `bank` is validated against `^(DBS\|OCBC\|UOB)$`, `window` against `^(7d\|30d\|all_time)$`, `bucket` against `^(week\|month\|quarter)$`; bad values give HTTP 422, and an unknown bucket gives 400 | Done, covered in `tests/test_api.py` |
| A3 | A chat UI can offer questions the data can actually answer | `/suggestions?limit=N` returns questions generated from the index, never hardcoded, excluding advice-seeking and out-of-scope framings | Done |
| A4 | A caller can distinguish "no data" from "neutral sentiment" | `/coverage` reports `has_data`; thin results carry `insufficient_data` | Done |
| A5 | A caller can retrieve evidence with provenance | `/evidence` returns `sentence_id`, `url`, `published_at` per hit | Done |
| A6 | A caller can reach the chatbot | `POST /chat` accepts a message and optional backend | Done |
| A7 | Service health is checkable | `GET /health` returns `{"status": "ok"}` | Done |

### 4.3 Chatbot

| # | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| C1 | Answers questions about sentiment by querying the store, not from model memory | Six tools: `get_sentiment`, `compare_banks`, `get_trend`, `get_coverage`, `search_evidence`, `get_analyst_consensus` | Done |
| C2 | Never states a number it did not retrieve | Enforced in code by the volume floor, and by prompt rule 1 | **Partial** — the floor is enforced; numerical fidelity of answers is not automatically checked |
| C3 | Never cites evidence it did not retrieve | If `search_evidence` was not called, any quoted evidence, `sentence_id` or URL is fabricated by definition and the answer is flagged | **Partial** — detection works; local models still fabricate at 43–48% (3B) and 13% (8B) |
| C4 | Declines investment advice | Advice-seeking questions are declined with a not-financial-advice statement | **Partial** — best observed is 3 of 7 gold-set questions, on every model tested |
| C5 | Says so plainly when data is thin | Tools return `insufficient_data` below 5 observations | Done |
| C6 | Runs without any API key | Ollama backend auto-selected when no key is present | Done |
| C7 | Works with hosted models too | Claude, OpenAI and Gemini backends implemented | **Partial** — Claude verified; GPT and Gemini never run against real APIs |

C2, C3 and C4 are the honest weak points of the system and are the most
report-relevant findings in the project. See the evaluation section of STATUS.

### 4.4 Labelling workflow

| # | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| L1 | Export a stratified candidate set for annotation | `preprocess/export_candidates.py` writes 998 rows: 798 `train_dev`, 200 `test` | Done |
| L2 | The test split is drawn at random before any model screening, and frozen | `split=test` rows are randomly sampled independently of model output | Done |
| L3 | Annotators are not shown model opinions when labelling the test set | `preprocess/export_blind_test.py` writes a sheet carrying sentence, aspect and provenance only | Done |
| L4 | Pre-labelling reduces annotation to correction | `train/llm_prelabel.py` fills `llm_prelabel` and `llm_rationale`, never `label`; checkpointed and resumable | Done, 997 of 998 rows |
| L5 | Agreement between annotators is measured before dividing the work | `train/agreement.py` reports Cohen's κ against a 0.6 target | Done |
| L6 | A fine-tuned classifier is trained and evaluated against baselines | `train/finetune.py`, `train/evaluate.py` | **Blocked** — zero rows human-labelled |

L6 blocks the project's deep-neural-network deliverable. It is the single
highest-value outstanding task.

---

## 5. Requirement traceability

### Course rubric

| Requirement | Satisfied by | Code | Status |
|---|---|---|---|
| Conversational user interface | Tool-calling chatbot with RAG evidence retrieval, on CLI, dashboard tab and API | `chatbot/` | Done |
| At least two text mining tasks | (1) Unsupervised aspect discovery, (2) supervised aspect-sentiment classification, (3) rule-based bank entity attribution | `aspects/discover.py`, `sentiment/score.py`, `preprocess/pipeline.py` | Done for 1 and 3; 2 is zero-shot, not yet supervised |
| A sentiment mining component | Overall and aspect-based sentiment index across four sources | `sentiment/`, `aggregate/` | Done |
| At least one deep neural network task | Fine-tuned FinBERT aspect-sentiment classifier | `train/finetune.py` | **Blocked on labelling** |

The DNN requirement is the one at risk. Base FinBERT is a deep neural network
and is used throughout, but the *self-built or fine-tuned* element the rubric
asks for does not exist until the labelled data does.

### Proposal commitments

| Commitment | Reality | Status |
|---|---|---|
| Four data streams | All four exist; earnings and Reddit carry the corpus, consensus is aggregates not text, news is marginal | Partial |
| Aspects: dividend policy, asset quality, NIM, management guidance | Implemented as the frozen taxonomy, but not validated. Clustering the full corpus produces 281 finer clusters that cut across these four, and these four centroids are the least distinct of three candidates tested | **Open decision** |
| ~1,000 labelled examples, 200–300 per class | 998 candidates exported, 0 labelled. Two aspects cannot reach 200 per class from the current pool | Blocked |
| Accuracy, precision, recall, F1 per class, macro-F1 on a held-out split | Implemented in `train/evaluate.py` against base FinBERT, a lexicon baseline and a classical ML baseline | Blocked on labelling |
| Dashboard with overall and aspect sentiment, batch refreshed | Done, five tabs | Done |
| Chatbot answering with supporting evidence | Done, with the grounding caveats in 4.3 | Partial |

---

## 6. Known limitations

Summarised from [STATUS.md](../STATUS.md), which is the authority.

1. **No fine-tuned model exists.** All sentiment is base FinBERT, zero-shot.
2. **Aspect assignment is not validated.** Reddit sentences are assigned to
   `net_interest_margin` although the Reddit corpus contains zero occurrences
   of the phrase.
3. **Local models fabricate citations**, and the check detects rather than
   prevents.
4. **Advice-declining fails more often than it works.**
5. **Blended cross-bank figures track earnings coverage.** DBS carries roughly
   six times the earnings volume of the other two banks.
6. **Relevance filtering is weak.** Sentences mentioning a bank incidentally
   still enter the corpus. Roughly 2.6% of sentences are extraction artifacts.
7. **GPT and Gemini backends are unverified.**

---

## 7. Glossary

| term | meaning |
|---|---|
| **Aspect** | A financial topic a sentence is about. Currently one of `dividend_policy`, `asset_quality`, `net_interest_margin`, `management_guidance`, or `other`. |
| **Sentence** | The unit of analysis. Everything downstream keys off `sentence_id`. A document is split into sentences before anything is scored. |
| **Sentiment index** | The aggregated score per (bank, aspect, window, source), in the range −1 to +1. |
| **Volume floor** | The minimum number of observations, 5, below which the system reports insufficient data instead of a score. |
| **Shrinkage** | Pulling a score toward neutral at low volume, `score × n/(n+5)`, so a handful of observations cannot produce an extreme number. |
| **Blended vs per-source** | A blended row combines every source; per-source rows sit alongside it so the composition of a blended figure is visible. |
| **Verification warning** | The flag attached to a chatbot answer that cites evidence when `search_evidence` was never called, meaning the citation is fabricated by definition. |
| **Frozen centroid** | Aspect assignment matches sentences against centroids fixed in `config/aspects.yaml`, rather than re-clustering each batch, so categories do not shift under a user between runs. |
| **`train_dev` vs `test`** | `train_dev` is model-assisted stratified sampling that oversamples non-neutral candidates. `test` is drawn purely at random before any model screening, and frozen. |
