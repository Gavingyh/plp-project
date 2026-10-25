# Technical Specification

The contracts between the parts of the system: data model, module boundaries,
API shapes, configuration, and how it is tested.

Reasoning lives in [DESIGN.md](../DESIGN.md) and is referenced rather than
repeated. Commands live in [RUNBOOK.md](../RUNBOOK.md). Current state and
caveats live in [STATUS.md](../STATUS.md).

Checked against the code, the configuration and the database (data to
25 Sep 2026) on 25 Oct 2026. Planned components are marked as such and
sequenced in [PLAN.md](../PLAN.md). The current figures, each with its
source, are in [docs/README.md](../README.md).

---

## 1. Architecture

The pipeline diagram is in [DESIGN.md](../DESIGN.md#what-the-system-does).
Rather than redraw it, here is one sentence's journey through the system, with
`sentence_id` as the thread that ties it together. Twenty-three diagrams, each
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

`aspects.assign` asks the local model `llama3.1:8b` which one of the ten
aspects, or `other`, the sentence is about, reading each aspect's definition
and the examples fixed in `config/aspects.yaml` (`assignment_method: llm`).
The answer, `net_interest_margin`, becomes the sentence's one
`sentence_aspects` row. `sentiment.score` classifies the (sentence, aspect)
pair with the model in use, three fine-tuned FinBERT seeds with their
probabilities averaged, and writes `aspect_sentiment` with a label, a
confidence and the `model_version`; base FinBERT's label is stored beside it
under its own version, as the baseline.
`aggregate.index` folds it into `sentiment_index` rows for DBS with weighting
and shrinkage. When a user later asks the chatbot about DBS margins,
`search_evidence` finds it among the sentences stored under that aspect,
ordered by the question's words and then by date,
and the answer cites it by that same `sentence_id` and the transcript's URL.
The Streamlit dashboard, like any other frontend, reads them through the
REST API ([api-integration.md](../api-integration.md)).

The invariant: **the sentence is the unit of analysis**, and every downstream
artifact keys off `sentence_id`. Document-level sentiment would defeat the
aspect-based premise, because one Reddit comment can praise a dividend and
criticise an app in consecutive sentences.

---

## 2. Module map

| module | responsibility | entry points |
|---|---|---|
| `ingest/` | Source adapters, DB schema and connection, retry helper, bank detection, news relevance filter and cross-source dedup | `arctic_shift`, `google_news`, `yahoo_news`, `newsapi`, `yahoo_analyst`, `analyst_tag`, `alphavantage`, `news_filter`, `cna_scraper` (RSS to a JSON file), `cna_archive` (CNA backfill into the database), `sgx_research_extract` (broker research PDFs), plus the three-stage earnings group: `earnings_fetch_ir`, `earnings_fetch_uob`, `earnings_extract` |
| repository root | Batch entry points | `run_news_pull.py` (every news source, then a source × bank × month table; `--audit` re-checks stored news), `run_daily_batch.py` (news, Reddit, consensus) |
| `preprocess/` | Documents to sentences; labelling exports; a dry-run debris filter; bank entity recognition | `pipeline`, `export_candidates`, `export_blind_test`, `export_topup`, `bank_ner` (evaluated, not applied), `fragments` (reports only) |
| `aspects/` | FinBERT embeddings, embedding cache, taxonomy discovery, assignment, taxonomy comparison, the LLM aspect classifier and assignment evaluation | `assign`, `discover`, `compare_taxonomies`, `embed_store`, `llm_classify` (evaluation and the corpus run), `assignment_eval` |
| `sentiment/` | Aspect-conditioned sentiment classification | `score` (scores each new pair with base FinBERT and with the model in use, through `finetuned`) |
| `aggregate/` | The sentiment index, continuous time series, and the read-only preview of pending changes | `index`, `preview` |
| `chatbot/` | Tool-calling agent, tools, RAG retrieval, prompts, backends, evaluation, a terminal chat for testing | `chat`, `agent`, `run_eval`, `search_vectors` (the evidence search's vectors) |
| `train/` | Label cleaning, fine-tuning, evaluation, pre-labelling, annotator agreement, the Opus labeller | `labels`, `finetune`, `evaluate`, `llm_prelabel`, `agreement`, `rater_labels` |
| `api/` | FastAPI REST API: the documented interface for any frontend (DESIGN decision 23); `api/pipeline.py` adds the routes that start and follow a manual pipeline run | `uvicorn api.main:app` |
| `pipeline/` | Manual pipeline runs started from the API: collection, the inference stages and run records, in a separate worker process so no model runs in a request handler | `service`, `runner`, `stages`, `jobs` |
| `dashboard/` | Streamlit dashboard, maintained by a teammate; reads everything through the REST API (`dashboard/api_client.py`) | `streamlit run dashboard/app.py` |
| `docker/` | Setup for Docker or a native install: restores the files missing from `data/data.zip`, checks them, downloads the models and builds the search vectors if absent | `bootstrap` (`python -m docker.bootstrap --data-only` restores the data alone) |
| `config/` | Aspect taxonomy and assignment method, the served model version and the fine-tuned models behind it, logging configuration | none |
| `scripts/` | Service lifecycle, overnight backfill, scheduling template, data repairs, the re-score step, the sharing bundle | `start.sh`, `stop.sh`, `status.sh`, `overnight_backfill.py`, `rescore.py`, `fix_earnings_dates.py`, `share_bundle.sh`, `com.plp.dailybatch.plist` (launchd job, not installed anywhere) |

The LLM aspect classifier of DESIGN decision 16 (`aspects/llm_classify.py`)
is applied: every stored sentence has one aspect from it, and
`aspects/assign.py` uses it for new sentences (`assignment_method: llm`).
`scripts/rescore.py` is the step that applied it, with the fine-tuned scores.
Bank entity recognition (decisions 17–18) is built and evaluated
(`preprocess/bank_ner.py`) but not applied: stored sentences keep their
alias-matching tags. Aspect agreement is in `train/agreement.py`
(`--field aspect`). Decision 19's chatbot harness is
built: `chatbot/intent.py` with `config/intents.yaml` (a local model sorts each
question into an intent; all but in_scope get a fixed reply, decision 24),
`chatbot/guards.py` (figure and sentence-id checks), and `Conversation` /
`answer_turn` in `chatbot/agent.py` (memory, state, per-turn record); `/chat`
accepts earlier turns as `history`. Chatbot settings: `config/chatbot.yaml`
through `chatbot/settings.py`.

Run every module as `.venv-plp/bin/python3 -m <module>`. Never plain
`python3`; see RUNBOOK for why.

---

## 3. Data model

One SQLite file, `data/plp.db`, 101.4 MB as restored from `data/data.zip`. Six tables. WAL journal mode.

### `documents`
One row per ingested item, before segmentation.

| column | type | meaning |
|---|---|---|
| `doc_id` | TEXT PK | Deterministic hash of source plus native ID. Makes ingestion idempotent. |
| `source` | TEXT | `arctic_shift` \| `earnings` \| `google_news` \| `yahoo_news` \| `newsapi` \| `cna` \| `sgx_research` (broker research) \| `alphavantage` |
| `source_detail` | TEXT | Publication name, subreddit, or document type |
| `bank` | TEXT | `DBS` \| `OCBC` \| `UOB` \| `MULTI` |
| `doc_type` | TEXT | `article` \| `submission` \| `comment` \| `earnings_release` \| `analyst_report` \| `analyst_report_web` (the last two broker research) |
| `title`, `body` | TEXT | `body` is NOT NULL |
| `published_at` | TEXT | ISO 8601 with offset: UTC, except CNA's +08:00 |
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
The aspect each sentence is about: one row per sentence (45,844 rows for
45,844 sentences), chosen by the local LLM and stored with `similarity` 1.0,
since the LLM gives no score.

`(sentence_id, aspect)` primary key, plus `similarity` and `assigned_at`. The
key allows more than one aspect a sentence, which the earlier method used.

`assignment_method` in `config/aspects.yaml` decides how new sentences are
assigned: `llm` (in use) or `centroid`, the earlier method, which matched a
sentence to every aspect whose seed centroid it cleared a similarity floor
for, and is kept for comparison.

### `aspect_sentiment`
One classification per (sentence, aspect, model version).

`(sentence_id, aspect, model_version)` primary key, plus `label`
(`positive` \| `neutral` \| `negative`), `confidence`, `scored_at`. The
`model_version` in the key lets two models' scores sit side by side: the
model in use, `finbert-adapted-finetuned-2026-10-11-3seed-m0`, and base
FinBERT, `finbert-base-zeroshot-v1`, 45,844 rows each. Every reader (the API, the chatbot's tools, evidence search,
suggestions and the time series) returns only the version named in
`config/model_version.py`, so two models' rows never mix; change it in the
commit that re-scores the corpus. If that version has no rows,
`get_sentiment` says so and a warning is logged. The index and the time
series count a row only while its pair is in `sentence_aspects`, so scores
left from an earlier aspect method never count; `scripts/rescore.py`, which
applies the LLM aspects and the fine-tuned scores, also deletes them.

### `sentiment_index`
The aggregate the API and chatbot read, and a dashboard through the API.

`(bank, aspect, window, source, model_version)` primary key, plus `score`,
`n`, `pos_n`, `neu_n`, `neg_n`, `confidence_mean`, `computed_at`.

- `aspect` is `'ALL'` for the overall per-bank row.
- `window` is `'7d'`, `'30d'` or `'all_time'`.
- `source` is `'ALL'` for the blended row, otherwise a single source. This
  dimension exists so a blended figure is never opaque.
- `score` is shrunk and weighted, in −1 to +1.
- `n` is always stored and always displayed. A sentiment number without its
  sample size is the main way a dashboard could mislead someone, so the API
  returns it with every score.

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
- **Windows and series buckets use parsed UTC instants.** CNA's timestamps
  carry +08:00 and NewsAPI's `Z`, so comparing the strings put CNA rows up to
  eight hours on the wrong side of a cutoff or month edge (fixed 3 Oct).
  Weeks are ISO weeks (`2025-W01`, never `W00`). Documented in
  `aggregate/index.py`.
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
| `aspects.assign` | `sentences` | `sentence_aspects` (+ embedding cache) | sentence not yet assigned | with `llm`, about a day for the whole corpus; 10–20 min per ~10k sentences with `centroid` |
| `sentiment.score` | `sentence_aspects` | `aspect_sentiment` | pair not scored at this `model_version` | 20–30 min per ~18k pairs with base FinBERT; the model in use runs three models, not one |
| `aggregate.index` | `aspect_sentiment`, `sentences` | `sentiment_index` | full recompute | ~2 s |

Timings are from RUNBOOK, measured on an M-series Mac with MPS.

Every step after ingestion needs `HF_HUB_OFFLINE=1`, or HuggingFace's
rate-limited metadata check can stall with near-zero CPU and look like a hang.

FinBERT's sentence vectors are cached in `data/sentence_embeddings.npz`
(132 MB) for aspect discovery, taxonomy comparison and the `centroid` method.
The chatbot's evidence search uses its own vectors,
`data/search_embeddings.npz` (66 MB, from `all-MiniLM-L6-v2`,
`chatbot/search_vectors.py`).

---

## 5. Models and libraries

| what | version | used for |
|---|---|---|
| `ProsusAI/finbert` | none | Sentence embeddings (mean-pooled over tokens, not CLS) for aspect discovery, the zero-shot baseline, and the base of the model in use |
| the model in use | `finbert-adapted-finetuned-2026-10-11-3seed-m0` | Three FinBERT seeds, the encoder further pretrained on the corpus, fine-tuned on (sentence, aspect) pairs, probabilities averaged; downloaded from Hugging Face, `plp-bank-sentiment/plp-finbert-absa` ([model card](../model-card.md)) |
| `sentence-transformers/all-MiniLM-L6-v2` | pinned in `docker/models.json` | The chatbot's evidence-search vectors for a search with no topic |
| spaCy `en_core_web_sm` | spaCy ≥3.8 | Sentence segmentation with financial abbreviation exceptions |
| torch | ≥2.9 | Model runtime; MPS on Apple silicon |
| transformers | ≥5.0 | FinBERT loading |
| scikit-learn | ≥1.7 | TF-IDF for cluster labelling, Cohen's κ, classical baseline, metrics |
| umap-learn | ≥0.5 | Dimensionality reduction before clustering |
| hdbscan | ≥0.8 | Density clustering for taxonomy discovery |
| fastapi + uvicorn | ≥0.115 / ≥0.30 | REST API |
| pdfplumber | ≥0.11 | Earnings PDF prose extraction |
| vaderSentiment | ≥3.3.2 | Lexicon baseline for evaluation |
| anthropic | ≥0.40 | Claude backend (the OpenAI backend calls the API with `requests`) |
| pytest, httpx | ≥8.0 / ≥0.27 | Tests; `httpx` is required by `TestClient` |

**Mean pooling, not CLS**, is deliberate: BERT-family CLS vectors without a
sentence-level training objective are poor similarity representations.

The chatbot's default answer model is hosted: OpenAI's `gpt-6-luna`
(`config/chatbot.yaml`). Local models available through Ollama:

| model | size | notes |
|---|---|---|
| `llama3.1:8b` | 4.9 GB | The intent classifier on every turn, the aspect classifier, and the answer model when `CHATBOT_BACKEND=ollama` (the no-key option). Before the evidence checks, 11 of 32 gold-set answers carried a citation warning |
| `llama3.2:3b` | 2.0 GB | The local answer model before `llama3.1:8b`; 15 of 32 on the same set |
| `phi4-mini` | 2.5 GB | Called a tool 0 of 16 times; fabricated in 83% of answers |
| `gemma3:4b` | 3.3 GB | No Ollama tool-calling support; all 23 questions error |
| `qwen3:4b` | 2.5 GB | Emits a hidden reasoning chain first; roughly 7x slower per chatbot call. For aspect classification `--no-think` turns it off (1.3 s a sentence) |

---

## 6. Configuration

### `.env`

| variable | default | read by |
|---|---|---|
| `NEWSAPI_KEY` | none | `ingest/newsapi.py` |
| `ALPHAVANTAGE_KEY` | none | `ingest/alphavantage.py` (contributes nothing) |
| `REDDIT_CLIENT_ID` / `_SECRET` / `_USER_AGENT` | none | Unused; Arctic Shift needs no key |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | none | The hosted backends' keys. `OPENAI_API_KEY` is needed for the default backend |
| `CHATBOT_BACKEND` | `openai` | `openai` \| `ollama` \| `claude` \| `auto`. A missing key never changes the provider: with no OpenAI key, set `ollama`. `auto` takes Claude's key, then OpenAI's, else Ollama |
| `OPENAI_MODEL` / `CLAUDE_MODEL` / `OLLAMA_MODEL` | `gpt-6-luna` / `claude-sonnet-5` / `llama3.1:8b` | The answer model of each backend |
| `CHATBOT_INTENT_MODEL` | `llama3.1:8b` | The local intent classifier, used whichever backend answers |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | The `openai` backend's address; any OpenAI-compatible provider, e.g. `https://api.groq.com/openai/v1` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama backend and the service scripts |
| `LOG_LEVEL` | `INFO` | Console verbosity |
| `DEBUG` | `false` | DEBUG level plus un-silencing third-party libraries |
| `LOG_FILE` | `data/logs/plp.log` | `none` disables file logging |
| `PLP_API_PORT` | 8000 | `scripts/start.sh`, `stop.sh`, `status.sh` |
| `PLP_DASHBOARD_PORT` | 8501 | the same scripts, for the dashboard |
| `CHATBOT_VERIFY_BEFORE_REPLY` | `true` | A draft with a figure, a reading or a quote no tool returned is rewritten once, then trimmed or withheld, never shown with a warning |
| `CHATBOT_ENFORCE_EVIDENCE` | `strip` | `strip` removes evidence no search returned and takes the quote marks off any other words no search returned (DESIGN decision 26); `search` also adds real quotes the harness finds; `off` only flags it |
| `OLLAMA_THINK` | unset | `false` turns a reasoning model's hidden thinking off (qwen3) |

`.env.example` is tracked, so every value in it must be a placeholder. Real
keys were committed there from the first commit until 2026-09-11 and must be
treated as compromised.

### `config/aspects.yaml`

Ten aspects plus `other` (DESIGN decision 21). Each has a `label` and an
`llm_definition`; with `llm_examples` they are what the LLM method reads
(`assignment_method: llm`, one aspect a sentence). Each also keeps
`seed_terms`, sentences whose mean FinBERT embedding was the centroid of the
earlier `centroid` method; its `similarity_floor: 0.65`, at which a sentence
matched 6.4 aspects on average, is used only by that method. The chatbot's
tool schemas and system prompt read the aspect list and definitions from
this file, so changing it changes what the chatbot can ask for. A changed
definition or example changes the LLM cache's prompt hash: the corpus must
then be classified again (about a day) and re-scored with
`scripts/rescore.py`.

### Tuning constants

| constant | value | where | meaning |
|---|---|---|---|
| `SHRINKAGE_K` | 5 | `aggregate/index.py` | `score × n/(n+k)` |
| `MIN_VOLUME_FOR_SCORE` | 5 | `chatbot/tools.py` | Below this, report insufficient data |
| source `weight` | earnings 1.0, arctic_shift 1.0, sgx_research 1.0; news sources 1.5 (google_news, yahoo_news, newsapi, cna, alphavantage); `default_weight` 1.0 | `config/sources.yaml`, read by `aggregate/index.py` | Earnings was 3.0 until it became the second-largest and most positively skewed source |
| `_LEXICAL_WEIGHT` | 0.15 | `chatbot/retrieval.py` | Keyword-overlap boost over cosine similarity, for a search with no aspect |
| `evidence.within_topic` | `words_then_newest` | `config/chatbot.yaml` | Within one aspect: the question's words, then the newest first, with no vectors |
| `MODEL_NAME` | `sentence-transformers/all-MiniLM-L6-v2` | `config/search_model.py` | The vectors for a search with no aspect |
| `similarity_floor` | 0.65 | `config/aspects.yaml` | `centroid` method only: below it, a sentence falls to `other` |

---

## 7. API contract

Base `http://localhost:8000`. No authentication; do not expose publicly. CORS
is open for local frontend development.

| method | path | parameters | returns |
|---|---|---|---|
| GET | `/health` | none | `{"status": "ok"}` |
| GET | `/banks` | none | Supported bank codes |
| GET | `/sentiment` | `bank*`, `aspect`, `window` | Score, `n`, class counts |
| GET | `/sentiment/compare` | `aspect`, `window` | All three banks side by side |
| GET | `/sentiment/trend` | `bank*`, `aspect` | Direction from the 7d vs 30d delta of the unshrunk scores, up to 12 monthly points |
| GET | `/sentiment/index` | `window`, `source` | Full index rows |
| GET | `/sentiment/series` | `bank*`, `aspect`, `bucket`, `source`, `min_n` | Continuous series; each point carries `sufficient` |
| GET | `/sources` | none | Sources present, for per-source breakdowns |
| GET | `/coverage` | `bank`, `aspect` | `has_data`, so callers can tell absence from neutrality |
| GET | `/evidence` | `query*`, `bank`, `aspect`, `sentiment`, `k` (1–50) | Sentences with `sentence_id`, `source`, `url`, `published_at` |
| GET | `/evidence/latest` | `bank*`, `aspect`, `limit` | The newest sentences with their stored label, for a drill-down list |
| GET | `/analyst-consensus` | `bank*` | Latest Yahoo snapshot, with its unofficial-API caveat |
| GET | `/analyst-consensus/latest` | none | Every bank's newest consensus row |
| GET | `/aspects` | none | Aspect keys and readable labels |
| GET | `/suggestions` | `limit` (1–20) | Starter questions generated from the index |
| POST | `/chat` | `{message, backend?, history?}` | Chatbot answer with its verification flags |
| GET | `/chat/status` | none | Whether the chat backend is configured, and the problem if not; never calls a model or shows a key |
| GET | `/pipeline/sources` | none | The local folders and online collectors a manual run can take; never fetches |
| POST | `/pipeline/runs` | `{sources*, since?, until?}` | Starts an incremental run in a separate process and returns its queued record; writes to the database |
| GET | `/pipeline/runs` | `limit` | The newest runs and the active one |
| GET | `/pipeline/runs/{run_id}` | `run_id*` | One run's stage metrics, file outcomes and warnings |

Twenty paths, twenty-one operations (`docs/api/openapi.json`); the four
`/pipeline` operations are in `api/pipeline.py`, the rest in `api/main.py`.

`*` marks required. A bad `bank`, `window` or `bucket` returns **HTTP 422**
from FastAPI before the handler runs (regex on the query parameter), and so
does an unknown `aspect` on every endpoint that takes one (a readable name
such as "dividend policy" is accepted; 4 Oct). On `/chat`, an unknown
`backend` or message `role` is a 422, an empty message a 400, and a backend
that fails (Ollama not running, a missing or rejected key) a 503. Covered by
`tests/test_api.py` and `tests/test_validate_api*.py`.

### Chatbot tools

Schemas in `chatbot/tools.py`, expressed in Anthropic's native shape; each
backend converts them to what it needs.

| tool | arguments | purpose |
|---|---|---|
| `get_sentiment` | `bank*`, `aspect` | The number, or `insufficient_data` |
| `compare_banks` | `aspect` | All three banks |
| `get_trend` | `bank*`, `aspect` | Direction plus a capped monthly series |
| `get_coverage` | `bank`, `aspect` | Distinguishes no data from neutral |
| `search_evidence` | `query*`, `bank`, `aspect`, `sentiment`, `k`, `window` | Retrieval; calling this is what makes a citation legitimate. `window` (`7d`, `30d`, `all_time`) limits the quotes to those days and sets the days the attached score covers; `get_sentiment` and `compare_banks` take it too. With none, all stored data (`CHATBOT_DEFAULT_WINDOW`; a `30d` or `7d` default falls back to all stored data when too thin). A `sentiment` other than positive, neutral or negative ("all") is dropped, not applied; a search that finds nothing returns `no_evidence`, and the attached score says what it covers (`covers`). Results carry a `period` in words, and the answer ends with a "Period searched" line built from them |
| `get_analyst_consensus` | `bank*` | Yahoo aggregates |

The system prompt lists each topic with its definition from `config/aspects.yaml`, so the model can match a
question to a topic by meaning; if none fits it leaves `aspect` out and says it found no matching topic.

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
sentiment and date does most of the narrowing. Within one aspect, what
survives is ordered by the question's words and then by date, with no
vectors: FinBERT similarity ranked that pool below a random draw, and no model
built for search beat the word ordering. With no aspect, cosine similarity
over cached vectors from a model built for search (all-MiniLM-L6-v2,
`chatbot/search_vectors.py`) ranks what survives, and a small lexical-overlap
boost ensures exact identifiers like ticker codes or "DBS Multiplier" are not
found by semantic proximity alone (`docs/evidence/search-models-2026-10-24.md`).
At tens of thousands of sentences, brute-force cosine over an in-memory matrix
is as correct as FAISS or Chroma and far simpler.

**Grounding is enforced in code, not requested in the prompt**, because prompt
instructions alone failed in testing:

1. *Volume floor.* `get_sentiment` returns `insufficient_data` below 5
   observations rather than a number the model might report as fact.
2. *Citation verification.* If `search_evidence` was never called, any quoted
   evidence, `sentence_id` or URL in the answer is fabricated by definition,
   and the response is flagged. Added after a local model invented sources
   twice, once as plausible URLs and once as placeholder tokens a URL-matching
   check alone would have missed.
3. *Reading check.* A score described in words (`neutral`, `slightly`,
   `moderately` or `clearly` positive or negative) must use a reading a tool
   returned for the question (`unverified_readings`). Added on 18 Oct 2026
   after an answer called a topic "neutral" and "slightly positive" beside a
   score the tools read as "clearly positive".
4. *Verified before it is returned.* A draft that fails the citation, figure
   or reading check is never shown with a warning. The model is told what was
   wrong and writes the answer again once; a second failure is trimmed to the
   sentences that pass, and an answer with too little left is replaced by a
   reply saying no answer could be backed up. The API's three flags are then
   empty. The first draft's flags stay on the turn for the evaluation
   (`chatbot/agent.py`, `answer_turn`; `CHATBOT_VERIFY_BEFORE_REPLY`,
   `CHATBOT_VERIFY_RETRIES`). Added on 18 Oct 2026 after a follow-up ("and
   UOB?") was answered from no tool call, with three warnings under it.

**Evaluation.** A gold set in `chatbot/eval_gold_set.py` covering lookups,
comparisons, trends, out-of-scope questions, thin data, evidence requests and
advice-seeking: 23 questions in v1, 32 in v2 (`--set v2`), plus four
multi-turn conversations (`--multi-turn`), retrieval MRR and an LLM judge
([evidence](../evidence/chatbot-eval-build-2026-10-01.md)). `chatbot/run_eval.py --tag <name>` writes a
transcript and a summary per model. Tool selection, advice-declining,
citation fabrication and the figure check are automated, and each check's
flags are recorded twice: on the model's first draft and on the answer
shown, which differ when a failing draft is rewritten or trimmed.
`--recheck --tag <name>` checks the stored answers of an earlier run again
without calling any model. On the latest runs (32 questions), `gpt-6-luna`
and `llama3.1:8b` each chose the right tool 24 of 24 times, declined advice
and admitted missing data 8 of 8 times, and showed no answer with a figure
no tool returned (0 of 32; 3 and 1 first drafts had one)
([evidence](../evidence/chatbot-fixes-2026-10-24.md)). Whether a stated number is *correct* is
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

**Blind labelling.** The test split should be labelled from
`data/labeled/test_blind.csv`, which withholds both `llm_prelabel` and
`base_finbert_label`. The latter matters most, because base FinBERT is one of
the two models the test set exists to compare. The first-round test rows were
not labelled this way: annotators saw a small local model's suggested label,
test rows included, and 89% of the test labels match it, so the first-round
test set is not blind. The 100 broker research test rows were labelled with no
suggestion ([model card](../model-card.md), Limitations;
[evidence](../evidence/model-rerun-2026-10-11.md), Limits).

**Agreement.** Two annotators label the same ~150 rows independently; Cohen's
κ must reach 0.6 before the work is divided. Watch the gap between κ and raw
agreement, since 70% of corpus sentences are neutral under base FinBERT.

**Additional rater.** Opus 5.5 labelled the 1,277 sentences blind as one
more rater (DESIGN decision 22); its agreement with the human labels (aspect
κ 0.80, sentiment κ 0.79) is a human–LLM figure, and it never replaces a
human label. Its labels of 1,563 sentence-aspect pairs, under the rules of
10 Oct, are the training labels of the model in use; every test label is a
person's ([model card](../model-card.md), Training).

**Required baselines**, all on the same frozen test set: base FinBERT
zero-shot, a lexicon method, and a classical ML method (TF-IDF plus logistic
regression). "Fine-tuning helped" is unsupported without them.

**Metrics.** Accuracy, precision, recall and F1 per class, plus macro-F1.
Report mean and standard deviation across at least three seeds; a single run's
F1 is seed noise at this data size.

**Training configuration** in `train/finetune.py`: sentence-pair input
`[CLS] sentence [SEP] aspect [SEP]` into a 3-way softmax, one model for all
aspects rather than one per aspect, learning rate 2e-5, batch 16, max length
128, 10% warmup, early stopping on dev macro-F1 (patience 2), per-batch
padding, and optional class or source weighting (`--class-weights`,
`--source-weights`; off by default, and they did not improve
cross-validation). The configuration chosen by 5-fold cross-validation is up
to 8 epochs with the aspect's readable label (`--aspect-text label`) as the
second segment. The model in use adds a first stage (`train/dapt.py`): the
encoder's masked-word training continued for 3 epochs on 42,822 corpus
sentences, leaving out every labelled sentence and anything resembling one.
The candidate models were compared by a rule written down before the test
rows were scored: test macro-F1 over three seeds, with cross-validation as
the tie-breaker.

**Results.** The model in use, three seeds averaged, on the 299 first-round
test rows: macro-F1 0.670 and accuracy 0.716, against base FinBERT zero-shot's
0.571 and 0.699. Each seed is above base FinBERT: 0.628, 0.657 and 0.662
(mean 0.649, sd 0.018). The gain is on the negative and positive classes
(recall 0.59 and 0.73 against 0.21 and 0.53), paid for with neutral recall
(0.73 against 0.91); the accuracy difference is not significant (exact
McNemar p = 0.65). On the 100 broker research test rows: 0.770 against 0.687
([model card](../model-card.md), [evidence](../evidence/model-rerun-2026-10-11.md)).
The first configuration, trained on people's labels alone, scored
0.604 ± 0.035 and was never served. The aspect classifier: `llama3.1:8b`
matches people's aspect on 73.9% of the 1,277 labelled sentences, against
41.3% for seed-centroid matching
([evidence](../evidence/wealth-definition-trial-2026-10-12.md)).

---

## 10. Testing

2957 tests in `tests/` (3004 from the repository root, adding the diagram and
notebook checks), no network calls. External APIs are mocked with captured real
payloads, so a provider changing its response shape surfaces as a failing test
rather than a silent production break.

- `tests/conftest.py` provides `temp_db`, which redirects `ingest.db.DB_PATH`
  to a throwaway file and creates every table, so tests never touch
  `data/plp.db`.
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

**Setup on another machine.** `docker compose up --build` (`compose.yaml`)
starts the API, the dashboard and Ollama. Its setup step (`docker/bootstrap.py`)
restores the files missing from `data/data.zip` (the database, both vector
files, the CNA cache and the aspect answers), checks the database's integrity
and that the vectors match the sentences, downloads base FinBERT, the three
fine-tuned models from the public Hugging Face repo
`plp-bank-sentiment/plp-finbert-absa` (checked against SHA-256) and the
search model, and pulls `llama3.1:8b`. Natively, `python -m docker.bootstrap
--data-only` restores the data alone. Commands are in the
[README](../../README.md).

**Manual pipeline runs.** `POST /pipeline/runs` starts an incremental run of
chosen sources in a separate worker (`pipeline/`); `GET /pipeline/runs/{run_id}`
follows it. The dashboard's Data Management page uses these routes.

**Data snapshots.** `data/plp.db` is not in git (it passed GitHub's 100 MB
limit). After a material change, `PRAGMA wal_checkpoint(TRUNCATE)`, then
gzip it to `data/snapshots/plp-<date>[-vN].db.gz` (gitignored), verify it
unpacks and passes `PRAGMA integrity_check`, and record the name, size and
SHA-256 in the README. Snapshots are how a reported number is tied to the
exact data behind it. `scripts/share_bundle.sh` builds `data.zip` from the
latest snapshot, for the team and the assessors; it holds CNA and Reddit
text, so it is never published or committed.

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
   the module and the API response, and the integration guide asks a
   dashboard to show it.

`sgx.com` and `sginvestors.io` were tested and both serve bot-protection
responses to plain clients. Scraping them would need a headless browser and
was assessed as disproportionate and in greyer territory than reading a public
feed.

**Not financial advice.** The chatbot is required to decline buy/sell framing
and state that it does not give investment advice. Prompt instructions alone
managed this in 2–3 of 7 gold-set cases on every model tested. From 26 Sep a
regex input guard answered advice-seeking questions with a fixed reply and
declined 7 of 7; the intent classifier (decision 24) now does, and
recognised all 17 advice questions in its evaluation (100 of 103 questions
right overall, `data/eval/intent_eval_llama8b.md`).

**Hosted model.** Reddit text never reaches a hosted model: each hosted
backend replaces it with a placeholder before sending a tool result
(`chatbot/backends/base.py`). CNA and broker research sentences may be sent,
a team decision of 24 Oct 2026 (`hosted_model` in `config/sources.yaml`,
DESIGN decision 28).

**Personal data.** Reddit content is public but user-authored. Documents store
the source URL rather than building user profiles, and no analysis is done per
author.

---

## 13. Ownership and open decisions

Ownership is by role, filled offline; see [HANDOFF.md](../HANDOFF.md). No
personal names are kept in the repository.

### Open decisions

> **Updated 2026-09-26.** Decisions 1 and 5 were made by the team (PLAN.md
> section 2: LLM aspects, and annotators labelling aspect and sentiment) and 3 has a planned fix (DESIGN decision 19). The live
> list is PLAN.md's "Still open" table; the rows below record how they stood
> on 2026-09-11.

| # | Decision | Evidence available | Who decides |
|---|---|---|---|
| 1 | **Aspect taxonomy.** Keep the proposal's four, adopt a data-derived alternative, or use different taxonomies per source. *Decided 2026-09-30: ten data-derived aspects (DESIGN decision 21)* | `docs/evidence/aspect-discovery-2026-09-11.md`, `docs/evidence/taxonomy-comparison-2026-09-11.md`, `aspects/compare_taxonomies.py --sweep` | Team. It changes what was proposed, so the report must explain it. |
| 2 | **Default local model.** *Decided 4 Oct: `llama3.1:8b`.* On gold set v2 (1 Oct) it carried a citation warning on 11 of 32 answers against `llama3.2:3b`'s 15, and on 4 Oct the 3B was no faster. *Since 24 Oct the default answer model is OpenAI's `gpt-6-luna`; `llama3.1:8b` stays the local option and the intent classifier* | `docs/evidence/chatbot-eval-build-2026-10-01.md`, `docs/evidence/chatbot-fixes-2026-10-24.md` | Team |
| 3 | **Advice-declining fix.** *Done:* the fixed replies decline 7 of 7, where prompts alone managed 2 or 3 of 7 | `docs/evidence/chatbot-harness-2026-09-26.md` | none |
| 4 | **Whether blending is right at all.** Management commentary and retail chatter in one index is a legitimate methodological question, currently resolved in favour of the proposal with composition made visible | Per-source rows in `sentiment_index` | Team |
| 5 | **Labelling split across four people**, and whether to reduce the per-class target given `asset_quality` has only 58 candidate rows | `docs/STATUS.md` labelling section | Team |
