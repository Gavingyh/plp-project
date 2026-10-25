# Runbook

How to set up and run the system. For why it's built this way, see
[DESIGN.md](DESIGN.md). For what's unfinished, see [STATUS.md](STATUS.md).

The native setup and Docker verification procedures are documented below.
Docker validation results are recorded in the Docker section.

---

## Setup

Python 3.10 or newer is required (developed on 3.14). A Mac's built-in
`python3` is 3.9: `pip install` then fails on `torch>=2.9.0` without saying
why, so create the environment with a newer interpreter
(`python3.14 -m venv .venv-plp`) after installing one from python.org or
Homebrew ([evidence](evidence/install-test-2026-10-01.md)).

```bash
cd /path/to/plp-project
python3 -m venv .venv-plp
.venv-plp/bin/python3 -m pip install -r requirements.txt
.venv-plp/bin/python3 -m spacy download en_core_web_sm
cp .env.example .env        # then fill in keys, see API_KEYS.md
```

The pipeline runs without any API key. Keys only add sources:

| key | adds | required? |
|---|---|---|
| *(none)* | Reddit, earnings PDFs, Yahoo consensus, local chatbot | — |
| `NEWSAPI_KEY` | news articles (~1 month lookback on free tier) | optional |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | hosted chatbot model (`OPENAI_API_KEY` is required for the default OpenAI answer backend; `ANTHROPIC_API_KEY` for explicit Claude) | required for the selected hosted backend; other tabs work without it |

## Docker setup

