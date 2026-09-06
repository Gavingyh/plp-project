# MVP Implementation Plan — Retail Investor Sentiment Dashboard (DBS / OCBC / UOB)

**Scope:** end-to-end slice from data retrieval → aspect discovery → fine-tuned aspect-sentiment classifier → sentiment index → dashboard → agentic chatbot.
**Status:** planning pass only. No implementation code here.
**Prepared for:** review by the team, then handoff to an implementation agent.

---

## 0. Read this first — four findings that change the plan

Before the phases, four things that alter sequencing. They are not nitpicks; each one invalidates an assumption the proposal currently rests on. Finding (a) is a live blocker and is the reason the Reddit ingestion design below differs from the current code.

**(a) Reddit API access is blocked, and the fix is a better corpus than PRAW would have given you.**
Reddit has not approved the team's API application, so `reddit_pull.py` cannot run. **Recommended replacement: [Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift)** — a public Reddit archive with a free HTTP API and downloadable per-subreddit dumps. No application, no approval, no key. I tested it live against this project's actual query needs; results and the resulting design constraints are in Phase 1c. In short: it works, it is current to today, and it gives you *years* of history where PRAW's search would have given you months. Full comparison against Apify in Phase 1c.

**(b) Alpha Vantage will almost certainly return nothing for these banks.**
`news_pull.py:133` queries `NEWS_SENTIMENT` with `.SI` tickers (`D05.SI`, `O39.SI`, `U11.SI`). Alpha Vantage's news coverage is overwhelmingly US-listed tickers; SGX listings are generally not indexed. The last survey run is consistent with this but does not prove it, because no key was set. **This must be tested in Phase 0 before any plan depends on it.** If it returns empty, the four-source proposal drops to three sources and the plan below is unaffected — but you need to know in week 1, not week 6.

**(c) NewsAPI free tier truncates article body text to ~200 characters.**
`news_pull.py:108` stores `content`, but on the free tier that field arrives clipped with a `[+N chars]` suffix. Your usable news text is effectively **title + description only** — roughly 30–50 words per article. That is enough for sentence-level ABSA (it is comparable to a tweet), but it means news cannot carry the "long-form analyst reasoning" role the proposal implies. Earnings releases have to carry that role instead.

**(d) The pulls are not re-runnable as a daily batch.**
All ingestion scripts write a full-overwrite CSV (`news_pull.py:117`, `reddit_pull.py:118`) with no stable document ID, no dedup, and no append. Run them twice and you have replaced yesterday's data, not accumulated it. Since the whole proposal rests on "recomputed after each batch cycle," **an ingestion-layer rewrite is a prerequisite, not a nice-to-have.** This is Phase 1 and it is unavoidable.

**Also:** the repo is not a git repository. Initialize it in Phase 0 before anything else — you are about to generate model checkpoints, labeled data, and a multi-module codebase across a team.

---

## Architecture at a glance

```
                       ┌──────────── ingest/ ────────────┐
  NewsAPI ────────────►│                                 │
  Alpha Vantage ──────►│   normalize → dedup → append    │──► documents
  Reddit (Arctic Shift)►│                                 │    (raw text + provenance)
  Earnings PDFs ──────►│                                 │
                       └─────────────────────────────────┘
                                     │
                         preprocess/ │ sentence split + clean + filter
                                     ▼
                                 sentences  (the unit of analysis)
                                     │
                    ┌────────────────┴────────────────┐
          aspects/  │                                 │  sentiment/
   FinBERT embed →  │                                 │  fine-tuned FinBERT
   cluster (once) → │                                 │  (sentence, aspect) → pos/neu/neg
   FROZEN taxonomy  │                                 │
   → assign each    │                                 │
     sentence       │                                 │
                    └────────────────┬────────────────┘
                                     ▼
                            aspect_sentiment  (sentence × aspect × label × confidence)
                                     │
                          aggregate/ │ per bank × aspect × day, volume-weighted + shrunk
                                     ▼
                          sentiment_index  ──────┬──────► dashboard/  (Streamlit)
                                                 │
                                                 └──────► chatbot/  (tool-calling agent)
                                                             tools query BOTH the index
                                                             (numbers) and sentences
                                                             (evidence quotes)
```

**The single most important design decision below:** the unit of analysis is the **sentence**, not the document. Everything downstream — aspect assignment, sentiment labels, the index, and the chatbot's evidence citations — keys off a sentence ID. Document-level sentiment would defeat the entire ABSA premise of the project.

---

## Phase 0 — Foundation & data reality check

**Goal:** prove the data actually exists before building anything on top of it.

**Steps**

