# Retail Investor Sentiment Dashboard — DBS, OCBC, UOB

Aspect-based sentiment analysis of Singapore's three listed banks, built for
the Practice Module of the Graduate Certificate in Practical Language
Processing (NUS-ISS).

The system ingests public text about the three banks (Reddit, news, earnings
releases, analyst consensus), splits it into sentences, assigns each sentence
to a financial aspect, scores sentiment, and exposes the result through a
REST API and a chatbot that answers questions by querying the sentiment
store, and a Streamlit dashboard (`dashboard/`, maintained by a teammate).
The API is the documented interface for any frontend:
[docs/api-integration.md](docs/api-integration.md) is its contract.

---

## Documentation

| document | what it covers |
|---|---|
| **[docs/PLAN.md](docs/PLAN.md)** | What happens between now and submission on 1 Nov 2026: decisions made, open decisions, workstreams by role, week-by-week sequence, and how every component maps to the course |
| [docs/submission-checklist.html](docs/submission-checklist.html) | The same plan as a tickable checklist, split into what only people can do and what AI can do |
| [docs/data-report-2026-09-24.html](docs/data-report-2026-09-24.html) | What the database holds: sources, bank balance, coverage over time, pipeline status, caveats |
| **[docs/DESIGN.md](docs/DESIGN.md)** | How the system works and **why** it's built this way — the decision log with the evidence behind each choice |
| **[docs/RUNBOOK.md](docs/RUNBOOK.md)** | How to set up and run everything, expected timings, troubleshooting |
| **[docs/STATUS.md](docs/STATUS.md)** | What's done, what isn't, and how to improve it |
| **[docs/api-integration.md](docs/api-integration.md)** | For whoever builds the dashboard: running the API, which endpoint feeds which view, example responses, the chat contract, and what the screen must say |
| [docs/report/report-draft.md](docs/report/report-draft.md) | Draft of the report's factual sections, every figure linked to its evidence; conclusions and contributions left to the team |
| **[docs/HANDOFF.md](docs/HANDOFF.md)** | Start here if you're new to the project — read order, open decisions, what needs a human |
| [docs/spec/functional-spec.md](docs/spec/functional-spec.md) | What the system does, for whom, with acceptance criteria and rubric traceability |
| [docs/spec/technical-spec.md](docs/spec/technical-spec.md) | Data model, API contract, module map, configuration, testing |
| [docs/diagrams/README.md](docs/diagrams/README.md) | Twenty-three diagrams of the system (data model, pipeline, sequences, chatbot, labelling, plan), each traced to the code, with a shortlist for the report |
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
- **The fine-tuned model leads base FinBERT on macro-F1, not on accuracy.**
  With the readable aspect label as input it scores test macro-F1 0.604 ±
  0.035 over three seeds (0.615 for the three averaged) against base
  FinBERT zero-shot's 0.571; base FinBERT still has the higher accuracy
  (0.70 against 0.66) and calls far fewer neutral sentences polar
  ([evidence](docs/evidence/finetune-fixes-2026-10-01.md)). All scores in
  the database still come from base FinBERT; switching is a team decision.
- **Local chatbot models fabricate citations.** Answers carrying a
  `⚠️ VERIFICATION WARNING` cited evidence that was never retrieved.
- **Per-aspect scores aren't meaningful yet.** Aspects are matched by
  embedding similarity, which gives a sentence 6.4 of the 10 aspects on
  average, and annotators disagreed with the matched aspect on 86% of
  labelled rows. LLM classification is the replacement: `llama3.1:8b`
  matches the human aspect on 73% of the 1,277 labelled sentences against
  41% for the embedding match
  ([evidence](docs/evidence/llm-aspect-classifier-2026-10-01.md)), but it
  hasn't been run on the corpus yet (DESIGN decisions 16 and 21).
- **News volume over time is a sampling artefact.** Google News favours recent
  articles; normalise per month before comparing periods.

[docs/STATUS.md](docs/STATUS.md) is the single source of truth for these
caveats — this list is a summary.

---

## Quick start

**You need Python 3.10 or newer** (developed and tested on 3.14). Check with
`python3 --version`. On a Mac the built-in `python3` is 3.9, and
`pip install` then fails with `No matching distribution found for
torch>=2.9.0`; install a newer Python from python.org or Homebrew and create
the environment with it, e.g. `python3.14 -m venv .venv-plp`.

