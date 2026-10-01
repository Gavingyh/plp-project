# Technical Specification

The contracts between the parts of the system: data model, module boundaries,
API shapes, configuration, and how it is tested.

Reasoning lives in [DESIGN.md](../DESIGN.md) and is referenced rather than
repeated. Commands live in [RUNBOOK.md](../RUNBOOK.md). Current state and
caveats live in [STATUS.md](../STATUS.md).

Verified against the code and database on 2026-09-11; the module map,
operations and open decisions were updated on 2026-09-26. Planned components
are marked as such and sequenced in [PLAN.md](../PLAN.md).

---

## 1. Architecture

The pipeline diagram is in [DESIGN.md](../DESIGN.md#what-the-system-does).
Rather than redraw it, here is one sentence's journey through the system, with
`sentence_id` as the thread that ties it together. Twenty more diagrams, each
traced to the code, are in [docs/diagrams](../diagrams/README.md).

A DBS analyst-call transcript PDF is downloaded to
`data/earnings_pdfs/DBS/`. `ingest.earnings_extract` extracts prose lines from it,
skipping table rows and headers, and writes one `documents` row with a
`doc_id` hashed deterministically from source plus native identifier, so
re-running inserts nothing new. `preprocess.pipeline` picks up that document
because its `doc_id` does not yet appear in `sentences`, cleans it with the
earnings-specific cleaner, and segments it with spaCy plus financial
abbreviation exceptions so "S$1.2b" and "Q3 FY25" do not split. One resulting
sentence, "Net interest margin declined 4 basis points to 2.11%", is attributed
to DBS, hashed for near-duplicate detection, and stored with a
`sentence_id`.

`aspects.assign` embeds it with FinBERT, mean-pooled over tokens, and compares
it to each frozen centroid from `config/aspects.yaml`. It clears the 0.65
similarity floor for `net_interest_margin`, giving a `sentence_aspects` row.
`sentiment.score` classifies the (sentence, aspect) pair with base FinBERT and
writes `aspect_sentiment` with a label, a confidence, and a `model_version`.
`aggregate.index` folds it into `sentiment_index` rows for DBS with weighting
and shrinkage. When a user later asks the chatbot about DBS margins,
`search_evidence` retrieves it by cosine similarity over the cached embedding,
and the answer cites it by that same `sentence_id` and the transcript's URL.

The invariant: **the sentence is the unit of analysis**, and every downstream
artifact keys off `sentence_id`. Document-level sentiment would defeat the
aspect-based premise, because one Reddit comment can praise a dividend and
criticise an app in consecutive sentences.

---

## 2. Module map

| module | responsibility | entry points |
|---|---|---|
| `ingest/` | Source adapters, DB schema and connection, retry helper, bank detection, news relevance filter and cross-source dedup | `arctic_shift`, `google_news`, `yahoo_news`, `newsapi`, `yahoo_analyst`, `analyst_tag`, `alphavantage`, `news_filter`, `cna_scraper` (RSS to a JSON file), `cna_archive` (CNA backfill into the database), plus the three-stage earnings group: `earnings_fetch_ir`, `earnings_fetch_uob`, `earnings_extract` |
| repository root | Batch entry points | `run_news_pull.py` (every news source, then a source × bank × month table; `--audit` re-checks stored news), `run_daily_batch.py` (news, Reddit, consensus) |
| `preprocess/` | Documents to sentences; labelling exports | `pipeline`, `export_candidates`, `export_blind_test` |
| `aspects/` | FinBERT embeddings, embedding cache, taxonomy discovery, assignment, taxonomy comparison | `assign`, `discover`, `compare_taxonomies`, `embed_store` |
| `sentiment/` | Aspect-conditioned sentiment classification | `score` |
| `aggregate/` | The sentiment index and continuous time series | `index` |
| `chatbot/` | Tool-calling agent, tools, RAG retrieval, prompts, backends, evaluation | `agent`, `run_eval` |
| `train/` | Fine-tuning, evaluation, pre-labelling, annotator agreement | `finetune`, `evaluate`, `llm_prelabel`, `agreement` |
| `api/` | FastAPI REST layer | `uvicorn api.main:app` |
| `dashboard/` | Streamlit UI | `streamlit run dashboard/app.py` |
| `config/` | Aspect taxonomy, logging configuration | — |
| `scripts/` | Service lifecycle, overnight backfill, model comparison, scheduling template | `start.sh`, `stop.sh`, `status.sh`, `overnight_backfill.py`, `compare_chatbot_models.sh`, `com.plp.dailybatch.plist` (launchd job, not installed anywhere) |

Planned (DESIGN decisions 16–18, not yet in the code): an LLM aspect
classifier replacing `aspects/assign.py`'s seed-centroid matching, a bank
entity recognition step, and aspect + sentiment labelling support in
`preprocess/` and `train/agreement.py`. Decision 19's chatbot harness is
built: `chatbot/guards.py` (advice, off-topic, figure and sentence-id checks)
and `Conversation` / `answer_turn` in `chatbot/agent.py` (memory, state,
per-turn record); `/chat` accepts earlier turns as `history`.

Run every module as `.venv-plp/bin/python3 -m <module>`. Never plain
`python3`; see RUNBOOK for why.

---

## 3. Data model

One SQLite file, `data/plp.db`, 83 MB. Six tables. WAL journal mode.

### `documents`
One row per ingested item, before segmentation.

| column | type | meaning |
|---|---|---|
| `doc_id` | TEXT PK | Deterministic hash of source plus native ID. Makes ingestion idempotent. |
| `source` | TEXT | `arctic_shift` \| `earnings` \| `google_news` \| `yahoo_news` \| `newsapi` \| `cna` \| `alphavantage` |
| `source_detail` | TEXT | Publication name, subreddit, or document type |
| `bank` | TEXT | `DBS` \| `OCBC` \| `UOB` \| `MULTI` |
| `doc_type` | TEXT | `article` \| `submission` \| `comment` \| `earnings_release` |
| `title`, `body` | TEXT | `body` is NOT NULL |
| `published_at` | TEXT | ISO 8601 UTC |
| `url` | TEXT | Provenance, surfaced in every citation |
| `ingested_at` | TEXT | Batch provenance |
| `raw` | TEXT | Original payload as JSON, for auditability |
| `has_analyst_view` | INTEGER | Set by `analyst_tag`; currently 0 for every row |

### `sentences`
The unit of analysis.

| column | type | meaning |
|---|---|---|
| `sentence_id` | TEXT PK | Referenced by every downstream table and every citation |
| `doc_id` | TEXT FK | Parent document |
| `bank` | TEXT | Resolved *per sentence*, may differ from the document's bank |
| `text` | TEXT | Cleaned sentence |
| `char_start`, `char_end` | INTEGER | Offsets into the source body |
| `published_at`, `source`, `url` | TEXT | Denormalised from the document for query speed |
| `norm_hash` | TEXT | Normalised-text hash used for near-duplicate removal |
| `processed_at` | TEXT | When preprocessing wrote it |

### `sentence_aspects`
Which aspects a sentence cleared the similarity floor for. A sentence may
appear more than once: "NIM held up but provisions rose" is genuinely two
aspects.

`(sentence_id, aspect)` primary key, plus `similarity` and `assigned_at`.

### `aspect_sentiment`
One classification per (sentence, aspect, model version).

`(sentence_id, aspect, model_version)` primary key, plus `label`
(`positive` \| `neutral` \| `negative`), `confidence`, `scored_at`. The
`model_version` in the key is what will let a fine-tuned model's scores
coexist with the current `finbert-base-zeroshot-v1` rather than overwrite
them.

### `sentiment_index`
The aggregate the dashboard, API and chatbot read.

`(bank, aspect, window, source, model_version)` primary key, plus `score`,
`n`, `pos_n`, `neu_n`, `neg_n`, `confidence_mean`, `computed_at`.

- `aspect` is `'ALL'` for the overall per-bank row.
- `window` is `'7d'`, `'30d'` or `'all_time'`.
- `source` is `'ALL'` for the blended row, otherwise a single source. This
  dimension exists so a blended figure is never opaque.
- `score` is shrunk and weighted, in −1 to +1.
- `n` is always stored and always displayed. A sentiment number without its
  sample size is the main way this dashboard could mislead someone.

### `analyst_consensus`
Standalone; not part of the sentence pipeline. `(bank, as_of_date)` primary
key, one snapshot per bank per day, carrying analyst counts, the rating
distribution, `recommendation_mean` on Yahoo's 1.0 (strong buy) to 5.0 (strong
sell) scale, and price target statistics.