1. `git init`; commit the current state as a baseline. Confirm `.gitignore` excludes `.env`, `data/`, `.venv-plp/`, `__pycache__/`, and (add) `models/`.
2. Every team member obtains their own NewsAPI and Alpha Vantage keys; fill `.env` from `.env.example`. **Reddit credentials are no longer needed** — see finding (a) and Phase 1c.
3. Run `python run_data_survey.py` for real (news sources only). Record actual per-bank, per-source counts.
4. **Test the two remaining unknowns:**
   - Does Alpha Vantage return anything for `.SI` tickers? (See finding (b).) If empty, retry once using the `topics`/keyword form rather than `tickers` to confirm it is a coverage gap and not a query-shape bug, then close the question.
   - Is NewsAPI `content` truncated? Inspect 5 raw rows. (See finding (c).)
5. Re-point the Reddit survey at Arctic Shift and re-measure volume with the corrected subreddit list (Phase 1c). The Reddit unknown is already partly answered — see the measured results in Phase 1c.
6. Re-set the volume thresholds in `run_data_survey.py` from placeholders to numbers the team agrees on, informed by steps 4–5.

**Deliverable:** a committed `data/survey_report.txt` with real numbers, plus a short `docs/data-viability.md` recording the answers above.

**Validation checkpoint (hard gate):**
- ≥ 200 usable news items per bank over the available window, **and**
- ≥ 300 Reddit items (submissions + comments) per bank over 12 months.

If Reddit for OCBC/UOB comes in thin — which is plausible; Singapore retail chatter skews heavily to DBS — do **not** proceed as if it hadn't. With Arctic Shift the first lever is cheap and legitimate: **widen the time window**, since the archive goes back years rather than PRAW's practical months. After that, add subreddits (see the measured list in Phase 1c), or accept that Reddit is a DBS-dominant source and say so explicitly in the report.

---

## Phase 1 — Ingestion layer rewrite + the two missing sources

**Goal:** turn three one-shot scripts into an idempotent, append-only daily batch pipeline, and settle where Reddit, earnings, and analyst data come from.

### 1a. Unified document schema

Replace the three incompatible CSV shapes with one `documents` table. Proposed contract:

| field | type | notes |
|---|---|---|
| `doc_id` | str (PK) | deterministic hash of `source` + native id or URL — this is what makes re-runs idempotent |
| `source` | enum | `newsapi` \| `alphavantage` \| `arctic_shift` \| `earnings` |
| `source_detail` | str | publication name, subreddit, or document type |
| `bank` | enum | `DBS` \| `OCBC` \| `UOB` \| `MULTI` |
| `doc_type` | enum | `article` \| `submission` \| `comment` \| `earnings_release` |
| `title` | str, nullable | |
| `body` | str | the concatenated usable text (news: title + description; reddit: selftext/comment body; earnings: extracted section text) |
| `published_at` | ISO 8601 UTC | normalize `publishedAt` / `time_published` / `created_utc` here |
| `url` | str | required — the chatbot cites this |
| `ingested_at` | ISO 8601 UTC | batch provenance |
| `raw` | JSON str | original payload, kept for auditability |

`bank = MULTI` matters: an article comparing all three banks should not be silently assigned to whichever keyword matched first, which is what the current per-bank query loop does. Handle it by detecting all bank mentions and, at the sentence level (Phase 2), attributing each sentence to the bank named in or nearest to it.

**Storage:** SQLite (`data/plp.db`) via pandas/SQLAlchemy. Rationale over Parquet-on-disk: the chatbot's tools need point lookups and filtered aggregation, the dashboard needs the same, and SQLite gives you both with zero infrastructure and a single file that is easy to share across a student team. Parquet is the better choice only if data volume exceeds a few hundred MB, which it will not here.

**Batch scheduling:** a single `run_daily_batch.py` entrypoint invoked by cron (or run manually before demos). Do not build a scheduler. "Daily, not live" is satisfied by a cron line and an `ingested_at` column.

### 1b. Quarterly earnings releases

There is no free API for SGX company announcements worth building against for an MVP. **Recommended approach: a one-time manual corpus.** Download from each bank's investor-relations site — results announcements, financial statements, and (most valuable) the CEO/CFO commentary and presentation decks — for the last 8–12 quarters. That is 24–36 PDFs, an afternoon of work, and it is a *better* corpus than anything you would scrape.

Extract text with `pdfplumber` (better table/layout handling than `pypdf` for financial statements). Keep only prose sections — management commentary, outlook, risk discussion. **Discard the financial tables**: FinBERT scores numeric tables as noise and they will pollute both clustering and sentiment.

Commit the extracted text (not the PDFs) to `data/earnings/`. This corpus is static, so it is ingested once and does not participate in the daily batch.

### 1c. Reddit via Arctic Shift — replacing the blocked API

Reddit has not approved the API application, so PRAW is unavailable. **Recommendation: Arctic Shift.** I tested it live against this project's real queries; the findings below are measured, not assumed, and two of them change the ingestion design.

**Why Arctic Shift over Apify**

