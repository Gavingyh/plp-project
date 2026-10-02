# System context

Who uses the system and which outside services it depends on. For a reader meeting the project for the first time, and for the report's introduction.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
flowchart LR
  accTitle: System context
  accDescr: The sentiment system with its three kinds of user, its five text and data sources, and its four model backends.

  investor(["Retail investor"])
  team(["Project team<br/>ingests, labels, trains"])
  grader(["Grader<br/>installs from the README"])

  subgraph sys["Sentiment dashboard for DBS, OCBC and UOB"]
    core["Batch pipeline<br/>dashboard, REST API, chatbot"]
  end

  subgraph sources["Text and data sources"]
    reddit["Arctic Shift<br/>Reddit archive"]
    gnews["Google News RSS"]
    yahoo["Yahoo Finance<br/>news, analyst consensus"]
    newsapi["NewsAPI"]
    cna["CNA<br/>article pages"]
    av["Alpha Vantage<br/>returns nothing for SGX tickers"]
    ir["DBS and OCBC<br/>investor-relations sites"]
    wayback["Wayback Machine<br/>UOB earnings PDFs,<br/>index of CNA URLs"]
  end

  subgraph llms["Language-model backends"]
    ollama["Ollama, local<br/>default, no key needed"]
    hosted["Claude, OpenAI, Gemini<br/>hosted; Claude and Gemini verified"]
  end

  investor -- "asks questions,<br/>reads scores and quotes" --> core
  team -- "runs ingestion,<br/>labelling, training" --> core
  grader -- "restores a snapshot,<br/>starts the services" --> core

  reddit -- "posts, comments" --> core
  gnews -- "headlines" --> core
  yahoo -- "headlines, rating aggregates" --> core
  newsapi -- "headlines, descriptions" --> core
  cna -- "full articles" --> core
  av -. "no articles" .-> core
  ir -- "results PDFs" --> core
  wayback -- "archived PDFs,<br/>CNA URLs and pages" --> core

  core <-- "prompts, tool calls,<br/>answers" --> ollama
  core <-- "same, with an API key" --> hosted
```

Rendered for the report: [SVG](img/01-system-context.svg) · [PNG](img/01-system-context.png)

## What this shows and doesn't show

Shows every external party the code talks to and what crosses each boundary. It
doesn't show internals (see [02](02-runtime.md) and [04](04-pipeline.md)) or the CNA
feed, which has a scraper (`ingest/cna_scraper.py`) that writes a JSON file and is not
connected to the system. Alpha Vantage is drawn dashed because its adapter runs but no
SGX ticker is indexed, so it contributes nothing. Of the hosted backends, Claude and
(since 2026-09-30) Gemini have returned real responses; OpenAI is implemented but unverified (it also
reaches any OpenAI-compatible provider, such as Groq, through `OPENAI_BASE_URL`).

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| Arctic Shift | `ingest/arctic_shift.py:40` | `BASE_URL = "https://arctic-shift` |
| Google News RSS | `ingest/google_news.py:55` | `RSS_URL = "https://news.google.com` |
| Yahoo Finance news | `ingest/yahoo_news.py:93` | `yf.Ticker(ticker).get_news(` |
| Yahoo Finance consensus | `ingest/yahoo_analyst.py:71` | `finance/quoteSummary/` |
| NewsAPI | `ingest/newsapi.py:58` | `newsapi.org/v2/everything` |
| CNA article pages | `ingest/cna_archive.py:69` | `SITE = "www.channelnewsasia.com"` |
| Wayback index of CNA URLs | `ingest/cna_archive.py:68` | `CDX_URL = "https://web.archive.org/cdx/search/cdx"` |
| archived CNA pages | `ingest/cna_archive.py:214` | `archived = f"https://web.archive.org/web/` |
| Alpha Vantage | `ingest/alphavantage.py:51` | `alphavantage.co/query` |
| Alpha Vantage returns nothing | `ingest/alphavantage.py:49` | `doesn't index SGX-listed names` |
| DBS investor relations | `ingest/earnings_fetch_ir.py:64` | `https://www.dbs.com/investors` |
| OCBC investor relations | `ingest/earnings_fetch_ir.py:70` | `https://www.ocbc.com/group/investors` |
| Wayback Machine | `ingest/earnings_fetch_uob.py:49` | `CDX_URL = "http://web.archive.org` |
| Ollama | `chatbot/backends/ollama_backend.py:37` | `DEFAULT_BASE_URL = "http://localhost:11434"` |
| Claude | `chatbot/backends/claude_backend.py:36` | `import anthropic` |
| OpenAI, or any compatible provider via `OPENAI_BASE_URL` | `chatbot/backends/openai_backend.py:46` | `DEFAULT_BASE_URL = "https://api.openai.com/v1"` |
| OpenAI unverified | `chatbot/backends/openai_backend.py:7` | `NOT VERIFIED AGAINST THE LIVE API` |
| Gemini verified | `chatbot/backends/gemini_backend.py:4` | `VERIFIED against the live API on 2026-09-30` |
| Gemini | `chatbot/backends/gemini_backend.py:46` | `generativelanguage.googleapis.com` |
| Ollama is the default without a key | `chatbot/backends/__init__.py:50` | `return "ollama"` |
| CNA scraper writes JSON, not the database | `ingest/cna_scraper.py:21` | `import json` |
