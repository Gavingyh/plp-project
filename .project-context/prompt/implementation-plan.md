# Prompt for Opus: Generate MVP Implementation Plan

You are acting as a senior ML/NLP solutions architect. Produce a detailed, phased **implementation plan** (not code) for an MVP that goes end-to-end from raw data retrieval to a working agentic chatbot. Do not start implementing — output a plan document I can review and hand to an engineering agent afterward.

## Project context

This is a graduate certificate practice-module project (NUS-ISS, Graduate Certificate in Practical Language Processing). Team is building a **Retail Investor Sentiment Dashboard** for Singapore's three listed banks — DBS, OCBC, UOB.

**Problem statement:** Singapore retail investors are heavily concentrated in DBS/OCBC/UOB (>S$180B combined market cap, ~half the STI) but lack accessible, regularly refreshed research. They rely on scarce analyst PDFs instead of an ongoing read of sentiment, earnings, and news.

**Proposed solution:** A dashboard that ingests four data streams in scheduled batches (daily, not real-time/streaming):
1. Quarterly earnings releases
2. Social media chatter (Reddit, currently)
3. Analyst consensus reports
4. News articles (NewsAPI, Alpha Vantage)

The dashboard surfaces overall **and aspect-based sentiment** (e.g. dividend policy, asset quality/provisioning, net interest margin, management guidance) per bank, recomputed each batch cycle.

**Modeling approach (required by the course, already decided — do not relitigate):**
- **FinBERT**, used two ways:
  - Job 1 (no fine-tuning needed): embedding similarity to cluster text into aspects/topics (unsupervised aspect discovery).
  - Job 2 (fine-tuning required): aspect-level sentiment classification (positive/neutral/negative), fine-tuned on ~1,000 labeled examples (200-300 per class minimum), evaluated via held-out train/test split (or k-fold given small seed set), with accuracy/precision/recall/F1 per class + macro-F1.
- A **conversational chatbot** layer letting users ask natural-language questions (e.g. "How does the market feel about DBS's Q2 results?") and get an aspect-based sentiment summary with supporting evidence — this should be **agentic** (able to call tools/retrieval functions, not just a static prompt-response wrapper), per this conversation's actual goal.

**Practice module deliverable requirements this plan must satisfy:**
- A conversational user interface
- At least two text mining tasks (plan already covers: unsupervised aspect discovery + supervised aspect-sentiment classification)
- A sentiment mining component (overall + aspect-based)
- At least one deep neural network task (fine-tuned FinBERT classifier)

**Course sequence the team has completed/is completing (for calibrating technique choices — don't introduce methods outside what's been taught unless clearly justified):**
- Module 1: Text Analytics — preprocessing, document classification/clustering, information extraction
- Module 2: New Media & Sentiment Mining — sentiment/ABSA theory, aspect extraction families (frequency-based, lexico-syntactic/dependency parsing, supervised sequence labeling, DL, LLM-based), sentiment system design (5-step process: objectives → data source → training corpora → classification/scoring → KPIs/visualization), summarization & visualization (word clouds, sentiment heatmaps, time-series)
- Module 3: Text Processing using ML — DNNs for text mining, model training techniques (content not yet summarized in this repo — assume standard DNN/transformer fine-tuning practice)
- Module 4: Conversational UIs — architecture, conversation flow, building/evaluating chatbots (content not yet summarized in this repo — assume standard agentic/RAG chatbot architecture patterns)

## Current repo state (do not re-derive — this is ground truth)

Repo root: `plp-project` (not yet a git repo).

