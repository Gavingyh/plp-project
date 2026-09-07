# Runbook

How to set up and run the system. For why it's built this way, see
[DESIGN.md](DESIGN.md). For what's unfinished, see [STATUS.md](STATUS.md).

Every command below has been executed against this repository, not written
from memory.

---

## Setup

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
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | hosted chatbot model | optional |

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

```bash
# 1. Ingest. Default is a 7-day incremental Reddit pull.
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

### Expected timings

Do not assume a hang. On an M-series Mac with MPS:

| step | time | note |
|---|---|---|
| `run_daily_batch.py` (7-day) | ~2–5 min | network-bound |
| `preprocess.pipeline` | seconds–2 min | scales with new documents |
| `aspects.assign` | **10–20 min** for ~10k new sentences | FinBERT embedding; longer sentences cost more |
| `sentiment.score` | **20–30 min** for ~18k new pairs | FinBERT classification |
| `aggregate.index` | ~2 s | pure SQL + arithmetic |

Steps 3 and 4 only process *new* work, so subsequent runs are fast. Progress
appears in the logs; the log file also captures DEBUG detail
(`data/logs/plp.log`).

---

## One-off ingestion tasks

```bash
# Download earnings PDFs from DBS and OCBC IR sites (~116 files, several minutes)
.venv-plp/bin/python3 -m ingest.earnings_fetch --dry-run   # preview first
.venv-plp/bin/python3 -m ingest.earnings_fetch

# Extract prose from downloaded PDFs into the documents table
.venv-plp/bin/python3 -m ingest.earnings

# Analyst consensus (fast, safe to re-run daily)
.venv-plp/bin/python3 -m ingest.yahoo_analyst
```

**UOB earnings must be downloaded by hand.** Its IR site blocks automated
access. Save its quarterly results PDFs into `data/earnings_pdfs/UOB/` and
`ingest.earnings` will pick them up with the others. This matters — see the
coverage caveat in [STATUS.md](STATUS.md).

### Historical Reddit backfill

For multi-year history, use the chunked script rather than
`run_daily_batch.py --reddit-since`. It commits after each month, so an
interruption doesn't lose the whole run, and it resumes by skipping completed
chunks.

```bash
caffeinate -i .venv-plp/bin/python3 scripts/overnight_backfill.py
```

Progress: `data/backfill_overnight.log` and `data/.backfill_progress.txt`.

---

## Interfaces

```bash
# Dashboard
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m streamlit run dashboard/app.py

# REST API (docs at http://localhost:8000/docs)
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m uvicorn api.main:app --port 8000

# Chatbot
CHATBOT_BACKEND=ollama .venv-plp/bin/python3 -m chatbot.agent "How does the market feel about DBS's dividend policy?"
```

### Chatbot backends

With no API key set, the chatbot uses a local model via Ollama:

```bash
ollama pull llama3.2:3b
ollama serve
```

Set `CHATBOT_BACKEND` to `ollama`, `claude`, `openai` or `gemini` to force
one; otherwise it auto-detects from whichever key is present. Local model
answers may carry a `⚠️ VERIFICATION WARNING` — that means the model cited
evidence it never retrieved, and the answer should not be trusted.

The answer goes to stdout and diagnostics to stderr, so:

```bash
# just the answer
.venv-plp/bin/python3 -m chatbot.agent "..." 2>/dev/null
```

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

144 tests, ~30 seconds. No network calls — external APIs are mocked with
captured real payloads, so a provider changing its response shape surfaces as
a failing test rather than a silent production break.

---

## Labelling workflow (not yet started)

```bash
.venv-plp/bin/python3 -m preprocess.export_candidates --train-dev 800 --test 200
# -> data/labeled/candidates.csv
```

Fill in the `label` column per [annotation-guideline.md](annotation-guideline.md).
The `split=test` rows are randomly sampled and must stay untouched by any
model-assisted process — that is what keeps the eventual evaluation honest.

Then:

```bash
.venv-plp/bin/python3 -m train.finetune --seed 42
.venv-plp/bin/python3 -m train.evaluate --model-dir models/finbert-absa/seed_42/final
```

---

## Troubleshooting

| symptom | cause | fix |
|---|---|---|
| `ModuleNotFoundError: torch` | wrong interpreter (system Python) | use `.venv-plp/bin/python3` |
| `TypeError: unsupported operand \|` | conda Python 3.9 | use `.venv-plp/bin/python3` |
| Step hangs, near-zero CPU | HuggingFace metadata check | `HF_HUB_OFFLINE=1` |
| `Could not reach Ollama` | Ollama not running | `ollama serve` |
| Dashboard: "No sentiment data yet" | pipeline not run | run steps 1–5 above |
| Chatbot answer has a verification warning | model fabricated citations | don't trust it; try a hosted backend |
| `pip: bad interpreter` | venv was created under an older directory name | use `.venv-plp/bin/python3 -m pip` |
