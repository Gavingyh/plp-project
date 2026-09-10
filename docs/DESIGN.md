# Design & Reasoning

Why this system is built the way it is. For how to run it, see
[RUNBOOK.md](RUNBOOK.md). For what is and isn't finished, see
[STATUS.md](STATUS.md).

---

## Before you trust any number

Four things a reader could otherwise take for findings when they are not:

1. **The blended cross-bank comparison is currently invalid.** Earnings
   material exists for DBS and OCBC but almost none for UOB (its IR site
   blocks automated access). Earnings text is management describing its own
   results and scores far more positive than any other source, so the
   blended gap between banks reflects coverage, not sentiment. Use the
   Reddit-only rows for cross-bank comparison until UOB's earnings PDFs are
   added. Detail in [STATUS.md](STATUS.md).
2. **There is no fine-tuned model.** All sentiment scores come from base
   FinBERT applied zero-shot. The fine-tuned aspect classifier the project
   proposal calls for requires labelled data that does not exist yet.
3. **The GPT and Gemini chatbot backends have never been run against their
   real APIs.** No keys were available. They are written to documented
   contracts; treat the first successful response as their verification.
4. **Local chatbot models fabricate citations.** A code-level check flags
   this (`⚠️ VERIFICATION WARNING`), but the check is a detector, not a fix.

---

## What the system does

Ingests public text about DBS, OCBC and UOB from several sources, splits it
into sentences, assigns each sentence to one or more financial aspects,
scores sentiment per (sentence, aspect), aggregates into a per-bank index,
and exposes the result through a dashboard, a REST API and a chatbot that
answers questions by querying that store.

```
 sources                  ingest/            preprocess/         aspects/
┌──────────────┐         ┌─────────┐        ┌───────────┐      ┌──────────────┐
│ Reddit       │────────▶│         │        │  clean    │      │ FinBERT      │
│ (ArcticShift)│         │ dedupe  │───────▶│  segment  │─────▶│ embeddings   │
│ NewsAPI      │────────▶│ normalise│       │  attribute│      │ + assignment │
│ Earnings PDFs│────────▶│ upsert  │        │  to bank  │      └──────┬───────┘
│ Yahoo consensus│──────▶│         │        └───────────┘             │
└──────────────┘         └────┬────┘                                  ▼
                              │                              ┌──────────────┐
                              │                              │ sentiment/   │
                         documents                           │ scoring      │
                              │                              └──────┬───────┘
                              ▼                                     ▼
                          sentences ──────────────────────▶ aspect_sentiment
                                                                    │
                                                                    ▼
                                                            aggregate/index
                                                                    │
                                    ┌───────────────────────────────┼────────────────┐
                                    ▼                               ▼                ▼
                              dashboard/                          api/           chatbot/
                              (Streamlit)                      (FastAPI)     (tools + RAG)
```

Everything is stored in one SQLite file (`data/plp.db`). Tables:
`documents` → `sentences` → `sentence_aspects` + `aspect_sentiment` →
`sentiment_index`, plus a standalone `analyst_consensus`.

---

## Decision log

The consequential choices, with the evidence behind each. This is the
section most worth reading before changing anything.

### 1. The sentence is the unit of analysis, not the document

Aspect-based sentiment requires it. A single Reddit comment can praise a
bank's dividend and criticise its app in consecutive sentences; scoring the
document as a whole would average those into meaningless neutrality.
Everything downstream — aspect assignment, sentiment, the index, chatbot
citations — keys off `sentence_id`.

### 2. Reddit via Arctic Shift, not the official API or a paid scraper

Reddit declined the project's API application, so PRAW was unavailable.

| option | outcome |
|---|---|
| Reddit official API | application declined |
| Apify (commercial scraper) | ~$0.28–3.40 per 1,000 results; live scrape, not reproducible |
| **Arctic Shift** | free, no key, multi-year archive, reproducible |

Arctic Shift is a public research archive in the Pushshift lineage. Two
constraints found by testing it rather than reading its docs: keyword search
times out on active subreddits (so the pipeline harvests whole subreddits by
date window and filters locally), and pagination requires a moving `after`
cursor with `sort=asc` because there is no page token.

Subreddit selection was also corrected empirically. `r/SingaporeInvestments`
has had no posts since Oct 2023; `r/singapore` and `r/investing` returned
zero bank-mentioning items across 7,000+ sampled. `r/singaporefi` is the
only productive source.

### 3. Earnings from bank IR sites, not SGX

SGX looks like the obvious source and is the wrong one. SGXNet carries
company announcements and SGX's own commentary; third-party analyst reports
are brokerage IP behind client entitlements and are not on SGX at all. Its
API also returns 403 behind a WAF.

DBS and OCBC publish the same earnings material openly on their own IR
sites — plain HTTP, no bot protection, no ToS grey area. UOB sits behind an
F5 WAF that answers scripted requests with a challenge stub.

The choice there was deliberate: rather than escalate to fingerprint-spoofing
tools to defeat the WAF, the same PDFs are fetched from the Wayback Machine,
which archived them at their original UOB URLs and is not behind that WAF
(`ingest/uob_wayback_fetch.py`). The bytes are UOB's own published documents;
only the transport differs. This respects the signal the WAF is sending while
still closing a coverage gap that had invalidated every cross-bank
comparison in the project — UOB went from 4 earnings sentences to 1,600.

This also produced the closest thing the project has to genuine analyst
input: DBS publishes a quarterly **analyst call transcript**, in which named
brokerage analysts question management on margins, asset quality and
guidance. Fourteen consecutive quarters are available.

