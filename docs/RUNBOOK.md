# Runbook

How to set up and run the system. For why it's built this way, see
[DESIGN.md](DESIGN.md). For what's unfinished, see [STATUS.md](STATUS.md).

Every command below has been executed against this repository, not written
from memory.

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
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | hosted chatbot model (`OPENAI_API_KEY` with `OPENAI_BASE_URL` for any OpenAI-compatible provider, such as Groq) | optional |

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
    --aspects llm --finetuned --margin 0.13 --cpu
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 scripts/rescore.py --db /tmp/plp-rescore.db --fresh-copy \
    --aspects llm --finetuned --margin 0.13 --cpu --apply
```

Which models and margin: `--version` with a version listed in `FINETUNED`
(`config/model_version.py`) uses that entry's models and margin, and refuses
others, because new sentences are scored with exactly those. Without it, the
1 Oct seeds are used with the margin their entry lists; other models
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

By default the chatbot uses the local demo model, `llama3.1:8b`, via Ollama
(decided 4 Oct), whatever API keys `.env` holds:

```bash
ollama pull llama3.1:8b
ollama serve
```

To use Gemini instead, set `CHATBOT_BACKEND=gemini` (in `.env` or the shell,
for example `CHATBOT_BACKEND=gemini scripts/start.sh api`); `claude` and
`openai` work the same way, each with its own key. `CHATBOT_BACKEND=auto`
picks the first key set (Claude, then OpenAI, then Gemini), as the default
did before 4 Oct.

**Gemini** (`GEMINI_API_KEY`, the team's key is for the chatbot only): the
model comes from `GEMINI_MODEL` or `GEMINI_CHAT_MODEL`, default
`gemini-3.8-flash`; on 2026-09-30 that model and 3.7 kept answering 503 (high
demand) while `gemini-3.6-flash` worked, so set that if 3.8 is busy. The
backend retries a 503 or 429 three times. On the free tier Google may use prompts and responses to improve its
products and people may review them, and its terms say not to send
sensitive, confidential or personal information. Since 4 Oct the Gemini
backend withholds Reddit evidence (text, link and citation) and quoted text
from earlier answers, so Reddit text never reaches it; it still sees news
and earnings evidence. Check the terms again before wider use:
https://ai.google.dev/gemini-api/terms.

**Any OpenAI-compatible provider** (Groq, NVIDIA NIM, OpenRouter, …) goes
through the `openai` backend with its address in `OPENAI_BASE_URL`. For
Groq's free tier: create a key at https://console.groq.com/keys, consider
switching on Zero Data Retention in its Data Controls settings (evidence
searches send Reddit text), and put three lines in `.env`:

```bash
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_API_KEY=<the Groq key>
OPENAI_MODEL=openai/gpt-oss-120b        # or llama-3.3-70b-versatile, qwen/qwen3.8-27b
```

Then set `CHATBOT_BACKEND=openai` to use it (or `auto`, which prefers it
over Gemini). Groq's free tier allowed 8,000
tokens a minute on 2026-09-30, about one question a minute with this
chatbot's prompt and tools; the backend waits out a 429 or 503 (after
Groq's `Retry-After` when sent) four times. Not yet run against Groq: the
first successful answer is this setup's verification.

Two warnings
can be appended to an answer, and both mean "don't trust this part":

- `⚠️ VERIFICATION WARNING`: the model cited evidence (a quote, sentence id or
  URL) it never retrieved, or put words no search returned in quote marks.
  With `CHATBOT_ENFORCE_EVIDENCE` at `strip`, the default, such evidence is
  removed and the quote marks come off such words first (DESIGN decision
  26), so the warning shows only with `off`.
- `⚠️ NUMBER CHECK`: a figure in the answer matches nothing the tools returned
  for that question. The check is strict: a figure the model derived
  legitimately in an unusual way can also trip it, so read the flagged one.

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
| `CHATBOT_BACKEND` | `ollama` (since 4 Oct) | `gemini`, `claude` or `openai` to use a hosted model; `auto` picks the first API key set |
| `OLLAMA_MODEL` | `llama3.1:8b` (since 4 Oct) | the local chatbot model, used when the backend is Ollama (the default) |
| `CHATBOT_INTENT_MODEL` | `llama3.1:8b` | the model that sorts questions into intents |
| `CHATBOT_TEMPERATURE` | `0.2` | decoding temperature on every backend; low for grounded answers |
| `CHATBOT_TRACE_FILE` | unset | if set, each terminal-chat or API turn appends a JSON line: question, answer, tool calls and results, intent, state |
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

### Comparing Ollama, Groq and Gemini without hitting a rate limit

Free tiers limit requests per minute, requests per day and (Groq) tokens per
minute. `chatbot/ratelimit.py` keeps every hosted request under a budget set in
`rate_limits` in `config/chatbot.yaml` (below the providers' published limits),
counts requests over a rolling 24 hours in `data/ratelimit_state.json`, waits
for a provider's `Retry-After`, believes Groq's own remaining-quota headers, and
stops the run if a provider still returns 429 three times in a row. A stopped run
keeps its answers; `--resume` asks only what is left.

```bash
.venv-plp/bin/python3 -m chatbot.provider_eval --dry-run   # what is ready and the request budget; sends nothing
.venv-plp/bin/python3 -m chatbot.provider_eval             # every ready arm, Ollama first
.venv-plp/bin/python3 -m chatbot.provider_eval --resume    # after a stop
.venv-plp/bin/python3 -m chatbot.provider_report           # rebuild docs/evidence/chatbot-provider-eval-<date>.md
```

Keys come from `.env` and are never printed: Groq's from `GROQ_API_KEY`, or from
`OPENAI_API_KEY` when `OPENAI_BASE_URL` points at Groq; Gemini's from
`GEMINI_API_KEY` (a key from aistudio.google.com/apikey, which starts with
`AIza`). The local Ollama arm needs Ollama running with `llama3.1:8b` pulled,
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

2491 tests in `tests/`; `pytest -q` from the repository root runs 2538,
adding the diagram and notebook checks. These are a fresh checkout's counts:
one test runs per gold-set results file in `data/eval/`, so a machine that
holds the results kept out of git (they quote CNA text) collects one more for
each (six on the team's Mac on 6 Oct). A bug that `/validate` confirms gets a
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
