# PLP Practice Module — Project Context
 
**Status: Theme locked. Building phase. Refine details as we go, not the core scope.**
 
---
 
## 1. Course Requirements (fixed, non-negotiable)
 
- Team of 4 (course recommends 3; 4 justified by dual-source pipeline, see §4)
- Must include: one of {sentiment mining, conversational UI} — we have both (sentiment mining is core; chatbot added on top)
- At least 2 text mining tasks — **updated 2026-09-26:** four are planned: aspect discovery (clustering, done), aspect categorisation (LLM, planned), bank entity recognition (NER, planned; before this date no NER existed despite being listed here), sentiment classification (fine-tuned FinBERT, blocked on labels). See `docs/PLAN.md` section 3
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

> **Superseded by what was actually built (2026-09-26).** Reddit: PRAW was
> unavailable (application declined), so Arctic Shift supplies
> `r/singaporefi`; the planned subreddits returned almost nothing. News:
> NewsAPI's one-month limit made it marginal; Google News RSS, backfilled
> month by month from Jan 2023, is the main news source, with Yahoo Finance
> headlines. **Yahoo Finance, excluded below as too fragile/ToS-risky, is
> used** for news headlines and consensus aggregates; the reversal and its
> risk are DESIGN decision 14. Alpha Vantage indexes none of the tickers.
> Analyst stream: Yahoo consensus aggregates, not report text. Current
> sources: `docs/spec/functional-spec.md` section 3 and `docs/news-data.md`.
 
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
**CORRECTED 2026-09-11 — DO NOT CITE THE OLD NUMBERS.** This line previously read: "FinBERT benchmarks at ~88.2% accuracy vs. ~62.1% for lexicon-only (Loughran-McDonald) scoring — this number is accurate per published research, safe to cite in the report." Neither figure could be traced to a source, and they are not in the FinBERT paper.

What the primary source actually reports. Araci (2019), *FinBERT: Financial Sentiment Analysis with Pre-trained Language Models*, arXiv:1908.10063, Table 2, on the Financial PhraseBank:

| model | accuracy (all data) | F1 (all data) | accuracy (100% annotator agreement) | F1 (100% agreement) |
|---|---|---|---|---|
| LSTM | 0.71 | 0.64 | 0.81 | 0.74 |
| LSTM + ELMo | 0.75 | 0.70 | 0.84 | 0.77 |
| ULMFit | 0.83 | 0.79 | 0.93 | 0.91 |
| LPS | 0.71 | 0.71 | 0.79 | 0.80 |
| HSC | 0.71 | 0.76 | 0.83 | 0.86 |
| FinSSLX | — | — | 0.91 | 0.88 |
| **FinBERT** | **0.86** | **0.84** | **0.97** | **0.95** |

Two things to be careful about when citing this. **There is no Loughran-McDonald lexicon baseline in that table at all** — the comparisons are against LSTM, ELMo, ULMFit and three prior published systems, so the "vs. lexicon-only" framing has no basis in this paper. And the two accuracy columns measure different things: 0.97 is on the subset where all annotators agreed, which is the easy subset, so quoting it as FinBERT's accuracy overstates it. Quote 0.86, or quote both and say which is which.

For the reference list: arXiv:1908.10063 is a University of Amsterdam MSc thesis posted to arXiv (25 June 2019), not a peer-reviewed conference paper. Cite it as such.

If the report wants a lexicon comparison, find one and cite it directly. One example located but **not verified in detail**: "Sentiment trading with large language models" (arXiv:2412.19245) reports FinBERT at 72.2% against the Loughran-McDonald dictionary at 50.1% on its own task — different dataset, different setup, not interchangeable with the table above.
 
**Two-stage pipeline:**
1. **Unsupervised — aspect discovery.** Each batch (earnings text, analyst notes, news, social chatter) embedded via FinBERT representations, clustered/topic-modelled (BERTopic or NMF) to surface recurring aspects: dividend policy, asset quality/provisioning, net interest margin, management guidance. No labels needed — pure similarity grouping.
2. **Supervised — sentiment classification (the DNN task).** FinBERT fine-tuned to predict sentiment polarity (Positive/Neutral/Negative) per (document, aspect) pair.
 
**Model inputs (independent variables):** contextual text embedding (FinBERT), source type (earnings/social/analyst/news), discovered aspect tag, bank identity (DBS/OCBC/UOB).
**Target (dependent variable):** sentiment polarity per (document, aspect) pair.
 
**Seed-labelling plan (3 steps)** — *as proposed; what is actually planned is
in `docs/PLAN.md` section 6: a local LLM pre-labels, people correct, and each
row records aspect and sentiment. The Loughran-McDonald weak-labelling step
was not used.*
1. Weak/bootstrap labels via Loughran-McDonald financial dictionary (general lexicons like VADER mislabel financial phrasing, e.g. "beat lowered guidance").
2. Human-verified seed set: stratified sample (~500–800 docs across banks/sources/aspects), manually annotated → gold fine-tuning/validation set.
3. Iterative multi-pass refinement: 2–3 annotation passes, using inter-pass disagreements to refine aspect seeds and relabel edge cases.
 
