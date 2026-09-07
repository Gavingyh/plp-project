# plp-project

Retail Investor Sentiment Dashboard for Singapore's three listed banks —
DBS, OCBC, UOB. Practice Module project, Graduate Certificate in Practical
Language Processing (NUS-ISS). See `.project-context/proposal/` for the full
proposal and `.project-context/plan/mvp-implementation-plan.md` for the
phased implementation plan this codebase follows.

## Status (2026-09-07)

End-to-end pipeline is wired up and has been run against live data:
ingestion → sentence preprocessing → aspect assignment → sentiment scoring →
aggregation → dashboard → API → chatbot. **Phase 5's fine-tuned classifier
does not exist yet** — that needs ~1,000 human-labeled examples (Phase 4),
which is annotation-bound work this pipeline can't do on its own. Everything
currently runs on **base FinBERT (zero-shot)** as a placeholder, which is
also the plan's own required baseline #1 — so the comparison you need for
the report falls out for free once the fine-tuned model exists.

The chatbot runs on either a local model (Ollama, no API key — the default
for grading this as a school project) or Claude, selected automatically or
explicitly via `CHATBOT_BACKEND` — see "Running the chatbot" below.

See `docs/data-viability.md` for what's been verified against live data
(what works, what doesn't, and why).

## Setup

```bash
python3 -m venv .venv-plp && source .venv-plp/bin/activate
python3 -m pip install -r requirements.txt
python3 -m spacy download en_core_web_sm
cp .env.example .env   # fill in your own keys — see API_KEYS.md
```

Note: use `python3 -m pip` rather than the `pip` script directly — if this
venv was ever created under a different directory name and the folder later
renamed, the `pip` script's shebang points at the old path and breaks;
`python3 -m pip` always works.

**If a FinBERT-loading step (assign/score/discover) hangs** with a
"sending unauthenticated requests to the HF Hub" warning and near-zero CPU
usage: HuggingFace's rate-limited etag-check can hang once the model is
already cached locally. `export HF_HUB_OFFLINE=1` before running — this was
hit and fixed live during development (see git history).

## Running the pipeline

```bash
# 1. Ingest (news + Reddit). Add --reddit-since 2020-01-01 for a full backfill.
python run_daily_batch.py

# One-time, after adding PDFs to data/earnings_pdfs/<BANK>/*.pdf:
python -m ingest.earnings

# Tag analyst-consensus language in the news stream (proxy, see ingest/analyst_tag.py)
python -m ingest.analyst_tag

# 2. Preprocess: documents -> sentences
python -m preprocess.pipeline

# 3. Aspect discovery (run occasionally, inspect output, update config/aspects.yaml)
python -m aspects.discover

# 3b. Aspect assignment (run every batch, against the frozen taxonomy)
python -m aspects.assign

# 4. Sentiment scoring (currently base FinBERT zero-shot — see Status above)
python -m sentiment.score

# 5. Aggregate into the per-bank/aspect sentiment index
python -m aggregate.index

# 6. Dashboard
streamlit run dashboard/app.py

# 6b. Minimal API, for a frontend other than the Streamlit dashboard
uvicorn api.main:app --reload --port 8000
# interactive docs: http://localhost:8000/docs

# 7. Chatbot — see "Running the chatbot" below for local vs. frontier
python -m chatbot.agent "How does the market feel about DBS's dividend policy?"
```

## Running the chatbot — local model or frontier model

This is a school project: grading it shouldn't require an API key. The
chatbot backend is pluggable (`chatbot/backends/`):

```bash
# Local, free, no API key — needs Ollama installed and a model pulled:
ollama pull llama3.2:3b        # ~2GB, verified tool-calling support, recommended default
ollama serve                   # if not already running
python -m chatbot.agent "How does the market feel about DBS's dividend policy?"

# Frontier model — set ANTHROPIC_API_KEY in .env, then it's picked automatically:
python -m chatbot.agent "..."

# Or force either explicitly:
CHATBOT_BACKEND=ollama python -m chatbot.agent "..."
CHATBOT_BACKEND=claude python -m chatbot.agent "..."
```

With no `ANTHROPIC_API_KEY` set, Ollama is used automatically. Other models
confirmed to support tool-calling via Ollama: `qwen3:4b` (works identically,
but ~7x slower per call — it emits a hidden reasoning chain first),
`gemma3:4b`, `phi4-mini` (tool-calling not yet verified for these two).

**Read `chatbot/agent.py`'s module docstring before trusting local-model
output blindly** — live-testing surfaced small models fabricating entire
"supporting evidence" sections (fake quotes, fake URLs, fake sentence_ids)
that were never actually retrieved. There's a code-level safety net that
detects this and appends a `⚠️ VERIFICATION WARNING` to the response when it
happens, but a warning is a detector, not a fix — if you see one, don't
trust the citations above it. This did not occur with Claude in testing.

## Labeling workflow (Phase 4 — the actual bottleneck)

```bash
python -m preprocess.export_candidates --train-dev 800 --test 200
# -> data/labeled/candidates.csv
```

Open the CSV, fill in the `label` column per `docs/annotation-guideline.md`.
**The `split=test` rows are sampled purely at random and must stay untouched
by any model-assisted process** — see the guideline and the plan's Phase 4
section for why this matters (it's what makes the eventual F1 comparison
against base FinBERT valid rather than inflated).

Once labeled:

```bash
python -m train.finetune --seed 42      # needs data/labeled/candidates.csv filled in
python -m train.evaluate --model-dir models/finbert-absa/seed_42/final
```

## Architecture

```
ingest/          NewsAPI, Alpha Vantage (dead for SGX names, kept for completeness),
                 Arctic Shift (Reddit — PRAW replaced, API access wasn't approved),
                 earnings PDFs, analyst-view tagging (proxy), Yahoo Finance analyst
                 consensus. -> documents / analyst_consensus tables (SQLite).
preprocess/      documents -> sentences (the unit of analysis for everything downstream).
aspects/         FinBERT embeddings (embed.py, embed_store.py — shared with chatbot RAG),
                 discovery (discover.py, offline/manual), assignment (assign.py, every batch).
sentiment/       Aspect-sentiment classification (currently base FinBERT placeholder).
aggregate/       Per-bank/aspect sentiment index (7d/30d/all_time windows), volume shrinkage.
train/           Fine-tuning + evaluation (Phase 5) — not runnable until labeling is done.
dashboard/       Streamlit app (reference UI).
api/             Minimal FastAPI app over the same data, for any other frontend.
chatbot/         Agentic chatbot: tools.py (structured queries + RAG evidence search +
                 argument type-coercion for local models), retrieval.py (the RAG core —
                 FinBERT embeddings + SQL pre-filter, no vector DB needed at this corpus
                 scale), agent.py (tool-use loop + citation-fabrication safety net),
                 backends/ (pluggable Claude / local-Ollama model).
data/plp.db      SQLite store for everything above (gitignored).
```

## Files

- `requirements.txt` — all dependencies across every phase
- `.env.example` — copy to `.env` and fill in keys (never commit `.env`)
- `API_KEYS.md` — how to get each API key
- `run_daily_batch.py` — single entrypoint for scheduled ingestion (cron-able)
- `docs/data-viability.md` — live-tested findings on each data source
- `docs/annotation-guideline.md` — labeling instructions for Phase 4
- `config/aspects.yaml` — the frozen aspect taxonomy (currently seeded from
  the proposal's a-priori aspects, pending refinement from `aspects/discover.py`
  output on a larger corpus)

## Known limitations (see docs/data-viability.md for detail)

- Alpha Vantage has zero SGX coverage — confirmed live, not just assumed.
- NewsAPI free tier: ~1 month lookback, and only title+description text
  (the `content` field is truncated).
- News-derived analyst-tag proxy (`ingest/analyst_tag.py`) still returns 0
  matches — largely superseded by `ingest/yahoo_analyst.py` (real consensus
  ratings + price targets from Yahoo Finance, an unofficial but verified-live
  API), kept as-is rather than removed since its 0-match result is itself a
  documented finding. Direct SGX/aggregator scraping was tested and is
  bot-protected against non-browser clients either way.
- Reddit data (via Arctic Shift, a public archive) skews heavily toward DBS
  — roughly 3x OCBC by sentence volume in the current corpus.
- The aspect taxonomy in `config/aspects.yaml` is seeded from the proposal's
  4 a-priori aspects; `aspects/discover.py` found the real corpus splits along
  a coarser axis (consumer-banking-service vs. investment-discussion) instead
  — see the file's header comment for the decision this raises.
- `get_trend` compares two discrete windows (7d vs. 30d), not a continuous
  day-by-day time series.
- Local chatbot models (via Ollama) have been observed fabricating citations
  — see "Running the chatbot" above. A code-level safety net catches and
  flags it, but doesn't make the local model actually reliable at citing
  evidence; treat any `⚠️ VERIFICATION WARNING` as "don't trust this answer."
