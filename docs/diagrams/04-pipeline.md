# Pipeline: from sources to the dashboard

How text becomes a sentiment score, stage by stage, and what each stage writes. For the report's solution-approach section.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
flowchart TB
  accTitle: Processing pipeline
  accDescr: Sources are ingested into documents, split into sentences, embedded, tagged with aspects, scored and aggregated into an index that the dashboard, API and chatbot read. Planned replacements are dashed.

  subgraph src["Sources"]
    reddit["Reddit<br/>ingest.arctic_shift"]
    news["News<br/>Google, Yahoo, NewsAPI, CNA"]
    pdfs["Earnings PDFs<br/>ingest.earnings_extract"]
    cons["Analyst consensus<br/>ingest.yahoo_analyst"]
  end

  filt{{"News filter<br/>bank named? duplicate?"}}
  docs[("documents")]
  acons[("analyst_consensus")]
  prep["Split into sentences, attribute bank,<br/>drop near-duplicates<br/>preprocess.pipeline"]
  ner["Bank entity recognition<br/>(planned, DESIGN 18)"]
  sents[("sentences")]
  emb["FinBERT embeddings<br/>aspects.embed_store"]
  disc["Aspect discovery, offline<br/>UMAP + HDBSCAN, aspects.discover"]
  assign["Seed-centroid aspect assignment<br/>aspects.assign"]
  llm["LLM aspect classifier<br/>(planned, DESIGN 16)"]
  sa[("sentence_aspects")]
  score["Base FinBERT, zero-shot<br/>sentiment.score"]
  ft["Fine-tuned FinBERT, trained 30 Sep;<br/>replaces base only if it beats it<br/>(PLAN section 5)"]
  as[("aspect_sentiment")]
  agg["Index: windows, sources,<br/>shrinkage at low volume<br/>aggregate.index"]
  idx[("sentiment_index")]
  ui["Dashboard, REST API, chatbot"]

  reddit --> docs
  news --> filt --> docs
  pdfs --> docs
  cons --> acons
  docs --> prep --> sents
  ner -.-> prep
  sents --> emb --> assign --> sa
  emb -.-> disc
  disc -. "informs the taxonomy" .-> assign
  llm -. "replaces" .-> assign
  sa --> score --> as
  ft -. "replaces" .-> score
  as --> agg --> idx
  idx --> ui
  sents -- "evidence" --> ui
  acons --> ui

  classDef planned stroke-dasharray: 5 5,color:#555,fill:#fafafa;
  class ner,llm,ft planned;
```

Rendered for the report: [SVG](img/04-pipeline.svg) · [PNG](img/04-pipeline.png)

## What this shows and doesn't show

Each arrow is a step someone runs; RUNBOOK lists them in order. Every step between
ingestion and the index processes only rows it hasn't processed before; the index is
recomputed in full each time (see [06](06-batch-pipeline.md)). Discovery runs offline and doesn't write to the pipeline's
tables: its output is evidence for choosing the aspect taxonomy
(`docs/evidence/aspect-discovery-2026-09-11.md`). The three dashed boxes are decided but
not built: bank NER would improve attribution inside preprocessing, the LLM classifier
would replace seed-centroid assignment, and a fine-tuned model would replace zero-shot
scoring only if it beats it; the first run, on 1,277 labelled rows, did not (macro-F1 0.547
against 0.571, `docs/evidence/finetune-2026-09-30.md`).
Earnings PDFs are fetched by two modules (`earnings_fetch_ir`, `earnings_fetch_uob`)
before `earnings_extract` reads them; the fetch step is folded into the source box.

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| Reddit adapter | `ingest/arctic_shift.py:40` | `BASE_URL = "https://arctic-shift` |
| news filter | `ingest/news_filter.py:258` | `def filter_and_dedup(` |
| news sources | `ingest/news_filter.py:54` | `NEWS_SOURCES = ("newsapi", "alphavantage", "yahoo_news", "google_news", "cna")` |
| consensus writes analyst_consensus | `ingest/yahoo_analyst.py:146` | `def upsert(rows` |
| preprocessing | `preprocess/pipeline.py:97` | `def run(sources: set[str]` |
| bank attribution per sentence | `preprocess/pipeline.py:67` | `def _resolve_sentence_bank(` |
| sentence splitting | `preprocess/segment.py:62` | `def segment(text: str)` |
| embeddings | `aspects/embed_store.py:61` | `def update(path: str | None = None, embed=None, width: int = 768) -> dict:` |
| FinBERT embedding model | `aspects/embed.py:19` | `MODEL_NAME = "ProsusAI/finbert"` |
| discovery: UMAP | `aspects/discover.py:90` | `reducer = umap.UMAP(` |
| discovery: HDBSCAN | `aspects/discover.py:95` | `clusterer = hdbscan.HDBSCAN(` |
| assignment from seed centroids | `aspects/assign.py:68` | `vecs = embed_sentences(cfg["seed_terms"])` |
| sentiment scoring | `sentiment/score.py:111` | `def run(sources: set[str]` |
| zero-shot base FinBERT | `sentiment/score.py:43` | `MODEL_NAME = "ProsusAI/finbert"` |
| index aggregation | `aggregate/index.py:334` | `def run() -> int:` |
| fine-tuning code | `train/finetune.py:267` | `def run(seed: int = 42` |
| first run below base FinBERT | `docs/evidence/finetune-2026-09-30.md:36` | `**Fine-tuning did not beat base FinBERT on macro-F1.**` |
| evidence read by the chatbot | `chatbot/retrieval.py:175` | `all_ids, all_vecs = load_for_search()` |

## Planned elements

| element | recorded in |
|---|---|
| Bank entity recognition | DESIGN.md decision 18 |
| LLM aspect classifier | DESIGN.md decision 16 |
| Scoring the corpus with the fine-tuned model | PLAN.md section 5; only if it beats base FinBERT |