**System components:**
- Dashboard: overall + aspect-based sentiment index per bank, batch-refreshed (daily, not live streaming)
- Chatbot: natural-language Q&A over the dashboard (e.g. "How does the market feel about DBS's Q2 results?") returning aspect-based sentiment summaries with supporting evidence — this is what satisfies the conversational-UI requirement
 
**Rubric mapping** — *as proposed. The current mapping, with course module and
evaluation per component, is `docs/PLAN.md` section 3:*
| Requirement | Satisfied by |
|---|---|
| Conversational UI | Chatbot layer |
| ≥2 text mining tasks | Unsupervised aspect discovery + supervised sentiment classification (+ NER as a 3rd) |
| Sentiment mining component | Overall + aspect-based sentiment engine, 4 data sources |
| ≥1 DNN | Fine-tuned FinBERT classifier |
 
---
 
## 6. Open Items / Risks Still Active

> **Status 2026-09-26:** 1 resolved (Yahoo consensus aggregates, disclosed as
> such); 2 resolved (volumes measured, news backfilled); 3 and 5 are handled
> by role-based workstreams in `docs/PLAN.md`; 4 resolved (Arctic Shift
> instead of PRAW). Live risks are in `docs/PLAN.md` section 8.
 
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

- *What it did well.* It found four real defects that human review had missed: `ingest/earnings_extract.py` called `text.split("")`, an empty separator that raises `ValueError` on every PDF page while `pull()` swallowed the exception, so the earnings source silently produced nothing; `aspects/discover.py` bound one SQL parameter per sentence and had been dying on SQLite's 32,766-parameter limit since the corpus grew past it; `aspects/compare_taxonomies.py` measured at a hardcoded similarity floor of 0.35 while the pipeline had moved to 0.65, so the tool meant to inform the taxonomy decision was describing a threshold nothing used; and `docs/STATUS.md`'s by-source document counts summed to 18,815 against its own stated total of 21,924.
- *What had to be constrained.* The session ran under an explicit rule that every number trace to a command run in that session and every external fact to a fetched source, with the results recorded in `docs/verification-ledger.md`. That rule caught the model's own errors twice: it drew a confident conclusion from the taxonomy table before checking which floor the tool used (wrong floor, wrong conclusion), and it wrote a test asserting Cohen's κ below 0.1 for a case where κ is arithmetically 0.46. Both were caught by verifying rather than by review.
- *The honest reading.* Model-written text about a codebase is plausible by construction and unreliable without checking. The verification ledger, not the fluency of the prose, is what makes this documentation trustworthy.

**2026-09-24 to 2026-09-26 — Claude Code (Opus 5.5), interactive sessions.**
News backfill (Google News RSS and Yahoo, with a shared relevance and dedup
filter, a seven-technique query pilot, and two audited clean-ups), the
database moved out of git into checksummed snapshots, a full pipeline run on
the news, a daily scheduling job (later stopped by the team), the data report
and submission checklist, the analysis of why named aspects score neutral,
and this round of plan and documentation updates against all four course
modules.

- *What it did well.* It found that 12 of the original 20 news rows named no
  bank, that the chat tab never sent conversation history to the model, that
  the aspect assignment rather than the scorer explained the neutral named
  aspects, and that the leaked API keys had not been rotated.
- *What went wrong and was caught by checking.* A filter rule silently failed
  because it ran on the headline twice, which let 63 analyst calls into the
  database before an audit caught it. A pilot on three sample months
  under-predicted the `intitle:` backfill's volume and missed a flood of
  syndicated FX notes that only appeared in 2026; 195 were removed after a
  quality check. A regex used to measure junk headlines was itself wrong on
  the first attempt, and one report sentence claimed DBS's lead came from
  earnings when, against OCBC, Reddit contributed slightly more. Each was
  caught by re-checking against the data before it was relied on.
- *Where people stayed in control.* Every deletion and the git history
  rewrite waited for explicit approval; the rewrite was run by a team member
  after the assistant's own attempt was blocked as destructive. Decisions on
  aspects, labelling, NER scope and naming were put to the team as questions
  rather than made.

**2026-09-26 — Claude Code (Opus 5.5): the chatbot harness.** Conversation
memory, advice and off-topic guards, a check of every figure against the
tools' results, evidence packaged for citing, and lower decoding temperature
(DESIGN decision 19), evaluated live against the gold set. The honest reading
for the report: the guards moved advice and out-of-scope handling from 2 of 7
to 7 of 7 because they take the decision away from the model; nothing the
harness did reduced a 3B model's invented citations (still 43–48%). The first
live run exposed five false alarms in the new checks, one of which predated
the work; each was fixed with a regression test, and the off-topic rule was
added after seeing a failure, which is stated rather than hidden.

**2026-09-26 — Claude Code (Opus 5.5), unattended: the system diagrams.**
Twenty Mermaid diagrams drawn from the code and the live schema, each element
tied to a `file:line` that `docs/diagrams/check_sources.py` re-checks, with a
render script and a test. The checker it wrote first silently skipped three
rows whose symbol contained backticks; the verification pass caught that, and
it now reports any row it can't parse as a failure.