Existing files:
- `news_pull.py` (185 lines) — pulls from NewsAPI + Alpha Vantage, keeps raw article title/summary text only (Alpha Vantage's built-in sentiment score must NOT be used as a training label)
- `reddit_pull.py` (136 lines) — pulls via PRAW
- `run_data_survey.py` (128 lines) — runs both pulls, writes `data/survey_report.txt`, a go/no-go volume report per bank/source against thresholds (15 news articles/bank, 10 Reddit submissions/bank/subreddit — adjustable, not fixed)
- `requirements.txt` — requests, pandas, praw, python-dotenv
- `.env.example`, `API_KEYS.md` — credential setup for NewsAPI, Alpha Vantage, Reddit
- `data/survey_report.txt` — **last run returned zero data from all three sources** (API keys not yet configured in `.env`) — this has not actually been validated with real data yet
- No quarterly-earnings ingestion, no analyst-report ingestion, no labeling pipeline, no fine-tuning code, no aspect model, no dashboard, no chatbot yet — those are all greenfield

Known constraints already surfaced by the team:
- NewsAPI free tier: ~1 month lookback only. A longer historical window is a paid-tier/alternative-source decision, not silently worked around.
- Reddit free tier: 100 queries/minute, non-commercial/research use only.
- Volume thresholds in `run_data_survey.py` are placeholders pending team agreement.

## What the plan should cover

Produce a phased implementation plan (e.g. Phase 0 data validation → Phase N agentic chatbot) that includes, per phase:
- Concrete steps and deliverables
- Which existing files get extended vs. what new modules/files are needed
- Data schema/contracts between stages (e.g. what a "labeled example" record looks like, what an "aspect-sentiment record" looks like, what the chatbot's retrieval layer queries)
- Explicit go/no-go or validation checkpoints (e.g. don't proceed to fine-tuning until the labeled seed set hits per-class minimums)
- Tooling/library choices with rationale, staying within what's justifiable from the course content above (HuggingFace transformers for FinBERT fine-tuning is expected; for the chatbot's agentic layer, propose an approach and justify it — e.g. tool-calling LLM + retrieval over the sentiment store — rather than assuming a specific vendor)

Specifically, the plan must address, in order:

1. **Data retrieval completion** — validating/fixing the credential setup so the survey actually returns data; adding the two missing sources (quarterly earnings releases, analyst consensus reports) with a sourcing strategy for each (where does a retail-facing project legally/practically get analyst consensus data and structured earnings releases for 3 SGX-listed banks?)
2. **Data storage/pipeline design** — how raw pulls become a versioned, queryable dataset (schema, storage format/location, batch scheduling approach for "daily, not live" ingestion)
3. **Preprocessing** — cleaning/normalizing text per source type before it hits FinBERT
4. **Aspect discovery (unsupervised, Job 1)** — using FinBERT embeddings to cluster into aspect categories (dividend policy, asset quality, NIM, management guidance, etc.), and how discovered clusters get mapped to human-readable aspect labels
5. **Labeling pipeline (for Job 2 fine-tuning)** — how ~1,000 examples get labeled to hit 200-300/class minimum, what tooling/process, quality control
6. **Fine-tuning FinBERT for aspect-sentiment classification** — training setup, train/test split or k-fold strategy given small seed set, evaluation metrics (per-class P/R/F1 + macro-F1), acceptance criteria for the MVP
7. **Sentiment aggregation** — per-bank overall + aspect-based index computation, recompute cadence tied to batch cycle
8. **Dashboard/visualization** — minimal viable surface for overall + aspect sentiment (can reference word clouds/heatmaps/time-series patterns from course content, but keep it MVP-scoped)
9. **Agentic chatbot layer** — architecture for a tool-using conversational agent that can query the sentiment store/evidence (not just summarize a static context window), retrieve supporting evidence for a claim, and answer natural-language questions like the example in the proposal. Cover: what tools/functions the agent needs, how it grounds answers in the sentiment index + underlying evidence text (to support "supporting evidence" requirement), and how correctness/hallucination risk is evaluated for an MVP.
10. **Cross-cutting MVP scoping call** — explicitly flag what should be cut vs. kept for a first working end-to-end slice (e.g. is 1 bank end-to-end before scaling to 3 acceptable? is a placeholder/synthetic analyst-report source acceptable for MVP if real access is blocked?), since this is a time-boxed practice-module project, not a production system.

## Output format

A structured markdown plan with numbered phases, each phase having: goal, steps, deliverable/artifact, and a validation checkpoint. Call out open decisions that need the team's/mentor's input rather than silently assuming an answer (e.g. analyst-report data source, MVP bank scope, agentic framework choice). Do not write implementation code — this is a planning pass only.
