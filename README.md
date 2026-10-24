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
| [docs/manual-pipeline.md](docs/manual-pipeline.md) | Manual updates: local PDFs, Google News and Reddit, stages, prerequisites, persisted run status and failure recovery |
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
- **The index is scored by a fine-tuned model that leads base FinBERT, by a
  modest margin.** Since 12 Oct 2026 the API and the chatbot serve the
  adapted encoder fine-tuned on LLM labels, three seeds averaged. On the 299
  hand-labelled test rows it scores macro-F1 0.670 and accuracy 0.716
  against base FinBERT zero-shot's 0.571 and 0.699. The gain is in negative
  sentences (it finds 59% of them against 21%), paid for with neutral recall
  (0.73 against 0.91), and its precision on negative is 0.48
  ([evidence](docs/evidence/model-rerun-2026-10-11.md)). Base FinBERT's
  scores stay in the database beside it, for comparison.
- **Each sentence has one aspect, chosen by a local LLM.** Until 12 Oct a
  sentence carried every aspect it resembled, 6.4 on average, so per-aspect
  figures from before and after are not comparable
  ([evidence](docs/evidence/rescore-rehearsal-2026-10-12.md)).
- **Recent figures are "as of" the newest stored sentence, 25 Sep 2026.**
  Collection has stopped, so the 7- and 30-day windows count back from that
  date, not from today.
- **Local chatbot models fabricate citations.** Answers carrying a
  `⚠️ VERIFICATION WARNING` cited evidence that was never retrieved.
- **Per-aspect scores aren't meaningful yet.** Aspects are matched by
  embedding similarity, which gives a sentence 6.4 of the 10 aspects on
  average, and annotators disagreed with the matched aspect on 86% of
  labelled rows. LLM classification is the replacement: `llama3.1:8b`
  matches the human aspect on 73% of the 1,277 labelled sentences against
  41% for the embedding match
  ([evidence](docs/evidence/llm-aspect-classifier-2026-10-01.md)). It has
  classified the whole corpus (3 Oct) but isn't applied to the database yet:
  that is a team decision, and `scripts/rescore.py` is ready for it (DESIGN
  decisions 16 and 21).
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
   scripts/start.sh     # Ollama, the REST API and the dashboard, with health checks
   scripts/status.sh    # what's up, on which port
   scripts/stop.sh      # stop it again
   ```

   The API uses port 8000 (interactive docs at `http://localhost:8000/docs`).
   If it's taken, the script says so; choose another with
   `PLP_API_PORT=8100 scripts/start.sh`. To try the chatbot in the terminal:
   `.venv-plp/bin/python3 -m chatbot.chat`.