| | Arctic Shift | Apify Reddit actors |
|---|---|---|
| Cost | Free | ~$0.28–$3.40 per 1,000 results depending on actor and tier |
| Access | Open HTTP API, no key, no approval | Account + platform credits (free tier ~$5/mo) |
| History | Multi-year archive | Live scrape — recent content only |
| Legal posture | Research archive, the accepted successor to Pushshift and the standard corpus in published Reddit research | Third-party scraping of a site whose ToS prohibits it; the vendor absorbs that risk, but your report still has to describe the method |
| Reproducibility | Fixed archive — a rerun returns the same data | Live scrape — not reproducible |
| Reliability | "No uptime or performance guarantees"; keyword search times out | Commercial SLA |

For an academic project needing **historical depth and a reproducible corpus**, Arctic Shift is the better fit on every axis that matters here, and citing a Pushshift-lineage archive is well-precedented in the literature. Apify's real advantage is a commercial SLA, which is worth little for a batch pipeline you rerun on failure. **Keep Apify as the documented fallback** if Arctic Shift's uptime proves unworkable — the ingestion interface should be written so the source is swappable behind it.

**Measured findings (tested 2026-09-06 against `arctic-shift.photon-reddit.com`)**

1. **The archive is current, not stale.** Newest post in r/singapore: 2026-09-06 — same day. This is a live archive, not a frozen dump, so it supports the daily batch cycle.
2. **Keyword search is unusable — this changes the ingestion design.** `?subreddit=X&query=DBS` returns `HTTP 422 {"error":"Timeout. Maybe slow down a bit"}`, consistent with the API docs' warning that keyword search is "not supported with very active users or subreddits." The same request without `query` returns `HTTP 200` and real data.
   **Therefore: harvest by `subreddit` + date window, then filter for bank mentions locally.** This is the opposite of `reddit_pull.py`'s current per-bank remote-query approach, and it is actually preferable — you get the full subreddit corpus once, and the bank-matching alias list becomes a local, versionable, tunable artifact rather than a remote query string.
3. **Two of the three configured subreddits are worthless, and that is a live bug in the current code.**
   - `r/SingaporeInvestments` — **newest post is 2023-10-01**; the subreddit is effectively dead. It is currently the *first* entry in `reddit_pull.py:43`.
   - `r/singapore` — **0 of 100 recent posts mention any of the three banks.** It is a general-interest subreddit; for this purpose it is noise.
   - `r/singaporefi` — **live and on-topic: 11 of 100 posts in a 90-day sample mention a bank.** This is the primary source and it is *not currently in the config at all*.

   Revise `SUBREDDITS` to `["singaporefi", "SingaporeInvestments" (historical only, pre-Oct 2023), "investing"]` and evaluate `r/askSingapore` and `r/stocks` for marginal additional volume. Had this gone unchecked, the project would have harvested a dead subreddit and a noise subreddit as its two primary social sources.

4. **Volume clears the Phase 0 gate from r/singaporefi alone.** Measured over 12 months (Sep 2025 – Sep 2026):

   | | total harvested | bank-mentioning | DBS | OCBC | UOB |
   |---|---|---|---|---|---|
   | posts | 7,084 | 775 | 494 | 213 | 288 |
   | comments | 24,000 \* | 662 | 448 | 127 | 204 |
   | **combined** | | **1,437** | **942** | **340** | **492** |

   \* comments hit my pagination cap, so 24,000 and the 662 derived from it are **floors, not totals** — actual comment volume is higher.

   Against the ≥300-items-per-bank gate: **DBS and UOB pass comfortably; OCBC passes but only just**, and OCBC is the thinnest of the three across both formats. Two cheap levers if OCBC needs more: extend the window backwards (the archive supports it), and add `r/investing` plus pre-Oct-2023 `r/SingaporeInvestments`. The DBS skew anticipated above is real and measured — roughly 2.8× OCBC — and should be stated in the report rather than smoothed over, since it means the three banks' indices rest on materially different sample sizes.

   This also sizes the labeling budget: ~1,437 bank-mentioning items sentence-splits into several thousand candidate sentences, comfortably more than the 1,000-example target in Phase 4 needs.

**Implementation shape**