Use the professor-facing [Docker quick start](../README.md#run-with-docker-recommended-for-assessment)
for the normal launch. Put the supplied archive at **`data/data.zip`** before
the first startup; manual extraction is unnecessary. The project folder
supplied to assessors should already contain the ZIP at that path.

`Dockerfile` installs the Python dependencies, CPU PyTorch and the spaCy English
model. `docker/constraints.txt` pins direct dependency versions. `compose.yaml`
runs one setup service followed by one FastAPI service and Streamlit. The
existing manual-pipeline subprocess runs inside the API container, using the
same database, models and run directory. No separate job queue is needed.

The setup service strips the archive's existing `data/` prefix, restores only
the database, FinBERT embedding cache, optional search cache, CNA cache and aspect-answer caches, and checks
SQLite integrity, the served model version and embedding IDs. Old archive and
preview files in the ZIP are ignored. Existing files are preserved. A missing,
invalid or mismatched dataset stops setup with a specific error before the
application starts. A partial restoration can be retried with the same command.

`docker/models.json` records the public Hugging Face revisions and the three
fine-tuned checkpoint SHA-256 hashes. The Docker runtime uses the same pinned
base-model revision that setup downloaded, with Hugging Face offline mode
enabled. MiniLM is pinned in both the manifest and `config/search_model.py`,
so cache creation and runtime queries use the same search model revision. Each unique configured Ollama model is pulled once and reused.
Setup warms the local intent classifier with a synthetic question before
starting the API/UI, so the first real question can reuse its model/prompt.
Docker uses a 180-second intent timeout for CPU-only cold requests; native
Python keeps its 60-second default. Override `CHATBOT_INTENT_TIMEOUT` if needed.
`PLP_WARM_INTENT=0` skips this optional readiness/inference check, for example
when reviewing only the read-only data pages. No paid API is used for warm-up.
The optional evaluation judge is not needed to run the app; add
`PLP_EXTRA_OLLAMA_MODELS=qwen3:4b` if running judge-based evaluations.

Setup runs search-vector preparation in a separate process before warming
Ollama, releasing MiniLM's model memory first. If `search_embeddings.npz` is
absent from the supplied ZIP, setup generates it from the database; no new
bundle or teammate-provided cache is required. An optional supplied cache is
checked for unique sentence IDs, finite 384-dimensional vectors and database
coverage, separately from FinBERT's 768-dimensional vectors. Invalid search
caches are rebuilt. Complete caches are reused without rewriting them; partial
caches embed only missing sentences and remove deleted IDs. Writes use atomic
replacement so interruption cannot expose a half-written cache. The database
is not modified by this preparation. First-time generation logs its progress
and can take several minutes depending on CPU resources.

The API's pipeline preflight checks that MiniLM is cached before importing
documents. Runtime Hugging Face access stays offline. If this check fails,
rerun setup with `docker compose up --build` rather than enabling runtime
downloads.

| persisted asset | location |
|---|---|
| ZIP, database, embeddings, CNA, PDF inputs, run history, logs | host `data/` mounted at `/app/data` |
| fine-tuned checkpoints | host `models/` mounted at `/app/models` |
| base FinBERT, MiniLM and downloaded Hugging Face snapshots | project-scoped `hf-cache` Docker volume |
| Ollama models | project-scoped `ollama-models` Docker volume |

For an automatic dataset download, supply a direct HTTPS `PLP_DATA_URL` in
`.env`, optionally with `PLP_DATA_TOKEN` (Bearer authentication) and
`PLP_DATA_SHA256`. Setup uses it only when the ZIP and required runtime files
are missing. An HTML sharing/login page is not a download link. The URL/token
are not printed. Public models require no HF token; `HF_TOKEN` is supported
for an access-restricted mirror. Setup credentials are not passed to Streamlit
or FastAPI. OpenAI/NewsAPI credentials are passed only to FastAPI.

The image build excludes `.env`, datasets, models, logs, Git history and local
development settings. Containerised Ollama is reachable on the internal Compose
network; it does not expose port 11434 on the host. Dashboard/API ports bind to
localhost. Override `PLP_API_PORT` and `PLP_DASHBOARD_PORT` in `.env` if needed.

### Docker: using native Ollama on a Mac

Start the native Ollama app, then:

```bash
docker compose -f compose.yaml -f compose.native-ollama.yaml up --build
```

This mode requires current Compose with `!reset` support (2.24.4+). The override
uses `http://host.docker.internal:11434`, skips the Ollama container and pulls
missing models through the native server. It reuses native Ollama's model
storage; the two Docker-managed model volumes are independent of that storage.
Apple GPU acceleration is available through native Ollama; Docker Desktop on
macOS cannot pass that GPU to the Ollama container. See
[Ollama's FAQ](https://docs.ollama.com/faq#how-do-i-use-ollama-with-gpu-acceleration-in-docker).

### Docker: clean-install test

On macOS/Linux, from this repository with `data/data.zip` present:

```bash
bash scripts/docker-clean-test.sh
```

The script creates a new `.docker-test/<project>/` folder containing only the
ZIP and the repository's PDF/glossary inputs. It uses empty model folders,
new project-scoped Hugging Face/Ollama volumes and containerised Ollama. Your
native venv, database and model caches are not mounted. The normal `.env`
supplies configuration, but only FastAPI receives hosted-provider keys.
It builds/starts the services, waits for health checks and runs read-only API,
dashboard and pipeline-prerequisite checks. It sends no paid-model requests
and starts no collection or pipeline run. Leave the containers running to
review the dashboard at **http://localhost:8502**, API at
**http://localhost:8100/docs**. Set `PLP_TEST_API_PORT` /
`PLP_TEST_DASHBOARD_PORT` if these test ports are already occupied.

The script prints the exact restart/stop commands for its selected project and
mounts. Reuse those settings for that project. Use a new project name for a
second fresh-install test; `-p` alone does not isolate host bind-mounted files.
To resume an interrupted test, use
`bash scripts/docker-clean-test.sh <project-name> --resume`; keep any custom
`PLP_TEST_API_PORT` / `PLP_TEST_DASHBOARD_PORT` values the same.
On Windows, use a separate checkout with only the ZIP and a fresh `.env`, set
different API/dashboard ports, and run `docker compose -p plp-clean-test up --build`.

For additional local-model inference checks (use the selected project name):

```bash
docker compose -p <project-name> exec -T api python -m docker.smoke --inference
```

This checks actual offline MiniLM and FinBERT embeddings, all three fine-tuned
models and an Ollama intent response. The default smoke check also verifies
full search-cache coverage and calls `/evidence` without a topic filter to
exercise semantic retrieval without a hosted chatbot request. Run `--ui` separately to render all six pages;
the flags are mutually exclusive so UI test state is released before loading
the 8B model. Wait until image builds finish before running inference tests.
These checks make no OpenAI/Claude requests. To exercise the update workflow, select a
local source in Data Management in this test instance, run it, then stop/start
the same test project. Verify that run history and the database persist and
that setup reports the models as already downloaded. Stopping during a run
leaves saved work intact; the existing runner recovers it as interrupted and
the next incremental run completes pending work.

### Initial Docker validation (24 Oct 2026, before the MiniLM integration)

Validated using Linux ARM64 containers on an Apple Silicon Mac with an 8 GB
Docker allocation, isolated data/model folders and empty project model caches
at the start. The supplied ZIP restored 45,844 sentences and embeddings.

| check | result |
|---|---|
| Public model downloads | Base FinBERT, three fine-tuned checkpoints and `llama3.1:8b` downloaded; all recorded checkpoint hashes matched |
| Offline FinBERT inference | Base embeddings and all three fine-tuned models produced valid outputs |
| Local intent inference | Passed in containerised and native Ollama modes; cold CPU warm-up took 47 seconds in this test |
| Dashboard/API | All six pages rendered against the real API; health, sentiment and pipeline routes passed |
| Manual local-PDF update | All six stages completed; 0 new documents and 4 warnings from existing earnings PDFs |
| Restart | Modified database and completed run history preserved; setup restored 0 files and reused the downloaded models |
| Interrupted worker | Forced API termination recovered the paused run as interrupted; another incremental run completed |
| Setup errors | Missing ZIP produced the documented path; missing OpenAI key produced `openai_key_missing` without changing provider |
| Image contents | Local `.env`, data ZIP and downloaded models excluded from the image |
| Regression suite | 2,900 passed, 58 subtests passed; 2 skipped and 46 expected failures |

Smoke checks generated no hosted-model requests and performed no live web
collection. Windows/x86 hardware was not directly exercised. Containerised
Ollama on a Mac is slower than native GPU inference; warm-up is a readiness
step rather than a chatbot latency guarantee. Run UI and model tests separately
and finish image builds before model inference to avoid competing memory use.

### MiniLM integration validation (24 Oct 2026)

Validated after merging the chatbot fixes from `main`, using the existing
`data.zip` without a search cache and the same Apple Silicon Docker setup.

| check | result |
|---|---|
| Automatic preparation | Pinned MiniLM downloaded; 45,844 search vectors generated from the restored database |
| Network-disabled inference | MiniLM produced valid normalized vectors with Docker networking disabled and cached files mounted read-only |
| Evidence retrieval | `/evidence` without a topic filter passed with Hugging Face offline mode enabled |
| New local PDF | On a disposable database/cache copy, one synthetic PDF added one document/sentence; all six stages completed, including both embedding caches and the served fine-tuned sentiment model |
| Repeated ingestion | No duplicate documents/sentences/scores; search cache unchanged |
| Dashboard | All six pages rendered against the merged API |
| Restart | Complete search vectors reused without rebuilding; cache checksum and modification time preserved |
| Regression suite | 2,935 passed and 58 subtests passed; 2 skipped and 46 expected failures |

The synthetic PDF and its run records remain under the ignored
`data/run/minilm-validation-*/` folder; the dashboard database retains its
45,844 sentences. No hosted-model requests or online collection were used.
The host regression run reused the existing Python test environment (linked
temporarily for the native startup-script test, then removed); Docker startup
and inference required no host Python environment. An existing sklearn
single-label warning and Streamlit deprecation warnings remain unrelated to
this integration.

### Docker troubleshooting

| symptom | action |
|---|---|
| Cannot connect to the Docker daemon | Start Docker Desktop and wait until it is ready |
| Setup cannot find the ZIP | Put the supplied file at `data/data.zip` or configure a direct `PLP_DATA_URL` |
| Database/model version or cache mismatch | Obtain the matching team dataset; setup preserves existing files rather than silently replacing them |
| Download interrupted | Check connectivity/free space and repeat `docker compose up --build`; model download caches are retained |
| Ask reports a missing key | Set `OPENAI_API_KEY` in `.env`, then `docker compose up -d api` |
| Port already allocated | Stop the previous instance or set different host ports in `.env` |
| Local inference slow on a Mac | Use the native Ollama override for GPU acceleration |
| Container exits with code 137 | Increase Docker Desktop's memory allocation; allow at least 8 GB for this stack |
| Need startup details | Run `docker compose logs --tail=100 setup api dashboard` |

`docker compose down` retains persistent storage. Removing volumes discards
downloaded model caches; host `data/` and `models/` remain. Do not start two
independent application instances against the same writable data directory.

---

## Use the venv interpreter explicitly

**Run everything as `.venv-plp/bin/python3`, not `python3`.** There are three
Python installations on a typical setup here and only one works:

| what `python3` may resolve to | result |
|---|---|
| `.venv-plp/bin/python3` | correct |
| system Python 3.14 | `ModuleNotFoundError: No module named 'torch'` |
| miniforge/conda Python 3.9 | `TypeError: unsupported operand type(s) for \|` |

That last one is the dangerous one: the code uses `X \| None` type syntax
which Python 3.9 cannot parse, so **every module fails at import**. A
scheduled overnight backfill was lost this way — conda activation in a shell
profile can silently shadow an activated venv, and the run failed all 79 of
its work units identically without producing any data.

`scripts/overnight_backfill.py` now fails immediately with a clear message
rather than proceeding, but other entry points do not. Using the absolute
path avoids the problem entirely.

---

## If a FinBERT step appears to hang

Set `HF_HUB_OFFLINE=1`. HuggingFace performs a rate-limited metadata check
even when the model is already cached locally, which can stall with near-zero
CPU usage — it looks like a hang but is a network wait.

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.assign
```

---

## The pipeline

Steps are **order-dependent** — each consumes the previous step's output.

The corpus is frozen from 2026-09-26 and the shared snapshot has already been
through every step below, so a teammate restoring it (README, "Getting the
database") needs none of this. Run the steps only after adding data.

```bash
# 1. Ingest: news, a 7-day incremental Reddit pull, analyst consensus.
.venv-plp/bin/python3 run_daily_batch.py

# 2. Documents -> sentences
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m preprocess.pipeline

# 3. Embed + assign aspects            [SLOW - see timings below]
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.assign

# 4. Score sentiment                   [SLOW]
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m sentiment.score

# 5. Aggregate into the index
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.index
```

### Manual data updates through the API

The [manual pipeline](manual-pipeline.md) coordinates local earnings/research
PDF extraction, cached CNA article import and selected Google News/Reddit/NewsAPI collection through index aggregation, using the existing trained models
and `data/plp.db` by default. Selected sources control imports; subsequent
analysis completes all pending work in that database. Model training is not
part of a run.

Restart the API to load the new routes:

```bash
scripts/stop.sh api
scripts/start.sh api
curl http://localhost:8000/pipeline/sources
```

When an update changes both the source list and dashboard modules, restart
the dashboard as well (`scripts/stop.sh dashboard`, then
`scripts/start.sh dashboard`). A browser refresh alone can retain imported
modules in the running Streamlit process. A source-definition mismatch is a
service-version issue, not a problem with the PDFs or stored documents.

To start a real incremental update (**writes to the configured database**):

```bash
curl -X POST http://localhost:8000/pipeline/runs \
  -H 'Content-Type: application/json' \
  -d '{"sources":["earnings","sgx_research"]}'
```

Use PDF keys, `cna` (local article cache), `google_news`, `arctic_shift` (Reddit),
`newsapi`, or a combination. NewsAPI requires `NEWSAPI_KEY` in the API host's
ignored `.env` or environment; restart the API after changing credentials. Online
collection accepts `since` (inclusive) and `until` (exclusive) in UTC, limited
to 1–31 days; omitting both defaults to the last seven days including today.
For example, `{"sources":["google_news","arctic_shift"],"since":"2026-10-01","until":"2026-10-08"}`.
The dashboard displays inclusive From/Through dates and converts the end date.
Inspect `source_results` and warnings for failed/incomplete collection windows;
retry the same dates to recover gaps without duplicating stored documents.
Google News and Reddit need no key; NewsAPI uses the configured server-side key.
Other providers are not enabled.

HTTP 202 returns a queued run and a `Location`
header containing `/pipeline/runs/<run_id>`; poll it every two seconds for
stage results. `GET /pipeline/runs` lists recent run summaries and the active
ID. A missing model or source folder appears as a failed run at that URL.
HTTP 409 means another run is active; 503 means worker launch or state storage
failed. The API responds without waiting for inference.

The dashboard also provides **Data Management**, below Ask in the sidebar:
place PDFs in the displayed API-host folders, supply `data/cna/articles.jsonl`,
or select Google News, Reddit and NewsAPI.
Choose sources or **All available sources**, set online collection dates when
needed, and click **Run selected sources**. All selects existing PDF folders,
the readable CNA cache, Google News, Reddit and configured NewsAPI. Missing local
inputs and NewsAPI without a key are skipped.
CNA reads usable cached articles from 1 Jan 2023 through today in Singapore
without online discovery; online dates
apply only to Google News, Reddit and NewsAPI. Other providers are not started.
Folder paths are resolved from the API checkout location and can be viewed
under **Folder locations**. This writes to the configured database.
The page polls progress every two seconds and keeps the latest 20 runs
available for inspection. Controls are disabled while a run is active;
after an uncertain start, use **Check run status** before retrying. Other
tabs display an update notice and reload cached data when the run ends.
Existing chat messages are preserved. The page remains accessible when the
sentiment index is empty; it still needs a working API connection.

Run records and logs are saved under `data/run/pipeline/`. Restarting the API
does not stop a running worker. Completed data remains after a later failure;
rerun to finish pending stages. For terminal use and prerequisite checks, see
[manual-pipeline.md](manual-pipeline.md); for fields and response codes, see
[the API contract](api-integration.md#manual-pipeline-api-milestone-2).

### Expected timings

Do not assume a hang. On an M-series Mac with MPS:

| step | time | note |
|---|---|---|
| `run_daily_batch.py` (7-day) | ~2–5 min | network-bound |
| `preprocess.pipeline` | seconds–2 min | scales with new documents |
| `aspects.assign` | **10–20 min** for ~10k new sentences | FinBERT embedding; longer sentences cost more |
| `sentiment.score` | **20–30 min** for ~18k new pairs | FinBERT classification |
| `aggregate.index` | ~2 s | pure SQL + arithmetic |

Measured 2026-09-24 on news: 5,751 headline sentences were embedded and
assigned in under a minute, and 9,891 pairs scored in about a minute.
Headlines are short; long earnings sentences sit at the slow end of the table.

Steps 3 and 4 only process *new* work, so subsequent runs are fast. Progress
appears in the logs; the log file also captures DEBUG detail
(`data/logs/plp.log`).

Step 3 assigns new sentences by `assignment_method` in `config/aspects.yaml`:
`centroid` (today) or `llm`, one aspect per sentence from `llama3.1:8b`,
which needs Ollama running. Step 4 stops with "probabilities don't sum to 1"
if the GPU returns garbage; rerun it with `--cpu`.

### Apply the aspect and sentiment decisions (the re-score)

`scripts/rescore.py` replaces the centroid aspects with the LLM's one aspect
per sentence and adds the fine-tuned models' scores (three seeds averaged,
neutral margin) beside base FinBERT's, then recomputes the index. It reads
the LLM's answers and the fine-tuned probabilities from the caches the
corpus run and the full-corpus preview left, so on this Mac it takes
seconds. It refuses `data/plp.db` unless given `--real-db`: rehearse on a
copy first.

```bash
# a fresh copy, a dry run, then the copy changed
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 scripts/rescore.py --db /tmp/plp-rescore.db --fresh-copy \
    --aspects llm --finetuned --cpu
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 scripts/rescore.py --db /tmp/plp-rescore.db --fresh-copy \
    --aspects llm --finetuned --cpu --apply
```

Which models and margin: `--version` with a version listed in `FINETUNED`
(`config/model_version.py`) uses that entry's models and margin, and refuses
others, because new sentences are scored with exactly those. Without it, the
chosen model's three seeds are used (`DEFAULT_FINETUNED`) with the margin
their entry lists; other models
(`--models`, such as the retrained seeds in
`models/experiments-2026-10-03/label/`) need `--margin` and get a version of
their own. Base FinBERT's tag is refused.

It prints its checks (one aspect per sentence, no scored pair without an
assignment) and every bank's headline per model version, which should match
the preview's columns B and D. On 3 Oct the copy matched all 36 bank-aspect
cells of the full-corpus preview (scores within 0.0001). After the real run,
which only the team can approve: set `MODEL_VERSION` in
`config/model_version.py` to the version it prints, set `assignment_method:
llm`, take a snapshot (below), and run the evaluations again. On another
device (a CUDA PC, or the Mac's GPU without `--cpu`) the fine-tuned pairs
are scored again, since the cache is kept per device.

**The real run was on 2026-10-12**, after a rehearsal on a copy that the
database then matched row for row
([evidence](evidence/rescore-rehearsal-2026-10-12.md)). `data/plp.db` now
holds one LLM aspect a sentence and two models' scores: the served one,
`finbert-adapted-finetuned-2026-10-11-3seed-m0`, and base FinBERT's. The
copy before it is `data/snapshots/plp-before-rescore-20261012-141607.db`.
Anyone on an older database must restore the latest snapshot (README): with
the old one the API finds no rows for the served model, and
`sentiment.score` would start scoring every old pair with the fine-tuned
models.

**A second run followed on 2026-10-14**, after the corpus was classified
again under the wealth rule of 10 Oct (about a day of the MacBook). It
changed the aspect of 6,914 sentences and lowered each bank's headline by
0.010 to 0.015, because the served model reads the aspect's name with the
sentence ([evidence](evidence/rescore-wealth-wording-2026-10-14.md)). The
copy before it is `data/snapshots/plp-before-rescore-20261014-000702.db`.
The files teammates need are gathered by
`data/run/rescore-2-2026-10-14/build_share.sh` into `data/run/share/`.

Links to locally read PDFs are relative paths (decided 4 Oct, applied
12 Oct): `scripts/rewrite_pdf_paths.py` counts by default and writes only
with `--apply`, and refuses `data/plp.db` without `--real-db` (it backs it up
first). It covers earnings reports and broker research, whose links carried
a home folder. On 12 Oct it rewrote 203 documents and 12,895 sentences in
the database (178 and 12,254 earnings, 25 and 641 broker research) and
10,443 links in 46 committed files under `data/`, changing nothing but the
link. The snapshots from before 12 Oct were left as they are and still hold
the old links.

```bash
.venv-plp/bin/python3 scripts/rewrite_pdf_paths.py --db data/plp.db --snapshots --files            # counts only
.venv-plp/bin/python3 scripts/rewrite_pdf_paths.py --db data/plp.db --real-db --snapshots --files --apply
```

`aggregate.preview --per-seed` scores the LLM-aspect pairs with each model
alone and prints the spread of every bank's headline between seeds.

---

## One-off ingestion tasks

Earnings ingestion is three modules: two fetchers that put PDFs on disk, and
one extractor that reads whatever is there.

| module | does what |
|---|---|
| `ingest.earnings_fetch_ir` | Downloads DBS's and OCBC's PDFs from their IR sites |
| `ingest.earnings_fetch_uob` | Downloads UOB's from the Wayback Machine, because its IR site is WAF-blocked |
| `ingest.earnings_extract` | Turns everything in `data/earnings_pdfs/<BANK>/` into `documents` |

The extractor does not care which fetcher produced a file, or whether you put
it there by hand. Run it after either.

```bash
# Download earnings PDFs from DBS and OCBC IR sites (~116 files, several minutes)
.venv-plp/bin/python3 -m ingest.earnings_fetch_ir --dry-run   # preview first
.venv-plp/bin/python3 -m ingest.earnings_fetch_ir

# Extract prose from downloaded PDFs into the documents table
.venv-plp/bin/python3 -m ingest.earnings_extract

# Analyst consensus (fast, safe to re-run daily)
.venv-plp/bin/python3 -m ingest.yahoo_analyst
```

### News

Every news source goes through `ingest/news_filter.py`; rejected and flagged
articles are logged in `data/news_flagged.csv`. Method and rules:
[news-data.md](news-data.md).

```bash
# all news sources; Google News backfilled month by month from 2023-01-01 (~20 min)
.venv-plp/bin/python3 run_news_pull.py

# one source, or a date range
.venv-plp/bin/python3 run_news_pull.py --source google --since 2024-01-01 --until 2024-07-01
.venv-plp/bin/python3 -m ingest.google_news --since 2023-01-01 --query-filter intitle:

# source x bank x month counts; re-check stored news against the current rules (flags only)
.venv-plp/bin/python3 run_news_pull.py --report
.venv-plp/bin/python3 run_news_pull.py --audit
```

Removing articles an audit flags is a manual, approved step; see the two
clean-ups recorded in news-data.md.

CNA is separate from `run_news_pull.py` because it is slow: it fetches every
article's full text at CNA's 10-second crawl delay (about 75 minutes for the
2023–2026 backfill). A re-run only fetches what `data/cna/` doesn't hold yet.

```bash
caffeinate -i .venv-plp/bin/python3 -m ingest.cna_archive --since 2023-01-01 --until 2026-09-26
.venv-plp/bin/python3 -m ingest.cna_archive --load-only --since 2023-01-01 --until 2026-09-26  # cache only
```

### Snapshot the database after a material change

```bash
sqlite3 data/plp.db "PRAGMA wal_checkpoint(TRUNCATE);"
gzip -9 -c data/plp.db > data/snapshots/plp-<date>-vN.db.gz
gunzip -c data/snapshots/plp-<date>-vN.db.gz > /tmp/check.db && sqlite3 /tmp/check.db "PRAGMA integrity_check;"
shasum -a 256 data/snapshots/plp-<date>-vN.db.gz   # record name, size and checksum in the README
```

### Scheduling

Not running since 2026-09-26. To run the ingestion daily on a Mac, install
`scripts/com.plp.dailybatch.plist`; its header has the install, run-now and
remove commands. Replace its `/path/to/plp-project` placeholders with the
checkout's path first. It ingests only; run the pipeline steps afterwards.
`run_daily_batch.py` logs failed Reddit or Google News windows at error
level but still exits 0; `run_news_pull.py` exits non-zero, and the
backfill below records such a month as incomplete and moves on.

### UOB earnings — fetched from the Wayback Machine

UOB's IR site sits behind an F5 WAF that answers any scripted request with a
199-byte challenge stub (`Request Redirected` / `TS.request.ID`), so
`ingest.earnings_fetch_ir` cannot reach it the way it reaches DBS and OCBC.

The Wayback Machine holds captures of the same PDFs at their original UOB
URLs and is not behind that WAF, so fetch them from there instead:

```bash
.venv-plp/bin/python3 -m ingest.earnings_fetch_uob --dry-run   # preview
.venv-plp/bin/python3 -m ingest.earnings_fetch_uob             # ~67 PDFs, 2020-2025
.venv-plp/bin/python3 -m ingest.earnings_extract                # extract prose
```

The bytes are UOB's own published PDFs; only the transport differs. Two
limits matter: archive coverage thins out for the most recent
quarters (the dry run prints per-year counts), and a capture is occasionally
the WAF stub rather than the document — those are detected by magic bytes and
discarded rather than saved as unreadable `.pdf` files.

archive.org is a donated public service and rate-limits under load; the
fetcher backs off and retries, but avoid re-running it in a loop.

### Historical Reddit backfill

For multi-year history, use the chunked script rather than
`run_daily_batch.py --reddit-since`. It commits after each month, so an
interruption doesn't lose the whole run, and it resumes by skipping completed
chunks.

```bash
caffeinate -i .venv-plp/bin/python3 scripts/overnight_backfill.py
```

Progress: `data/backfill_overnight.log` and `data/.backfill_progress.txt`.
A month in which a page kept failing after its retries ends with exit code 3
and an `INCOMPLETE` line naming the lost windows, and is not marked done, so
the next run retries it. Before 3 Oct such months were marked done, and Sep
2021, May 2024 and Mar 2025 lost most of their comments that way. They were
refilled on 11 Oct 2026 with `python -m ingest.arctic_shift --since <month
start> --until <next month start>` for each, then the pipeline for the new
rows (825 documents).

---

## Interfaces

The interfaces are the REST API, a terminal chat for testing the chatbot,
and the Streamlit dashboard (`dashboard/`, a teammate's), which reads the
database directly. The API is the documented interface for any frontend
(DESIGN decision 23); [api-integration.md](api-integration.md) is its contract.

### Start and stop

```bash
scripts/start.sh              # Ollama (if needed), the API and the dashboard
scripts/status.sh             # what's running, on which port, healthy or not
scripts/stop.sh               # stop everything this project started
```

Each takes an optional service name (`api`, `ollama` or `dashboard`) to act
on just one. Ports come from `PLP_API_PORT` (default 8000) and
`PLP_DASHBOARD_PORT` (default 8501); the script refuses a port already in use.
The scripts work from any directory.

The API's port comes from `PLP_API_PORT` (default 8000):

```bash
PLP_API_PORT=8100 scripts/start.sh api
```

To serve another database, such as a rescored copy, without touching
`data/plp.db`, set `PLP_DB_PATH`, and `PLP_EMBEDDINGS_PATH` if its sentence
embeddings differ. The API and the dashboard both read it:

```bash
PLP_DB_PATH=data/plp_rescored.db PLP_API_PORT=8100 scripts/start.sh api
```

`scripts/rescore.py` refuses to change `data/plp.db`, or the database
`PLP_DB_PATH` names, without `--real-db`.

What the scripts do that the raw commands below don't:

- **Refuse a port they don't own.** If something else is listening, they print
  the owning process and exit rather than starting or killing anything. This
  is not hypothetical: 8000 is a common default, and another project on the
  development Mac already uses it.
- **Wait for a real health check** before reporting success (`/health` for
  the API), so a green message means the service answers, not merely that a
  process exists.
- **Fail fast on the wrong interpreter**, with the same check
  `scripts/overnight_backfill.py` uses, instead of failing per-request later.
- **Set `HF_HUB_OFFLINE=1`** and load `.env`.
- **Leave Ollama alone if it's already running.** `stop.sh` shuts it down only
  if `start.sh` was the one that started it, since it's a machine-wide service
  that other things may be using.

PID files live in `data/run/`, logs in `data/logs/<service>.log`. Both start
and stop are safe to run twice.

`.env` is parsed line by line rather than sourced, because `. .env` executes
the file as shell and `.env.example` ships with
`REDDIT_USER_AGENT=plp-practice-module/0.1 by u/your_username` — an unquoted
value whose spaces make `by` look like a command. Python's `dotenv` accepts
that line, so the file is fine; shell is just the wrong parser for it.

### The underlying commands

These are what the scripts run, and remain the reference:

```bash
# REST API (docs at http://localhost:8000/docs)
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m uvicorn api.main:app --port 8000

# Chatbot, interactive, with memory and the answer flags (/suggest, /tools, /reset, /quit)
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m chatbot.chat --backend ollama

# Chatbot, one question
CHATBOT_BACKEND=ollama .venv-plp/bin/python3 -m chatbot.agent "How does the market feel about DBS's dividend policy?"
```

### Suggested questions

`GET /suggestions?limit=6` returns starter questions for a chat UI to render
as clickable prompts:

```bash
curl 'http://localhost:8000/suggestions?limit=6'
```

```json
{"suggestions": [
  {"question": "What is the overall sentiment on DBS?", "category": "overall"},
  {"question": "Compare DBS, OCBC and UOB on dividend policy.", "category": "compare"}
]}
```

The questions are generated from the sentiment index, not hardcoded, so a
bank or aspect without enough data is never suggested and a clicked
suggestion won't dead-end on "insufficient data". Categories are `overall`,
`aspect`, `compare`, `consensus`, `trend`, `evidence` — useful if the
frontend wants to group or icon them. The terminal chat prints the same list
with `/suggest`.

### Chatbot backends

By default the chatbot answers through OpenAI using `gpt-6-luna`. This applies
even when `CHATBOT_BACKEND` is omitted; `OPENAI_API_KEY` must be configured on
the API server. To use local answers explicitly, set `CHATBOT_BACKEND=ollama`.

The switch belongs to **FastAPI**, in `.env` on the API host. The dashboard
sends the same `/chat` request for every provider and has no provider control.
The dashboard checks `GET /chat/status` before enabling Ask. A missing or
blank key produces a setup message and disables the input and suggested
questions, while other tabs keep working. The Administrator setup expander
explains which environment variable to configure. The browser never asks for
or receives the key. Add the matching key locally and choose:

| `CHATBOT_BACKEND` | Key | Default answer model |
|---|---|---|
| `openai` (default) | `OPENAI_API_KEY` | `gpt-6-luna` |
| `ollama` (explicit local option) | none | `llama3.1:8b` |

For example, edit `.env` (keep the actual keys out of Git):

```dotenv
CHATBOT_BACKEND=openai
OPENAI_API_KEY=<your OpenAI key>
OPENAI_MODEL=gpt-6-luna
```

Only change `CHATBOT_BACKEND` to switch backends. Restart the API to load `.env`:

```bash
scripts/stop.sh api
scripts/start.sh api
```

Then clear the conversation in Ask before testing another provider. Keep Ollama
running: the existing intent classifier remains local for all providers. This
switch changes the answer model, not FinBERT, topic assignment or training.
Providers do not automatically fall back to another.
`claude` remains available; legacy `CHATBOT_BACKEND=auto` explicitly opts into
key detection (Claude, then OpenAI, otherwise Ollama).

The configuration check makes no model requests and does not verify the key,
remaining credit, model availability or connectivity. Rejected keys, exhausted
credit/quota, temporary rate limits and connection failures get readable
errors when a question is sent; a failed question does not enter conversation
history. Billing/quota failures are not retried automatically. Credentials are
configured in `.env` on the API host, never through a dashboard key-entry form.

**Getting keys:**

**OpenAI:** open [OpenAI API keys](https://platform.openai.com/api-keys),
   select your API project and create a secret key. Put it in `OPENAI_API_KEY`
   in `.env`; requests use that project's API credit. See the
   [official quickstart](https://developers.openai.com/api/docs/quickstart).

Model defaults and parameters were checked against provider documentation on
24 Oct 2026. OpenAI uses
[`gpt-6-luna`](https://developers.openai.com/api/docs/models/gpt-6-luna) with
`reasoning_effort=none` for Chat Completions function calls. Run a small pilot
with each real key before the full benchmark; mocked tests do not verify account
access or live quotas. The backends retry rate-limit/service-busy responses and
return HTTP 503 with a useful message when the provider remains unavailable.

Existing hosted-provider filtering remains in force: Reddit, CNA, broker-research
and private/unknown evidence text, links and citations are withheld, as are earlier
assistant answers that may quote them. Aggregate figures can still include those
sources. Hosted evidence answers therefore see a different evidence pool from
the local model; record this when comparing quality.

**Any OpenAI-compatible provider** (Groq, NVIDIA NIM, OpenRouter, …) goes
through the `openai` backend with its address in `OPENAI_BASE_URL`. For
Groq's free tier: create a key at https://console.groq.com/keys, check its
Data Controls settings, and put three lines in `.env`:

```bash
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_API_KEY=<the Groq key>
OPENAI_MODEL=openai/gpt-oss-120b        # or llama-3.3-70b-versatile, qwen/qwen3.8-27b
```

Then set `CHATBOT_BACKEND=openai` to use it. Groq's free tier allowed 8,000
tokens a minute on 2026-09-30, about one question a minute with this
chatbot's prompt and tools; the backend waits out a 429 or 503 (after
Groq's `Retry-After` when sent) four times. Not yet run against Groq: the
first successful answer is this setup's verification.

An answer is checked before it is returned, and the reader never sees a warning
(`CHATBOT_VERIFY_BEFORE_REPLY`, on by default since 18 Oct 2026). Each draft is
checked for three things: evidence (a quote, sentence id or URL) no search
returned, or words no search returned in quote marks; a figure that matches
nothing the tools returned for that question (strict: a figure the model
derived legitimately in an unusual way can also trip it); and a score described
as "neutral", "slightly positive" or the like in words the tools did not return
as that score's reading (the bands are in `config/chatbot.yaml`, `reading`; the
check does not know which score the words describe, so a bank's overall reading
can vouch for a topic's). A draft that fails is not shown. The model is told
what was wrong and asked once more (`CHATBOT_VERIFY_RETRIES`); a second draft
that fails is cut down to the sentences that pass; and if too little is left the
reply says it could not back up an answer. A turn that was rewritten, trimmed or
withheld has `repaired` set in the trace and the terminal chat; the first draft's
flags stay on the turn for the evaluation, and the API and dashboard flags
(`citation_unverified`, `unverified_numbers`, `unverified_readings`) are empty for
a verified answer. With no period named, the chatbot's tools use all stored data (`CHATBOT_DEFAULT_WINDOW`, `all_time`; `30d` or `7d` can be set), and the line says so. An answer that used a tool ends with a "Period searched" line, followed by the standing rule ("If no period is named, all stored data is used.") (for example "the last 30 days of data (26 Aug 2026 to 25 Sep 2026)"), added by the harness from the tools' own `period` fields. A rewrite costs a second model call, so a flagged answer
takes about twice as long. With `CHATBOT_VERIFY_BEFORE_REPLY=false` the old
behaviour returns: the answer is shown with a `NUMBER CHECK`, `READING CHECK` or
`VERIFICATION WARNING` under it.

Before the model runs, a local model sorts the question into an intent
(`chatbot/intent.py`, DESIGN decision 24): buy/sell/hold and price
predictions, other banks, greetings and thanks, "what can you do?",
banking-service requests, attempts to change the instructions, complaints
and off-topic questions get a reviewed fixed reply from
`config/intents.yaml`; only questions about the three banks' sentiment reach
the chatbot model. It needs Ollama; if the classifier can't answer, the
question goes to the model and the turn records no intent. Measure it:

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m chatbot.eval_intent --model llama3.1:8b --tag llama8b
```

Every chatbot setting has its default in `config/chatbot.yaml`, with the
environment variable that overrides it (models, Ollama address, temperature,
timeouts, retries, history length, the trend threshold). The ones most often
changed:

| setting | default | effect |
|---|---|---|
| `CHATBOT_BACKEND` | `openai` | requires `OPENAI_API_KEY`; `ollama` explicitly selects local answers; `claude` selects Claude; legacy `auto` opts into key detection |
| `OLLAMA_MODEL` | `llama3.1:8b` (since 4 Oct) | the answer model when `CHATBOT_BACKEND=ollama` |
| `OPENAI_MODEL` | `gpt-6-luna` | OpenAI answer model; choose one supporting Chat Completions function calls |
| `CHATBOT_INTENT_MODEL` | `llama3.1:8b` | the model that sorts questions into intents |
| `CHATBOT_TEMPERATURE` | `0.2` | decoding temperature on every backend; low for grounded answers |
| `CHATBOT_TRACE_FILE` | unset | if set, each terminal-chat or API turn appends a JSON line: question, answer, tool calls and results, intent, state |
| `CHATBOT_VERIFY_BEFORE_REPLY` | `true` (since 18 Oct) | an answer with a figure, a reading or a quote no tool returned is rewritten, trimmed or withheld before it is returned; `false` shows it with a warning instead |
| `CHATBOT_DEFAULT_WINDOW` | `all_time` (since 18 Oct) | the chatbot's period when the question names none: `all_time`, `30d` or `7d`; a `30d` or `7d` default that holds too little to report, or a search that finds nothing in it, falls back to all stored data and says so |
| `CHATBOT_VERIFY_RETRIES` | `1` | times the model is asked to write a failed answer again before it is trimmed |
| `CHATBOT_ENFORCE_EVIDENCE` | `strip` (since 4 Oct) | `strip` removes evidence no search returned and takes the quote marks off any other words no search returned, so only text a search returned stands in quote marks (the Grounded chatbot claim relies on it; DESIGN decision 26); `search` also adds real quotes the harness finds; `off` only flags it |
| `OLLAMA_THINK` | unset | `false` turns a reasoning model's thinking off (qwen3) |
| `OLLAMA_KEEP_ALIVE` | `30m` | how long Ollama keeps the local model loaded after a question; a shorter time frees its memory sooner, and the next question then waits for the model to load |
| `OLLAMA_TOOLS_IN_SYSTEM` | `false` | `true` writes the tool descriptions at the start of the instructions, where Ollama caches them, instead of passing them with every question (see `chatbot/backends/ollama_backend.py`) |
| `CHATBOT_ASPECT_QUERY` | on (since 4 Oct) | `0` turns it off. On, evidence search, when given an aspect, ranks by the aspect's name plus the question's own topic words instead of the whole question: MRR 0.559 against 0.217 on the human-labelled pool ([evidence](evidence/chatbot-eval-build-2026-10-01.md)); off until the team switches it on |

The terminal chat remembers the last three turns, so follow-ups like
"and OCBC?" work. The API is stateless: send earlier turns in `history`:

```bash
curl -s localhost:8000/chat -H 'content-type: application/json' -d '{
  "message": "and OCBC?",
  "history": [{"role": "user", "content": "How is sentiment on DBS dividends?"},
              {"role": "assistant", "content": "..."}]}'
```

The answer goes to stdout and diagnostics to stderr, so:

```bash
# just the answer
.venv-plp/bin/python3 -m chatbot.agent "..." 2>/dev/null
```

### Evaluating the chatbot

```bash
.venv-plp/bin/python3 -m chatbot.run_eval --limit 3   # smoke test
.venv-plp/bin/python3 -m chatbot.run_eval             # full 23-question gold set
```

Runs `chatbot/eval_gold_set.py` against the chatbot and writes:
- `data/eval/chatbot_eval_results.jsonl` — full transcript (question, answer,
  every tool call and its raw result)
- `data/eval/chatbot_eval_summary.md` — automated checks: tool selection,
  advice-decline behaviour, citation-fabrication rate, how many questions an
  input guard answered, and how many answers carried an unverified figure

Use `--tag` to keep runs apart, and `CHATBOT_TEMPERATURE` to compare decoding
settings. Gold set v2 on each Groq model, one after another (the free tier's
rate limit makes each run slow, roughly 45 minutes):

```bash
for m in openai/gpt-oss-120b llama-3.3-70b-versatile qwen/qwen3.8-27b; do
  OPENAI_MODEL=$m HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m chatbot.run_eval \
      --backend openai --set v2 --tag "groq_${m//[^A-Za-z0-9.]/_}_v2"
done
```

The number check flags figures no tool returned; it doesn't prove the
unflagged ones are used correctly. Read the transcript for that.

### Comparing the local baseline with OpenAI

OpenAI requests use API credit and the account's rate limits. Optional free-tier
providers such as Groq also limit requests per day and tokens per minute. `chatbot/ratelimit.py` keeps every hosted request under a budget set in
`rate_limits` in `config/chatbot.yaml` (below the providers' published limits),
counts requests over a rolling 24 hours in `data/ratelimit_state.json`, waits
for a provider's `Retry-After`, believes Groq's own remaining-quota headers, and
stops the run if a provider still returns 429 three times in a row. A stopped run
keeps its answers; `--resume` asks only what is left.

```bash
.venv-plp/bin/python3 -m chatbot.provider_eval --dry-run   # what is ready and the request budget; sends nothing
.venv-plp/bin/python3 -m chatbot.provider_eval --arms openai  # OpenAI only; uses API credit
.venv-plp/bin/python3 -m chatbot.provider_eval --resume    # after a stop
.venv-plp/bin/python3 -m chatbot.provider_report           # rebuild docs/evidence/chatbot-provider-eval-<date>.md
```

OpenAI uses `OPENAI_API_KEY` from `.env` and the configured `OPENAI_MODEL`.
The default comparison arms are Ollama and OpenAI. Groq remains optional with
`--arms groq` and `GROQ_API_KEY`. Keys are never printed. The local Ollama arm needs Ollama running with `llama3.1:8b` pulled,
which the intent classifier uses in every arm; without it the hosted arms still
run but no intent is found, so the input-guard checks are not comparable.
The hosted models never receive Reddit, CNA or broker-research text, so they
see less evidence than the local one.

---

## Logging and debugging

Configured in `config/logging_config.py`, driven by `.env`:

```bash
LOG_LEVEL=INFO              # console verbosity
DEBUG=true                  # DEBUG level + un-silences third-party libraries
LOG_FILE=data/logs/plp.log  # "none" to disable file logging
```

The log file always records DEBUG regardless of console level, so an
unattended run stays diagnosable afterwards. `DEBUG=true` additionally
restores transformers/urllib3/httpx output, including HTTP-level tracing.

```bash
DEBUG=true .venv-plp/bin/python3 -m ingest.yahoo_analyst   # full detail
LOG_LEVEL=WARNING .venv-plp/bin/python3 run_daily_batch.py  # quiet, for cron
```

---

## Tests

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest tests/ -q
```

2949 tests in `tests/`; `pytest -q` from the repository root runs 2996,
adding the diagram and notebook checks. These are a fresh checkout's counts:
one test runs per gold-set results file in `data/eval/`, so a machine that
holds the results kept out of git (they quote CNA text) collects one more for
each. Since 24 Oct the team's Mac holds none (its results files were committed), so it collects the same; checked against a fresh clone on 25 Oct. A bug that `/validate` confirms gets a
test marked `xfail(strict=True)` in `tests/test_validate_*.py`, which passes as
"xfailed" until the bug is fixed; the marker comes off in the fixing commit.
On 6 Oct 2026 three markers are left, covering five cases, each kept as a
recorded limit (evidence page, Known limits): a quote holding two quotes of
the other style is removed whole, a real one inside it too, two cases
(`tests/test_validate_chatbot_round7_review_findings.py`); and three
ordinary dates the figure check flags, accepted false alarms
(`tests/test_validate_chatbot_round9_probes.py`). The twelfth validation added
25 more cases, all recorded limits too (a source note after a quote keeps its
citation, a figure vouched for by subject words, text in backticks, a
blockquote's citation line; `tests/test_validate_chatbot_round12_*.py`), and
the thirteenth 16 more, also recorded limits (a removed quote's citation kept
behind a dash or bold, figures skipped as years, durations or under 10, "45
per cent", ".87"; `tests/test_validate_chatbot_round13_review_findings.py`):
46 expected failures in all.
No network calls: external APIs are mocked with captured real payloads, so a
provider changing its response shape surfaces as a failing test rather than
a silent production break.

On 2026-10-01, 479 ran in 45 seconds on a quiet MacBook Air, and 539 took
2.1 minutes that evening alongside other jobs; a fresh clone's
first run of `tests/` took 2.6 minutes. Part of every run is
`umap`/`hdbscan` import cost (numba), paid once by the aspect-discovery
tests.

---

## Diagrams

The diagrams in `docs/diagrams/` are drawn by hand from the code, so update them when
the code they describe changes. Edit the `.mmd` in `docs/diagrams/src/`, copy it into
the page's Mermaid block, then:

```bash
docs/diagrams/render_diagrams.sh                       # all; or pass a prefix, e.g. 07
.venv-plp/bin/python3 docs/diagrams/check_sources.py   # every sources-table line still says what it claims
```

Rendering needs Node (`npx` fetches the Mermaid CLI). `docs/diagrams/test_diagrams.py`
fails if a page and its `.mmd` differ; `pytest -q` from the repository root runs it, but
`pytest tests/` (above) doesn't. See
[docs/diagrams/README.md](diagrams/README.md).

---

## Labelling workflow

> **First round labelled 2026-09-27** under the 10-aspect taxonomy
> (DESIGN decisions 17 and 21; results in
> [evidence/annotation-agreement-2026-09-27.md](evidence/annotation-agreement-2026-09-27.md)).
> `data/labeled/` holds each annotator's sheets (`agreement/`), the resolved
> candidates (`resolved/`), the resolved blind test sheet (`test_blind.csv`),
> and `candidates.csv`, which training reads. **Don't edit `candidates.csv`
> by hand**: rebuild it from the resolved sheets, which removes duplicated
> pairs and train/test leakage and takes test labels from the blind sheet:
>
> ```bash
> .venv-plp/bin/python3 -m train.labels
> ```
>
> A labelled top-up sheet (`preprocess.export_topup`) is added the same way;
> its rows join train_dev, `not_about_bank` rows are left out, and a sentence
> already labelled is refused:
>
> ```bash
> .venv-plp/bin/python3 -m train.labels --topup data/labeled/topup/topup_sheet.csv
> ```
>
> The commands below are for the next round.

```bash
.venv-plp/bin/python3 -m preprocess.export_candidates --train-dev 800 --test 200
# -> data/labeled/candidates.csv
```

### Optional: LLM-assisted pre-labelling

Before a human labels anything, a local model can propose a label and
rationale for each row (`llm_prelabel` / `llm_rationale` columns only — it
never touches `label`). This is free, runs on Ollama, and typically cuts
labelling to correction rather than labelling from scratch.

```bash
.venv-plp/bin/python3 -m train.llm_prelabel --limit 5   # smoke test first
.venv-plp/bin/python3 -m train.llm_prelabel              # full run, ~1-2 hours for 1,000 rows
```

Checkpointed and resumable: every result is written to
`data/labeled/llm_prelabel_progress.jsonl` immediately, and re-running skips
whatever is already recorded there. Safe to kill and restart, and safe to
leave running unattended overnight (`nohup ... &` / `disown`, or `caffeinate`
on macOS to also stop the machine sleeping).

Fill in the `label` column per [annotation-guideline.md](annotation-guideline.md),
using `llm_prelabel`/`llm_rationale` to correct rather than label from
scratch. **Label independently first if you want to measure how often the
model was right** — anchoring on its suggestion before forming your own view
defeats that measurement.

The `split=test` rows are randomly sampled and must stay untouched by any
model-assisted process — that is what keeps the eventual evaluation honest.

### Label the test split from the blind sheet, not from candidates.csv

The pre-labelling run above reached the test split before anyone noticed it
shouldn't have: 199 of the 200 `test` rows carry an `llm_prelabel`, and every
row carries `base_finbert_label` — base FinBERT being one of the two models
the test set exists to compare. Labelling next to either column measures
agreement with a model rather than establishing ground truth.

```bash
.venv-plp/bin/python3 -m preprocess.export_blind_test               # write the blind sheet (refuses to
                                                                    # replace a filled one without --force)
.venv-plp/bin/python3 -m preprocess.export_blind_test --check-leakage  # what's withheld, and why
.venv-plp/bin/python3 -m preprocess.export_blind_test --merge       # merge the filled sheet back
```

`data/labeled/test_blind.csv` carries the sentence, its aspect and its
provenance and nothing else. Fill in `label`, and `flag` for rows that
shouldn't be scored at all — expect some, since a known limitation is that
sentences mentioning a bank incidentally still enter the corpus.

Label the blind sheet on its own, before or without looking at the same rows
in `candidates.csv`. In the 27 Sep round each annotator's blind labels were
identical to their candidates-sheet labels on all 299 rows, so the test
labels can't be called blind.

### Check agreement before splitting up the work

Two annotators label the same ~150 rows independently, then:

```bash
.venv-plp/bin/python3 -m train.agreement --a data/labeled/agreement/test_blind_coder_a.csv \
    --b data/labeled/agreement/test_blind_coder_b.csv --show-disagreements 20
```

Target is Cohen's κ ≥ 0.6. Below that, the guideline is ambiguous somewhere
rather than an annotator being careless — find the disagreements, tighten the
guideline, re-label the sample. For the aspect, add `--field aspect`: the
sheets are then matched on `sentence_id` alone and compared over the eleven
aspect keys.

```bash
.venv-plp/bin/python3 -m train.agreement --a sheet_a.csv --b sheet_b.csv --field aspect --show-disagreements 20
```

Watch the gap between raw agreement and κ:
70% of corpus sentences are neutral under base FinBERT, so two annotators who both
default to `neutral` will agree ~90% of the time while sharing no judgement
at all. The tool prints both and warns when the gap is large.

The same tool compares any two label columns, which is how the
model-vs-model figure in [annotation-guideline.md](annotation-guideline.md)
was produced:

```bash
.venv-plp/bin/python3 -m train.agreement --file data/labeled/candidates.csv \
    --col-a llm_prelabel --col-b base_finbert_label
```

### Then fine-tune

The configuration chosen on 2026-10-01 by cross-validation (8 epochs, the
aspect's readable label as the second segment):

```bash
for seed in 42 1 7; do
  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m train.finetune --seed $seed --epochs 8 --aspect-text label \
      --out-dir models/experiments-2026-10-01/label
done
# each model, their average (mean of probabilities), the three baselines, accuracy by source
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m train.evaluate \
    --model-dir models/experiments-2026-10-01/label/seed_{42,1,7}/final
```

| `train.finetune` option | effect |
|---|---|
| `--epochs N` | upper bound; early stopping (patience 2 on dev macro-F1) usually ends sooner |
| `--aspect-text key\|label` | the aspect as its key (`dividend_policy`, default) or its label from `config/aspects.yaml` |
| `--no-aspect` | sentence only |
| `--class-weights none\|balanced\|prior` | default `none`, plain cross-entropy (what every model before 1 Oct used) |
| `--source-weights` | weight rows so the training source mix matches the corpus |
| `--folds 5 --fold F` | one cross-validation fold: prints dev macro-F1 and keeps no model |
| `--out-dir DIR` | where `seed_<s>/final` goes (default `models/finbert-absa`) |

Each saved model records its input format in `input_format.json`, and
`train.evaluate` feeds it the same way. Both refuse a `candidates.csv` with
duplicated pairs or a sentence in both splits. Report mean and standard
deviation across the seeds — a single run's F1 can be seed noise at this data
size. Choose configurations on cross-validation, never on the test split.
Models land in `models/` (gitignored, about 440 MB each); share them through
the team folder with the checksums in the evidence, not git. Results:
[evidence/finetune-fixes-2026-10-01.md](evidence/finetune-fixes-2026-10-01.md)
(earlier: [finetune-experiments-2026-09-30.md](evidence/finetune-experiments-2026-09-30.md)).

### The LLM aspect classifier

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.llm_classify --eval                              # llama3.1:8b
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.llm_classify --eval --model qwen3:4b --no-think
caffeinate -i .venv-plp/bin/python3 -m aspects.llm_classify --corpus --model llama3.1:8b          # every sentence without an answer yet (44,345 were classified on 3 Oct; the 1,499 added on 11 Oct, broker research and refilled Reddit comments, are not)
```

`--eval` classifies the 1,277 labelled sentences through local Ollama and
scores them against the human aspect: about 40 minutes for `llama3.1:8b`, 30
for `qwen3:4b`. `--no-think` is needed for qwen3, whose hidden reasoning
otherwise takes minutes a sentence. `--corpus` classifies every corpus
sentence in a fixed random order: about a day for `llama3.1:8b`, longer with
another job running on the Mac at the same time.

Answers are cached in `data/aspect_llm/<model>.<prompt>.jsonl` (gitignored),
so an interrupted run resumes with the same command and new sentences are
the only ones classified. `<prompt>` is a hash of the aspect keys,
definitions, examples and instructions (`96efe244` on 2 Oct). The definitions
(`llm_definition`), the examples (`llm_examples`) and the model (`llm_model`)
are in `config/aspects.yaml`; a test pins the hash, so a change to them is
deliberate. Change any of them and the next run starts a new file, so the corpus needs a full redo;
change them back and the old file is used again. Each run prints its cache
file. Neither command writes to the database; applying the answers to it is a
team decision ([evidence](evidence/llm-aspect-classifier-2026-10-01.md)).

### The index preview (reads only)

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.preview --n 11000 --cpu
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.preview --n 44345 --cpu --margin 0.13   # whole corpus, neutral margin
```

Shows the index four ways: today's centroid aspects or the LLM's, each with
base FinBERT or the fine-tuned average. It uses the LLM's cached answers for
the sampled sentences and asks Ollama for any that are missing. The
fine-tuned probabilities are saved in `data/preview/scores.<key>.jsonl`
(`<key>` names the models and the device), so a stopped run resumes and a
second margin takes minutes. Use `--cpu`: on 1 Oct the GPU returned garbage
under memory pressure (the run now stops if that happens). The whole corpus
takes about half a day on the CPU. `--llm-only` skips the centroid pairs
with the fine-tuned models (the slow scenario); `--per-seed` also scores the
LLM-aspect pairs with each model alone and prints the spread between seeds;
`--models` takes another set of models, whose output files carry their
experiment date. Results go to `data/preview/index_preview*.csv`
([evidence](evidence/index-preview-2026-10-01.md)).

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.preview --n 44345 --cpu --margin 0.13 --llm-only --per-seed
```

### The Opus labeller

Opus 5.5 labelled the 1,277 sentences as an additional rater through Claude
Code subagents, each given one instructions file and one batch from
`data/labeled/llm_rater/` (DESIGN decision 22). The answers are kept; to rebuild
the merged file and the review queues:

```bash
.venv-plp/bin/python3 -m train.rater_labels merge
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m train.rater_labels score --centroid
```

People settle the disagreements in `data/labeled/llm_rater/review_aspect.csv`
and `review_sentiment.csv` (the `decision` column); nothing changes
`candidates.csv` automatically
([evidence](evidence/llm-rater-2026-10-01.md)).

### Running on a Colab GPU

The code picks CUDA automatically (`config/device.py`), so nothing needs
patching on Colab. In a notebook:

```bash
!git clone https://github.com/Gavingyh/plp-project.git   # or upload a zip if the repo is private
%cd plp-project
!pip install -q -r requirements.txt
# upload data/plp.db (restore it from the snapshot, README "Getting the database")
!python -m aspects.assign && python -m sentiment.score && python -m aggregate.index
!for s in 42 1 7; do python -m train.finetune --seed $s --epochs 8 --aspect-text label; done
!python -m train.evaluate --model-dir models/finbert-absa/seed_42/final models/finbert-absa/seed_1/final models/finbert-absa/seed_7/final
```

Download `models/` and the updated `data/plp.db` afterwards; a Colab runtime
forgets both. The notebooks the team used are in [notebooks/](../notebooks/README.md);
commit a notebook only with its outputs cleared, since outputs carry corpus
text (`tests/test_notebooks.py` checks).

---

## Troubleshooting

| symptom | cause | fix |
|---|---|---|
| `ModuleNotFoundError: torch` | wrong interpreter (system Python) | use `.venv-plp/bin/python3` |
| `TypeError: unsupported operand \|` | conda Python 3.9 | use `.venv-plp/bin/python3` |
| Step hangs, near-zero CPU | HuggingFace metadata check | `HF_HUB_OFFLINE=1` |
| `Could not reach Ollama` | Ollama not running | `ollama serve` |
| Chatbot says the model `went silent for 120 seconds` | the computer is short of memory, so the local model is loading or writing very slowly | close other heavy programs and stop any other model job, then ask again; `ollama ps` shows whether the model is loaded |
| API returns `insufficient_data` everywhere | pipeline not run, or no database restored | restore the snapshot (README), or run steps 1–5 above |
| Chatbot answer has a verification warning | model fabricated citations | don't trust it; try a hosted backend |
| `pip: bad interpreter` | venv was created under an older directory name | use `.venv-plp/bin/python3 -m pip` |
