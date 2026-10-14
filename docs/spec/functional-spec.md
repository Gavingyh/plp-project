# Functional Specification

What the system does, for whom, and how you would tell whether it works.

This is the document a teammate joining now still lacks. The others cover
adjacent ground and are not repeated here: [DESIGN.md](../DESIGN.md) explains
*why* each choice was made, [RUNBOOK.md](../RUNBOOK.md) how to run things, and
[STATUS.md](../STATUS.md) what is and is not finished. Where this document
states a limitation, STATUS is the authority and this is a summary.

Current as of 2026-10-14 for the sentiment model, the aspects, the index and
the corpus figures, which describe the database of that date (collection
stopped on 2026-09-26, with two later additions); the other sections were
last checked against the code on 2026-10-04. Requirements marked **Planned**
were decided on 2026-09-26 and are sequenced in [PLAN.md](../PLAN.md).

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
| **Retail reader** | A quick read on sentiment per bank and aspect, with the evidence behind it and an honest signal when data is thin | the Streamlit dashboard (`dashboard/`, a teammate's), chatbot |
| **Dashboard builder or API consumer** | Every number, its evidence and the chat, as JSON | FastAPI REST API ([api-integration.md](../api-integration.md)) |
| **Teammate, marker** | To reproduce every number, see what is unfinished, and judge what the numbers support | Docs, evidence files, verification ledger, test suite |

The third user is not an afterthought. This is a graded practice module whose
deliverables include a report, a demo video and source code, so
reproducibility is a functional requirement rather than an engineering
nicety.

---

## 2. Scope and non-goals

**In scope.** Batch ingestion of public text about the three banks;
sentence-level aspect assignment and sentiment scoring; a per-bank, per-aspect
index with time windows and a continuous series; a REST API and a grounded
chatbot; a Streamlit dashboard maintained by a teammate; a labelling workflow for the fine-tuning dataset.

**Explicit non-goals**, each a deliberate decision rather than an omission:

| non-goal | why |
|---|---|
| Investment advice | The chatbot must decline buy/sell framing. The system reports sentiment, not recommendations. |
| Real-time streaming | The proposal specifies scheduled batches. Sources are polled on demand; the daily job is not running, and the corpus is frozen at 26 Sep 2026 for analysis. |
| Voice input or output | The chatbot is text-only. The speech content of the Conversational UIs module is out of scope. |
| Full analyst report text | Brokerage IP behind entitlements. Yahoo Finance consensus *aggregates* are the substitute, disclosed as such. |
| Price prediction or backtesting | No claim is made that sentiment predicts returns. Price data is reference only. |
| Beating a WAF | UOB's IR site signals refusal to scripted clients; the Wayback Machine is used instead of fingerprint spoofing. |
| Multi-user accounts, auth, deployment | Single-user local tool for a practice module. The API has no authentication and must not be exposed publicly. |

---

## 3. Data sources

| source | provides | cadence | key | caveats |
|---|---|---|---|---|
| **Reddit** via Arctic Shift | `r/singaporefi` posts and comments, 2020 to Sep 2026. 22,630 documents, 25,533 sentences | Incremental 7-day pull; resumable multi-year backfill | none | Reddit declined the API application, so PRAW is unavailable. Keyword search times out, so whole subreddits are harvested by date window and filtered locally. `r/singapore` and `r/investing` returned zero bank-mentioning items and were dropped. |
| **Earnings PDFs** | Results releases, CEO presentations, and DBS analyst-call transcripts. 178 documents, 12,254 sentences | Manual, quarterly | none | DBS and OCBC fetched directly from IR sites; UOB via the Wayback Machine because its site is WAF-blocked. Archive coverage thins for recent quarters. Tables are not extracted, only prose. |
| **Google News RSS** | Headlines with publisher and date, found by date-windowed searches, Jan 2023 to Sep 2026. 5,685 documents, 5,447 sentences | Backfill by month; safe to re-run | none | No official API; results are Google's ranking, not a census, and favour recent articles, so monthly volume rises towards the present. Headlines only; stored links are Google redirects. Filtered and deduplicated as described in [news-data.md](../news-data.md). |
| **Yahoo Finance news** | Headline and summary for SGX and ADR tickers. 114 documents, 344 sentences | On demand | none | Unofficial endpoint (`yfinance`); no date parameter and no paging, so no history beyond about 12 months, and three daily runs added nothing new. |
| **Yahoo Finance consensus** | Analyst counts, rating distribution, mean and median price targets | On demand, safe to re-run | none | **Unofficial API.** No published terms bless it; it needs a cookie and crumb handshake. Provides aggregates, not analyst reasoning. Must not be described as "analyst reports". |
| **CNA** | Full article text, found through the Wayback Machine's index of CNA URLs that name a bank. 207 documents, 1,599 sentences, Jan 2023 to Sep 2026 | Backfill; re-runs fetch only what isn't cached | none | Covers only what the archive captured, 0 to 13 articles a month. Fetched at CNA's robots.txt crawl delay; the text is kept out of git (DESIGN decision 20) |
| **Broker research** | Analysts' reports on the three banks, read from PDFs. 25 documents, 641 sentences | Manual | none | Third-party text, kept within the team like CNA's. A few sentences are report disclaimers; the chatbot's evidence search skips them. |
| **NewsAPI** | Article title and description. 13 documents, 26 sentences | On demand | `NEWSAPI_KEY` | Free tier gives roughly one month of lookback and truncates body text, so usable text is title plus description. 12 of the original 20 rows named no bank and were removed on 2026-09-24. |
| **Alpha Vantage** | Nothing | — | `ALPHAVANTAGE_KEY` | Does not index SGX-listed tickers at all, confirmed live across three ticker formats for all three banks. Adapter retained in case coverage is added. |

The proposal committed to four streams. All four exist. Reddit carries most
of the text, earnings and news are substantial, and consensus is structured
data rather than text. A fifth, CNA, adds full-text news articles
(DESIGN decision 20).

---

## 4. Functional requirements

Each requirement has acceptance criteria that can be checked against the code,
a test, or a running instance. Status values: **Done**, **Partial**,
**Blocked**, and **Planned** (decided, not yet built).

### 4.1 Dashboard

*Changed 2026-10-01 (DESIGN decision 23, amended the same night).* A
teammate maintains the Streamlit dashboard in `dashboard/`, redesigned on
1 Oct; it reads the database directly. Every requirement also has API
support, so a view can move onto the API. The UI column below was not
re-checked after the redesign.

| Requirement | API support here | Status |
|---|---|---|
| As a retail reader, I see an overall sentiment score per bank so I can compare the three at a glance | `GET /sentiment?bank=` returns a score with its sample size `n`; no score without `n` | API done; UI not re-checked |
| I see sentiment broken down by aspect so I can drill into what drives the headline | `GET /sentiment/index` returns the whole bank × aspect grid in one call | API done; UI not re-checked |
| I see how sentiment moved over time, not just a snapshot | `GET /sentiment/series` with a week/month/quarter bucket; thin buckets come back `sufficient: false`, never interpolated | API done; UI not re-checked |
| I can read the actual sentences behind a score | `GET /evidence/latest` and `GET /evidence` return sentences with `sentence_id`, source URL and date | API done; UI not re-checked |
| I can ask questions in natural language | `POST /chat` runs the same agent as the terminal chat and returns the verification flags; `GET /suggestions` gives starter questions | API done; UI not re-checked |
| I am told when the data cannot support a number | results below the volume floor carry `insufficient_data` | API done; UI not re-checked |
| I can see which sources produced a blended figure | `GET /sentiment/index?source=*` and `GET /sources` | API done; UI not re-checked |

### 4.2 REST API

Sixteen endpoints in `api/main.py`. No authentication; localhost only; CORS
open so a browser dashboard on any port can call it. The integration guide is
[api-integration.md](../api-integration.md), and `docs/api/openapi.json` is the
machine-readable contract (a test keeps it current).

| Requirement | Acceptance criteria | Status |
|---|---|---|
| A dashboard can fetch every number it shows | `/sentiment`, `/sentiment/compare`, `/sentiment/index`, `/sentiment/trend`, `/sentiment/series` return JSON matching the stored index | Done |
| Invalid input is rejected, not guessed at | `bank` is validated against `^(DBS\|OCBC\|UOB)$`, `window` against `^(7d\|30d\|all_time)$`, `bucket` against `^(week\|month\|quarter)$`; bad values give HTTP 422 on every endpoint that takes them, as does an unknown `aspect` (4 Oct; readable names like "dividend policy" are accepted) | Done, covered in `tests/test_api.py` and `tests/test_validate_api.py` (3 Oct: `/coverage` and `/evidence` now check `bank` too) |
| A chat UI can offer questions the data can actually answer | `/suggestions?limit=N` returns questions generated from the index, never hardcoded, excluding advice-seeking and out-of-scope framings | Done |
| A caller can distinguish "no data" from "neutral sentiment" | `/coverage` reports `has_data`; thin results carry `insufficient_data`, including each `/sentiment/index` row (3 Oct) | Done |
| A caller can retrieve evidence with provenance | `/evidence` returns `sentence_id`, `url`, `published_at` per hit | Done |
| A caller can reach the chatbot | `POST /chat` accepts a message, an optional backend and the earlier turns (`history`); an unknown backend or role is a 422, a failing backend a 503 | Done |
| Service health is checkable | `GET /health` returns `{"status": "ok"}` | Done |

### 4.3 Chatbot

| Requirement | Acceptance criteria | Status |
|---|---|---|
| Answers questions about sentiment by querying the store, not from model memory | Six tools: `get_sentiment`, `compare_banks`, `get_trend`, `get_coverage`, `search_evidence`, `get_analyst_consensus` | Done |
| Never states a number it did not retrieve | Enforced in code by the volume floor, and by prompt rule 1; every figure is checked against the tools' results (the number check below) | **Partial** — invented figures are detected and flagged, not prevented; on the gold set of 6 Oct with the 8B, 0 of 32 answers carried a figure no tool returned (one run; earlier runs had 1 to 4 of 32, and a dashboard answer the same day was flagged for one); some numbers are skipped by design (years, durations, numbers under 10: Known limits) |
| Never cites evidence it did not retrieve | If `search_evidence` was not called, any quoted evidence, `sentence_id` or URL is fabricated by definition and the answer is flagged | **Done within known limits** (6 Oct): in strip mode, the default, every passage of three or more words shown in quote marks is text a search returned (or the tools' own wording, such as a reading or a topic name), and a citation stays only where its sentence's quoted words were returned (DESIGN decision 26); on the gold set of 6 Oct with the 8B, 0 of 32 answers were flagged for fabricated citations. What is left is listed under Known limits in [evidence/chatbot-answers-2026-10-04.md](../evidence/chatbot-answers-2026-10-04.md) |
| Declines investment advice | Advice-seeking questions are declined with a not-financial-advice statement | Done through the advice guard below — prompt-only was 2–3 of 7 on every model tested |
| Says so plainly when data is thin | Tools return `insufficient_data` below 5 observations | Done |
| Runs without any API key | Ollama backend auto-selected when no key is present | Done |
| Works with hosted models too | Claude, OpenAI and Gemini backends implemented | **Partial** — Gemini verified on 2026-09-30 ([evidence](../evidence/gemini-backend-2026-09-30.md)); the Claude backend has no recorded run, and GPT has never been run |
| Follows a conversation across turns | "What about OCBC?" after a DBS question answers about OCBC on the same aspect and window; recent turns and the current bank, aspect and window are passed to the model | Done — terminal chat and API (`history`); verified live in a three-turn conversation |
| Declines investment advice reliably | Advice-seeking is recognised before the model runs and answered with a fixed, reviewed reply; ≥ 6 of 7 advice gold-set questions declined | Done — 7 of 7 by the regex guard (26 Sep); since 4 Oct an intent classifier decides (DESIGN decision 24), to be re-measured with `chatbot/eval_intent.py` |
| Handles small talk, off-topic and service questions gracefully | Greetings, thanks, "what can you do?", banking-service requests, attempts to change the instructions, complaints and off-topic questions (also mid-conversation) get a fitting fixed reply that says what the assistant can do; real questions with off-topic-looking words still reach the model | **Built 2026-10-04**; measured by `chatbot/eval_intent.py` and `run_eval --set scope` |
| Every number in an answer matches a tool result | An output guard compares each figure with the tools' results and flags a mismatch, as the citation check does | Done — 18 of 19 flagged figures in the final run were invented; the one false alarm is fixed |
| Evaluated on a frozen, sliced gold set | About 30 questions with expected behaviour written before tuning; retrieval Hit@K and MRR; faithfulness via an LLM judge calibrated on human ratings; multi-turn scenarios; SASSI questionnaire with 5–8 users | **Partial** — gold set v2 (32 questions), four multi-turn conversations, retrieval MRR and an LLM judge since 1 Oct ([evidence](../evidence/chatbot-eval-build-2026-10-01.md)); the questions were also used during tuning, and the SASSI sessions are still to come |

Numbers and citations remain the honest weak points: the harness detects invented
figures and citations but the local models keep producing them (on gold set
v2, 15 of 32 answers on the 3B and 11 of 32 on the 8B). The last four (conversation, advice guard, number check, gold-set
evaluation) apply the Conversational UIs module and are DESIGN decision
19; results in [evidence/chatbot-harness-2026-09-26.md](../evidence/chatbot-harness-2026-09-26.md).

### 4.4 Labelling workflow

| Requirement | Acceptance criteria | Status |
|---|---|---|
| Export a stratified candidate set for annotation | `preprocess/export_candidates.py` writes the candidate set: re-drawn on 2026-09-27 to 1,277 rows, 978 `train_dev` and 299 `test` (the first draw had 997) | Done (see the last row) |
| The test split is drawn at random before any model screening, and frozen | `split=test` rows are randomly sampled independently of model output | Done |
| Annotators are not shown model opinions when labelling the test set | `preprocess/export_blind_test.py` writes a sheet carrying sentence, aspect and provenance only | Done |
| Pre-labelling reduces annotation to correction | `train/llm_prelabel.py` fills `llm_prelabel` and `llm_rationale`, never `label`; checkpointed and resumable | Done, all 1,277 rows |
| Agreement between annotators is measured before dividing the work | `train/agreement.py` reports Cohen's κ against a 0.6 target | Done |
| A fine-tuned classifier is trained and evaluated against baselines | `train/dapt.py`, `train/finetune.py`, `train/evaluate.py` | **Met, and in use** since 2026-10-12: FinBERT with its encoder pretrained further on the corpus, fine-tuned on 1,563 LLM-labelled pairs, three seeds averaged. On the 299 test rows, which carry people's labels: macro-F1 0.670 and accuracy 0.716 against base FinBERT's 0.571 and 0.699 (three seeds' mean macro-F1 0.649 ± 0.018); on the 100 broker research test rows 0.770 against 0.687. Precision and recall for each class, a lexicon and a TF-IDF baseline, and every other candidate are in the [evidence](../evidence/model-rerun-2026-10-11.md) and the [model card](../model-card.md). The first configuration, trained on people's labels, scored 0.604 ± 0.035 |
| Annotators choose the aspect and the sentiment for each sentence | Re-drawn candidate set across Reddit, earnings and news; ≥ 200 rows per sentiment class overall, ~80 per aspect; blind test sheet; κ reported for aspect and for sentiment | **Partly met** by the 2026-09-27 round: 1,277 rows (617 Reddit, 477 earnings, 183 news), 275 / 543 / 459 negative / neutral / positive, sentiment κ 0.93. Not met: five aspects below 80 rows, and aspect κ between people (only human–LLM, 0.80, DESIGN decision 22). Three later rounds (268 top-up, 150 active-learning and 380 broker research rows) and the rules of 10 Oct were labelled by an LLM rater; the training labels are its labels, and the test labels stay people's |

What the aspect-and-sentiment labelling still owes is human–human aspect agreement and more rows for the
five smallest aspects.

### 4.5 Text-mining tasks

| Task | Acceptance criteria | Status |
|---|---|---|
| Aspect discovery by clustering | FinBERT embeddings, UMAP, HDBSCAN over the full corpus; cluster count, noise share and correspondence to the aspects reported | Done on 36,884 sentences (2026-09-11, 281 clusters, 67% noise); swept over `min_cluster_size` on all 44,345 sentences on 2026-09-30 (10: 358 clusters, 65% noise; 100: 25 clusters, 52% noise; [evidence](../evidence/aspect-discovery-sweep-2026-09-30.md)) |
| Aspect categorisation | A local LLM assigns each sentence one of the ten aspects (DESIGN decision 21) or `other`; accuracy and macro-F1 against the human aspect labels, with seed-centroid assignment as baseline | **Done and applied**: every stored sentence has one aspect from `llama3.1:8b`, whose prompt carries the wealth rule of 10 Oct. Against people's aspect labels it is right 73.9% of the time (macro-F1 0.676), against seed-centroid's 41.3% (0.296); against the LLM rater's labels under the new rule, 79.4%, where the first wording scored 75.5% ([classifier](../evidence/llm-aspect-classifier-2026-10-01.md), [wording trial](../evidence/wealth-definition-trial-2026-10-12.md), [applied](../evidence/rescore-wealth-wording-2026-10-14.md)) |
| Bank entity recognition and resolution | Organisation mentions recognised and resolved to DBS, OCBC, UOB or not the bank; precision, recall and F1 on a ~200-sentence gold set against alias matching | **Evaluated, not applied**: against the LLM rater's answers on 201 sentences, taken as the reference in place of hand labels, NER names exactly the right banks for all 201 and alias matching for 161 (F1 0.89). The last NER rules were written from this sheet's errors, so this is not a held-out score. Stored sentences keep their alias-matching tags; the two methods differ on 258 of the 45,844 ([evidence](../evidence/bank-ner-2026-10-01.md), [validation](../evidence/report-figures-validation-2026-10-14.md)) |
| Sentiment classification (fine-tuned FinBERT) | As for the fine-tuned classifier (4.4): per-class P/R/F1 and macro-F1 on the frozen test split, mean ± sd over ≥ 3 seeds, against three baselines | **Done and applied**: 0.649 ± 0.018 over three seeds, 0.670 averaged, against base FinBERT's 0.571 (see 4.4); every stored sentence carries the averaged model's score beside base FinBERT's |

---

## 5. Requirement traceability

### Course rubric

| Requirement | Satisfied by | Code | Status |
|---|---|---|---|
| Conversational user interface | Tool-calling chatbot with RAG evidence retrieval, in the terminal chat and through the API (the dashboard's chat uses `POST /chat`) | `chatbot/` | Done |
| At least two text mining tasks | Four, per 4.5: aspect discovery, aspect categorisation, bank entity recognition, sentiment classification | `aspects/discover.py`, `aspects/llm_classify.py`, `preprocess/bank_ner.py`, `train/finetune.py` | Aspect discovery, aspect categorisation and sentiment classification done and applied; bank entity recognition evaluated, not applied |
| A sentiment mining component | Overall and aspect-based sentiment index across four sources | `sentiment/`, `aggregate/` | Done |
| At least one deep neural network task | Fine-tuned FinBERT aspect-sentiment classifier | `train/dapt.py`, `train/finetune.py` | **Met**: the encoder pretrained further on 42,822 corpus sentences, then fine-tuned on 1,563 labelled pairs, three seeds; tested on 299 and 100 held-out rows with people's labels; ahead of base FinBERT on macro-F1 and level with it on accuracy |

The DNN requirement is met by the model the product serves: FinBERT, its
encoder pretrained further on the project's corpus, fine-tuned on (sentence,
aspect) pairs and averaged over three seeds. On the 299 test rows it leads
base FinBERT on macro-F1 (0.670 against 0.571) because it finds far more of
the negative and positive sentences (recall 0.59 and 0.73 against 0.21 and
0.53), at a cost in neutral recall (0.73 against 0.91). On accuracy the two
are level: 0.716 against 0.699, with the model right on 41 rows base FinBERT
gets wrong and wrong on 36 it gets right. Its training labels are an LLM's
and its test labels people's, made under an older rule for retail products;
the report has to explain all three points
([evidence](../evidence/model-rerun-2026-10-11.md)).

### Proposal commitments

| Commitment | Reality | Status |
|---|---|---|
| Four data streams | All four exist. News now spans every month from Jan 2023 (5,812 articles); consensus is aggregates, not text | Done |
| Aspects: dividend policy, asset quality, NIM, management guidance | Kept within ten aspects derived from the corpus (DESIGN decision 21). Seed-centroid assignment failed validation; LLM assignment, one aspect per sentence, replaced it in the stored corpus (right 73.9% of the time against 41.3%) | Done |
| ~1,000 labelled examples, 200–300 per class | 1,277 labelled on 2026-09-27: 275 negative, 543 neutral, 459 positive (the target read as per sentiment class overall) | Done |
| Accuracy, precision, recall, F1 per class, macro-F1 on a held-out split | `train/evaluate.py` on the 299-row random test split, against base FinBERT, a lexicon baseline and a classical ML baseline | Done |
| Dashboard with overall and aspect sentiment, batch refreshed | The Streamlit dashboard (`dashboard/`, a teammate's); the API also serves every view (DESIGN decision 23) | API done; UI not re-checked |
| Chatbot answering with supporting evidence | Done, with the grounding caveats in 4.3 | Partial |

---

## 6. Known limitations

Summarised from [STATUS.md](../STATUS.md), which is the authority.

1. **The served model is right on about seven sentences in ten.** It leads
   base FinBERT on macro-F1 (0.670 against 0.571) and is level on accuracy.
   About half of what it calls negative, people did not (precision 0.48).
   Its training labels are an LLM's; its test labels are people's, made
   under an older rule for retail products, so part of that error is the
   rule ([evidence](../evidence/model-rerun-2026-10-11.md)).
2. **Per-aspect figures rest on small counts, and the aspect reaches the
   sentiment.** Each sentence has one aspect, right 74% of the time against
   people's labels; some bank and aspect cells hold under 100 sentences. The
   served model reads the aspect's name with the sentence, so re-filing a
   sentence can change its label: the second re-score moved 6,914 sentences
   and each bank's headline by 0.010 to 0.015
   ([evidence](../evidence/rescore-wealth-wording-2026-10-14.md)).
3. **The chatbot's checks read quotes and figures, not its wording.** A
   quote no search returned is removed and a figure no tool returned is
   marked (`CHATBOT_ENFORCE_EVIDENCE=strip`, the default); before those
   checks 11 of 32 answers on `llama3.1:8b` cited evidence that was never
   retrieved, and none does now. A wrong description passes: one gold-set
   question, asked about "the last 7 days", is answered with the all-time
   figure in every recent run
   ([evidence](../evidence/chatbot-eval-rescored-2026-10-14.md)).
4. **Bank attribution is by alias matching.** The entity recogniser is
   evaluated but not applied to the stored sentences, so a sentence naming
   only UOB Kay Hian still counts for UOB (258 sentences would change).
5. **Blended cross-bank figures track earnings coverage.** DBS carries roughly
   six times the earnings volume of the other two banks.
6. **Relevance filtering is weak.** Sentences mentioning a bank incidentally
   still enter the corpus. Roughly 2.6% of sentences are extraction artifacts.
7. **The GPT backend is unverified** (Gemini was verified on 2026-09-30).
8. **News volume over time is a sampling artefact.** Google News favours
   recent articles; compare periods only after normalising per month.

---

## 7. Glossary

| term | meaning |
|---|---|
| **Aspect** | A financial topic a sentence is about: one of ten derived from the corpus (DESIGN decision 21; keys in `config/aspects.yaml`, readable labels from `GET /aspects`), or `other`. |
| **Sentence** | The unit of analysis. Everything downstream keys off `sentence_id`. A document is split into sentences before anything is scored. |
| **Sentiment index** | The aggregated score per (bank, aspect, window, source), in the range −1 to +1. |
| **Volume floor** | The minimum number of observations, 5, below which the system reports insufficient data instead of a score. |
| **Shrinkage** | Pulling a score toward neutral at low volume, `score × n/(n+5)`, so a handful of observations cannot produce an extreme number. |
| **Blended vs per-source** | A blended row combines every source; per-source rows sit alongside it so the composition of a blended figure is visible. |
| **Verification warning** | The flag attached to a chatbot answer that cites evidence when `search_evidence` was never called, meaning the citation is fabricated by definition. |
| **Frozen centroid** | The first aspect method: sentences matched against centroids fixed in `config/aspects.yaml`, rather than re-clustered each batch, so categories do not shift under a user between runs. Replaced in the stored corpus by one aspect a sentence from a local LLM, whose definitions and examples are fixed in the same file for the same reason. |
| **`train_dev` vs `test`** | `train_dev` is model-assisted stratified sampling that oversamples non-neutral candidates. `test` is drawn purely at random before any model screening, and frozen. |
