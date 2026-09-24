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
| **[docs/HANDOFF.md](docs/HANDOFF.md)** | Start here if you're new to the project — read order, open decisions, what needs a human |
| [docs/spec/functional-spec.md](docs/spec/functional-spec.md) | What the system does, for whom, with acceptance criteria and rubric traceability |
| [docs/spec/technical-spec.md](docs/spec/technical-spec.md) | Data model, API contract, module map, configuration, testing |
| [learning/](learning/) | Study material on the concepts and techniques used, by subject |
| [docs/data-viability.md](docs/data-viability.md) | Evidence appendix — per-source findings from testing each data source |
| [docs/news-data.md](docs/news-data.md) | News dataset: sources, coverage, filter and dedup rules, known gaps, counts by month |
| [docs/annotation-guideline.md](docs/annotation-guideline.md) | Labelling scheme for the annotation task |
| [docs/verification-ledger.md](docs/verification-ledger.md) | Every number in the docs, with the command that produced it |
| [API_KEYS.md](API_KEYS.md) | Obtaining each API key |

---

## Read this before quoting any number

- **Read blended cross-bank figures next to the per-source breakdown.** All
  three banks have earnings coverage now, but DBS carries roughly six times
  the earnings volume of the other two, and earnings text scores far more
  positive than retail chatter.
- **No fine-tuned model exists.** All sentiment comes from base FinBERT
  applied zero-shot; the labelled dataset it needs hasn't been created yet.
  Zero rows are human-labelled.
- **Local chatbot models fabricate citations.** Answers carrying a
  `⚠️ VERIFICATION WARNING` cited evidence that was never retrieved.
- **Aspect assignment is not validated** and the taxonomy decision is open.

[docs/STATUS.md](docs/STATUS.md) is the single source of truth for these
caveats — this list is a summary and every figure in STATUS is traceable
through [docs/verification-ledger.md](docs/verification-ledger.md).

---

## Quick start

```bash
python3 -m venv .venv-plp
.venv-plp/bin/python3 -m pip install -r requirements.txt
.venv-plp/bin/python3 -m spacy download en_core_web_sm
cp .env.example .env
```

Run the pipeline (order matters — each step consumes the previous one's
output):

```bash
.venv-plp/bin/python3 run_daily_batch.py
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m preprocess.pipeline
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.assign
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m sentiment.score
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.index
```

Then start the interfaces:

```bash
scripts/start.sh     # dashboard + API + Ollama, with health checks
scripts/status.sh    # what's up, on which port
scripts/stop.sh      # stop it again
```

No API key is required — the pipeline runs on Reddit, earnings PDFs and
local models alone. Two things that will otherwise cost you time:
**always invoke `.venv-plp/bin/python3` by path**, and set `HF_HUB_OFFLINE=1`
for FinBERT steps. [docs/RUNBOOK.md](docs/RUNBOOK.md) explains both.

---

## Pulling news

```bash
.venv-plp/bin/python run_news_pull.py            # Yahoo, Google News (from 2023-01-01), NewsAPI, Alpha Vantage
.venv-plp/bin/python run_news_pull.py --report   # source × bank × month counts
```

Writes into the `documents` table after a bank-mention check, broker/venue
false-positive masking and cross-source dedup. Rejected articles go to
`data/news_flagged.csv`, not silently away. Safe to re-run. It does not
create `sentences`; run `python -m preprocess.pipeline` afterwards.
[docs/news-data.md](docs/news-data.md) has the sources, rules and gaps.

---

## Running the CNA scraper

`ingest/cna_scraper.py` reads a CNA (Channel News Asia) RSS feed, fetches each
linked article and extracts the full text (not just the RSS summary) with
trafilatura, falling back to a BeautifulSoup heuristic. It is a standalone
script: it writes a JSON or CSV file and does not touch `data/plp.db`.

Its dependencies (`feedparser`, `beautifulsoup4`, `trafilatura`) are in
`requirements.txt`, so the Quick start install covers them.

```bash
# default feed, all items, writes articles.json in the current directory
.venv-plp/bin/python3 ingest/cna_scraper.py

# a specific feed, first 20 items, 2s between requests
.venv-plp/bin/python3 ingest/cna_scraper.py \
    --feed "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936"\
    --limit 20 --delay 2 --output ingest/cna_articles.json

# CSV instead (also inferred from a .csv --output)
.venv-plp/bin/python3 ingest/cna_scraper.py --format csv --output articles.csv
```

| option | default | meaning |
|---|---|---|
| `--feed` | CNA feed URL | RSS feed URL, refer to https://www.channelnewsasia.com/rss for different categories|
| `--limit` | all items | maximum number of articles to fetch |
| `--delay` | `1.5` | seconds to wait between article requests |
| `--output` | `articles.json` | output path |
| `--format` | from `--output` extension, else `json` | `json` or `csv` |

Each record has `title`, `link`, `published`, `feed_summary`, `full_text`,
`author`, `extraction_method` (`trafilatura`, `bs4_fallback` or `none`) and
`error`. Progress goes to stderr, ending with a count of articles extracted
successfully. Articles that fail to fetch or parse are still written, with
`full_text` empty and the reason in `error`.

Only use the output for personal research or archiving; respect CNA's Terms
of Service and copyright before redistributing it.

---

## Layout

```
ingest/       Data sources -> documents table
preprocess/   documents -> sentences (the unit of analysis), labelling exports
aspects/      FinBERT embeddings, taxonomy discovery, aspect assignment
sentiment/    Aspect-sentiment classification
aggregate/    Per-bank/aspect index, volume shrinkage, time series
train/        Fine-tuning, evaluation, pre-labelling, annotator agreement
dashboard/    Streamlit UI (Overview, Heatmap, Time Series, Evidence, Chat)
api/          FastAPI REST endpoints
chatbot/      Tool-calling agent, RAG retrieval, pluggable model backends
config/       Aspect taxonomy, logging configuration
scripts/      start/stop/status, resumable overnight backfill, model comparison
learning/     Study material on the concepts and techniques used
docs/spec/    Functional and technical specifications
docs/evidence/  Dated outputs backing claims in the docs
data/plp.db   SQLite store (gitignored)
```

## Tests

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest tests/ -q   # 251 tests
```
