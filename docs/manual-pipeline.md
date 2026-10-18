# Manual PDF pipeline

The manual runner imports selected local PDF sources, completes pending
analysis with the existing trained models, and rebuilds the sentiment index
in `data/plp.db`. It does not train a model or change the selected model version.

Implementation milestones:

1. **Runner (implemented):** reusable orchestration, prerequisite checks,
   persisted progress, file outcomes, process locking and interruption recovery.
2. **FastAPI (implemented):** launch a separate worker and expose
   source/start/status/history endpoints, with HTTP 202/409/503 handling.
3. **Dashboard (implemented):** Data Management source checkboxes, run button,
   progress/history and refresh of the dashboard's cached API responses.

## Run from the dashboard

Open **Data Management** below Ask in the sidebar. Place PDFs in the listed
folders on the API host, select Bank earnings PDFs, Broker research PDFs, or
**All PDF sources**, then click **Run selected sources**. The All checkbox
selects both local PDF sources; individual choices and All stay in sync.
Online news and Reddit collectors are separate workflows in this milestone.
This writes to the configured
database, normally `data/plp.db`. It uses the existing trained models and
completes all pending analysis; selecting a folder limits imports only.

The page shows each folder's PDF inventory, not an estimate of new documents.
The source-selection and recent-activity panels have equal widths and stretch
to the same height on wider screens; they stack on narrow screens. The run
selector sits inside the activity panel so both panel headings align.
Completed stage lists are collapsed by default; active and failed runs show
their stages immediately. Cards show compact folder names;
**Folder locations** reveals the absolute paths returned by the API. Those
paths are derived from each checkout's location, not a particular user's
home directory. For example, a checkout under `/srv/bankpulse` reads earnings
from `/srv/bankpulse/data/earnings_pdfs`; another checkout can be elsewhere.
The relative `data/earnings_pdfs` and `data/sgx_research` layout is fixed by
the existing extractors. In a remote setup, use the API machine's folders.

A missing folder cannot be selected. An existing empty folder can still be
selected to resume pending database work. The worker checks the database,
models and other prerequisites after the run is accepted.

The six stages update every two seconds while the page is open. Progress
counts completed stages; it is not an estimate of elapsed or remaining time.
New-document and already-stored-PDF counts, warnings, file outcomes, stage
metrics and the imported document manifest are available in run details.
The latest 20 runs are loaded from the API, including after a page refresh.
Older records remain on disk. There is no cancel/delete control in this version.

Run controls are disabled while a job is queued/running or its status cannot
be checked. The API also rejects concurrent starts. HTTP 409, launch failures
and lost responses show a **Check run status** action. Starts are never
retried automatically; checking, polling and navigation make GET requests.
Review the saved history before explicitly starting another run.

Other tabs show an update-in-progress notice while a run is active. Scores
remain at the last computed index until aggregation; evidence may change as
earlier stages commit. On completion, cached index, evidence, source, series,
trend, analyst and suggestion responses are cleared and the page reloads.
Failure/interruption also clears caches because earlier stages can have
committed data. The conversation and user selections remain intact; existing
chat answers retain their original text and are not regenerated.

Data Management remains accessible when the sentiment index is empty or its
endpoint fails. The API must still be reachable to start or inspect a run.
Status polling uses Streamlit [fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment),
so charts and the conversation are not rebuilt on every progress poll.

## Select sources and run

Put files in the existing locations. The runner does not upload PDFs or
download online news, Reddit, earnings or research reports.

| Source key | Files read |
|---|---|
| `earnings` | `data/earnings_pdfs/DBS/*.pdf`, `OCBC/*.pdf`, `UOB/*.pdf` |
| `sgx_research` | `data/sgx_research/*.pdf` |

From the repository root, **these commands perform a real import and write
to the configured database**:

```bash
# One source
.venv-plp/bin/python3 -m pipeline.runner --sources earnings

# Both sources, once each
.venv-plp/bin/python3 -m pipeline.runner --sources earnings sgx_research
```

The existing environment variables still apply: `PLP_DB_PATH` selects the
database (default `data/plp.db`); `PLP_EMBEDDINGS_PATH` selects the sentence
embedding cache (default `data/sentence_embeddings.npz`). Set them before
launching the worker. A missing database is refused rather than created empty.

