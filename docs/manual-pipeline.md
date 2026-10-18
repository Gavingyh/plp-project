# Manual PDF pipeline

The manual runner imports selected local PDF sources, completes pending
analysis with the existing trained models, and rebuilds the sentiment index
in `data/plp.db`. It does not train a model or change the selected model version.

Implementation milestones:

1. **Runner (implemented):** reusable orchestration, prerequisite checks,
   persisted progress, file outcomes, process locking and interruption recovery.
2. **FastAPI (next):** launch a worker and expose source/start/status/history
   endpoints. There are no pipeline API endpoints in milestone 1.
3. **Dashboard (later):** Data Management source checkboxes, run button,
   progress/history and refresh of the dashboard's cached API responses.

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
slow inference job has died. Reopening the page in milestone 3 will read this
same persisted status.

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
lock. Neither the API nor dashboard imports the worker in this milestone.

Tests use temporary SQLite databases and embedding files, fake PDF text and
fake model predictions. They exercise the real preprocessing/assignment/
scoring writes and index aggregation without reaching network/model services
or writing to the shared corpus.

```bash
HF_HUB_OFFLINE=1 LOG_FILE=none .venv-plp/bin/python3 -m pytest \
  tests/test_pipeline_runner.py tests/test_pipeline_preflight.py \
  tests/test_earnings_extract.py tests/test_sgx_research_extract.py \
  tests/test_assign_method.py tests/test_finetuned_pass.py -q
```