### Invariants to know before changing anything

- **Idempotency.** `doc_id` is deterministic and inserts use
  `INSERT OR IGNORE`. Re-running any adapter is a no-op.
- **Deduplication** is by `norm_hash` on the normalised sentence text, which
  catches syndicated wire copy republished across outlets.
- **Window filtering compares `published_at` strings** against an ISO cutoff
  string rather than parsed datetimes. Correct at day granularity given every
  source is UTC, but it relies on comparing digits before any `Z` versus
  `+00:00` suffix difference. Switch to parsed datetimes before adding
  sub-day windows. Documented in `aggregate/index.py`.
- **SQLite binds at most 32,766 parameters.** Never build `IN (?,?,...)` over
  a per-row list; this crashed `aspects/discover.py` once the corpus passed
  that size.

---

## 4. Pipeline contracts

Steps are order-dependent. Each consumes the previous step's output and
processes only new work.

| step | reads | writes | "new work" means | typical time |
|---|---|---|---|---|
| `run_daily_batch.py` | external APIs | `documents` | `doc_id` not already present | 2–5 min (network) |
| `preprocess.pipeline` | `documents` | `sentences` | `doc_id` not represented in `sentences` | seconds to 2 min |
| `aspects.assign` | `sentences` | `sentence_aspects` (+ embedding cache) | sentence not yet assigned | 10–20 min per ~10k sentences |
| `sentiment.score` | `sentence_aspects` | `aspect_sentiment` | pair not scored at this `model_version` | 20–30 min per ~18k pairs |
| `aggregate.index` | `aspect_sentiment`, `sentences` | `sentiment_index` | full recompute | ~2 s |

