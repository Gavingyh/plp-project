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

### UOB earnings — fetched from the Wayback Machine

UOB's IR site sits behind an F5 WAF that answers any scripted request with a
199-byte challenge stub (`Request Redirected` / `TS.request.ID`), so
`ingest.earnings_fetch` cannot reach it the way it reaches DBS and OCBC.

The Wayback Machine holds captures of the same PDFs at their original UOB
URLs and is not behind that WAF, so fetch them from there instead:

```bash
.venv-plp/bin/python3 -m ingest.uob_wayback_fetch --dry-run   # preview
.venv-plp/bin/python3 -m ingest.uob_wayback_fetch             # ~67 PDFs, 2020-2025
.venv-plp/bin/python3 -m ingest.earnings                      # extract prose
```

The bytes are UOB's own published PDFs; only the transport differs. Two
limits are worth knowing: archive coverage thins out for the most recent
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

---

## Interfaces

### Start and stop

```bash
scripts/start.sh              # Ollama (if needed), API, dashboard
scripts/status.sh             # what's running, on which port, healthy or not
scripts/stop.sh               # stop everything this project started
```

Each takes an optional service name — `dashboard`, `api` or `ollama` — to act
on just one. The scripts work from any directory.

Ports come from `PLP_DASHBOARD_PORT` (default 8501) and `PLP_API_PORT`
(default 8000):

```bash
PLP_DASHBOARD_PORT=8511 scripts/start.sh dashboard
```

What the scripts do that the raw commands below don't:

- **Refuse a port they don't own.** If something else is listening, they print
  the owning process and exit rather than starting or killing anything. This
  is not hypothetical: 8501 is a common default and a second Streamlit project
  on the same machine will already be there.
- **Wait for a real health check** before reporting success — `/health` for
  the API, `/_stcore/health` for the dashboard — so a green message means the
  service answers, not merely that a process exists.
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
# Dashboard
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m streamlit run dashboard/app.py

# REST API (docs at http://localhost:8000/docs)
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m uvicorn api.main:app --port 8000

# Chatbot (also available as the dashboard's Chat tab)
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
frontend wants to group or icon them. The Chat tab in the Streamlit
dashboard renders the same list as buttons.

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

### Evaluating the chatbot

```bash
.venv-plp/bin/python3 -m chatbot.run_eval --limit 3   # smoke test
.venv-plp/bin/python3 -m chatbot.run_eval             # full 23-question gold set
```

Runs `chatbot/eval_gold_set.py` against the chatbot and writes:
- `data/eval/chatbot_eval_results.jsonl` — full transcript (question, answer,
  every tool call and its raw result)
- `data/eval/chatbot_eval_summary.md` — automated checks: tool selection,
  advice-decline behaviour, citation-fabrication rate

Whether a stated *number* is correct isn't automated — read the transcript
for that; free-text extraction is less trustworthy than the check itself.

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

246 tests. No network calls — external APIs are mocked with captured real
payloads, so a provider changing its response shape surfaces as a failing test
rather than a silent production break.

Runtime depends on what else the machine is doing: about 60 seconds idle, and
2.5 minutes measured while a local model evaluation ran alongside it. Roughly
35 seconds of that is `umap`/`hdbscan` import cost (numba), paid once per run
by the aspect-discovery tests.

---

## Labelling workflow

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
.venv-plp/bin/python3 -m preprocess.export_blind_test               # write the blind sheet
.venv-plp/bin/python3 -m preprocess.export_blind_test --check-leakage  # what's withheld, and why
.venv-plp/bin/python3 -m preprocess.export_blind_test --merge       # merge the filled sheet back
```

`data/labeled/test_blind.csv` carries the sentence, its aspect and its
provenance and nothing else. Fill in `label`, and `flag` for rows that
shouldn't be scored at all — expect some, since a known limitation is that
sentences mentioning a bank incidentally still enter the corpus.

### Check agreement before splitting up the work

Two annotators label the same ~150 rows independently, then:

```bash
.venv-plp/bin/python3 -m train.agreement --a alice.csv --b bob.csv
.venv-plp/bin/python3 -m train.agreement --a alice.csv --b bob.csv --show-disagreements 20
```

Target is Cohen's κ ≥ 0.6. Below that, the guideline is ambiguous somewhere
rather than an annotator being careless — find the disagreements, tighten the
guideline, re-label the sample. Watch the gap between raw agreement and κ:
this corpus is 87% neutral under base FinBERT, so two annotators who both
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

```bash
.venv-plp/bin/python3 -m train.finetune --seed 42
.venv-plp/bin/python3 -m train.evaluate --model-dir models/finbert-absa/seed_42/final
```

Neither runs until `label` is filled in. Report mean and standard deviation
across at least three seeds — a single run's F1 can be seed noise at this
data size.

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
