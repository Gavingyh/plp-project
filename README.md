# Retail Investor Sentiment Dashboard — DBS, OCBC, UOB

Aspect-based sentiment analysis of Singapore's three listed banks, built for
the Practice Module of the Graduate Certificate in Practical Language
Processing (NUS-ISS).

The system ingests public text about the three banks (Reddit, news, earnings
releases, analyst consensus), splits it into sentences, assigns each sentence
to a financial aspect, scores sentiment, and exposes the result through a
dashboard, a REST API, and a chatbot that answers questions by querying the
sentiment store.

---

## Documentation

| document | what it covers |
|---|---|
| **[docs/DESIGN.md](docs/DESIGN.md)** | How the system works and **why** it's built this way — the decision log with the evidence behind each choice |
| **[docs/RUNBOOK.md](docs/RUNBOOK.md)** | How to set up and run everything, expected timings, troubleshooting |
| **[docs/STATUS.md](docs/STATUS.md)** | What's done, what isn't, and how to improve it |
| [docs/data-viability.md](docs/data-viability.md) | Evidence appendix — per-source findings from testing each data source |
| [docs/annotation-guideline.md](docs/annotation-guideline.md) | Labelling scheme for the annotation task |
| [API_KEYS.md](API_KEYS.md) | Obtaining each API key |

---

## Read this before quoting any number

- **The blended cross-bank comparison is not currently valid** — earnings
  data exists for DBS and OCBC but not UOB, and earnings text is far more
  positive than other sources. Use the Reddit-only figures for cross-bank
  comparison.
- **No fine-tuned model exists.** All sentiment comes from base FinBERT
  applied zero-shot; the labelled dataset it needs hasn't been created yet.
- **Local chatbot models fabricate citations.** Answers carrying a
  `⚠️ VERIFICATION WARNING` cited evidence that was never retrieved.

Full caveats in [docs/STATUS.md](docs/STATUS.md).

---

## Quick start

```bash
python3 -m venv .venv-plp
.venv-plp/bin/python3 -m pip install -r requirements.txt
.venv-plp/bin/python3 -m spacy download en_core_web_sm
cp .env.example .env
```

Run the pipeline, then the dashboard:

```bash
.venv-plp/bin/python3 run_daily_batch.py
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m preprocess.pipeline
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.assign
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m sentiment.score
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.index
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m streamlit run dashboard/app.py
```

No API key is required — the pipeline runs on Reddit, earnings PDFs and
local models alone. Two things that will otherwise cost you time:
**always invoke `.venv-plp/bin/python3` by path**, and set `HF_HUB_OFFLINE=1`
for FinBERT steps. [docs/RUNBOOK.md](docs/RUNBOOK.md) explains both.

---

## Layout

```
ingest/       Data sources -> documents table
preprocess/   documents -> sentences (the unit of analysis)
aspects/      FinBERT embeddings, taxonomy discovery, aspect assignment
sentiment/    Aspect-sentiment classification
aggregate/    Per-bank/aspect index with volume shrinkage
train/        Fine-tuning + evaluation (awaiting labelled data)
dashboard/    Streamlit UI
api/          FastAPI REST endpoints
chatbot/      Tool-calling agent, RAG retrieval, pluggable model backends
config/       Aspect taxonomy, logging configuration
scripts/      Resumable overnight backfill
data/plp.db   SQLite store (gitignored)
```

## Tests

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest tests/ -q
```