1. Install:

   ```bash
   python3 -m venv .venv-plp
   .venv-plp/bin/python3 -m pip install -r requirements.txt
   .venv-plp/bin/python3 -m spacy download en_core_web_sm
   cp .env.example .env
   ```

2. Restore the database from the latest snapshot (see
   [Getting the database](#getting-the-database) below).

3. Start the interfaces:

   ```bash
   scripts/start.sh     # the REST API + Ollama, with health checks
   scripts/status.sh    # what's up, on which port
   scripts/stop.sh      # stop it again
   ```

   The API uses port 8000 (interactive docs at `http://localhost:8000/docs`).
   If it's taken, the script says so; choose another with
   `PLP_API_PORT=8100 scripts/start.sh`. To try the chatbot in the terminal:
   `.venv-plp/bin/python3 -m chatbot.chat`.

The snapshot already holds the processed corpus. To refresh or rebuild it,
run the pipeline (order matters — each step consumes the previous one's
output):

```bash
.venv-plp/bin/python3 run_daily_batch.py
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m preprocess.pipeline
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.assign
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m sentiment.score
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aggregate.index
```

No API key is required — the pipeline runs on Reddit, earnings PDFs and
local models alone. Two things that will otherwise cost you time:
**always invoke `.venv-plp/bin/python3` by path**, and set `HF_HUB_OFFLINE=1`
for FinBERT steps. [docs/RUNBOOK.md](docs/RUNBOOK.md) explains both.

---

## Getting the database

`data/plp.db` (198.5 MB restored from the latest snapshot) is too large for GitHub, so it isn't in the repo.
Download the latest snapshot from the team's shared folder, then:

```bash
gunzip -c plp-2026-09-30.db.gz > data/plp.db
shasum -a 256 plp-2026-09-30.db.gz   # should match the checksum below
```

| snapshot | size | sha256 | contents |
|---|---|---|---|
| `plp-2026-09-30.db.gz` (latest; the frozen corpus) | 41.5MB | `e238338726c7da661496d99b2c14a998588fd007d1f189a0690cc67f657dd3f0` | Same documents and sentences as the snapshot below (28,002 and 44,345), re-assigned to the 10-aspect taxonomy (281,744 sentence–aspect pairs, [docs/DESIGN.md](docs/DESIGN.md), decision 21), re-scored with base FinBERT, and the index rebuilt counting each sentence once in its cross-aspect rows. The corpus is frozen from here ([docs/PLAN.md](docs/PLAN.md), D5) |
| `plp-2026-09-26-v2.db.gz` (superseded) | 28.9MB | `f6aac79a212368747abd14382838e2bb639ea25366df74015a1ffe6208e4a62b` | 28,002 documents, 44,345 sentences, to 25 Sep: the snapshot below plus 207 CNA articles from 2023 on ([docs/DESIGN.md](docs/DESIGN.md), decision 20); every sentence embedded, aspect-tagged and baseline-scored under the four-aspect taxonomy; index recomputed |
| `plp-2026-09-26.db.gz` (superseded) | 28.0MB | `3d2417d89eccd7fc21dd7e365f77445e0f0bfc869cc8f30301d50df1fd88fa45` | 27,795 documents, 42,746 sentences, to 25 Sep; every sentence embedded, aspect-tagged and baseline-scored; index recomputed; before CNA |
| `plp-2026-09-24-v2.db.gz` (superseded) | 28.0MB | `cd3aceff1e8c865ca9b64209b4088dec4913eaed2984497036d318117b469fb0` | 27,737 documents, 42,690 sentences; news backfilled to 2023-01; every sentence embedded, aspect-tagged and baseline-scored; index recomputed ([docs/data-report-2026-09-24.html](docs/data-report-2026-09-24.html)) |
| `plp-2026-09-24.db.gz` (superseded) | 26.8MB | `f317cf87fb9250a715480c8ee0554d780edbf8ddd19f240be11951ea1d6f2489` | same day, before embeddings, aspects, sentiment and index were run on the news |

`data/sentence_embeddings.npz` isn't shared either. It is a cache that
`python -m aspects.embed_store` rebuilds from the database.

### Sharing the data and models

What a teammate needs, beyond `git clone` and the Quick start:

| file | needed for | size |
|---|---|---|
| the latest snapshot (`plp-2026-09-30.db.gz`) | everything: unpack to `data/plp.db` | 41.5 MB |
| `data/sentence_embeddings.npz` | the chatbot's evidence search (without it, search falls back to word overlap) | 127 MB |
| the three fine-tuned models | only to reproduce the sentiment results or re-score with them; the database holds base FinBERT's scores | 3 × 438 MB |

`scripts/share_bundle.sh OUT_DIR [--with-models]` copies these into one
folder with a `SHA256SUMS` file (check with `shasum -a 256 -c SHA256SUMS`);
the models go to `models/experiments-2026-10-01/label/seed_*/final/` on the
receiving side. FinBERT downloads from Hugging Face on first use, and each
machine pulls its own Ollama models. Never share `.env` (API keys) or
`data/cna/` (CNA's articles).

The models are also in a private Hugging Face model repo,
`plp-bank-sentiment/plp-finbert-absa`, open to the organisation's members
(ask to be added); [docs/model-card.md](docs/model-card.md) is its
`README.md`. `hf` is installed in the project's environment, not on your
PATH. Log in with your own token, download, and check the checksums against
the table at the end of the model card:

```bash
.venv-plp/bin/hf auth login
.venv-plp/bin/hf download plp-bank-sentiment/plp-finbert-absa --local-dir models/experiments-2026-10-01/label
shasum -a 256 models/experiments-2026-10-01/label/seed_*/final/model.safetensors
```

To upload a new version, leave `training_args.bin` out (it records a local
path):

```bash
for s in 42 1 7; do
  .venv-plp/bin/hf upload plp-bank-sentiment/plp-finbert-absa models/experiments-2026-10-01/label/seed_$s/final seed_$s/final \
      --exclude "training_args.bin" --private
done
.venv-plp/bin/hf upload plp-bank-sentiment/plp-finbert-absa docs/model-card.md README.md --private
```

The database stays on the team drive: it holds CNA and Reddit text and isn't
ours to publish.

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

To run the daily batch (news, Reddit, analyst consensus) every morning on a
Mac, install the launchd job (not running anywhere since 2026-09-26) in
[scripts/com.plp.dailybatch.plist](scripts/com.plp.dailybatch.plist); the
file's header has the install, run-now and remove commands. Output goes to
`data/logs/daily_batch.log`.
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

### Loading CNA into the database

The RSS feed only holds the latest items, so for history use
`ingest/cna_archive.py`. It finds CNA articles whose URL names a bank (from
the Wayback Machine's index of CNA URLs), fetches each one's full text from
CNA at the 10-second crawl delay CNA's robots.txt asks for, and loads them
through the same news filter as every other source, as `source = 'cna'`.
Fetched text is cached in `data/cna/` (gitignored), so a re-run resumes.

```bash
.venv-plp/bin/python3 -m ingest.cna_archive --since 2023-01-01 --until 2026-09-26 --dry-run
.venv-plp/bin/python3 -m ingest.cna_archive --since 2023-01-01 --until 2026-09-26
# the RSS scraper's output loads the same way:
.venv-plp/bin/python3 -m ingest.cna_archive --from-json ingest/cna_articles.json
```

Then run the pipeline steps in `docs/RUNBOOK.md`.

---

## Layout

```
ingest/       Data sources -> documents table
preprocess/   documents -> sentences (the unit of analysis), labelling exports
aspects/      FinBERT embeddings, taxonomy discovery, aspect assignment, the LLM aspect classifier
sentiment/    Aspect-sentiment classification
aggregate/    Per-bank/aspect index, volume shrinkage, time series
train/        Fine-tuning, evaluation, pre-labelling, annotator agreement, the Opus labeller
api/          FastAPI REST API: the interface a dashboard builds on (docs/api-integration.md)
chatbot/      Tool-calling agent, RAG retrieval, pluggable model backends, a terminal chat for testing
config/       Aspect taxonomy, logging configuration
scripts/      start/stop/status, resumable overnight backfill, the sharing bundle
notebooks/    The text-analytics workstream's Colab notebooks (outputs cleared)
learning/     Study material on the concepts and techniques used
docs/spec/    Functional and technical specifications
docs/evidence/  Dated outputs backing claims in the docs
docs/diagrams/  Twenty-three diagrams, each traced to the code
data/labeled/ Human labels; data/labeled/claude/ holds the Opus labeller's answers
data/plp.db   SQLite store (gitignored; see Getting the database)
```

## Tests

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest tests/ -q   # 797 tests; 10 are known bugs marked xfail
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest -q          # 844: adds the diagram and notebook checks
```
