# Runtime: what runs where

Which processes run on one machine, their ports, and which files each reads or writes. For whoever installs, demos or debugs the system.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
flowchart TB
  accTitle: Runtime view
  accDescr: The services started by scripts/start.sh or by Docker, the batch commands, and the local files each reads or writes. The dashboard reads everything through the API; the API asks Ollama to sort each question and OpenAI, by default, to answer it.

  subgraph services["Services: scripts/start.sh, or Docker (compose.yaml)"]
    dash["Streamlit dashboard<br/>port 8501"]
    api["FastAPI REST API and chatbot<br/>port 8000"]
    oll["Ollama<br/>port 11434"]
  end

  hosted["OpenAI API<br/>answers by default"]

  subgraph files["Local files in data/"]
    zip["data.zip<br/>the shared dataset, not in git"]
    db[("plp.db<br/>SQLite, not in git")]
    emb[("sentence_embeddings.npz<br/>FinBERT vectors, not in git")]
    semb[("search_embeddings.npz<br/>evidence search, not in git")]
    flagged["news_flagged.csv<br/>news filter log"]
    snaps["snapshots/*.db.gz<br/>not in git"]
  end

  subgraph batch["Batch commands, run by hand or from the dashboard"]
    pull["Ingestion<br/>run_news_pull.py, run_daily_batch.py,<br/>ingest.sgx_research_extract"]
    pipe["Pipeline steps<br/>preprocess, aspects, sentiment, aggregate"]
  end

  plist["launchd daily job<br/>not installed"]

  dash -- "every view, the chat<br/>and pipeline runs" --> api
  api -- "reads scores, evidence" --> db
  api -- "evidence search" --> semb
  api -- "sorts each question;<br/>answers if chosen" --> oll
  api -- "answers; never Reddit text" --> hosted
  api -- "starts a run in a worker" --> pipe
  zip -- "restored by docker.bootstrap" --> db
  pull -- "writes documents" --> db
  pull -- "logs decisions" --> flagged
  pipe -- "reads and writes" --> db
  pipe -- "updates" --> emb
  pipe -- "updates" --> semb
  db -- "checkpoint and gzip, by hand" --> snaps
  snaps -- "scripts/share_bundle.sh" --> zip
  plist -. "would run" .-> pull

  classDef inactive stroke-dasharray: 5 5,color:#555,fill:#fafafa;
  class plist inactive;
```

Rendered for the report: [SVG](img/02-runtime.svg) · [PNG](img/02-runtime.png)

## What this shows and doesn't show

Ports are the defaults; each can be changed with `PLP_DASHBOARD_PORT`, `PLP_API_PORT`
or `OLLAMA_BASE_URL`. The dashboard reads every view, chats and starts pipeline runs only
through the API. For each chat question the API asks Ollama to sort it, then OpenAI (the
default) or Ollama to answer it (see [01](01-system-context.md)); a hosted model is never
sent Reddit text. A pipeline run started from the dashboard goes to a worker that runs the
batch steps in order (`POST /pipeline/runs`, `pipeline/runner.py`; [06](06-batch-pipeline.md)).
Under Docker (`compose.yaml`) the API, the dashboard and Ollama run in containers, and a
setup container first restores `data.zip` into `data/` ([18](18-snapshots.md)). Every
process also writes to `data/logs/plp.log`, which git ignores; those arrows are left out to
keep the picture readable. `news_flagged.csv` is committed to git as the audit trail of the
news filter; the database, the vector files, the snapshots and `data.zip` are not. The
launchd job is a template in `scripts/` that is not installed on any machine.

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| dashboard port 8501 | `scripts/start.sh:33` | `DASHBOARD_PORT="${PLP_DASHBOARD_PORT:-8501}"` |
| API port 8000 | `scripts/start.sh:34` | `API_PORT="${PLP_API_PORT:-8000}"` |
| Ollama port 11434 | `scripts/start.sh:35` | `OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"` |
| dashboard process | `scripts/start.sh:185` | `-m streamlit run dashboard/app.py` |
| API process | `scripts/start.sh:193` | `-m uvicorn api.main:app` |
| Ollama started if needed | `scripts/start.sh:201` | `start_ollama() {` |
| plp.db location | `ingest/db.py:17` | `DB_PATH = os.path.join(BASE_DIR, "data", "plp.db")` |
| embeddings cache location | `aspects/embed_store.py:34` | `STORE_PATH = os.path.abspath(os.environ.get("PLP_EMBEDDINGS_PATH")` |
| search vectors location | `chatbot/search_vectors.py:32` | `STORE_PATH = os.path.abspath(os.environ.get("PLP_SEARCH_EMBEDDINGS_PATH")` |
| news filter log location | `ingest/news_filter.py:52` | `FLAGGED_PATH = os.path.join(BASE_DIR, "data", "news_flagged.csv")` |
| dashboard reads only through the API | `dashboard/api_client.py:39` | `base_url = (os.getenv("PLP_API_URL") or default_url).rstrip("/")` |
| API reads the database | `api/main.py:42` | `from ingest.db import get_connection` |
| evidence search reads the search vectors | `chatbot/retrieval.py:175` | `all_ids, all_vecs = load_for_search()` |
| dashboard chat goes through the API | `dashboard/chat.py:47` | `"/chat",` |
| API chat | `api/main.py:31` | `from chatbot.agent import Conversation` |
| database not in git | `.gitignore:21` | `data/plp.db` |
| embeddings not in git | `.gitignore:24` | `data/sentence_embeddings.npz` |
| search vectors not in git | `.gitignore:25` | `data/search_embeddings.npz` |
| snapshots not in git | `.gitignore:26` | `data/snapshots/` |
| data.zip not in git | `.gitignore:9` | `data/data.zip` |
| data.zip built from the latest snapshot | `scripts/share_bundle.sh:28` | `data/snapshots/plp-*.db.gz` |
| data.zip restored by the setup step | `docker/bootstrap.py:26` | `RUNTIME_FILES = {"plp.db"` |
| Docker: setup, then the services | `compose.yaml:46` | `command: ["python", "-m", "docker.bootstrap"]` |
| Docker: the dashboard container | `compose.yaml:101` | `"127.0.0.1:${PLP_DASHBOARD_PORT:-8501}:8501"` |
| OpenAI answers by default | `config/chatbot.yaml:5` | `backend:          {value: "openai", env: CHATBOT_BACKEND}` |
| a hosted model never sees Reddit text | `chatbot/backends/base.py:99` | `def withhold_reddit(name: str, content):` |
| the dashboard starts pipeline runs | `dashboard/pipeline_client.py:111` | `request_json("POST", "/pipeline/runs", body=body)` |
| a run goes to a worker | `pipeline/runner.py:7` | `The runner can run in the terminal or as a separate FastAPI-launched worker.` |
| broker research ingestion | `ingest/sgx_research_extract.py:4` | `Reads whatever is in data/sgx_research/*.pdf` |
| launchd job runs the daily batch | `scripts/com.plp.dailybatch.plist:26` | `<string>run_daily_batch.py</string>` |
| launchd job not running | `docs/PLAN.md:42` | `The daily ingestion job is not running on any machine` |