### 4. Aspect assignment is frozen-centroid, not re-clustered per batch

Clustering runs once, offline, to derive a taxonomy (`aspects/discover.py`).
Assignment then matches sentences to those frozen centroids every batch
(`aspects/assign.py`). Re-clustering per batch would renumber and rename
aspects between runs, so a dashboard user would see categories shift
underneath them.

### 5. Similarity floor raised 0.35 → 0.65

The original floor did not discriminate between anything. Measured sweep on
the real corpus:

| floor | avg aspects matched per sentence | % falling to "other" |
|---|---|---|
| 0.35 | 2.00 / 2 | 0.1% |
| 0.50 | 1.96 | 0.6% |
| 0.60 | 1.89 | 2.8% |
| 0.70 | 1.63 | 9.2% |
| 0.75 | 1.29 | 18.9% |

At 0.35 even a deliberately coarse two-aspect taxonomy matched *both*
aspects on essentially every sentence. 0.65 is a calibration point, not a
final answer — re-sweep when the corpus or taxonomy changes materially.

### 6. Earnings source weight 3.0 → 1.0, and the index gained a source dimension

The 3.0 weight was set when earnings was assumed to be a handful of
high-signal documents. It became the second-largest source, and it is
measurably the most positive one:

| source | positive | neutral | negative |
|---|---|---|---|
| Reddit | 2.3% | 94.8% | 3.0% |
| earnings | 24.7% | 67.9% | 7.4% |

Triple-weighting that amplified a known skew. Weight is now 1.0, and
`sentiment_index` carries a `source` column so every blended row sits
alongside its components — the blend is kept (the proposal calls for it) but
is no longer opaque.

### 7. Analyst consensus from Yahoo Finance, with the caveat stated

Full analyst reports are paywalled. The news-derived proxy in
`ingest/analyst_tag.py` matched zero documents. Yahoo Finance's
`quoteSummary` endpoint returns real consensus data (analyst counts, ratings,
price targets) for all three banks.

It is an **unofficial API** — the endpoint the `yfinance` library wraps, with
no published terms blessing it and a cookie/crumb handshake that exists to
slow automated access. It also provides consensus *aggregates*, not analyst
report text. Both caveats are surfaced in the module, the dashboard and the
API response.

### 8. Chatbot uses a plain tool-calling loop, not a framework

The loop is roughly fifty lines. A framework would add abstraction to explain
in the report without adding capability at this scale. Tools are ordinary
Python functions over SQLite, so the model backend is swappable without
touching them.

### 9. Grounding rules are enforced in code, not requested in the prompt

Two mechanisms exist because prompt instructions alone failed in testing:

- **Volume floor.** `get_sentiment` returns `insufficient_data` below 5
  observations rather than a number the model might report as fact.
- **Citation verification.** If `search_evidence` was never called, any
  quoted evidence, `sentence_id` or URL in the answer is fabricated by
  definition, and the response is flagged. This was added after a local
  model invented sources twice — once as plausible-looking URLs, once as
  placeholder tokens that a URL-matching check alone would have missed.

### 10. Retrieval is cosine similarity over cached embeddings, not a vector DB

At tens of thousands of sentences, brute-force cosine over an in-memory
matrix is as correct as FAISS or Chroma and far simpler. SQL pre-filters on
bank/aspect/date first, so the embedding comparison runs on a small
candidate set. A small lexical-overlap boost is added so exact identifiers
(ticker codes, product names) are not found by semantic proximity alone.

### 11. Local model support (Ollama) alongside hosted models

The project needs to be runnable by someone without an API key. Backend
selection auto-detects: a hosted model if a key is present, Ollama
otherwise. `llama3.2:3b` is the default — its tool-calling was confirmed
against a running instance, and it is roughly seven times faster per call
than `qwen3:4b`, which emits a hidden reasoning chain first.

### 12. Logging is centralised, and logs go to stderr

Third-party libraries (transformers, huggingface_hub) print progress bars
and load reports that bury pipeline output. `config/logging_config.py`
silences them by default and restores them under `DEBUG=true`. Logs go to
stderr so stdout carries only real program output — the chatbot's answer can
be piped on its own. A rotating file captures DEBUG regardless of console
level, so unattended overnight runs remain diagnosable.

---

## Notable implementation details

**Idempotent ingestion.** Every document has a deterministic `doc_id` hashed
from source plus native ID, and inserts use `INSERT OR IGNORE`. Re-running
any adapter is a no-op rather than a duplicate.

**Per-sentence bank attribution.** An explicit in-sentence bank mention wins.
A document's bank is inherited only for short, single-topic sources (news,
earnings) — never for long Reddit threads, where inheriting pulled unrelated
sentences into a bank's corpus.

**Earnings dates parsed from filenames.** `2Q26_...` → 2026-08-01. Without
this, every historical earnings document would carry ingestion time and drop
the entire back-catalogue into the dashboard's 7d/30d rolling windows at
once.

**Volume shrinkage in the index.** Scores are shrunk toward neutral at low
volume (`score × n/(n+5)`), and `n` is always stored and displayed. A
sentiment number without its sample size is the main way this dashboard
could mislead someone.

---

## Deliberate scope limits

- Batch, not streaming. Sources are polled on demand or by cron.
- Alpha Vantage is retained in the codebase but contributes nothing — it
  does not index SGX-listed tickers (confirmed across all three, in several
  ticker formats).
- Annual reports and financial-statement PDFs are not ingested; they are
  near-entirely tables, which the prose extractor would strip to nothing.
- `get_trend` compares two discrete windows (7d vs 30d) rather than
  producing a continuous time series.
