# PLP Practice Module — Project Context
 
**Status: Theme locked. Building phase. Refine details as we go, not the core scope.**
 
---
 
## 1. Course Requirements (fixed, non-negotiable)
 
- Team of 4 (course recommends 3; 4 justified by dual-source pipeline, see §4)
- Must include: one of {sentiment mining, conversational UI} — we have both (sentiment mining is core; chatbot added on top)
- At least 2 text mining tasks — we have 3 (NER, unsupervised aspect/topic discovery, supervised sentiment classification)
- At least 1 self-built/fine-tuned DNN — FinBERT fine-tuned (see §5)
- Implementation in Python
- ~10 man-days effort per participant
 
**Deadlines:**
| Deliverable | Weight | Date |
|---|---|---|
| Proposal | — | Aug 08, 2026 |
| Video presentation (~20 min, system demo, all members) | 5% | Nov 01, 2026 |
| System + source code + datasets + docs | 20% | Nov 01, 2026 |
| Report (<20 pages) | 20% | Nov 01, 2026 |
| Peer review | 5% | ongoing |
 
Report must include: business problem, datasets, solution approach, test results, conclusions, references to public libraries/models used, individual contribution summary, and a **GenAI/LLM usage declaration** (tools used, role, pros/cons).
 
---
 
## 2. Locked Decision: Project Theme
 
**Title (working): Retail Investor Sentiment Dashboard — SG's Three Listed Banks**
**Entities: DBS, OCBC, UOB** (SGX: D05, O39, U11)
 
We evaluated and passed on: a broad AI-bubble tracker, a multi-sector early-warning system, SG data-center REITs, and SG commercial REITs (CICT/FCT/Suntec). The bank trio was chosen for: strongest news/data volume of the SG-focused options, real survey-backed business problem, and a genuine comparative angle (3 similar-but-distinct entities, frequently discussed together, good NER challenge).
 
**This decision may still be refined in scope/detail — do not reopen the core "which entities" question without a strong new reason.**
 
---
 
## 3. Business Problem (from submitted proposal)
 
Singapore retail investors show strong interest in local equities but lack confidence and access to research:
- SIAS–Beansprout Pulse Survey (Mar 2025, n=1,011): 80%+ remain interested in SG stocks; 55% cite lack of attractive stocks, 57% cite low returns as barriers; 24% cite lack of guidance/research; 19% cite lack of familiarity.
- Among investors with small SG allocation: 31% cite unfamiliarity as main reason for staying out; 81% read an analyst report before investing — showing heavy dependence on scarce third-party research.
- MDRT survey (Apr 2025, n=2,000 SG adults): only 34% rate their own financial literacy "good," 15% "excellent."
 
DBS, OCBC, UOB together: >S$180B combined market cap, ~half of the Straits Times Index, the default entry point for most retail portfolios. A small gap in understanding their results/dividends/asset quality translates to outsized retail risk exposure, yet investors rely on scarce analyst PDFs rather than a regularly updated sentiment/news read.
 
**This survey data is real and citable — keep these numbers in the final report.**
 
---
 
## 4. Data Sources — Locked, Verified Access Status (as of Aug 01, 2026)
 
### Primary: Financial news
- **NewsAPI.org** — https://newsapi.org/docs — free tier: 100 req/day, ~1 month lookback only. Fine for a recent window; a longer historical pull needs a paid tier or a fallback dataset.
- **Alpha Vantage News & Sentiment** — https://www.alphavantage.co/documentation/ (`NEWS_SENTIMENT` endpoint) — free tier: 25 req/day. **Use raw title/summary text only — do NOT use its built-in sentiment score as a training label**, that would defeat the self-built-DNN requirement. Verify DBS/OCBC/UOB tickers are actually indexed.
- Fallback if both too restrictive: Kaggle SG/SGX finance news datasets (static, no rate limits, needs a direct search to confirm one exists with the right coverage).
 