The chatbot's answer provider is selected on the API server in `.env`:
`CHATBOT_BACKEND=openai` is the default, including when the variable is omitted.
Add `OPENAI_API_KEY`, then restart only the API with `scripts/stop.sh api`
followed by `scripts/start.sh api`. If the key is missing, Ask shows a setup
message and disables chat; the other tabs remain usable. Credentials stay on
the API server. Set `CHATBOT_BACKEND=ollama` explicitly for local answers.
The local intent classifier still uses Ollama with either answer provider.
See [chatbot setup and key instructions](docs/RUNBOOK.md#chatbot-backends).

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

The dashboard's **Data Management** page imports local earnings/research PDFs
and cached CNA articles (`data/cna/articles.jsonl`), and collects Google News/Reddit/NewsAPI
with progress and history. CNA imports do not call Wayback or fetch article pages. Select sources
or **All available sources**, choose collection dates for online sources,
and click **Run selected sources**. Collection defaults to seven UTC days
including today and is limited to 31 days per run. This updates the configured
database using existing trained models; analysis finishes all pending work.
See [manual-pipeline.md](docs/manual-pipeline.md) for source locations,
prerequisites and failure recovery.
NewsAPI is enabled when `NEWSAPI_KEY` is configured in the API machine's ignored
`.env`; it is excluded from All when the key is missing. See [API_KEYS.md](API_KEYS.md).

NewsAPI is optional; the pipeline also runs without API keys on Reddit, earnings PDFs and
local models alone. Two things that will otherwise cost you time:
**always invoke `.venv-plp/bin/python3` by path**, and set `HF_HUB_OFFLINE=1`
for FinBERT steps. [docs/RUNBOOK.md](docs/RUNBOOK.md) explains both.

---

## Getting the database

`data/plp.db` (101.4 MB restored from the latest snapshot) is too large for GitHub, so it isn't in the repo.
Download the latest snapshot from the team's shared folder, then:

```bash
gunzip -c plp-2026-10-14.db.gz > data/plp.db
shasum -a 256 plp-2026-10-14.db.gz   # should match the checksum below
```

| snapshot | size | sha256 | contents |
|---|---|---|---|
| `plp-2026-10-14.db.gz` (latest) | 26.2MB | `2e42aafeaa9d1e219b00359e8b31e7219b0fe1824f0aaaf9b3d2598607a857f0` | The snapshot below with the aspects made again under the wealth rule of 10 Oct (wealth means the priority and private banking tiers): 6,914 of the 45,844 sentences changed aspect, the wealth aspect went from 4,359 sentences to 1,423, and each bank's headline fell by 0.010 to 0.015. Same documents, sentences and models. It needs the code from 14 Oct on, whose aspect prompt it matches ([evidence](docs/evidence/rescore-wealth-wording-2026-10-14.md)) |
| `plp-2026-10-12.db.gz` (superseded; aspects from before the wealth rule) | 26.3MB | `b604bba0d27a9f44934a7af984abc784034824868eadc77a6a3d54f5a7296908` | The snapshot below, re-scored on 12 Oct: one aspect a sentence from the LLM classifier (45,844 sentence–aspect pairs, where there were 291,508); the chosen fine-tuned model's scores beside base FinBERT's (45,844 each); earnings and broker research links made relative to the repository, so no home folder is left in a link; and the index rebuilt with the 7- and 30-day windows ending at the newest sentence, 25 Sep (898 rows, 449 a model). 28,852 documents and 45,844 sentences, as before. It needs the code from 12 Oct on, which serves the fine-tuned model's rows ([evidence](docs/evidence/rescore-rehearsal-2026-10-12.md)) |
| `plp-2026-10-11-v2.db.gz` (superseded; base FinBERT's scores and centroid aspects only) | 43.2MB | `f703d2da4c3ea7b45cfc20ff1dc1ec29425a4778e6473b4262d93dd66a44b310` | The snapshot below with the three approved data repairs: six UOB earnings documents (114 sentences) re-dated from their extraction day to their announcement dates; the Reddit comments lost for September 2021, May 2024 and March 2025 refilled (825 documents, 858 sentences, assigned and scored like the rest); the index rebuilt the same way (580 rows). 28,852 documents, 45,844 sentences, 291,508 sentence–aspect pairs. For the team only. |
| `plp-2026-10-11.db.gz` (superseded the same day) | 42.4MB | `9ca50c4d95ec7d28cda35e0607dc6c138fa3ab2bb863f8099fcd6824b9472b37` | The 30 Sep snapshot below plus the broker research source (`sgx_research`: 25 reports, 641 sentences), copied from the Windows PC's database with `scripts/source_rows.py` so the sentence ids match the labels: 28,027 documents, 44,986 sentences, 286,277 sentence–aspect pairs, every one scored by base FinBERT. The index (592 rows) was rebuilt with its 7- and 30-day windows counted back from the moment the 30 Sep index was computed, so every earlier figure is unchanged and only the new source is added. Holds CNA and broker research text: for the team only. |
| `plp-2026-09-30.db.gz` (superseded; the corpus the evaluations to 10 Oct used) | 41.5MB | `e238338726c7da661496d99b2c14a998588fd007d1f189a0690cc67f657dd3f0` | Same documents and sentences as the snapshot below (28,002 and 44,345), re-assigned to the 10-aspect taxonomy (281,744 sentence–aspect pairs, [docs/DESIGN.md](docs/DESIGN.md), decision 21), re-scored with base FinBERT, and the index rebuilt counting each sentence once in its cross-aspect rows. The corpus is frozen from here ([docs/PLAN.md](docs/PLAN.md), section 2) |
| `plp-2026-09-26-v2.db.gz` (superseded) | 28.9MB | `f6aac79a212368747abd14382838e2bb639ea25366df74015a1ffe6208e4a62b` | 28,002 documents, 44,345 sentences, to 25 Sep: the snapshot below plus 207 CNA articles from 2023 on ([docs/DESIGN.md](docs/DESIGN.md), decision 20); every sentence embedded, aspect-tagged and baseline-scored under the four-aspect taxonomy; index recomputed |
| `plp-2026-09-26.db.gz` (superseded) | 28.0MB | `3d2417d89eccd7fc21dd7e365f77445e0f0bfc869cc8f30301d50df1fd88fa45` | 27,795 documents, 42,746 sentences, to 25 Sep; every sentence embedded, aspect-tagged and baseline-scored; index recomputed; before CNA |
| `plp-2026-09-24-v2.db.gz` (superseded) | 28.0MB | `cd3aceff1e8c865ca9b64209b4088dec4913eaed2984497036d318117b469fb0` | 27,737 documents, 42,690 sentences; news backfilled to 2023-01; every sentence embedded, aspect-tagged and baseline-scored; index recomputed ([docs/data-report-2026-09-24.html](docs/data-report-2026-09-24.html)) |
| `plp-2026-09-24.db.gz` (superseded) | 26.8MB | `f317cf87fb9250a715480c8ee0554d780edbf8ddd19f240be11951ea1d6f2489` | same day, before embeddings, aspects, sentiment and index were run on the news |

The two vector files aren't in git either. Each is a cache rebuilt from the
database: `python -m chatbot.search_vectors` rebuilds `data/search_embeddings.npz`,
the chatbot's evidence search (about 5 minutes on a laptop processor), and
`python -m aspects.embed_store` rebuilds FinBERT's `data/sentence_embeddings.npz`.

### Sharing the data and models

What a teammate needs, beyond `git clone` and the Quick start:

| file | needed for | size |
|---|---|---|
| the latest snapshot (`plp-2026-10-14.db.gz`) | everything: unpack to `data/plp.db` | 26.2 MB |
| `data/search_embeddings.npz` | the chatbot's evidence search when no topic is named (without it, search falls back to word overlap) | 66 MB |
| `data/sentence_embeddings.npz` | only aspect discovery and the similarity method; the chatbot no longer reads it | 132 MB |
| the three fine-tuned models (`models/experiments-2026-10-11/dapt/seed_{42,1,7}/final`) | only to score new sentences, reproduce the sentiment results or re-score; the database already holds their scores for every stored sentence | 3 × 438 MB |

`scripts/share_bundle.sh OUT_DIR` copies the snapshot, both vector files, the
aspect model's answers and the teammates' note (`data/README-teams.md`) into
one folder with a `SHA256SUMS` file (check with `shasum -a 256 -c
SHA256SUMS`), for the team's shared drive. The models go through Hugging Face
instead (below); `--with-models` adds them to the folder only if that is not
possible. FinBERT and the search model (`sentence-transformers/all-MiniLM-L6-v2`)
download from Hugging Face on first use, and each
machine pulls its own Ollama models. Never share `.env` (API keys) or
`data/cna/` (CNA's articles).

The models are in a private Hugging Face model repo,
`plp-bank-sentiment/plp-finbert-absa`, open to the organisation's members
(ask to be added); [docs/model-card.md](docs/model-card.md) is its
`README.md`. The models in use are in its `adapted-2026-10-11/` folder; the
top-level `seed_*` folders hold the earlier models trained on people's
labels. `hf` is installed in the project's environment, not on your PATH.
Log in with your own token, download the folder, move it to where
`config/model_version.py` looks for it, and check the checksums against the
table at the end of the model card:

```bash
.venv-plp/bin/hf auth login
.venv-plp/bin/hf download plp-bank-sentiment/plp-finbert-absa --include "adapted-2026-10-11/*" --local-dir models/hf-download
mkdir -p models/experiments-2026-10-11
mv models/hf-download/adapted-2026-10-11 models/experiments-2026-10-11/dapt
shasum -a 256 models/experiments-2026-10-11/dapt/seed_*/final/model.safetensors
```

To upload a new version, leave out `training_args.bin` (it records a local
path) and `dev_ids.json` (nothing needs it to load the model):

```bash
for s in 42 1 7; do
  .venv-plp/bin/hf upload plp-bank-sentiment/plp-finbert-absa models/experiments-2026-10-11/dapt/seed_$s/final adapted-2026-10-11/seed_$s/final \
      --exclude "training_args.bin" --exclude "dev_ids.json" --private
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
config/       Aspect taxonomy, source weights, the served model version, the chatbot's settings and intents, logging
scripts/      start/stop/status, resumable overnight backfill, the sharing bundle,
              the re-score step (rescore.py) and the earnings-date repair
notebooks/    The text-analytics workstream's Colab notebooks (outputs cleared)
learning/     Study material on the concepts and techniques used
docs/spec/    Functional and technical specifications
docs/evidence/  Dated outputs backing claims in the docs
docs/diagrams/  Twenty-three diagrams, each traced to the code
data/labeled/ Human labels; data/labeled/llm_rater/ holds the Opus labeller's answers
data/plp.db   SQLite store (gitignored; see Getting the database)
```

## Tests

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest tests/ -q   # 2894 tests
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest -q          # 2941: adds the diagram and notebook checks
```