Timings are from RUNBOOK, measured on an M-series Mac with MPS. They were not
re-measured during the 2026-09-11 documentation pass.

Every step after ingestion needs `HF_HUB_OFFLINE=1`, or HuggingFace's
rate-limited metadata check can stall with near-zero CPU and look like a hang.

Embeddings are cached in `data/sentence_embeddings.npz` (101 MB) and reused by
assignment, discovery, taxonomy comparison and chatbot retrieval.

---

## 5. Models and libraries

| what | version | used for |
|---|---|---|
| `ProsusAI/finbert` | — | Sentence embeddings (mean-pooled over tokens, not CLS) and zero-shot sentiment classification |
| spaCy `en_core_web_sm` | spaCy ≥3.8 | Sentence segmentation with financial abbreviation exceptions |
| torch | ≥2.9 | Model runtime; MPS on Apple silicon |
| transformers | ≥5.0 | FinBERT loading |
| scikit-learn | ≥1.7 | TF-IDF for cluster labelling, Cohen's κ, classical baseline, metrics |
| umap-learn | ≥0.5 | Dimensionality reduction before clustering |
| hdbscan | ≥0.8 | Density clustering for taxonomy discovery |
| streamlit | 1.63.0 | Dashboard; health at `/_stcore/health` |
| fastapi + uvicorn | ≥0.115 / ≥0.30 | REST API |
| pdfplumber | ≥0.11 | Earnings PDF prose extraction |
| vaderSentiment | ≥3.3.2 | Lexicon baseline for evaluation |
| anthropic | ≥0.40 | Claude backend |
| pytest, httpx | ≥8.0 / ≥0.27 | Tests; `httpx` is required by `TestClient` |