### Secondary: Social/crowd sentiment
- **Reddit via PRAW** — https://praw.readthedocs.io/en/latest/ — free tier: 100 queries/minute, non-commercial/research use. App registration: https://www.reddit.com/prefs/apps (type: script). Target subreddits: r/SingaporeInvestments (primary), r/singapore, r/investing.
- **StockTwits was excluded** — official API currently closed to new registrations (verified live blocker, not hypothetical).
- **Yahoo Finance was excluded** — no official API since 2017; only unofficial scraping exists, too fragile/ToS-risky for a graded deliverable.
 
### Fourth stream (from proposal): Analyst consensus reports
- **Unresolved risk, flagged, not yet solved.** Analyst reports are typically licensed/paywalled (Bloomberg, Refinitiv, brokerage-restricted). No confirmed free access path yet. If nobody on the team has institutional access, this stream may need to be dropped or substituted — **check this explicitly, don't let it default silently into "skipped."**
 
### Reference/price data (not text, evaluation only)
- SGX delayed price feed (REST API) — https://www.sgx.com/data-connectivity/sgx-delayed-price-feed
- Yahoo Finance (unofficial `yfinance`) — price reference only, not for text data
 
### Data survey tooling
- `plp-data/` project (news_pull.py, reddit_pull.py, run_data_survey.py) already built — run this to get an actual go/no-go volume read per bank per source before committing further. Output: `data/survey_report.txt`. **Analyst-report source is not covered by this tool yet — needs its own access check.**
 
---
 
## 5. Technical Approach (from submitted proposal)
 
**Pretrained model:** FinBERT (ProsusAI/finbert) — BERT pretrained on financial text (analyst reports, earnings calls, financial news), further tuned on Financial PhraseBank. Chosen so the 10-man-day budget goes to labelling/fine-tuning, not pretraining from scratch.
**Verified fact:** FinBERT benchmarks at ~88.2% accuracy vs. ~62.1% for lexicon-only (Loughran-McDonald) scoring — this number is accurate per published research, safe to cite in the report.
 
**Two-stage pipeline:**
1. **Unsupervised — aspect discovery.** Each batch (earnings text, analyst notes, news, social chatter) embedded via FinBERT representations, clustered/topic-modelled (BERTopic or NMF) to surface recurring aspects: dividend policy, asset quality/provisioning, net interest margin, management guidance. No labels needed — pure similarity grouping.
2. **Supervised — sentiment classification (the DNN task).** FinBERT fine-tuned to predict sentiment polarity (Positive/Neutral/Negative) per (document, aspect) pair.
 
**Model inputs (independent variables):** contextual text embedding (FinBERT), source type (earnings/social/analyst/news), discovered aspect tag, bank identity (DBS/OCBC/UOB).
**Target (dependent variable):** sentiment polarity per (document, aspect) pair.
 
**Seed-labelling plan (3 steps):**
1. Weak/bootstrap labels via Loughran-McDonald financial dictionary (general lexicons like VADER mislabel financial phrasing, e.g. "beat lowered guidance").
2. Human-verified seed set: stratified sample (~500–800 docs across banks/sources/aspects), manually annotated → gold fine-tuning/validation set.
3. Iterative multi-pass refinement: 2–3 annotation passes, using inter-pass disagreements to refine aspect seeds and relabel edge cases.
 
**System components:**
- Dashboard: overall + aspect-based sentiment index per bank, batch-refreshed (daily, not live streaming)
- Chatbot: natural-language Q&A over the dashboard (e.g. "How does the market feel about DBS's Q2 results?") returning aspect-based sentiment summaries with supporting evidence — this is what satisfies the conversational-UI requirement
 
**Rubric mapping (already confirmed satisfied):**
| Requirement | Satisfied by |
|---|---|
| Conversational UI | Chatbot layer |
| ≥2 text mining tasks | Unsupervised aspect discovery + supervised sentiment classification (+ NER as a 3rd) |
| Sentiment mining component | Overall + aspect-based sentiment engine, 4 data sources |
| ≥1 DNN | Fine-tuned FinBERT classifier |
 