Source selection controls **imports**. The subsequent preprocessing, topic
assignment and scoring stages finish **all pending work in the database**,
including work from previous failed runs or other sources. The final index
is recomputed from the full stored corpus. Previously scored rows are retained;
there is no full re-score or taxonomy change.

## Start and monitor through FastAPI

Restart the API after installing the milestone 2 code. The API provides
`GET /pipeline/sources`, `POST /pipeline/runs`, `GET /pipeline/runs` and
`GET /pipeline/runs/{run_id}`. See the
[request/response contract](api-integration.md#manual-pipeline-api-milestone-2).

The POST accepts `{"sources": ["earnings", "sgx_research"]}` and returns
HTTP 202 with a queued run and a status URL in `Location`. It does not wait
for model inference. The existing lock is reserved before launch and handed
to the separate worker without an unlocked gap. Another start request gets
409 during both queueing and processing. The process uses the API's Python
interpreter and explicitly inherits its configured DB/embedding paths.

Poll the status URL every two seconds and read history after reconnecting.
GETs never launch another worker. A worker which fails prerequisite checks
is reported as `failed` at its status URL; a failure to launch its process
gives HTTP 503 and a failed saved record. `queued` and `running` are active
states; all other states are terminal. An API restart does not stop its
separate worker. Stopping the worker itself releases the OS lock and its
saved run is recovered as interrupted/failed rather than left active forever.

Startup output is saved to `<run_id>.worker.log`; stage logs remain in
`<run_id>.log`. The API's process reaper records an exit code when it can
acquire the lock. The run status and stage results, not the optional exit
code, determine completion. History returns summaries; the status URL
includes the full file outcomes and import manifest.

## Stages and prerequisites

The order is fixed:

1. **Check prerequisites:** existing database and source folders, Python/PDF
   dependencies, installed `en_core_web_sm`, cached `ProsusAI/finbert`, the
   configured fine-tuned model files, and the configured topic model in Ollama.
2. **Import documents:** call the selected existing PDF extractors and
   `ingest.db.upsert_documents`. Already-stored document IDs are skipped
   before extracting a PDF again.
3. **Prepare sentences:** `preprocess.pipeline.run()`.
4. **Assign topics and update embeddings:** `aspects.assign.run()`.
5. **Score sentiment:** `sentiment.score.run()`, including missing scores
   from the served fine-tuned model as well as the existing base-model pass.
6. **Refresh sentiment index:** `aggregate.index.run()`.

The CLI forces Hugging Face offline mode before loading model libraries. It
does not download missing FinBERT checkpoints. Install/cache the models first;
the three served checkpoints are listed in `config/model_version.py`. Merely
restoring the database is enough for the existing dashboard, but not for
scoring new documents.

If a saved run failed with `Missing dependencies: en_core_web_sm`, install
spaCy's separate English model in the API's Python environment:

```bash
.venv-plp/bin/python3 -m spacy download en_core_web_sm
```

This is the existing setup step in README and RUNBOOK. The UI shows the
command and explains when no import started. A failed record remains an
accurate history entry after setup is fixed; start a new incremental update
to continue. Installing the package does not restart the old job.

Topic assignment currently uses Ollama's `llama3.1:8b`, from
`config/aspects.yaml`. Its address is `OLLAMA_BASE_URL`, default
`http://localhost:11434`. This is independent of the chatbot backend.

The PDF extractors retain their no-argument `pull()` interface and existing
CLI commands. Optional `skip_doc_ids` and `report` arguments let the runner
skip duplicates and persist structured per-file outcomes. Failed extraction,
no usable prose, and earnings filenames without a recognised reporting period
are visible in run warnings. The latter retains the existing import-date
fallback; it is not silently presented as a known publication date.

## Run records and failure behaviour

Records and logs live in `data/run/pipeline/<run_id>.json` and `.log`, already
ignored by Git. They include the selected sources, database/cache paths,
model version, UTC timestamps, current stage, stage results, file outcomes,
warnings and newly inserted document IDs. They survive application restarts
while the data directory is retained.

```bash
# Read the latest 20 records and mark any stopped worker as interrupted.
# This does not collect or analyse data.
.venv-plp/bin/python3 -m pipeline.runner --history
```

Each stage has its own timestamps and metrics. Final run states are
`completed`, `completed_with_warnings`, `failed` or `interrupted`. A stage
failure prevents later stages from starting. File-level extraction failures
are recorded as warnings and the usable files continue through analysis.
Only stages that finished have final metrics; partial file outcomes and the
import manifest remain available if a stage fails midway.

Run records use atomic replacement so a polling reader never reads half a
JSON write. A nonblocking OS file lock allows only one manual pipeline worker
per checkout, including across processes. macOS and Linux (Docker) are
supported; native Windows requires a different lock implementation. The old
standalone ingestion/scoring commands do not acquire this lock: **do not run
them concurrently with the manual runner**. Preflight folder counts are an
inventory, not a count of new/unprocessed documents.

Ctrl+C persists an interrupted run and releases the lock. After a process
crash or SIGTERM/SIGKILL, the OS releases the lock; the next history check or
new run marks the unfinished record interrupted. No timeout guesses that a
slow inference job has died. Reopening Data Management reads this
same persisted status. During API launch, the queued record is protected by
the inherited lock as well, so it is not mistaken for a stopped worker.

Completed database stages are **not rolled back** after a later failure.
Rerun to finish missing work. A candidate document manifest is saved before
insertion and reconciled against committed database rows after failure or
interruption, so a crash immediately after a commit still leaves a trace of
the inserted document IDs. This assumes the manual runner is the only writer;
it is not a general undo operation. Removing test data later also requires
removing dependent sentences/assignments/scores, rebuilding the embedding
cache and recomputing the index. No delete operation is included here.

The CLI prints the final run record as JSON. Exit codes: `0` completed
(possibly with warnings), `1` failed, `2` invalid invocation/startup error,
`3` another manual run is active, `130` interrupted with Ctrl+C.

## Docker setup requirements (planned)

Ryan's setup review on 18 October 2026: downloading the private models,
moving folders and checking three hashes is too much manual setup for the
professor. Docker packaging should automate these steps. This is a future
packaging requirement; no Docker setup command is implemented in milestone 1.

- Provide one documented setup/start entry point instead of separate Python,
  dependency, model-download and folder-move commands.
- Offer a prepared team asset bundle (the existing share script supports
  `--with-models`) so the professor can run with supplied files without a
  Hugging Face login. For a fresh online setup, accept one-time authentication
  for the private model repository.
- Download only `adapted-2026-10-11/`, put all three seeds at the paths in
  `config/model_version.py`, and verify the weights against the model card's
  checksums automatically. Reuse verified local files on later starts.
- Prepare the base FinBERT cache and spaCy model, and check the topic
  classifier's Ollama dependency. Account for native Ollama on a Mac when
  choosing the Compose service layout.
- Persist the database, model files, embeddings and run history across
  container recreation. Install dependencies in the image; keep credentials
  out of the image and source control.
- Show download/setup progress, separate initial setup from normal startup,
  and give an actionable error if authentication, files or checksums fail.

## Review and validation

`pipeline/runner.py` coordinates the stages; `pipeline/stages.py` adapts the
existing functions; `pipeline/jobs.py` owns persisted records and the process
lock. `pipeline/service.py` launches and reaps a separate worker process;
`api/pipeline.py` exposes its HTTP contract. The API does not run the model
stages in its own process. `dashboard/pipeline_client.py` makes uncached HTTP
calls; `dashboard/manage.py` renders controls and polls status. The dashboard
imports no pipeline worker, database or model modules.

Tests use temporary SQLite databases and embedding files, fake PDF text and
fake model predictions. They exercise the real preprocessing/assignment/
scoring writes and index aggregation without reaching network/model services
or writing to the shared corpus.

```bash
HF_HUB_OFFLINE=1 LOG_FILE=none .venv-plp/bin/python3 -m pytest \
  tests/test_pipeline_runner.py tests/test_pipeline_preflight.py tests/test_pipeline_api.py \
  tests/test_earnings_extract.py tests/test_sgx_research_extract.py \
  tests/test_assign_method.py tests/test_finetuned_pass.py \
  tests/test_dashboard_pipeline.py tests/test_dashboard_api_client.py \
  tests/test_dashboard_views.py -q
```