**Mean pooling, not CLS**, is deliberate: BERT-family CLS vectors without a
sentence-level training objective are poor similarity representations.

Local models available through Ollama:

| model | size | notes |
|---|---|---|
| `llama3.2:3b` | 2.0 GB | Current default. Fast; fabricates citations at 43–48% |
| `llama3.1:8b` | 4.9 GB | Fabricates at 13%; slower. The better default where it fits |
| `phi4-mini` | 2.5 GB | Called a tool 0 of 16 times; fabricated in 83% of answers |
| `gemma3:4b` | 3.3 GB | No Ollama tool-calling support; all 23 questions error |
| `qwen3:4b` | 2.5 GB | Emits a hidden reasoning chain first; roughly 7x slower per call |

---

## 6. Configuration

### `.env`

| variable | default | read by |
|---|---|---|
| `NEWSAPI_KEY` | — | `ingest/newsapi.py` |
| `ALPHAVANTAGE_KEY` | — | `ingest/alphavantage.py` (contributes nothing) |
| `REDDIT_CLIENT_ID` / `_SECRET` / `_USER_AGENT` | — | Unused; Arctic Shift needs no key |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | — | Backend auto-detection, preferring Claude, then OpenAI, then Gemini |
| `CHATBOT_BACKEND` | auto | Forces `ollama` \| `claude` \| `openai` \| `gemini` |
| `CLAUDE_MODEL` / `OPENAI_MODEL` / `GEMINI_MODEL` / `OLLAMA_MODEL` | per backend | Model override (`GEMINI_CHAT_MODEL` is also read for Gemini; default `gemini-3.8-flash`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama backend and the service scripts |
| `LOG_LEVEL` | `INFO` | Console verbosity |
| `DEBUG` | `false` | DEBUG level plus un-silencing third-party libraries |
| `LOG_FILE` | `data/logs/plp.log` | `none` disables file logging |
| `PLP_DASHBOARD_PORT` / `PLP_API_PORT` | 8501 / 8000 | `scripts/start.sh`, `stop.sh`, `status.sh` |

`.env.example` is tracked, so every value in it must be a placeholder. Real
keys were committed there from the first commit until 2026-09-11 and must be
treated as compromised.

### `config/aspects.yaml`

Ten aspects plus `other` (DESIGN decision 21), each with a `label` and
`seed_terms`: full sentences taken from the aspect's clusters, whose mean
embedding is the centroid. `similarity_floor: 0.65` was calibrated for the
earlier four-aspect taxonomy and not re-tuned; at this floor a sentence
matches 6.4 aspects on average. The chatbot's tool schemas read the aspect
list from this file, so changing it changes what the chatbot can ask for;
re-run `aspects.assign` (after clearing `sentence_aspects`) and
`sentiment.score` afterwards.

### Tuning constants

| constant | value | where | meaning |
|---|---|---|---|
| `SHRINKAGE_K` | 5 | `aggregate/index.py` | `score × n/(n+k)` |
| `MIN_VOLUME_FOR_SCORE` | 5 | `chatbot/tools.py` | Below this, report insufficient data |
| `_SOURCE_WEIGHT` | earnings 1.0, arctic_shift 1.0; news sources 1.5 (google_news, yahoo_news, newsapi, cna, alphavantage) | `aggregate/index.py` | Earnings was 3.0 until it became the second-largest and most positively skewed source |
| `_LEXICAL_WEIGHT` | 0.15 | `chatbot/retrieval.py` | Keyword-overlap boost over cosine similarity |
| `similarity_floor` | 0.65 | `config/aspects.yaml` | Below it, a sentence falls to `other` |

---

## 7. API contract

Base `http://localhost:8000`. No authentication; do not expose publicly. CORS
is open for local frontend development.

| method | path | parameters | returns |
|---|---|---|---|
| GET | `/health` | — | `{"status": "ok"}` |
| GET | `/banks` | — | Supported bank codes |
| GET | `/sentiment` | `bank*`, `aspect`, `window` | Score, `n`, class counts |
| GET | `/sentiment/compare` | `aspect`, `window` | All three banks side by side |
| GET | `/sentiment/trend` | `bank*`, `aspect` | Direction, 7d vs 30d delta, up to 12 monthly points |
| GET | `/sentiment/index` | `window`, `source` | Full index rows |
| GET | `/sentiment/series` | `bank*`, `aspect`, `bucket`, `source`, `min_n` | Continuous series; each point carries `sufficient` |
| GET | `/sources` | — | Sources present, for per-source breakdowns |
| GET | `/coverage` | `bank`, `aspect` | `has_data`, so callers can tell absence from neutrality |
| GET | `/evidence` | `query*`, `bank`, `aspect`, `sentiment`, `k` | Sentences with `sentence_id`, `url`, `published_at` |
| GET | `/analyst-consensus` | `bank*` | Latest Yahoo snapshot, with its unofficial-API caveat |
| GET | `/suggestions` | `limit` (1–20) | Starter questions generated from the index |
| POST | `/chat` | `{message, backend?}` | Chatbot answer |

`*` marks required. Validation is by regex on the query parameter, so a bad
`bank`, `window` or `bucket` returns **HTTP 422** from FastAPI before the
handler runs — verified against a live instance on 2026-09-11. The handler's
own `ValueError` to 400 path on `/sentiment/series` is therefore unreachable
through the API, since the regex admits only the three valid buckets; it still
guards `compute_time_series` when called directly from Python. Covered by
`tests/test_api.py`.

### Chatbot tools

Schemas in `chatbot/tools.py`, expressed in Anthropic's native shape; each
backend converts them to what it needs.

| tool | arguments | purpose |
|---|---|---|
| `get_sentiment` | `bank*`, `aspect` | The number, or `insufficient_data` |
| `compare_banks` | `aspect` | All three banks |
| `get_trend` | `bank*`, `aspect` | Direction plus a capped monthly series |
| `get_coverage` | `bank`, `aspect` | Distinguishes no data from neutral |
| `search_evidence` | `query*`, `bank`, `aspect`, `sentiment`, `k` | Retrieval; calling this is what makes a citation legitimate |
| `get_analyst_consensus` | `bank*` | Yahoo aggregates |

`aspect` arguments are validated against the real taxonomy, so a hallucinated
aspect name fails loudly instead of returning an empty result that reads like
"no sentiment".

---

## 8. Chatbot design

**A plain tool-calling loop, not a framework.** Roughly fifty lines. At this
scale a framework would add abstraction to explain in the report without
adding capability.

**Each backend owns its full loop.** Claude represents assistant turns as
content-block lists; Ollama and OpenAI use a flat `tool_calls` array plus one
`role="tool"` message per result. Forcing both through one shared loop would
need an abstraction layer purely to paper over that. Tool *schemas* stay in one
place. See `chatbot/backends/base.py`.

**Retrieval is hybrid, sized to the corpus.** A SQL pre-filter on bank, aspect,
sentiment and date does most of the narrowing; cosine similarity over cached
FinBERT embeddings ranks what survives; a small lexical-overlap boost ensures
exact identifiers like ticker codes or "DBS Multiplier" are not found by
semantic proximity alone. At tens of thousands of sentences, brute-force cosine
over an in-memory matrix is as correct as FAISS or Chroma and far simpler.

**Grounding is enforced in code, not requested in the prompt**, because prompt
instructions alone failed in testing:

1. *Volume floor.* `get_sentiment` returns `insufficient_data` below 5
   observations rather than a number the model might report as fact.
2. *Citation verification.* If `search_evidence` was never called, any quoted
   evidence, `sentence_id` or URL in the answer is fabricated by definition,
   and the response is flagged. Added after a local model invented sources
   twice, once as plausible URLs and once as placeholder tokens a URL-matching
   check alone would have missed.

**Evaluation.** A 23-question gold set in `chatbot/eval_gold_set.py` covering
lookups, comparisons, trends, out-of-scope questions, thin data, evidence
requests and advice-seeking. `chatbot/run_eval.py --tag <name>` writes a
transcript and a summary per model. Tool selection, advice-declining and
citation fabrication are automated. Whether a stated number is *correct* is
not, and deliberately so: verifying a number by extracting it with another
model is less trustworthy than the check itself.

---

## 9. Evaluation methodology

**Sampling.** `train_dev` uses model-assisted stratified sampling that
oversamples what base FinBERT calls non-neutral, to avoid a 60–70% neutral
training set starving the positive and negative classes. `test` is sampled
purely at random, before any model screening, and frozen. This cannot be
retrofitted: a test set drawn from model-screened candidates inflates the
fine-tuned model's reported F1 relative to the baseline it is compared
against.

**Blind labelling.** The test split must be labelled from
`data/labeled/test_blind.csv`, which withholds both `llm_prelabel` and
`base_finbert_label`. The latter matters most, because base FinBERT is one of
the two models the test set exists to compare.

**Agreement.** Two annotators label the same ~150 rows independently; Cohen's
κ must reach 0.6 before the work is divided. Watch the gap between κ and raw
agreement, since the corpus is 87% neutral under base FinBERT.

**Required baselines**, all on the same frozen test set: base FinBERT
zero-shot, a lexicon method, and a classical ML method (TF-IDF plus logistic
regression). "Fine-tuning helped" is unsupported without them.

**Metrics.** Accuracy, precision, recall and F1 per class, plus macro-F1.
Report mean and standard deviation across at least three seeds; a single run's
F1 is seed noise at this data size.

**Training configuration** in `train/finetune.py`: sentence-pair input
`[CLS] sentence [SEP] aspect [SEP]` into a 3-way softmax, one model for all
aspects rather than one per aspect, learning rate 2e-5, 3–5 epochs, batch 16,
max length 128, 10% warmup, early stopping on dev macro-F1, per-batch
padding, and optional class or source weighting (`--class-weights`,
`--source-weights`; off by default). Models trained before 2026-10-01 used
plain cross-entropy: weights were computed but never applied.

**Status: not run.** Zero rows are labelled.

---

## 10. Testing

379 tests, no network calls. External APIs are mocked with captured real
payloads, so a provider changing its response shape surfaces as a failing test
rather than a silent production break.

- `tests/conftest.py` provides `temp_db`, which redirects `ingest.db.DB_PATH`
  to a throwaway file and creates every table, so tests never touch
  `data/plp.db`.
- Runtime is about 60 seconds idle. Roughly 35 seconds is `umap`/`hdbscan`
  import cost from the discovery tests.
- Several tests exist because of specific real bugs and say so in their
  docstrings: silent PDF extraction failure, the SQLite parameter ceiling, the
  fine-tune pipeline smoke test, and the port-refusal behaviour of
  `scripts/start.sh`.

The pattern worth keeping: *a function whose failure mode is "silently returns
nothing" needs a test that asserts it returns something.*

---

## 11. Operations

**Service lifecycle.** `scripts/start.sh`, `stop.sh`, `status.sh`. PID files
in `data/run/`, logs in `data/logs/<service>.log`. Start refuses a port it
does not own and waits for a real health check. Stop never kills by port scan,
and shuts down Ollama only if it started it.

**Logging.** `config/logging_config.py`. Logs go to stderr so stdout carries
only program output, which is what lets the chatbot's answer be piped alone. A
rotating file captures DEBUG regardless of console level, so an unattended
overnight run stays diagnosable. Third-party libraries are silenced unless
`DEBUG=true`.

**Long jobs.** `scripts/overnight_backfill.py` runs one child process per
month-sized chunk, each committing immediately, so an interruption loses at
most one chunk. It fails fast if launched under the wrong interpreter, which
is how one overnight run was lost.

**Data snapshots.** `data/plp.db` is not in git (it passed GitHub's 100 MB
limit). After a material change, `PRAGMA wal_checkpoint(TRUNCATE)`, then
gzip it to `data/snapshots/plp-<date>[-vN].db.gz` (gitignored), verify it
unpacks and passes `PRAGMA integrity_check`, and record the name, size and
SHA-256 in the README. Snapshots are how a reported number is tied to the
exact data behind it.

**Scheduling.** Ingestion is manual since 2026-09-26. The launchd template
in `scripts/` runs `run_daily_batch.py` at 07:30; it ingests only, so the
pipeline steps must still be run afterwards.

**Failure modes.** RUNBOOK's troubleshooting table is the reference. The two
that cost the most time historically are the wrong Python interpreter, which
fails every import with a Python 3.9 syntax error, and a missing
`HF_HUB_OFFLINE=1`, which looks like a hang.

---

## 12. Security, compliance and ethics

**Credentials.** Keys live in `.env`, gitignored. `.env.example` is tracked
and must contain only placeholders. It did not: real NewsAPI and Alpha Vantage
keys were committed from the first commit until 2026-09-11 and remain in git
history. Both should be regenerated.

**The API has no authentication** and CORS is open. It is a localhost
development tool and must not be exposed to a network.

**Data access posture.** Three deliberate positions:

1. *UOB's WAF.* Its IR site answers scripted requests with a challenge stub.
   Rather than escalate to fingerprint-spoofing tools, the same PDFs are
   fetched from the Wayback Machine, which archived them at their original UOB
   URLs. The bytes are UOB's own published documents; only the transport
   differs.
2. *archive.org* is a donated public service that rate-limits under load. The
   fetcher backs off and retries; do not run it in a loop.
3. *Yahoo Finance's `quoteSummary`* is an unofficial endpoint with no public
   terms blessing it, and a cookie-and-crumb handshake that exists to slow
   automated access. It provides consensus aggregates, not analyst reasoning,
   and must not be described as "analyst reports". The caveat is surfaced in
   the module, the dashboard and the API response.

`sgx.com` and `sginvestors.io` were tested and both serve bot-protection
responses to plain clients. Scraping them would need a headless browser and
was assessed as disproportionate and in greyer territory than reading a public
feed.

**Not financial advice.** The chatbot is required to decline buy/sell framing
and state that it does not give investment advice. It currently manages this
in 3 of 7 gold-set cases on every model tested, which is a known and
report-relevant gap.

**Personal data.** Reddit content is public but user-authored. Documents store
the source URL rather than building user profiles, and no analysis is done per
author.

---

## 13. Ownership and open decisions

Ownership is by role, filled offline; see [HANDOFF.md](../HANDOFF.md). No
personal names are kept in the repository.

### Open decisions

> **Updated 2026-09-26.** Decisions 1 and 5 were made by the team (PLAN.md
> section 2: D1, D2) and 3 has a planned fix (DESIGN decision 19). The live
> list is PLAN.md's "Still open" table; the rows below record how they stood
> on 2026-09-11.

| # | Decision | Evidence available | Who decides |
|---|---|---|---|
| 1 | **Aspect taxonomy.** Keep the proposal's four, adopt a data-derived alternative, or use different taxonomies per source. *Decided 2026-09-30: ten data-derived aspects (DESIGN decision 21)* | `docs/evidence/aspect-discovery-2026-09-11.md`, `docs/evidence/taxonomy-comparison-2026-09-11.md`, `aspects/compare_taxonomies.py --sweep` | Team plus supervisor. It changes what was proposed. |
| 2 | **Default local model.** `llama3.1:8b` fabricates citations at 13% against `llama3.2:3b`'s 43–48%, but is noticeably slower | STATUS chatbot evaluation | Team |
| 3 | **Advice-declining fix.** 3 of 7 at best on every model, so it is a prompt and design problem, not a model choice | `data/eval/chatbot_eval_results_*.jsonl` | Whoever owns the chatbot |
| 4 | **Whether blending is right at all.** Management commentary and retail chatter in one index is a legitimate methodological question, currently resolved in favour of the proposal with composition made visible | Per-source rows in `sentiment_index` | Team plus supervisor |
| 5 | **Labelling split across four people**, and whether to reduce the per-class target given `asset_quality` has only 58 candidate rows | `docs/STATUS.md` labelling section | Team |
