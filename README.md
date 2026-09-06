# plp-project

Retail Investor Sentiment Dashboard for Singapore's three listed banks —
DBS, OCBC, UOB. Practice Module project, Graduate Certificate in Practical
Language Processing (NUS-ISS). See `.project-context/proposal/` for the full
proposal and `.project-context/plan/mvp-implementation-plan.md` for the
phased implementation plan this codebase follows.

## Status (2026-09-06)

End-to-end pipeline is wired up and has been run against live data:
ingestion → sentence preprocessing → aspect assignment → sentiment scoring →
aggregation → dashboard → chatbot. **Phase 5's fine-tuned classifier does
not exist yet** — that needs ~1,000 human-labeled examples (Phase 4), which
is annotation-bound work this pipeline can't do on its own. Everything
currently runs on **base FinBERT (zero-shot)** as a placeholder, which is
also the plan's own required baseline #1 — so the comparison you need for
the report falls out for free once the fine-tuned model exists.

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

# 7. Chatbot (needs ANTHROPIC_API_KEY in .env)
python -m chatbot.agent "How does the market feel about DBS's dividend policy?"
```

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
                 earnings PDFs, analyst-view tagging. -> documents table (SQLite).
preprocess/      documents -> sentences (the unit of analysis for everything downstream).
aspects/         FinBERT embeddings (embed.py, embed_store.py — shared with chatbot RAG),
                 discovery (discover.py, offline/manual), assignment (assign.py, every batch).
sentiment/       Aspect-sentiment classification (currently base FinBERT placeholder).
aggregate/       Per-bank/aspect sentiment index, with volume shrinkage.
train/           Fine-tuning + evaluation (Phase 5) — not runnable until labeling is done.
dashboard/       Streamlit app.
chatbot/         Agentic chatbot: tools.py (structured queries + RAG evidence search),
                 retrieval.py (the RAG core — FinBERT embeddings + SQL pre-filter,
                 no vector DB needed at this corpus scale), agent.py (Claude tool-use loop).
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
- Analyst-consensus is a news-derived proxy (broker name + rating language),
  not a real fourth data source — direct SGX/aggregator scraping was tested
  and is bot-protected against non-browser clients.
- Reddit data (via Arctic Shift, a public archive) skews heavily toward DBS
  — roughly 4x OCBC by sentence volume in the current corpus.
- The aspect taxonomy in `config/aspects.yaml` is bootstrapped from a handful
  of seed terms per aspect, not yet validated against real cluster centroids
  from `aspects/discover.py` — early testing shows most sentences match
  multiple aspects near-equally, meaning the centroids aren't discriminating
  well yet. Needs another discovery pass once more data is in.
- Sentiment index currently stores a single all-time snapshot per
  (bank, aspect) — rolling time-series windows aren't implemented.