---
 
## 6. Open Items / Risks Still Active
 
1. **Analyst report data access** — no confirmed source yet. Needs a same-week check: does anyone have institutional access, or does this stream get dropped/substituted.
2. **Data volume confirmation** — run `plp-data` survey tool with real API keys before finalizing scope; NewsAPI's 1-month lookback limit may force a shorter historical window than originally planned, or a paid-tier decision.
3. **Dashboard + chatbot is two real interface builds on top of the NLP pipeline** — confirm explicit ownership; this is a meaningfully larger scope than a single dashboard, budget accordingly across the 4 team members.
4. **Reddit app registration** — should be done immediately if not already, self-service registration reportedly slower in 2026.
5. **10 man-day budget reality check** — 4 data streams × 2-stage pipeline (unsupervised + supervised) × dashboard × chatbot is ambitious. Not flagging to relitigate scope, but worth an honest team check-in on whether all 4 streams and both interfaces are realistic, or whether something gets simplified once real data volumes come back from the survey tool.
 
---
 
## 7. Things Explicitly Decided Against (don't re-litigate without new information)
 
- Single-stock (OCBC-only) scope — rejected: kills NER's purpose, no comparison basis for evaluation.
- StockTwits, Yahoo Finance, YouTube comments, StockGeist/Adanos/ApeWisdom as data sources — all rejected, reasons logged in §4.
- AI-bubble tracker, sector-wide early warning, DC REITs, commercial REITs as the project theme — all viable alternatives that were drafted in full but not chosen; available as reference if the bank-trio theme runs into a hard blocker, not as a default fallback to casually switch to.
 
---
 
## 8. AI Usage Declaration (running log — needed for report §, per AI Usage Declaration slide)
 
Claude has been used for: proposal ideation and comparison across multiple theme options, technical proposal drafting (business problem framing, approach, risk/limitation/assumption sections), data-source research and live verification (API access status, rate limits), Python script drafting for data collection (NewsAPI/Alpha Vantage/Reddit pulls), and this context-consolidation document.

**2026-09-11 — Claude Code (Opus 5), unattended session.** Documentation refresh, functional and technical specifications, the `learning/` study folder, service start/stop scripts, `train/agreement.py`, and re-runs of aspect discovery and the taxonomy comparison on the full corpus.

Worth stating plainly in the report, because it cuts both ways:

- *What it did well.* It found four real defects that human review had missed: `ingest/earnings.py` called `text.split("")`, an empty separator that raises `ValueError` on every PDF page while `pull()` swallowed the exception, so the earnings source silently produced nothing; `aspects/discover.py` bound one SQL parameter per sentence and had been dying on SQLite's 32,766-parameter limit since the corpus grew past it; `aspects/compare_taxonomies.py` measured at a hardcoded similarity floor of 0.35 while the pipeline had moved to 0.65, so the tool meant to inform the taxonomy decision was describing a threshold nothing used; and `docs/STATUS.md`'s by-source document counts summed to 18,815 against its own stated total of 21,924.
- *What had to be constrained.* The session ran under an explicit rule that every number trace to a command run in that session and every external fact to a fetched source, with the results recorded in `docs/verification-ledger.md`. That rule caught the model's own errors twice: it drew a confident conclusion from the taxonomy table before checking which floor the tool used (wrong floor, wrong conclusion), and it wrote a test asserting Cohen's κ below 0.1 for a case where κ is arithmetically 0.46. Both were caught by verifying rather than by review.
- *The honest reading.* Model-written text about a codebase is plausible by construction and unreliable without checking. The verification ledger, not the fluency of the prose, is what makes this documentation trustworthy.

**Keep updating this section as work continues — needed verbatim-ish for the report's GenAI declaration.**