**2026-09-26 to 2026-09-30 — Claude Code (Opus 5.5), interactive sessions.**
CNA articles loaded as full text through the Wayback Machine (DESIGN decision
20); the text-analytics workstream's labels, ten aspects and Colab notebooks
integrated; the Gemini chatbot backend verified live.

- *What it did well.* Building the training file found 5 train/dev copies of
  test sentences and 18 duplicate rows, now dropped and refused by training.
  It found that the index's headline rows counted a sentence once per aspect
  it matched; counted once, the published headlines (DBS +0.060, OCBC +0.071,
  UOB +0.036) gave way to the figures in STATUS. It moved the Gemini key from
  the request URL into a header, so it can't reach a tracked log.
- *Where people stayed in control.* Gemini's free-tier terms were checked
  before use (Google may use free-tier prompts and responses, with human
  review), and the team limited the key to the live chatbot.
- *Other AI use to declare from this period.* The workstream's cluster labels
  were drafted with an AI assistant and not checked by a second person (DESIGN
  decision 21). Annotators labelled with a local `llama3.2:3b` suggestion in
  view, and the final labels match it on 91.6% of rows.

**2026-09-30 to 2026-10-01 — Claude Code (Opus 5.5), two unattended runs.**
Fine-tuning experiments (longer training, the aspect input, 5-fold
cross-validation), centroid assignment measured against the human aspects, a
discovery sweep and the chatbot gold set on the rebuilt database; then
fine-tuning fixes, an LLM aspect classifier on local models, a preprocessing
dry run and a clean-copy install test.

- *What it did well.* Reading the code before training, it found that the
  class weights the docs and spec described had never been passed to the
  loss: every model until then had trained with plain cross-entropy. The
  install test found that the README never names the Python version it
  needs. Configurations were chosen on cross-validation with the selection
  rule fixed beforehand, never on the test split.
- *What went wrong and was caught by checking.* The night 1 prompt it wrote
  said the model made 48 of 115 test errors on neutral sentences; it made
  102 errors in all. An explanation it drafted for why readable aspect labels
  helped (tokenization) proved false when tested. A first draft listed wealth
  among the aspects where Opus led the local classifier; Opus is behind
  there. Each was corrected before it was committed.

**2026-10-01 — Opus 5.5 as an additional labeller (DESIGN decision 22).** At
the team's request, Claude Code subagents running Opus 5.5 labelled all 1,277
sentences of the 27 Sep round, blind to the human labels: the aspect first,
then sentiment given the human aspect, with the annotation guideline as their
instructions. All 22 raters' transcripts were audited; none opened another
file. Against the human labels: aspect κ 0.80, sentiment κ 0.79. The report
must say: these are human–LLM agreement figures, not human–human; the Opus
labels change no gold label, and their 202 aspect and 173 sentiment
disagreements are queued for people to settle; the sentences, Reddit text
included, were sent to Anthropic under the project's Claude subscription; the
run can be inspected but not exactly reproduced.

**2026-10-01 evening to 2026-10-02 — Claude Code (Opus 5.5), evaluation and
fixes, partly unattended.** The chatbot's gold set v2 and conversations on both
local models, an LLM judge, cross-validation on two more seeds, a blind top-up
labelling sheet, an examiner-style assessment and team to-do list, fixes to
the chatbot found by those runs, and two more Opus 5.5 rating rounds.

- *What it did well.* It read every flagged chatbot answer against the tool
  data and found that all 25 invented citations came from answers that never
  searched; it then checked the LLM judge against those known failures before
  anyone spent time calibrating it, and found the judge passed all of them.
  It replayed a proposed fix on the recorded answers, so the comparison held
  the model's output fixed. Cross-validation on two more seeds showed a
  configuration it had chosen on 1 October was no better than the baseline,
  and it corrected the docs that relied on it.
- *What went wrong and was caught by checking.* It first estimated that the
  top-up sheet's NIM rows would fall short and the others would not; an
  Opus rating round showed NIM would be fine and macro would fall short. It
  stated one relevance figure as 0.589 (the true minimum was 0.5853), and its
  first invented-citation count for the night was 26 (25: one flag was a
  tool call written as text). A pgrep-based wait matched its own command
  line and was replaced before it mattered.
- *Opus 5.5 as a rater again (DESIGN decision 22).* Eight more subagents
  labelled, blind, the top-up sheet's aspects (268 sentences) and the bank-NER
  gold sheet (201); transcripts audited, none opened another file. As before,
  the sentences (Reddit text included) went to Anthropic under the Claude
  subscription, and the labels replace nothing: they are a provisional
  reference until people label those sheets. Using such labels to *train* a
  model (distillation) was discussed and not done: Anthropic's consumer terms
  may restrict using outputs to train AI models, so that needs checking first.
- *A merge decided by a person.* A teammate pushed a dashboard redesign while
  Claude Code had removed the dashboard at the team's request; Claude Code
  stopped and asked, and the team chose to keep the teammate's dashboard.

**Keep updating this section as work continues — needed verbatim-ish