- `ingest/arctic_shift.py`, replacing `reddit_pull.py` but keeping its retry/backoff discipline.
- Endpoints: `/api/posts/search` and `/api/comments/search`. Params: `subreddit`, `after`, `before`, `limit` (max 100), `sort=asc`, `fields` (trim the payload — the archive returns large objects by default).
- **Paginate with a moving `after` cursor** set to `last_result.created_utc + 1`. There is no page token; this is the pagination method and it is why `sort=asc` matters.
- Harvest posts *and* comments. Comments are the bulk of usable retail sentiment — posts are often just headline links.
- Handle `429` (dynamic rate limits, reset headers provided) and the `422` timeout by narrowing the date window and retrying.
- **One-time backfill** over the full available history, then a daily incremental pull with `after = last_ingested_at`. Note the docs' caveat that scores and comment counts are incomplete for ~36 hours, so treat very recent engagement metrics as provisional.
- For large historical pulls, prefer the [download tool](https://arctic-shift.photon-reddit.com/download-tool) or the Academic Torrents dumps over hammering the API — more polite and far faster.

**Bonus:** this quietly fixes the project's biggest data weakness. News is capped at ~1 month by NewsAPI's free tier (finding (c)), but Arctic Shift gives Reddit **multi-year** history — enough to build a genuine time series across several earnings cycles, which the dashboard's trend view needs and the original PRAW plan could not have supplied.

**Ethics/compliance note for the report:** the archive contains public Reddit content including usernames. Do not store or display usernames — you do not need them, and dropping them at ingestion removes the main privacy exposure. Say so explicitly in the report.

### 1d. Analyst consensus reports — **open decision, flag to mentor**

Full analyst PDFs are behind brokerage entitlements. There is no legal free source, and scraping aggregator sites for consensus ratings generally violates their ToS.

**My recommendation:** do not build a fourth ingestion source. Instead, treat analyst consensus as a **derived view over the news stream** — financial media routinely reports analyst actions verbatim ("Maintains BUY, raises TP to S$X on NIM resilience"). Implement it as a tagging rule over `documents`: flag articles matching analyst-action patterns (broker names, `BUY|HOLD|SELL|target price|TP|upgrade|downgrade|maintains`) as `has_analyst_view = true`, and let the dashboard and chatbot filter on that flag.

This is honest, legal, costs a day rather than a fortnight, and still gives you an "analyst sentiment" view. It should be **disclosed plainly in the report** as a proxy for full analyst reports, not presented as equivalent to them.

**Alternatives if the mentor wants a genuine fourth stream:** (i) SGX Research / SGX Market Updates commentary, which is free and publishable; (ii) ask the mentor whether NUS library access provides Refinitiv/Bloomberg entitlements the project may use for academic purposes — worth one email, and it would be the strongest source available if the answer is yes.

**Do not** use Alpha Vantage's `overall_sentiment_score` anywhere, per the constraint already noted at `news_pull.py:154`.

**Deliverable:** `ingest/` module (`base.py`, `newsapi.py`, `alphavantage.py`, `arctic_shift.py`, `earnings.py`), `data/plp.db` populated, `run_daily_batch.py`. The news scripts get refactored into `ingest/` rather than deleted — their retry logic (`news_pull.py:53-76`) and rate-limit spacing are worth keeping. `reddit_pull.py` is replaced, but its subreddit/bank-alias config carries over (corrected per 1c).

**Validation checkpoint:** run the batch twice in a row; row count must not change on the second run and no duplicate `doc_id` may exist. If that fails, the daily-batch premise fails.

---

## Phase 2 — Preprocessing to a sentence-level corpus

**Goal:** produce the `sentences` table that every downstream stage consumes.

**Steps**

1. **Sentence segmentation.** spaCy `en_core_web_sm`. Note the failure modes on this data: Reddit comments have no reliable punctuation, and financial text is full of abbreviations (`S$1.2b`, `Q3 FY25`, `p.a.`) that naive splitters break on. Add abbreviation exceptions and a minimum-length filter.
2. **Per-source cleaning** (they differ materially):
   - *News:* strip the `[+N chars]` truncation marker, publication boilerplate, and `(Reuters)`-style datelines.
   - *Reddit:* strip markdown, quoted parent text (`>` blocks — quoting is not the commenter's own sentiment), URLs, and bot comments (AutoModerator etc.). Keep emoji and casing — both carry sentiment; do **not** lowercase, FinBERT is cased-aware and uppercase is meaningful in this register.
   - *Earnings:* drop headers/footers, page numbers, and any line that is >40% numeric.
3. **Bank attribution per sentence.** For `bank = MULTI` documents, assign each sentence to the bank it names; carry forward the document's bank when the sentence names none but the document names exactly one; drop sentences that are ambiguous within a multi-bank document.
4. **Relevance filter.** Drop sentences that mention a bank only incidentally (e.g. "I banked in via DBS PayNow" in a thread about something else). A keyword-plus-length heuristic is adequate for the MVP; note it as a known precision limitation.
5. **Deduplication.** Syndicated news republishes the same wire copy across outlets. Near-duplicate detection (MinHash, or simple normalized-text hashing) — otherwise the sentiment index double-counts one Reuters story ten times, which is the single most likely way to get a *silently wrong* index.

**Schema — `sentences`:**

| field | notes |
|---|---|
| `sentence_id` | PK |
| `doc_id` | FK → documents |
| `bank` | resolved per sentence |
| `text` | cleaned sentence |
| `char_span` | offsets into the source doc, so the chatbot can quote in context |
| `published_at`, `source`, `url` | denormalized for query speed |

**Deliverable:** `preprocess/` module; `sentences` table.

**Validation checkpoint:** hand-inspect 100 random sentences. Are they well-formed, on-topic, and correctly bank-attributed? If dedup or attribution is visibly wrong here, fix it now — every error at this layer propagates into labels, the model, the index, and the chatbot's citations.

> **Scheduling note:** the moment this phase produces sentences, **start Phase 4 (labeling) in parallel.** Labeling is human-time-bound and is the critical path of the entire project. Phase 3 is machine work and can proceed alongside it.

---

## Phase 3 — Aspect discovery (Text mining task 1, unsupervised)

**Goal:** discover the aspect taxonomy from data, freeze it, then assign every sentence to an aspect.

### The key architectural point

The proposal describes clustering FinBERT embeddings to discover aspects. But the dashboard needs a **stable** set of aspects — users cannot be shown "dividend policy" on Monday and a renumbered cluster on Tuesday. Resolve this by splitting the work in two:

- **Discovery (run once, offline).** Embed a large sample of sentences, cluster, inspect, and derive a human-readable aspect taxonomy. This is the unsupervised text mining deliverable, and it is a legitimate one — you are letting the data tell you the aspect set rather than assuming it.
- **Assignment (runs every batch).** With the taxonomy frozen, assign each new sentence to its nearest aspect centroid by cosine similarity, with an `OTHER` bucket below a similarity threshold. Deterministic, fast, and stable across runs.

### Steps

1. Embed sentences with FinBERT (`ProsusAI/finbert`), **mean-pooled over token embeddings, not the CLS token.** BERT-family CLS vectors without sentence-level training objectives are known to be poor similarity representations; mean pooling is materially better and costs nothing.
2. Reduce (UMAP) and cluster (HDBSCAN — it handles variable-density clusters and gives you a noise bucket, which K-means does not; you genuinely do not know k in advance).
3. Inspect each cluster's top TF-IDF terms and 10 representative sentences. Name the clusters by hand.
4. Reconcile against the proposal's a-priori aspects — dividend policy, asset quality/provisioning, net interest margin, management guidance. Expect the data to also surface things the proposal did not anticipate (digital banking outages, wealth-management fees, share buybacks, retail service complaints). **Keep them.** A discovered aspect the proposal missed is the strongest evidence that the unsupervised step did real work.
5. Freeze the taxonomy (target 6–10 aspects + `OTHER`) into `config/aspects.yaml` with a name, description, seed terms, and centroid vector for each.
6. Implement assignment. Allow a sentence to carry **more than one aspect** — "NIM held up but provisions rose" is two aspects with opposite sentiment, and collapsing it to one is exactly the error ABSA exists to avoid.

**Deliverable:** `aspects/` module, `config/aspects.yaml`, a cluster-inspection notebook (this is report material), `sentence_aspects` table (`sentence_id`, `aspect`, `similarity`).

**Validation checkpoint:** sample 50 assigned sentences across aspects and hand-check. **Target ≥ 70% assignment precision.**

**If FinBERT embeddings cluster poorly** — incoherent clusters, everything collapsing into one blob — the documented fallback is to use a sentence-transformer (`all-mpnet-base-v2`) for the *embedding/clustering step only*, while FinBERT remains the classifier in Phase 5. Decide this on the cluster-inspection evidence, and record the comparison in the report; "we tried the domain model, measured it, and switched with justification" is a stronger result than either choice unexamined. Confirm with the mentor that this preserves the FinBERT requirement — the DNN deliverable rests on Phase 5, which is unaffected.

---

## Phase 4 — Labeling pipeline

**Goal:** ~1,000 labeled `(sentence, aspect) → {positive, neutral, negative}` examples, ≥200–300 per class. **Start this as early as possible.**

### The sampling problem, and the trap in solving it

Random sampling of financial text yields roughly 60–70% neutral. Naive random sampling of 1,000 sentences would give you perhaps 150 positive and 150 negative — short of the per-class minimum.

The obvious fix is to pre-screen candidates with off-the-shelf FinBERT and oversample the ones it calls non-neutral. **This introduces a real methodological flaw if done carelessly:** your evaluation set then consists only of examples base FinBERT already flagged, so your fine-tuned model's reported F1 is inflated and the comparison against the base-model baseline is rigged in your favor.

**Mitigation — do this from the start, it cannot be retrofitted:**
- **Train/dev set (~800):** model-assisted stratified sampling is fine. Oversample predicted non-neutral to hit class balance.
- **Test set (~200): sampled purely at random, before and independently of any model screening, and frozen.** All headline metrics are reported on this set. It will be neutral-heavy — that is the point; it reflects the true distribution the system meets in production.

Report metrics on the random test set. You may additionally report on the stratified dev set, labeled as such.

### Steps

1. Write an annotation guideline (1–2 pages) with edge cases decided in advance: sentiment is toward *the bank as an investment*, not the writer's mood; factual statements with clear valence ("NPL ratio rose to 1.4%") are negative, not neutral; sarcasm; forward-looking guidance; quoted analyst opinion counted as the analyst's view.
2. Stratify by aspect **and** source. A model trained only on news will not transfer to Reddit register.
3. **LLM pre-labeling then human correction.** Batch sentences to a Claude API call producing structured JSON labels with a short rationale, then have humans accept/correct. This roughly triples throughput versus labeling from scratch. Two independent points: the LLM is a *labeling aid*, and every label ships human-reviewed; and this is methodologically distinct from using Alpha Vantage's canned score, which is a black-box vendor output on the same task.
4. **Inter-annotator agreement.** Two annotators independently label the same 150 sentences; compute Cohen's κ. Target κ ≥ 0.6. Below that, the guideline is ambiguous — fix the guideline and re-label, do not proceed.
5. Tooling: Label Studio if the team wants a UI; a shared spreadsheet with a fixed schema is genuinely sufficient at this scale and has less setup cost.

**Schema — `labeled_examples`:** `sentence_id`, `aspect`, `label`, `annotator`, `labeled_at`, `llm_prelabel`, `was_corrected`, `split` (`train`/`dev`/`test`), `sampling_method` (`random`/`stratified`).

Keeping `llm_prelabel` and `was_corrected` lets you report how often humans overrode the LLM — a useful honesty metric for the report.

**Deliverable:** `data/labeled/` (committed to git — this is your most expensive artifact), annotation guideline, κ score.

**Validation checkpoint (hard gate — do not enter Phase 5 early):** ≥900 labeled examples, ≥200 per class, κ ≥ 0.6, frozen random test set of ~200 untouched by model-assisted selection.

---

## Phase 5 — Fine-tune FinBERT (DNN task + Text mining task 2)

**Goal:** a fine-tuned aspect-sentiment classifier that measurably beats sensible baselines.

### Input formulation

Use the **sentence-pair (NLI-style) formulation**: `[CLS] {sentence} [SEP] {aspect} [SEP]` → 3-way softmax. One model handles all aspects, with the aspect supplied as context.

The alternative — a separate model or head per aspect — would split 1,000 examples across 6–10 aspects, leaving ~100 each. That is not enough to fine-tune anything. The sentence-pair formulation is the standard ABSA approach for exactly this reason and is what makes a 1,000-example budget viable.

### Training setup

- Base: `ProsusAI/finbert`, HuggingFace `transformers` + `Trainer`.
- LR **2e-5** (the BERT-family range noted in the course content), 3–5 epochs, batch 16, max_len 128, warmup 10%, early stopping on dev macro-F1.
- Class weighting in the loss to counter residual imbalance.
- **Fix and record the random seed**; report mean ± std across ≥3 seeds. With ~800 training examples, seed variance can exceed the effect you are claiming — a single run is not a result.
- 5-fold cross-validation on train+dev for model selection; final metrics on the frozen test set.
- Colab free-tier GPU is sufficient (this trains in minutes). Do not build for local GPU.

### Baselines — required, not optional

The claim "fine-tuning helped" is unsupported without these:

1. **Base FinBERT, zero-shot** — the most important comparison; it is the "why fine-tune at all" question.
2. **VADER or a finance lexicon** — the rule-based floor.
3. **TF-IDF + logistic regression** — the classical ML floor.
4. Optionally: a zero-shot LLM prompt (ties to Module 2's prompt-based ABSA content and makes a strong report section).

### Metrics

Per-class precision/recall/F1, **macro-F1 as the headline**, accuracy, and a confusion matrix. Expect neutral↔negative confusion to dominate — financial text hedges constantly.

**Deliverable:** `models/finbert-absa/`, `train/finetune.py`, `train/evaluate.py`, a results table across all baselines with seed variance, confusion matrix.

**Validation checkpoint:** macro-F1 **≥ 0.65** on the frozen test set **and** a clear margin over base FinBERT zero-shot.

If the fine-tuned model does *not* beat base FinBERT, that is a publishable finding, not a failure — but investigate first: label noise (check κ), too few examples, or aspect-conditioning not helping. Report whatever you find honestly; a negative result with diagnosis marks better than a suspiciously good number with no error analysis.

---

## Phase 6 — Scoring pipeline & sentiment index

**Goal:** turn per-sentence predictions into the per-bank, per-aspect index the dashboard and chatbot read.

**Steps**

1. Batch-score all `(sentence, aspect)` pairs → `aspect_sentiment` (`sentence_id`, `aspect`, `label`, `confidence`, `model_version`, `scored_at`). Keep `model_version` — you will retrain, and you need to know which rows came from which model.
2. **Index computation.** Map labels to {−1, 0, +1}, aggregate per `(bank, aspect, date)`:
   - weight by model confidence,
   - weight by source (earnings and analyst-flagged news should outweigh a single Reddit comment — set weights explicitly in config and justify them in the report),
   - **apply shrinkage toward neutral at low volume.** Without this, one Reddit comment produces a ±1.0 index reading and the dashboard shows a dramatic swing built on a single sentence. Use `score × n/(n+k)` with k≈5, or equivalent.
   - **always store and display `n` alongside every score.** A sentiment number without its sample size is the main way this dashboard could mislead a retail investor, which is precisely the audience harm the project exists to avoid.
3. Rolling windows (7d, 30d) with time decay for the headline index; raw daily values retained underneath.
4. Overall per-bank sentiment = volume-weighted mean across aspects.

**Schema — `sentiment_index`:** `bank`, `aspect` (`ALL` for the overall row), `date`, `window`, `score`, `n`, `pos_n`, `neu_n`, `neg_n`, `confidence_mean`, `model_version`.

**Deliverable:** `score/` and `aggregate/` modules wired into `run_daily_batch.py`.

**Validation checkpoint:** pick a known event with an obvious direction — a results day, a dividend announcement — and confirm the index moves the way a human reading the same coverage would say it should. If it does not, the pipeline is broken somewhere upstream and no amount of dashboard polish will fix it.

---

## Phase 7 — Dashboard

**Goal:** a minimal, honest surface for overall and aspect-based sentiment.

**Tooling: Streamlit.** Python-native, reads the same SQLite file, no frontend work, deploys free on Streamlit Community Cloud. For a time-boxed project where the differentiator is the NLP and not the UI, anything else is a poor trade.

**MVP views (four, no more):**
1. **Bank overview** — three cards, current overall sentiment + 30-day sparkline + `n`.
2. **Aspect heatmap** — bank × aspect grid, colored by score, cell labels showing `n`. (Module 2's heatmap content.)
3. **Time series** — sentiment over time per bank, filterable by aspect and source, with event markers for earnings dates.
4. **Evidence drill-down** — click any cell or point, see the actual sentences behind it with source links. This is the trust anchor of the whole product; build it early, not last.

**Cut from MVP:** word clouds (ambiguous across three entities, as the course material itself notes), price overlays, alerting, user accounts, mobile layout.

**Required on every view:** a "not financial advice" disclaimer, the sample size, and the last-refresh timestamp.

**Validation checkpoint:** a teammate who did not build it can answer "how does sentiment on DBS's dividend policy compare to UOB's, and what is that based on?" in under a minute, without help.

---

## Phase 8 — Agentic chatbot

**Goal:** a tool-using conversational agent that answers natural-language questions by *querying* the sentiment store and retrieving real supporting evidence — not by summarizing a pre-stuffed context window.

### Architecture

A **plain tool-calling loop against the Claude API** (Anthropic SDK, `claude-sonnet-5`), with tools implemented as ordinary Python functions over the SQLite store.

*Rationale over a framework (LangChain/LlamaIndex):* the agent loop here is roughly 50 lines — send messages, execute requested tools, append results, repeat until a text response. A framework adds abstraction you must then explain in a report and debug through, for no capability you need at this scale. Keeping the tools as plain functions also keeps the provider swap contained to one file, which is the actual portability that matters. **Flag as an open decision** if the mentor expects a specific framework for marking purposes — this is a defensible choice either way, but it should be a stated one.

### Tools the agent needs

| tool | purpose |
|---|---|
| `get_sentiment(bank, aspect?, window?, date?)` | the numbers — index score, `n`, class breakdown |
| `search_evidence(query, bank?, aspect?, sentiment?, date_range?, k=5)` | the quotes — semantic search over `sentences`, returns text + source + URL + date |
| `compare_banks(aspect, window)` | side-by-side across the three banks |
| `get_trend(bank, aspect, window)` | direction and magnitude of change, plus what drove it |
| `get_coverage(bank?, aspect?, date_range?)` | **what data exists at all** — this is what lets the agent say "I have no data on that" instead of inventing an answer |

`get_coverage` is not optional. Without a way to check its own coverage, an agent asked about a bank-aspect-period combination with zero data will confabulate. It is the cheapest hallucination defense available.

### Grounding rules

- Every quantitative claim traces to a `get_sentiment` result; every qualitative claim cites ≥1 `sentence_id` with its URL.
- **Refuse below a volume floor.** If `n < 5`, the agent says the data is too thin rather than reporting a score. Enforce this in the *tool response*, not only in the prompt — a tool that returns `{"insufficient_data": true, "n": 2}` is far more reliable than an instruction the model may skip under pressure.
- **Investment-advice guardrail.** "Should I buy DBS?" gets a redirect to what the data shows plus an explicit non-advice statement. This is both an ethical requirement and directly responsive to the proposal's own framing.
- Answer format: direct answer → supporting evidence with citations → sample size and time window → caveats.

### Evaluation (needed for the report)

Build a **30–40 question gold set** spanning: single-bank single-aspect lookups, cross-bank comparisons, trend questions, out-of-scope questions (a bank you do not cover), zero-data questions, and advice-seeking questions. Measure:

1. **Tool-selection accuracy** — did it call the right tool with the right arguments?
2. **Numerical fidelity** — does the stated number match a direct DB query? (Automatable; this is your strongest hallucination metric.)
3. **Citation validity** — human check: does the cited sentence actually support the claim?
4. **Appropriate abstention** — does it decline on zero-data and advice questions?

**Deliverable:** `chatbot/` (`tools.py`, `agent.py`, `prompts.py`), a Streamlit chat tab reusing the Phase 7 app, gold-set eval results.

**Validation checkpoint:** ≥90% numerical fidelity, 100% abstention on advice questions, zero fabricated citations across the gold set.

---

## Phase 9 — Integration, documentation, demo

Wire `run_daily_batch.py` end to end (ingest → preprocess → assign → score → aggregate) and run it on a schedule for at least a week before the demo so the time-series views have real movement in them. Write the README, the model card (training data, metrics, known limitations), and the report sections. Rehearse the demo against a frozen snapshot of the database — never a live API pull, which will fail on stage exactly once. This matters more than usual here: Arctic Shift explicitly offers no uptime guarantee.

---

## MVP scoping — what to cut and what to keep

**Keep all three banks. Do not do "one bank first."**

This is a deliberate disagreement with the usual advice. Every component below the ingestion layer is bank-agnostic — `bank` is a column, not a code path. Restricting to DBS saves you close to zero engineering time, while costing you cross-bank comparison, which is simultaneously the dashboard's main value proposition, the most compelling chatbot demo, and the thing that distinguishes this from a generic sentiment tutorial. The scoping savings people expect from "one bank first" are not actually there in this architecture.

**Cut instead:**

| Cut | Rationale |
|---|---|
| Analyst consensus as a separate ingestion stream | No legal free source; the derived flag over news (Phase 1d) delivers the capability at ~5% of the cost |
| Long historical backfill **for news** | Accept NewsAPI's ~1 month. Reddit via Arctic Shift now supplies multi-year depth for free, so backfill it generously — it is the cheapest history you have |
| Apify | Not needed unless Arctic Shift's uptime fails. Keep as documented fallback, do not build against both |
| Alpha Vantage | Drop it entirely if Phase 0 confirms no SGX coverage. Do not spend a week working around it |
| Word clouds, price overlays, alerts, auth | Not required by any deliverable |
| Real-time anything | The proposal already specifies batch. Hold that line |
| Multi-turn conversation memory beyond the current session | Nice to have; not a deliverable |

**Accept as known limitations, stated in the report rather than hidden:** ~1-month news window (Reddit is no longer window-limited); Reddit skew toward DBS; Reddit data comes from a third-party archive rather than the official API, with no uptime guarantee; analyst view as a news-derived proxy; English only (some SG retail chatter is Singlish/Chinese and will be missed); ~1,000 labeled examples is small and the confidence intervals on macro-F1 are correspondingly wide.

---

## Critical path & sequencing

```
Phase 0 ─► Phase 1 ─► Phase 2 ─┬─► Phase 3 (aspects) ────┐
                               │                          ├─► Phase 5 ─► 6 ─► 7 ─► 8 ─► 9
                               └─► Phase 4 (labeling) ────┘
                                    ▲ LONG POLE — human-bound, start the moment
                                      Phase 2 produces sentences, run in parallel
```

**Phase 4 is the critical path**, because it is bounded by human annotator hours rather than compute. Sequencing it after Phase 3 — the natural reading of the phase numbering — is the most likely way this project runs out of time. Start labeling the moment sentences exist.

The second-riskiest dependency is Phase 0 → everything: if the data is not there, no amount of downstream sophistication rescues the project. Do not let Phase 0 slip on the assumption that the data will be fine.

---

## Open decisions needing team / mentor input

1. **Analyst consensus source** — accept the news-derived proxy (recommended), or pursue SGX Research / NUS library entitlements? *Blocks Phase 1d.*
2. **Reddit via Arctic Shift** — confirm with the mentor that a public research archive is acceptable in place of the official API, given Reddit declined the application. This is standard practice in Reddit research (Pushshift lineage) and should be an easy yes, but get it on record since the proposal named the API. *Blocks Phase 1c.*
3. **Agentic framework** — plain Claude tool-calling loop (recommended) or a specific framework the module expects for marking? *Blocks Phase 8.*
4. **Embedding-model fallback** — is substituting a sentence-transformer for the *clustering* step acceptable if FinBERT embeddings cluster poorly, given FinBERT remains the fine-tuned classifier? *Contingency for Phase 3.*
5. **LLM-assisted pre-labeling** — confirm this is acceptable for the module, given every label is human-reviewed and the process is disclosed. *Blocks Phase 4.* (Worth asking explicitly rather than assuming.)
6. **Aspect taxonomy sign-off** — who approves the frozen aspect list before Phase 4 labeling starts against it? Re-deriving the taxonomy after labeling would invalidate the labels.
7. **Project deadline and per-phase time budget** — not recorded anywhere in the repo. The plan is ordered by dependency, not calendar; it needs a real deadline to become a schedule.
8. **Team split** — labeling is parallelizable across people and is the long pole; most other phases are not. Worth assigning deliberately.
