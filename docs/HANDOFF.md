# Handoff

Start here if you are new to this project, or picking it up after time away.

Written 2026-09-11; the reading order, "Needs a human" and ownership sections
were updated on 2026-09-26. The overnight run log further down is the record
of 2026-09-11 and is left as written.

---

## What this is

An aspect-based sentiment system for Singapore's three listed banks — DBS,
OCBC and UOB — built for the NUS-ISS Practical Language Processing practice
module. It ingests public text, splits it into sentences, assigns each
sentence to a financial aspect, scores sentiment, and exposes the result
through a REST API and a grounded chatbot; the dashboard is a separate
project built on the API ([api-integration.md](api-integration.md)).

**Deliverables are due 1 November 2026:** the system with source code and
datasets, a report under 20 pages, and a demo video.

---

## Read in this order

| # | document | why |
|---|---|---|
| 0 | [PLAN.md](PLAN.md) | What happens next, in what order, and the decisions already made. Read this first if you are picking up work |
| 1 | [STATUS.md](STATUS.md) | What is actually true today. **The single source of truth for caveats.** Read the first two sections before quoting any number to anyone. |
| 2 | [spec/functional-spec.md](spec/functional-spec.md) | What the system is supposed to do, and which requirements are Done, Partial or Blocked |
| 3 | [DESIGN.md](DESIGN.md) | Why it is built this way. The decision log is the section to read before changing anything |
| 4 | [RUNBOOK.md](RUNBOOK.md) | How to run it. Two things will otherwise cost you an afternoon: always invoke `.venv-plp/bin/python3` by absolute path, and set `HF_HUB_OFFLINE=1` for FinBERT steps |
| 5 | [spec/technical-spec.md](spec/technical-spec.md) | Data model, API contract, configuration. Reference rather than a read-through |
| 6 | [../learning/](../learning/) | The concepts and techniques, by subject. Start with whatever you are about to work on |

Also: [data-viability.md](data-viability.md) is the evidence appendix for
every data-source decision, and [evidence/](evidence/) holds dated outputs
backing claims made elsewhere.

## Get it running

```bash
python3 -m venv .venv-plp
.venv-plp/bin/python3 -m pip install -r requirements.txt
.venv-plp/bin/python3 -m spacy download en_core_web_sm
cp .env.example .env          # no keys needed to run

scripts/start.sh              # the API + Ollama, with health checks
scripts/status.sh
scripts/stop.sh
```

The pipeline needs no API key. You do need the database, which is not in git:
download the latest snapshot from the team's shared folder and unpack it as
described under "Getting the database" in the [README](../README.md).
Rebuilding from scratch is possible but slow, and would not reproduce the
exact corpus the report describes.

---

## Needs a human

> **Updated 2026-10-01.** Items 2 and 3 below describe 26 Sep and are
> superseded: the first labelling round is done (1,277 rows, sentiment κ
> 0.93), the taxonomy is ten aspects (DESIGN decision 21), and the LLM
> aspect classifier is built and evaluated but not run on the corpus. Gemini
> was verified on 30 Sep (item 5). The current list is "Needs a human (night
> 1)" at the end of the night 1 run log below: whether the fine-tuned model
> scores the corpus, whether to run the aspect classifier on it, the README
> fixes (now made), the Opus review queues and the wealth-versus-retail
> boundary. Item 1, rotating the keys, is still open.

Ordered by urgency. Updated 2026-09-26; the full sequence is in
[PLAN.md](PLAN.md) and a tickable list in
[submission-checklist.html](submission-checklist.html).

### 1. Rotate two API keys — still not done on 2026-09-26

`.env.example` is tracked in git and contained **real** NewsAPI and Alpha
Vantage keys from the first commit (`cd37dfa`) until 2026-09-11. They are
identical to the values in the live `.env`, and they remain in git history.

Treat both as compromised and regenerate them:

- NewsAPI: https://newsapi.org/account
- Alpha Vantage: https://www.alphavantage.co/support/#api-key

The file now carries placeholders. **History was deliberately not rewritten** —
that is a call for whoever owns the repository, and rewriting shared history
has its own costs. Rotating the keys makes the exposure harmless either way.

### 2. Label the data — this is the critical path

> **Updated 2026-09-26: wait for the re-drawn sheet.** Annotators will choose
> the aspect as well as the sentiment for each sentence (DESIGN decision 17),
> on a new candidate set that includes news, produced after the new aspect
> classifier runs (PLAN.md section 5, week 1). Don't label the current
> `candidates.csv`. The rules below about the blind test sheet and the
> agreement round still apply.

Zero of 998 candidate rows are human-labelled. This blocks the fine-tuned
classifier, which blocks the deep-neural-network deliverable the rubric
requires. Nothing else in the project is on the critical path; this is.

Everything around it is ready: candidates exported, 997 rows pre-labelled by a
local model, a blind sheet for the test split, an agreement tool, and
fine-tuning and evaluation scripts that are written and smoke-tested.

Read [annotation-guideline.md](annotation-guideline.md) first, then the
labelling section of [RUNBOOK.md](RUNBOOK.md). Three rules that matter:

- **Label the test split from `data/labeled/test_blind.csv` only**, never from
  `candidates.csv`. The latter shows you both a model's proposed label and
  base FinBERT's guess, and base FinBERT is one of the two models the test set
  exists to compare.
- **Two people label the same ~150 rows independently first**, then run
  `train/agreement.py`. Target Cohen's κ ≥ 0.6.
- Two aspects cannot reach the proposal's 200-per-class target regardless of
  how labels fall: `asset_quality` has 58 candidate rows and
  `management_guidance` has 97. Decide what to do about that before you start.
  (Resolved 2026-09-26: the proposal's 200–300 target is per *sentiment*
  class overall, not per aspect; the re-drawn set adds a floor of about 80
  rows per aspect. PLAN.md section 6.)

### 3. Settle the aspect taxonomy

> **Decided by the team 2026-09-26.** Keep the proposal's four aspects plus
> `other`, assigned by a local LLM, one per sentence (DESIGN decision 16).
> The report must explain it, because the method differs from the proposal.
> Evidence as it stood on 2026-09-11:

This is now well evidenced and needs a decision, not more analysis. Dropping
the proposal's four a-priori aspects changes what was proposed, so it is not a
config edit.

The evidence, all from 2026-09-11:

- The proposal's four centroids are the **least distinct** of three candidates
  tested (0.1125 mean pairwise cosine distance against 0.1695 and 0.2222), and
  that figure cannot be changed by tuning any threshold.
- No similarity floor gives them a usable operating point: at 0.60 they match
  2.55 of 4 aspects per sentence, at 0.65 they discard 37.3% of the corpus, at
  0.70 they discard 57.9%.
- **Assignment is demonstrably wrong for Reddit.** The 20 Reddit sentences most
  similar to the `net_interest_margin` centroid are all retail banking
  products — fees, credit cards, fixed deposits. None are about margins, and
  the ones mentioning interest invert the polarity, since a depositor's 5.2%
  is a funding cost to the bank.
- Clustering the full corpus **does** now produce analyst-style topics
  (leverage ratio, Basel III, fee income, return on equity) which a
  Reddit-only corpus never did — but 281 of them, finer than the four aspects
  and cutting across them.

Full write-ups in [evidence/](evidence/).

### 4. Decide what to do about blending

Whether management commentary and retail chatter belong in one index is a real
methodological question, currently resolved in favour of the proposal with
composition made visible. The strongest argument against: UOB has the
**highest** earnings-only score and the **lowest** blended score, purely
because it publishes less earnings text than DBS. A reader taking the headline
at face value reaches the opposite of the truth.

### 5. Smaller decisions

- **Default local model.** `llama3.1:8b` fabricates citations at 13% against
  `llama3.2:3b`'s 43–48%, at the cost of being noticeably slower — slow enough
  that it timed out on 8 of 23 questions when the machine was busy. Decide
  whether that trade suits a demo, and if you switch, raise the
  120-second Ollama read timeout.
- **Advice-declining.** 3 of 7 gold-set questions at best, on every model
  tested. A prompt and design problem, not a model choice, and the most
  serious behavioural gap for a tool carrying a not-financial-advice
  disclaimer.
- **Verify the GPT and Gemini backends** with one real API call each. They
  have never received a real response. Gemini carries more risk: its schema
  `type` field expects uppercase proto-enum values, unlike the JSON-Schema
  lowercase used everywhere else here.

---

## Ownership

By role. The team fills the roles offline; no personal names are kept in the
repository. One person can hold more than one role. Tasks per role are in
[PLAN.md](PLAN.md) section 4.

| role | covers |
|---|---|
| Data and NER | ingestion, news and CNA feeds, bank entity recognition, dataset packaging |
| Labelling | annotation guideline, agreement round, the labelled set |
| Modelling | aspect classifier, aspect discovery, fine-tuning and evaluation |
| Interfaces | the API, the chatbot and its evaluation; the Streamlit dashboard (`dashboard/`), a teammate's |
| Report and video | everyone; each person writes their own contribution summary |

---

## Things that will waste your time if nobody warns you

| symptom | cause | fix |
|---|---|---|
| `TypeError: unsupported operand type(s) for \|` | conda's Python 3.9 shadowing the venv | Use `.venv-plp/bin/python3` by absolute path, always |
| `ModuleNotFoundError: torch` | System Python | Same |
| A step hangs at near-zero CPU | HuggingFace metadata check | `HF_HUB_OFFLINE=1` |
| `scripts/start.sh` refuses port 8000 | Another project's server is on it | Use `PLP_API_PORT`, or stop that process yourself. The script will not kill it for you |
| Chatbot answer carries a verification warning | The model cited evidence it never retrieved | Do not trust that answer |
| Dashboard says "No sentiment data yet" | Pipeline has not run, or `data/plp.db` is missing | See RUNBOOK |
| `pip install` fails: `No matching distribution found for torch>=2.9.0` | The venv was made with Python 3.9 (a Mac's built-in `python3`) | Recreate it with Python 3.10 or newer, e.g. `python3.14 -m venv .venv-plp` |
| A long run stops for an hour, then carries on | The Mac slept: low battery, or the lid closed. `caffeinate -i` prevents neither | Keep it plugged in with the lid open |

---

## Overnight run log — 2026-09-11

An unattended session ran the documentation, specification, scripts and
learning-material work on branch `overnight/handoff-docs`. Nothing was pushed.

### Done

- **Committed the pre-existing uncommitted work** in three logical groups:
  UOB Wayback ingestion plus the earnings extraction fix, the continuous time
  series plus suggestions plus the dashboard Chat tab, and the blind test
  export.
- **Four real defects found and fixed**, each with a regression test:
  - `ingest/earnings_extract.py` called `text.split("")`, an empty separator that
    raises `ValueError` on every PDF page while the caller swallowed the
    exception, so the earnings source silently produced nothing.
  - `aspects/discover.py` bound one SQL parameter per sentence and had been
    dying on SQLite's 32,766-parameter ceiling since the corpus passed it,
    silently blocking the taxonomy decision.
  - `aspects/compare_taxonomies.py` measured at a hardcoded floor of 0.35
    while the pipeline used 0.65, so the tool meant to inform the taxonomy
    decision described a threshold nothing used. It also printed every table
    twice.
  - `chatbot/run_eval.py` discarded each tool call's result while the docs
    claimed the transcript contained it, which made the outstanding
    numerical-fidelity check impossible.
- **Compute jobs run:** aspect discovery on the full corpus, taxonomy
  comparison with a floor sweep, chatbot evaluation on `qwen3:4b` and a re-run
  of `llama3.1:8b`. Results in [evidence/](evidence/).
- **Documentation:** STATUS, DESIGN, RUNBOOK, README, data-viability,
  annotation-guideline, API_KEYS and `config/aspects.yaml` all corrected
  against the code and database. Stale sections marked superseded with dates
  rather than deleted.
- **New:** functional and technical specifications, 19 learning topics,
  `scripts/start.sh`/`stop.sh`/`status.sh`, `train/agreement.py`, and this
  file.
- **Tests:** 214 → 251, all passing in 62 seconds on an idle machine.

### Corrections

- STATUS's by-source document counts read 18,620 / 177 / 18 and summed to
  18,815 against its own stated total of 21,924. True figures are 21,726 /
  178 / 20.
- The FinBERT benchmark in the project context — "~88.2% accuracy vs ~62.1%
  for lexicon-only", marked *verified, safe to cite* — **is not in the FinBERT
  paper and could not be traced to any source.** Table 2 of arXiv:1908.10063,
  read directly from the PDF, reports 0.86 on the full Financial PhraseBank
  and 0.97 on the all-annotators-agree subset, with no Loughran-McDonald
  baseline at all. Corrected in place.
- The fabrication rate for the default chatbot model is 43–48%, not 48%. Two
  runs gave 11/23 and 10/23; the docs quoted one and the data file the other.
- These banks have not been required to report **quarterly** since 7 February
  2020. SGX RegCo moved to a risk-based framework with semi-annual reporting
  as the default. OCBC's 1Q and 3Q documents are voluntary business updates,
  not statutory results, and the corpus treats them as equivalent.

### Not done, and why

- **Fine-tuning.** Zero labels exist.
- **GPT and Gemini verification.** No API keys present.
- **A second pre-labelling pass with a different model.**
  `train/llm_prelabel.py` keys its progress file by sentence and aspect rather
  than by model, and its merge step writes into `candidates.csv`, so a second
  model would need code changes and must never touch `split=test` rows.
- **An incremental data refresh.** Deliberately skipped. Every figure in the
  documentation is from one consistent database snapshot, and a mid-run
  refresh would have invalidated numbers already written.
- **shellcheck** on the new scripts. Not installed on this machine; `bash -n`
  and a full start/stop/status lifecycle test were run instead.

### One late finding worth flagging

Re-running `llama3.1:8b` on the chatbot gold set turned up a measurement
problem, not just a model result. Its reported tool selection moved from 12/16
to 7/16 on identical questions, because 8 answers timed out and a question
that times out never calls a tool. **Tool-selection scores are confounded with
error counts in exactly the way fabrication rates are**, and only the
fabrication case was documented. Corrected in STATUS; do not compare that
column across models with different error counts. Detail in
[evidence/chatbot-eval-rerun-2026-09-11.md](evidence/chatbot-eval-rerun-2026-09-11.md).

### A bug the health check could not see

The Aspect Heatmap tab and the Overview page's per-source table had **never
rendered**. Both call pandas' `Styler.background_gradient`, which needs
matplotlib, and matplotlib was absent from `requirements.txt` from the first
commit. pandas defers that import until the Styler is rendered, inside
`st.dataframe`, so nothing failed at import time and `scripts/start.sh`
reported the dashboard healthy throughout — `/_stcore/health` answers for the
server, not for any page.

Fixed: matplotlib is declared, the tables fall back to a plain rounded view if
it ever goes missing again, and `tests/test_dashboard_styling.py` forces
`Styler._compute()`, which is the only thing that reproduces the failure.

**Open every tab after starting the dashboard.** A health check cannot tell
you a page renders.

### Runnable overnight next time

Aspect discovery with a swept `min_cluster_size` (the 281-cluster, 67%-noise
result used the default of 10 against a corpus that grew thirteen-fold, so it
is under-configured); a re-run of the full model comparison now that
transcripts capture tool results; and, once any labels exist,
`train/finetune.py` across at least three seeds.

## Overnight run log — diagrams (2026-09-26)

Ran `.project-context/prompt/overnight-diagrams.md`. Everything is in
[docs/diagrams/](diagrams/README.md); commits are on `main`, not pushed.

### Done

- All 20 diagrams, core 01–10 and extended 11–20. Each has the Mermaid source
  (`src/*.mmd`), a page with a sources table, and an SVG and PNG in `img/`.
  Commits `89237e9` (tooling and schema dump) through `88d63c4`, one per group.
- `docs/diagrams/README.md`: index, legend, how to regenerate, report shortlist.
- A "Diagrams" section in RUNBOOK, a row in the README documentation table, and
  one sentence linking the diagrams from technical-spec section 1. No other
  existing docs changed.
- Verification:
  - All 20 render (about 40 seconds).
  - `check_sources.py`: 286 rows, every `path:line` contains its symbol.
  - Schema check: diagram 03 matches the dump, 6 tables and 62 columns with the
    same types and primary keys.
  - Name check: 122 code-like names grepped. The 9 not found are state names in
    15 and 16 (now labelled as descriptive on those pages) and the RUNBOOK's
    shell and SQLite commands in 18.
  - Every PNG looked at; 14–20 re-laid out where labels overlapped or arrows
    crossed boxes.
  - `pytest -q` from the repository root: 395 passed, including the 41
    diagram-page tests.

### Found and fixed during verification

- `check_sources.py` skipped three rows whose symbol contains backticks,
  without saying so. It now parses them, and reports any row in a sources table
  it can't parse as a failure. Result: 286 checked, not 283.
- Adding the README row moved four README lines cited by diagram 18. The check
  caught it; the line numbers are updated.
- Re-rendering unchanged sources gives byte-different images: the Mermaid
  renderer jitters sub-pixel coordinates. The committed images were kept. A diff
  in `img/` with no diff in `src/` is noise.

### Doc/code disagreements (recorded, code not changed)

- **The conversation state's time window is never set.** DESIGN decision 19
  says the state tracks bank, aspect and time window. No tool schema offers the
  model a window argument (`get_sentiment` accepts one in Python only), so
  `window` stays empty. Diagram 15 shows it as it is.
- **The volume floor is applied when a score is read, not when the index is
  computed.** The chatbot tools apply it (`MIN_VOLUME_FOR_SCORE = 5`), and so
  does the time series (`min_n=5`, drawn on the dashboard as omitted buckets).
  Stored index rows carry `n` and shrinkage but no floor. PLAN section 3's
  "volume floors already in `aggregate/index.py`" is true only of the time
  series. Diagrams 04 and 12 are drawn from the code.
- **The index is not incremental.** Every other pipeline step skips rows it has
  already processed, but `aggregate.index` deletes and recomputes the whole
  index each run. Diagram 04's first caption said otherwise and was corrected
  before commit.
- **`documents.has_analyst_view` is not in the schema that `ingest/db.py`
  creates.** `ingest/analyst_tag.py` adds it with `ALTER TABLE`, so a fresh
  database lacks it until that step runs. It is 0 for all 27,795 documents, as
  the technical spec says.
- **Foreign keys are declared but not enforced.** Three are declared, but no
  code runs `PRAGMA foreign_keys=ON`, so SQLite ignores them. Diagram 03 draws
  them solid and says so.
- **The dashboard footer is stale.** It says news covers "~1-month", but news
  is backfilled to 2023 (`dashboard/app.py:132`).
- **The test count in the docs is stale.** RUNBOOK and technical spec say 251
  tests; `pytest tests/` collects 354. Also, `pytest tests/` doesn't run the
  diagram test; `pytest -q` from the root does (noted in the RUNBOOK section).
- **The evaluation tests single turns only.** `chatbot/run_eval.py` asks every
  gold-set question as a new conversation, so memory isn't covered by the
  suite. Diagram 20 says so; multi-turn scenarios are already planned.

### Left out, and why

- API endpoints other than `/chat`: they are one-line lookups; the technical
  spec's API contract covers them.
- The CNA scraper: it isn't wired into the pipeline yet (CNA loading is a PLAN
  week-2 task), so a diagram now would be of a plan that may change.
- Earnings and Reddit ingestion sequences: they follow the same shape as the
  news pull (05), and 06 shows where they sit in a batch run.
- The run log was written at the end of the run rather than after each group,
  as the prompt asked. Nothing was lost; the commits mark each group.

### Needs a human

- **Confirm the report shortlist** in `docs/diagrams/README.md`: 01, 03, 04,
  07 (or 08), 09, 10, with 17 and 20 as candidates.
- **Push, then check GitHub renders the pages.** GitHub renders Mermaid itself,
  from a different version than the CLI used here (11.17.0). If a page fails,
  the SVG linked under each diagram is the fallback.
- **Decide on the window gap:** either expose a window argument in the tool
  schemas, or drop "time window" from DESIGN decision 19.
- Optionally fix the dashboard footer and the test counts. They are one-line
  doc and UI edits, left alone because this run doesn't change code or existing
  docs beyond the links.

## CNA loaded (2026-09-26)

CNA was the one planned addition to the frozen corpus. `ingest/cna_archive.py`
finds CNA bank articles from 2023 on through the Wayback Machine's index of CNA
URLs, fetches their full text at CNA's robots.txt crawl delay, and loads them
through the news filter. Result: 207 articles and 1,599 sentences, run through
every pipeline step. The new snapshot is `plp-2026-09-26-v2.db.gz` (README).
Decision and trade-offs: DESIGN decision 20. Coverage and gaps: news-data.md.

- **The filter changed.** A full-text article is no longer dropped as a
  duplicate of a headline-only copy; 117 CNA stories would have been lost to
  Google News headlines. No stored row was deleted.
- **CNA is not a complete record.** Only headlines whose URL names a bank are
  found, and only what the archive captured: 0 to 13 articles a month.
- **Needs a human:** whoever owns the CNA scraper should spot-check a few
  articles, and share the new snapshot in the team folder.
- **Setup:** `trafilatura` is in `requirements.txt` but was missing from this
  machine's venv; run `pip install -r requirements.txt` after pulling.
- Superseded in the diagrams log above: CNA is now loaded (diagrams 01, 04
  and 11 show it), and the test counts in README, RUNBOOK, STATUS and the
  technical spec are corrected (379 in `tests/`).

## Text-analytics workstream integrated (2026-09-30)

The workstream's 25–27 Sep work (10-aspect taxonomy, first labelling round,
first fine-tuning) is now in the repository. Evidence:
[aspect taxonomy](evidence/aspect-taxonomy-2026-09-25.md),
[annotation agreement](evidence/annotation-agreement-2026-09-27.md),
[fine-tuning](evidence/finetune-2026-09-30.md). Decision: DESIGN 21.

- **Taxonomy.** `config/aspects.yaml` has ten aspects. The corpus was
  re-assigned and re-scored under them; snapshot `plp-2026-09-30.db.gz`.
- **Labels.** `data/labeled/` holds both annotators' sheets, the resolved
  sheets, and `candidates.csv`, which `python -m train.labels` builds: it
  removes 5 train/dev copies of test sentences and 18 duplicate rows, and
  takes test labels from the blind sheet. Training refuses a file that still
  has either problem. Sentiment κ 0.93 (test sheet 0.96).
- **Fine-tuning.** Three seeds, macro-F1 0.547 ± 0.013 against base FinBERT
  zero-shot's 0.571. Better on negative sentences (recall 0.54 against 0.21).
  Models in `models/` (gitignored); share `models/finbert-absa/seed_*/final`
  through the team folder.
- **Notebooks.** The workstream's four Colab notebooks are in `notebooks/`,
  outputs cleared; a test keeps them that way.
- **Fixed on the way.**
  - The index counted a sentence once per aspect it matched in its
    cross-aspect rows. At 6.4 aspects per sentence that would have lifted
    DBS's headline to +0.23. Each sentence now counts once: DBS +0.122,
    OCBC +0.136, UOB +0.074. Earlier published figures (+0.060, +0.071,
    +0.036) used the old method.
  - Scoring classified a sentence once per aspect. It now classifies each
    sentence once, batched by length, committing as it goes.
  - Colab needed a runtime patch for CUDA; `config/device.py` now picks it.
  - `train.agreement` double-counted duplicated pairs.
- **Needs people.**
  1. The test labels are not blind: each annotator's blind-sheet labels
     match their labels made with the LLM suggestion visible. Decide whether
     to relabel the 299 test rows blind.
  2. Aspect agreement was never measured; five aspects have under 80 rows.
     A small second round would fix both.
  3. The cluster labels behind the taxonomy were drafted with an AI
     assistant: put that in the GenAI declaration.
- **Gemini.** A free-tier `GEMINI_API_KEY` is in `.env`, for the chatbot
  only. It works (the first key didn't), and the backend is now verified live
  ([evidence](evidence/gemini-backend-2026-09-30.md)). While a key is set,
  the chatbot's auto-detection picks Gemini over Ollama; set
  `CHATBOT_BACKEND=ollama` to keep the local model. The model comes from
  `GEMINI_MODEL` or `GEMINI_CHAT_MODEL`; `.env` asks for `gemini-3.8-flash`,
  which was overloaded (503) on 2026-09-30, while `gemini-3.6-flash` worked.
  Free-tier inputs may be read by Google's reviewers: don't send evidence
  text (`search_evidence` returns Reddit posts).

## Overnight run log — experiments (2026-09-30)

Running `.project-context/prompt/overnight-experiments.md` from HEAD
`a6bad3d`. Baseline: 445 tests pass; Ollama up; 58 GB free.

- Job A (fine-tuning experiments): done, `454c989`. 8 epochs chosen on dev
  (0.637 against 0.616); test macro-F1 0.577 ± 0.027, level with base
  FinBERT's 0.571. The aspect input wins in all five CV folds (+0.026) and
  lifts negative-class F1 from 0.29 to 0.44
  ([evidence](evidence/finetune-experiments-2026-09-30.md), with model
  checksums).
- Job B (assignment calibration): done, `60b9a53`. Seed-centroid top-1
  accuracy against the human aspect labels is 0.41-0.42 at any floor up to
  0.70 (majority-class 0.37); no floor fixes it
  ([evidence](evidence/aspect-assignment-calibration-2026-09-30.md)).
- Job C (discovery sweep): done, `78d796b`. 358 clusters at 10 (65% noise),
  collapse into one cluster at 25 and 50, 25 aspect-like clusters at 100.
- Job D (chatbot evaluation): done, `d35d032`. 3B unchanged from 26 Sep;
  8B: 13/16 tools, 7/7 behaviour, 4/23 citation warnings, 3/23 answers with
  invented figures, no backend errors. All 29 flagged figures were real
  inventions; 2 of 14 citation warnings were false alarms
  ([evidence](evidence/chatbot-eval-2026-09-30.md)).
- Verification: 454 tests pass; diagram sources clean after updating nine
  moved line numbers in pages 04, 09, 16 and 17; every number in the four
  evidence files comes from a command in that file; `models/` stays out of
  git (weights and checksums listed in the fine-tuning experiments file).

Left out, and why:
- Nothing from the prompt. The CV fold models were deleted after scoring, as
  specified; only the final sentence-plus-aspect and sentence-only models are
  kept.
- `aspects.compare_taxonomies` measures its own hard-coded four-aspect
  candidate A, not the current config, despite its docstring. Recorded in the
  calibration file, not fixed (outside the run's scope).

Needs a human:
1. **Scoring model.** The sentence-plus-aspect model (8 epochs) is level with base FinBERT
   on macro-F1 (0.577 ± 0.027 against 0.571), better on negative sentences
   (0.44 against 0.30) and worse on neutral. Whether it replaces base
   FinBERT for the corpus is PLAN section 5's decision.
2. **Aspect assignment.** No floor makes centroid assignment accurate (top-1
   0.41); leave the floor at 0.65 and build the LLM classifier, whose
   baseline is now measured.
3. **Demo model.** The 8B invents far less than the 3B (3 against 9
   invented-citation answers) at about twice the runtime.
4. **Model weights** exist only on this MacBook; copy them to the team
   folder and check the SHA-256 values in the experiments file.


## Overnight run log — night 1 (2026-10-01)

Running `.project-context/prompt/overnight-night1.md` from HEAD `57a8230`.

- Doc/code disagreement found before training: `train/finetune.py` computed
  and printed balanced class weights but never passed them to the loss, while
  its docstring, the technical spec and the 30 Sep evidence said
  "class-weighted loss". Every model so far used plain cross-entropy. Fixed in
  the docs; the weighting is now a real option (`--class-weights`), default
  `none` so earlier results stay reproducible.
- Fine-tuning fixes: done
  ([evidence](evidence/finetune-fixes-2026-10-01.md)). Per-batch padding
  matches the old padding within noise (CV 0.621 against 0.622). On 5-fold
  CV, balanced class weights (0.630), source weights (0.633) and the
  readable aspect label (0.637) each lean ahead of the baseline (0.621),
  all within the noise between two runs of the same configuration; prior
  class weights collapse (0.525), which CV can't judge fairly. The three
  combined scored 0.635, so the readable label alone was trained on seeds
  42, 1, 7: test macro-F1 0.630, 0.617, 0.565 (0.604 ± 0.035; 3-model
  average 0.615) against 0.577 ± 0.027 on 30 Sep and base FinBERT's 0.571.
  Neutral sentences called polar remain the main error. The Mac slept
  12:22–13:29 (battery at 1%, then lid closed; `caffeinate -i` stops
  neither), pausing one CV fold; it resumed unharmed.
- LLM aspect classifier: done
  ([evidence](evidence/llm-aspect-classifier-2026-10-01.md)). On the 1,277
  human aspect labels, llama3.1:8b scores top-1 0.729 (macro-F1 0.679) and
  qwen3:4b without thinking 0.719 (0.671), against 0.413 (0.296) for
  seed-centroid assignment; no invalid answers. Full corpus: about 24 h
  (llama) or 16 h (qwen) on this Mac. Where the two agree (76%), they match
  the human label 83.5% of the time. Nothing written to the database.
  qwen3:4b needed a `--no-think` option: thinking took 92–216 s a sentence.
  The Mac slept again 15:51–17:20 (battery), pausing the qwen run.
- Opus 5.5 labeller (asked for on 1 Oct, outside the night 1 prompt; DESIGN
  22): Opus subagents labelled all 1,277 rows blind, aspect then sentiment
  given the human aspect, with the guideline as instructions; transcripts
  audited, no rater opened another file. Against the human labels: aspect
  κ 0.80 (0.842; llama3.1:8b 0.729), sentiment κ 0.79, every sentiment
  disagreement on the neutral boundary. Review queues: 202 aspect, 173
  sentiment rows in `data/labeled/llm_rater/`; nothing applied to
  `candidates.csv` ([evidence](evidence/llm-rater-2026-10-01.md)).
- Verification: 479 tests pass (`pytest -q` from the root, slow tests
  included); `docs/diagrams/check_sources.py` clean (moved line numbers
  updated); PLAN section 5 points to the night 1 evidence.

**Needs a human (night 1):**

1. Whether the readable-label fine-tuned model should score the corpus in
   place of base FinBERT, and if so the 3-model average (test macro-F1
   0.615) rather than one seed. It calls fewer sentences neutral.
2. Whether to run the LLM aspect classifier on the corpus (llama3.1:8b
   about 24 h on this Mac, qwen3:4b about 16 h, both about 40 h) and what
   to do where the two disagree (24% of sentences, each right under half the
   time): keep llama's answer, `other`, or unassigned.
3. ~~The four README fixes in
   [install-test-2026-10-01.md](evidence/install-test-2026-10-01.md).~~
   Made on 1 Oct, with RUNBOOK, STATUS and both specs brought up to date.
4. The Opus review queues (202 aspect, 173 sentiment rows; 43 and 37 on the
   test split), and where a retail customer's investment products belong,
   wealth or retail banking (63 rows), before the next labelling round.
5. Long runs need the Mac plugged in with the lid open: it slept twice on
   1 Oct (battery, then lid), pausing jobs for about an hour each time.
- Preprocessing dry run: done, `606dde4`. 98 of 44,345 sentences
  (0.22%, all earnings PDFs) are debris; broader rules remove real
  sentiment, so preprocessing isn't where the model's errors are.
- Install test: done, `1ff6c74`. With a Mac's default `python3`
  (Apple's 3.9) the install fails on `torch>=2.9.0` and the README never
  names the Python it needs; with 3.14 every step works, the snapshot
  checksum matches, 421 tests pass, and the API and dashboard answer on free
  ports ([evidence](evidence/install-test-2026-10-01.md), four README fixes
  listed there).

## 1 October, evening, and the night after (2026-10-01/02)

Work asked for during the day on 1 Oct, after night 1. Nothing was written
to the database.

- **Measurement tools.** `train.agreement --field aspect` measures aspect
  agreement (`302feb9`). `aspects.compare_taxonomies` now compares the live
  ten-aspect config, not a hard-coded four (`60ec01f`).
- **Fine-tuned model's errors** (`9d0be44`,
  [evidence](evidence/error-analysis-2026-10-01.md)). Most errors are
  neutral sentences called polar. A neutral margin chosen on dev lifts the
  3-model average to test macro-F1 0.624 (accuracy 0.682); base FinBERT
  scores 0.571 (accuracy 0.70).
- **Bank entity recognition** (`861d205`,
  [evidence](evidence/bank-ner-2026-10-01.md)). spaCy with an entity ruler,
  a resolution table and a gazetteer fallback. On the corpus it disagrees
  with alias matching on 714 sentences, mostly DBS Vickers (456) and UOB Kay
  Hian (132). A 201-row gold sheet is in `data/labeled/ner/`, blank: its
  labels are for people.
- **Dashboard handed to its own project** (`36283da`, DESIGN 23; reversed
  the same night, when the teammate pushed a redesign to this repository:
  the dashboard stays here, see the amendment to DESIGN 23). The API
  is the interface: `/evidence/latest`, `/analyst-consensus/latest` (which
  fixes UOB being hidden by a global latest date) and `/aspects` are new, and
  the contract is [api-integration.md](api-integration.md), with
  `docs/api/openapi.json` kept current by a test. The chatbot has a terminal
  client, `python -m chatbot.chat`.
- **Chatbot evaluation extended** (`701014d`,
  [evidence](evidence/chatbot-eval-build-2026-10-01.md)): gold set v2 (32),
  four multi-turn conversations, retrieval metrics and an LLM judge. Asked
  as a question, evidence search ranks no better than random (MRR 0.217,
  random 0.217); the aspect's name reaches 0.559. The fix is in place behind
  `CHATBOT_ASPECT_QUERY=1`, off by default (`2b209d3`).
- **Index preview** (`c7f21f1`,
  [evidence](evidence/index-preview-2026-10-01.md)). On 1,000 sampled
  sentences, LLM aspects leave the headline unchanged. The fine-tuned model
  raises every headline (by 0.06–0.19 on that sample; a second preview on
  11,000 sentences on 2 Oct gives 0.04–0.09 with LLM aspects and no change
  in ranking, so the UOB-ahead-of-DBS result was noise). On a
  swapping Mac, the GPU returned all-zero probabilities without an error;
  the preview now refuses them and was rerun on the CPU.
- **Report draft** of the factual sections (`a65c4b4`) and an
  **examiner's assessment** at Bloom levels 4–6, with the learning folder
  brought up to 1 Oct (`814b65d`).
- **Clean install retested** (`c7f21f1`): passes from a fresh clone with
  Python 3.14.
- **Top-up labelling sheet** (`092367c`,
  [evidence](evidence/labelling-topup-2026-10-01.md)). 268 blind rows for the
  five aspects under 80 labels. NIM may end near the floor: most Reddit rows
  the LLM called NIM are customer rates.
- **LLM aspect classifier corpus mode** (`5d7c591`). `--corpus` fills the
  answer cache in a fixed random order and writes nothing to the database.
- **Judge against the harness** (`1b665fb`). `chatbot.judge checks` scores
  the judge on answers the harness flagged for invented citations, with no
  human ratings needed.
- **Larger hosted models through the OpenAI backend.** It now reads
  `OPENAI_BASE_URL`, so any OpenAI-compatible provider works. Groq's free
  tier offers `openai/gpt-oss-120b`, `llama-3.3-70b-versatile` and
  `qwen/qwen3.8-27b`. It retries rate limits and sends back only standard
  message fields. Setup and the three-model gold-set loop are in the
  RUNBOOK. It is unverified until someone adds a Groq key: that's on the
  submission checklist.

### Overnight, 1–2 October

Run one job at a time on the MacBook from 22:54. Nothing was written to the
database.

- **Chatbot, gold set v2 and conversations** (`593dc96`, `e82f6a3`,
  [evidence](evidence/chatbot-eval-build-2026-10-01.md#live-runs)). On an
  idle machine `llama3.1:8b` chose the right tool for 20 of 24 questions,
  handled 8 of 8 advice and no-data questions, and invented citations in
  11 of 32 answers; `llama3.2:3b` 18/24, 8/8 and 15 of 32. Every flag was
  read by hand: all of the 8B's are real, 14 of the 3B's 15. **None of them
  called `search_evidence`**: the models write an evidence section after
  looking up a score, against prompt rule 8. Conversations: 7 of 9 turns
  right. The scope guard refused "Has that improved lately?" because it
  doesn't see the conversation, and the 8B once wrote a tool call as text.
  A first run that shared Ollama lost 6 questions to timeouts; it is kept,
  not reported.
- **The judge doesn't discriminate.** `qwen3:4b` without thinking scored all
  32 answers 3, including the 11 inventions. `chatbot.judge checks`
  (`1b665fb`) measures this against the harness's flags without people.
- **Noise-floor cross-validation**
  ([evidence](evidence/noise-floor-cv-2026-10-02.md)). Seeds 1 and 7, both
  inputs, 20 folds, 23:46–03:04. The readable label's lead on seed 42
  (+0.017) doesn't replicate (−0.003, +0.001; +0.005 over 15 paired folds).
  The final models stand; the report must not credit the input change.
- **Corpus aspect classification** started at 03:04 into the answer cache
  (`aspects.llm_classify --corpus`), about 20 sentences a minute; stop it
  with `pkill -f "llm_classify --corpus"` and it resumes from the cache.
- **Dashboard merged back** (`d31da61`): a teammate pushed a redesign while
  this branch had removed the dashboard; the team chose to keep it here
  (DESIGN 23, amended).
- **Verification:** 551 tests pass; `check_sources.py` clean.

**Needs a human (1–2 Oct):** the full list, with reasons, is the team to-do
page ([briefs/team-todo-2026-10-02.html](briefs/team-todo-2026-10-02.html)).
The new items since night 1: label the top-up sheet; fix the dashboard's
consensus panel (it hides UOB); get a free Groq key; decide whether evidence
search ranks by the aspect's name; and the examiner's assessment
([review/examiner-assessment-2026-10-02.md](review/examiner-assessment-2026-10-02.md)).

### 2 October, morning

Asked for after the night's results; nothing written to the database.

- **Chatbot fixes** (`29dee6b`; [evidence](evidence/chatbot-eval-build-2026-10-01.md#second-round-2-oct-the-fixes-live)).
  The scope guard reads the conversation, a tool call written as text is
  run, and `CHATBOT_ENFORCE_EVIDENCE=strip` (off by default) removes evidence
  written without a search. Live: conversations 9/9 on both models; invented
  citations 11 → 0 (8B) and 15 → 2 false alarms (3B), tool choice unchanged.
  `CHATBOT_ASPECT_QUERY=1` makes evidence more topical but often boilerplate.
  `qwen3:4b` isn't a viable chatbot here (22 of 32 timed out).
- **Judges.** The one-score judge passes everything; a checklist prompt
  (list unsupported quotes, sources, figures) catches all 11 known
  inventions with the same `qwen3:4b`, with about three false alarms (a
  quote it overlooked, a rounded figure; not truncation, as first written). `gemma3:4b` and thinking runs
  are not usable.
- **Labels.** The top-up merge is `train.labels --topup` (`a387f2a`); Opus
  rated the top-up and NER sheets blind (`15238d8`): NER matches it on 200
  of 201 after an "OCBC360" fix (`13897f6`); macro, not NIM, is the top-up
  shortfall. The ratings sheet now hides the harness's warnings.
- **For the report and team:** [local-context questions](local-context-questions.md),
  [the approach](report/approach.md) with diagrams 21–23,
  [findings, limitations and solutions](report/findings-limitations-solutions.md),
  the AI usage declaration up to date.
- **Code clean-up:** superseded scripts removed and `rater_extra` folded into
  `rater_labels` (`553a742`); comments and messages made plain across the
  code (no behaviour change); the teammate's dashboard left as written.

**Needs a human (2 Oct):** whether to switch strip enforcement on for the
demo; the answers in `local-context-questions.md`, the bank-economist
question first, since it decides whether macro can reach 80 labels;
whether the PDF URLs in the database, which carry the macOS username, should
become relative paths.

### 2 October, evening

- **The LLM aspect cache is named by its prompt:**
  `data/aspect_llm/<model>.<prompt>.jsonl`, where `<prompt>` hashes the
  aspect keys, definitions, examples and instructions (`96efe244`). Before,
  `--eval` and `--corpus` silently reused cached answers after a wording
  change. The three existing caches were renamed to `96efe244`: no edit after
  the first cached answer (1 Oct 14:43) touched the prompt, and
  `config/aspects.yaml` last changed on 30 Sep. The running corpus job kept
  its file handle, so it appends to the renamed file.
- **Corpus run time:** a full run takes about a day, a little more than the
  labelled-set estimate, and longer with another job on the Mac. This run
  finishes around midday on 3 Oct.
- **To-do page** (`2ee4597`): when the corpus run must be redone, with the
  run times, and the wealth-or-retail decision with its redo cost.
- **Run times as rough estimates** (the team asked for no exact hours): a
  full corpus run is about a day, testing a new wording under an hour.
- **Index preview made resumable** (`aggregate/preview.py`): the fine-tuned
  models' averaged probabilities are saved per pair in
  `data/preview/scores.<key>.jsonl` (models and device), a chunk at a time; a
  `--margin` option applies the dev-chosen neutral margin; the database
  query runs in batches, since one query for the whole corpus exceeded
  SQLite's 32,766-parameter limit. The 11,000-sentence outputs moved to
  `data/preview/n11000/`.
- **Full-corpus preview queued:** a watcher (scratchpad `after_corpus.sh`)
  waits for the corpus run, checks every sentence has an answer, then runs
  the preview on the CPU, plain and with margin 0.13. Logs:
  `after_corpus.log`, `preview_full.log`, `preview_full_m013.log`.
- **Decision brief:** decision 5 states the redo cost of "by customer".
- **Verification:** 552 tests pass in `tests/` (599 from the root);
  `check_sources.py` clean.
- **DBS Vickers checked on the web:** DBS Vickers Securities (Singapore) is
  in DBS Group's list of subsidiaries (31 Dec 2024); UOB Kay Hian is
  separately listed (SGX U10), UOB holding about a third. The 456 affected
  sentences are customers using DBS Vickers as their broker, none research
  about another bank. Recorded in the local-context DBS Vickers question, the bank-NER evidence,
  a note in PLAN section 7, decision 6 of the brief and the to-do; the
  `vickers` rule in `preprocess/bank_ner.py` is unchanged until the team
  confirms.
- **Model card and report docs corrected after a fact-check** of
  `docs/model-card.md` and then of the fix: averaging the seeds is
  the safer choice, not the best (seed 42 alone scores 0.630); train/dev was
  drawn in thirds by base FinBERT's label, not by aspect; product names are
  common in the labels (82 of 1,277), Singlish barely measured; the anchoring
  may favour the fine-tuned models, unmeasured; the margin is 0.133; the
  test labels weren't blind in practice; file sizes in decimal MB (models
  438 MB, embeddings 127 MB). Same fixes in `docs/report/approach.md`,
  `findings-limitations-solutions.md`, `local-context-questions.md`, the
  technical spec and the README.
- **Validation workflow added** (`.claude/`, see `CLAUDE.md` "Validation"):
  `reviewer`, `tester`, `triage`, `auditor` (docs) and `examiner` agents, and
  `/validate <scope>`, which reports the three success claims as PROVEN, DISPROVEN or UNTESTED
  and keeps dated runs in `docs/validation/`. The first run (API integrity, `api/`)
  found three medium bugs: the trend direction compares shrunk scores (UOB
  reads "declining" though its unshrunk change is +0.12), readers will mix
  model versions after the re-score, and `/coverage` and `/evidence` accept
  any bank. Each has a strict-xfail test in `tests/test_validate_api.py`;
  remove the marker in the commit that fixes it.
- **Fine-tuned models on Hugging Face:** private repo
  `plp-bank-sentiment/plp-finbert-absa` (organisation members only): the three
  seeds without `training_args.bin`, and the model card as `README.md`.
  Downloaded back and hashed on 2 Oct: all three match the model card's
  SHA-256 values. Commands in README, "Sharing the data and models".
- **Corpus run speed:** it slowed to 5–6 s a sentence while two external
  monitors (DisplayLink) were on and the upload ran, and returned to about
  2.5 s once both stopped. Keep external monitors off during long GPU jobs.

### 3 October

- **The three API bugs from the API-integrity validation run are fixed**, and three
  low ones with them; every `test_validate_api.py` test now passes, with no
  `xfail` left (592 tests in `tests/`, 639 from the root):
  - **Trend direction:** `get_trend` compares the 7d and 30d scores
    before the n/(n+5) shrinkage. UOB no longer reads "declining" when its
    week was better than its month.
  - **Model versions:** the current version lives in
    `config/model_version.py` (out of `sentiment/score.py`, which imports
    torch). The API, the chatbot's tools, evidence search, suggestions, the
    time series and the preview read only that version, so fine-tuned scores
    can sit beside the base ones at the re-score without doubling anything.
    **The dashboard still reads every version** (`dashboard/app.py` lines 72,
    89 and 103): its owner should add `AND model_version = ?` with
    `config.model_version.MODEL_VERSION` before the 12 Oct re-score.
  - **Bank names:** `/coverage` and `/evidence` reject a bad `bank` with
    422, like the other endpoints; `docs/api/openapi.json` regenerated.
  - **Low ones:** the spec's promised 400 for a bad bucket, which the API
    couldn't return, is gone, with its dead code; `/sentiment/index`
    rows carry `insufficient_data`; a database error in the trend's
    monthly series is logged and reported, not shown as "no data".
- **API integrity validated after the fixes** (`/validate`, record in
  `docs/validation/2026-10-03-api-integrity.md`): every index endpoint equals
  the stored rows and every bad `bank`, `window` or `bucket` gets 422
  (`tests/test_validate_api_integrity.py`, which reads a copy of the live
  database). It found three more problems, now fixed: the trend response
  returned shrunk scores beside a delta computed from unshrunk ones (it now
  returns `recent_7d_unshrunk_score` and `baseline_30d_unshrunk_score`); a
  model version with no rows looked like ordinary missing data (now reported
  and logged); `/evidence?k=-1` dropped the last result (`k` is now 1–50).
  Open: whether a 7-day window of 5 to 10 sentences is enough for a
  direction, and whether `source` and `aspect` should be validated.
- **Misdated UOB earnings files** (found by two reviewers): the filename
  parser in `ingest/earnings_extract.py` couldn't read `q1-2024` or
  `2023-results`, so six UOB documents (114 sentences of 2023–24 management
  prose) carry their ingestion date, 10 Sep 2026, and count as recent: 114 of
  the 230 sentences behind UOB's 30-day headline. The parser is fixed and
  tested. **Repairing the stored dates needs approval** (a database write):
  `.venv-plp/bin/python3 scripts/fix_earnings_dates.py` shows the six
  changes; add `--apply`, then re-run `aggregate.index`. Re-running the
  extraction alone doesn't fix them, because existing documents are skipped.
- **Scorer tag:** `sentiment/score.py` tags rows with the model it runs
  again, independent of the version readers serve, so changing
  `config/model_version.py` can't relabel base scores.
- **Chatbot grounding guards: eight confirmed weaknesses** (tests marked
  `xfail` in `tests/test_validate_chatbot_grounding.py`): an invented quote
  passes once any search has run; strip mode leaves evidence in a one-
  paragraph answer while saying it removed it; the number check ignores the
  sign, accepts 0.12 written as 0.12%, skips a number after a date, and its
  ratio set accepts 85–95 of the whole percentages 1–99 on a trend answer;
  curly or wrapped quotes and URLs without http(s) go unchecked. The "11 → 0
  invented citations" in the decision brief was measured with these guards.
- **Chatbot grounding guards fixed** (all eight; details and the re-measured
  table in `docs/evidence/chatbot-eval-build-2026-10-01.md`, "Third round"):
  strip still takes citation warnings to 0 on both models (8B 11 → 0, 3B
  16 → 0) under checks that now also compare quoted text with what was
  retrieved, respect signs and percentages, and pair counts only within one
  result. Figures no tool returned: 8B 10 → 0, 3B 12 → 2 (two inventions the
  old check missed). `chatbot.replay` now uses today's checks for both
  columns. The decision brief and the to-do carry the new figures.
- **Training review** (`docs/evidence/training-review-2026-10-03.md`):
  - **Fine-tuning relabelled FinBERT's head.** Base FinBERT orders its
    outputs positive, negative, neutral; training loaded it as negative,
    neutral, positive and kept the weights, so every model started with each
    output answering for the wrong class. Fixed in `train/finetune.py`. It
    biases the reported lead down, not up. **Retraining the three seeds is a
    team decision** (GPU time; changes the reported results).
  - **A top-up row nearly copies a test sentence** (word overlap 0.93,
    different id). `prepare` now drops such rows and `check_splits` refuses
    them.
  - Training saves its dev rows (`dev_ids.json`); the margin search refuses
    to reshuffle once train_dev has grown. The candidate export no longer
    overwrites the labelled file without `--force`.
  - The model card says these models weren't retrained; the copy on Hugging
    Face predates that line.
- **Reddit fetcher no longer reads a failure as the end of the data.**
  `ingest/arctic_shift.py` returned an empty page on any request error,
  server error, 422 timeout or bad JSON, and the window loop stopped there:
  comments are missing for 4–30 Sep 2021, 14–31 May 2024 and 5–31 Mar 2025,
  each gap ending at a month boundary while posts for the same months are
  normal. It now retries, then logs the window as incomplete. **Refilling the
  three gaps needs approval** (network pulls and database writes):
  `python -m ingest.arctic_shift --since <start> --until <end>` per gap, then
  preprocessing, embedding, aspects, scoring and the index for the new rows.
- **Still open from the reviews, for the team:** `ingest/cna_articles.json`
  (committed with the CNA scraper) holds the full text of 15 CNA articles,
  against the rule that CNA text is never committed; removing it is one
  `git rm`, but teammates lose their copy on the next pull and the text stays
  in git history. 118 "Kay Hian" sentences are attributed to UOB until NER
  is applied (known, decision brief).
- **Corpus aspect run done** (14:04, 3 Oct): all 44,345 sentences answered by
  `llama3.1:8b`, none invalid. Retail banking 19,089, investor stock 5,545,
  wealth 4,252, other 4,235, income and profit 3,602, guidance 2,023, asset
  quality 1,530, NIM 1,332, capital 1,222, macro 906, dividends 609.
- **Full-corpus index preview** (14:04–19:19,
  `docs/evidence/index-preview-2026-10-01.md`, last section): with LLM
  aspects and the fine-tuned models (margin 0.13) every headline rises by
  0.04–0.07 and DBS moves just ahead of OCBC (today OCBC is just ahead; both
  gaps under 0.02); UOB is last either way. **Correction:** the 11,000-sentence
  preview said the ranking was unchanged; today's index has OCBC first.
  Corrected in the evidence, findings, decision brief and to-do.
- **Code labels replaced by names** across the docs, the `.claude` agents and
  `/validate`, and the validation tests: success claims (Fine-tuning lead,
  API integrity, Grounded chatbot), the functional spec's requirement IDs (the
  `#` columns are gone), PLAN's made and open decisions, the 30 Sep
  experiments, the 1 Oct jobs, review findings and the local-context
  questions. Agents now name each finding in a few words instead of
  numbering it. `CLAUDE.md` ("Writing docs") says so. Two tables in the
  functional spec, split by a stray blank line, are whole again.
- **The re-score step is ready** (`040ed26`). `scripts/rescore.py` applies
  the LLM aspects and the fine-tuned scores (three seeds averaged, margin
  0.13) in one transaction with its checks and the index rebuild, refuses
  `data/plp.db` without `--real-db`, and backs it up first. On a fresh copy
  it took seconds and matched the full-corpus preview in all 36 bank-aspect
  cells (scores within 0.0001). Afterwards: set `MODEL_VERSION` (the version
  `finbert-finetuned-2026-10-01-3seed-m0.13` is already listed in
  `FINETUNED`) and `assignment_method: llm`. While a fine-tuned version is
  served, `sentiment.score` scores new pairs with it too. RUNBOOK, "Apply
  the aspect and sentiment decisions".
- **Index and scorer fixes** (`244b7c0`): windows and series buckets use
  UTC instants and ISO weeks; the index counts a score only while its pair
  is assigned; the series raises on an unknown label; `sentiment.score`
  refuses probabilities that don't sum to 1 and takes `--cpu`;
  `aggregate.preview --per-seed` measures the spread between seeds.
- **Ingestion fixes** (`bf0357f`), future data only: failed Reddit and
  Google News windows no longer pass as done or quiet, CNA retries
  temporary failures, PDF extraction keeps wrapped sentence ends, Reddit
  text is unescaped before quotes are removed, the blind-sheet export needs
  `--force` to overwrite, no home paths in code.
- **Earnings-date repair rehearsed on two copies**: only UOB's 30-day rows
  change (24 rows); its headline goes from +0.315 on 211 sentences to
  +0.251 on 97.
- **Hugging Face**: the model card is re-uploaded and matches
  `docs/model-card.md`. It has no metadata block, so the Hub warns; cosmetic.
- **New commands**: `/sync-docs`, `/handoff`, `/jobs`, `/examine`,
  `/team-message` (`CLAUDE.md`, "Validation").
- Three reviewer runs found the bugs above; every fix has a test that failed
  before it. 850 tests in `tests/` (848 pass, 2 skipped), 897 from the root.
- **Seed-to-seed spread measured** (index-preview evidence, last section):
  each fine-tuned seed alone gives DBS +0.113 to +0.235, OCBC +0.116 to
  +0.210, UOB +0.105 to +0.149. With seed 1 alone OCBC stays ahead of DBS
  and both fall below base FinBERT, so "DBS moves ahead" and "every
  headline rises" hold for the three-seed average only; 8 of 30 named cells
  (NIM and macro for every bank) change sign between seeds. Corrected in
  the findings, the decision brief and the to-do.

**Needs a human (3 Oct, evening):** approve the three data repairs on the
to-do (earnings dates; the Reddit gaps, whose three markers in
`data/.backfill_progress.txt` must be deleted before a rerun; CNA text in
git); the dashboard owner adds the `model_version` filter, and should check
that the series' week labels, now ISO weeks, still plot; retraining stays on
hold. Known and not fixed: `run_daily_batch.py` still exits 0 when a window
fails (it logs it; the daily job is stopped); a short PDF tail that starts
with a capital (say "S$1.2 billion") still splices; Reddit spoiler lines
(`>!`) are now removed as quotes; a few news sentences reach a bank only
through a venue name (UOB Plaza, OCBC Cycle), which NER's resolution table
doesn't cover yet; the LLM aspect cache has two duplicate lines (same
answers, harmless).


### 4 October

- **Chatbot questions are sorted by a model, not by word lists** (DESIGN
  decision 24). `chatbot/intent.py` asks a local model (`llama3.1:8b`,
  Ollama structured output) which of eleven intents a question is:
  in-scope questions go to the chatbot model; advice, another bank, small
  talk, help, banking service, prompt injection, feedback and off-topic get
  a reviewed fixed reply from `config/intents.yaml`. If the classifier is
  down, the question goes to the model (fail open). On 103 labelled
  questions (`python -m chatbot.eval_intent`): `llama3.1:8b` 100 correct,
  no real question blocked, two other-bank questions (HSBC, Standard
  Chartered) let through to the model; `llama3.2:3b` 94; `qwen3:4b` 99 but
  blocks three real questions. Results in `data/eval/intent_eval_*.md`.
  Possibly optimistic: the intent definitions quote some evaluation
  phrasings and name the evaluation's other banks; new questions written
  apart from the prompt would measure it fairly.
  Live with `llama3.1:8b` as classifier and chatbot model, the gold set
  under today's checks: behaviour 8/8, right tool 21 and 22 of 24 (20 on
  1–2 Oct; the prompt and checks changed too), answers with an unverified
  figure 4 of 32 (10 on 1 Oct); with
  strip, no invented citation and one invented figure. HSBC and Standard
  Chartered now reach the model, which declined both. Conversations 9/9,
  the new scope set 28 of 29, its conversations 9/9.
  `docs/evidence/chatbot-intent-2026-10-04.md`. Two checks were corrected
  after these runs, both for flagging correct answers (an analyst
  breakdown's shares; "I can't help with that" as a decline), and the
  earlier runs re-scored with them.
- **Settings in one place.** `config/chatbot.yaml` (every chatbot setting,
  with its environment override), `config/sources.yaml` (source weights;
  which sources' text the Gemini backend must never receive: Reddit, CNA,
  and any source not listed), `config/aspect_taxonomy.py` (the one reader of
  `config/aspects.yaml`), one minimum-sentences constant (`MIN_N`), one
  bank-name tuple (`BANK_NAMES`), one label order (`train/labels.py`),
  `BASE_VERSION` and `DEFAULT_FINETUNED` in `config/model_version.py`. The
  aspect classifier's definitions, examples and model are in
  `config/aspects.yaml`; its prompt fingerprint is unchanged (96efe244, a
  test pins it), so the corpus answers are still used.
- **`PLP_DB_PATH` / `PLP_EMBEDDINGS_PATH`** serve a copy (a rescored one,
  say) to the API and the dashboard without touching `data/plp.db`.
  `scripts/rescore.py` refuses both databases without `--real-db`, and
  `--fresh-copy` always copies `data/plp.db`.
- **Rescore: models and margin from `FINETUNED`.** A listed `--version`
  brings its own models and margin and refuses others; base FinBERT's tag is
  refused; models not listed need `--margin`. The undo advice mentions the
  WAL files.
- **The retrained models** (head-order fix): every seed beats base FinBERT
  (test macro-F1 0.646, 0.592, 0.625; mean 0.621 ± 0.027 against 0.571);
  the average matches base on accuracy (0.702 against 0.699). The
  dev-chosen margin (0.12) now lowers every seed's test score. On the full
  corpus the retrained average stays within 0.015 of base FinBERT's
  headlines with the margin and agrees with base on every aspect's sign;
  single seeds still differ. Not adopted: `docs/evidence/retrain-2026-10-04.md`
  (audited).
- **Fixes with tests:** evaluation stops on probabilities that don't sum to
  1 and takes `--cpu`; the label shares used for class weights count base
  FinBERT only; the API logs at startup when the served version has no index
  rows; the backup and rollback tests cover every table and an open WAL.
- **Validation:** the 4 Oct chatbot-and-API validation's findings are all
  fixed (`docs/validation/2026-10-04-chatbot-and-api.md`); two reviewer
  runs and two auditor runs on today's changes, all findings fixed.

**Needs a human (4 Oct):** decide whether to adopt the retrained models and
how to settle the margin on dev (decision brief, 7); anchor the 7- and
30-day windows to the newest sentence or collect up to the re-score, since
a rebuild after 12 Oct would otherwise leave them empty (12); whether the
Claude and OpenAI backends also withhold Reddit and CNA text (13); POSB as
a DBS alias at collection (14); read the fixed replies in
`config/intents.yaml`. Known and not fixed: the number check skips years,
so a wrong year ("2023" for 2026) passes; the classifier lets two
other-bank questions through to the model, which declined them.

### 4 October, afternoon

- **Dashboard menu fixed and pushed** (merge a99f271). The sidebar's page
  names were hidden by a CSS rule written for an older Streamlit, and the
  address didn't follow the page chosen; both fixed in `dashboard/` with
  the edit block lifted for it. The teammate who owns `dashboard/` should
  review the two lines.
- **Chatbot answers rewritten for a retail investor** (DESIGN decision 25,
  branch `fix/chatbot-answers`, not merged). In the dashboard the figures
  were right but every answer had the same labelled sections, scores read
  "0.122 out of 1", +0.124 was called "slightly negative", a trend question
  got "not available" though 66 months had enough sentences to score, and evidence was report
  boilerplate. Now the readings, shares, rankings and the trend sentence are
  computed in code and handed to the model, the prompt is a guide to
  writing for a retail investor, and citations show as numbered sources.
  Six runs of the 32-question gold set on the branch, plus the before run,
  with what each found: `docs/evidence/chatbot-answers-2026-10-04.md`.
  Answers are slower on the local model (about a minute). Validated
  (`docs/validation/2026-10-04-chatbot-answers.md`): API integrity held;
  three holes the change opened in the grounding checks and a trend sentence
  that could contradict its figures were found and fixed with tests. A
  second validation (`docs/validation/2026-10-04-chatbot-answers-recheck.md`)
  found the marker fix let an invented quote beside "[2]" survive strip mode
  and flagged real quotes; markers are now dropped, not flagged. A third
  (`docs/validation/2026-10-04-chatbot-answers-third-check.md`) found the
  pattern patches still opening gaps, so dates without a year now count only
  when a tool returned them, and markers are dropped only after the checks.
  A fourth (`docs/validation/2026-10-04-chatbot-answers-fourth-check.md`)
  found a returned date could swallow a figure ("September 25.7%") and
  quote shapes the pattern never matched (also on `main`); quotes were then
  found by pairing quote marks in order, and dates come only from date
  fields, never followed by a decimal, a thousands group or "%". An evidence
  search for a bank now also returns the bank's score (`topic_score` or
  `bank_overall_score`) and `data_runs_to` (6e8298b): asked what people say
  and how they feel, the model had searched only and called the mood
  "neutral". A fifth (`docs/validation/2026-10-04-chatbot-answers-fifth-check.md`)
  found one missing or stray quote mark shifted the pairing and hid the next
  quote; the earlier pattern and the pairing now run together, single-quoted
  passages of three words or more are checked, and the limits left are
  listed on the evidence page. The sixth and seventh validations, of 5 Oct,
  are under 5 October below.
- **Found on the way:** the full test suite stops a running API
  (`test_stop_is_idempotent` calls the real `stop.sh api`); the dashboard
  keeps the chatbot code it first loaded, so restart it after changing
  `chatbot/`; evaluation results now hold CNA text when evidence comes from
  CNA, so those results files stay out of git. Hiding evidence links from
  the model to save time let a Reddit post that came through a news feed
  reach Gemini in the privacy tests; links went back in before commit, and
  every run used the local model, so nothing left the machine.

**Needs a human (4 Oct, afternoon):** review and merge
`fix/chatbot-answers` (re-run `/validate` on the fixes first); write new test questions
apart from the prompt, since the gold set was used to tune it; decide
whether slower, fuller answers are worth it on the demo Mac.

### 5 October

- **Chatbot grounding checks, sixth and seventh validations** (branch
  `fix/chatbot-answers`, not merged). A sixth
  (`docs/validation/2026-10-05-chatbot-answers-sixth-check.md`) found the
  words after a nested quote unchecked, scare quotes in single marks
  stripped and "Data runs to September 25 for DBS" flagged, among others;
  7446c89 let straight and curly quotes hold each other, let quotes in
  straight marks or opened with a closing mark open and close beside any
  punctuation, counted single quotes from six words, took a returned day for
  a date unless a count or a share followed it, and added
  `scripts/replay_checks.py` to re-run the checks over every recorded
  answer. A seventh
  (`docs/validation/2026-10-05-chatbot-answers-seventh-check.md`) found that
  date rule hid a count before any word not on its list ("In September 25
  customers complained"), and a curly quote holding an inch mark ran on to
  the next quote's opening mark and hid that quote, among others. Now a
  double quote mark the checks can't place flags the answer and takes its
  line in strip mode, „...“ marks are read, single quotes count from three
  words after a quoting word or before a citation, a returned day is a date
  only where it reads as one, and `scripts/replay_checks.py --against
  <commit>` compares with any commit's checks; merged nested quotes stay a
  recorded limit, with the others on the evidence page.
- **Eighth validation**
  (`docs/validation/2026-10-05-chatbot-answers-eighth-check.md`): a count
  before a comma, a bracket or "for" was still hidden, and the seventh's quote
  rules removed correct text in four shapes. Now a comma or bracket after a
  returned day ends a date only with no number later in its clause (or one
  right after the comma) and "for" no longer does, a word in quote marks keeps
  its marks whatever follows, words glued to a real quote's closing mark stay
  unless a citation or a closing mark ends them, single quotes are cued only
  by verbs of saying, a speaker's colon or a citation after them, a stray
  mark after a quote or its citation at a line's end is placed, and
  `scripts/replay_checks.py` reads only the results files git tracks
  (`--include-untracked` adds the five runs that quote CNA text).
- **Ninth validation and a new design for strip mode**
  (`docs/validation/2026-10-05-chatbot-answers-ninth-check.md`, verdict
  rethink): the stray-mark rule added after the eighth hid an invented quote
  on the next line, words glued to a real quote passed, and "In September
  25, vs. 45" hid a count. The owner chose to change the design (DESIGN
  decision 26): strip mode removes the quotes no search returned, then takes
  the quote marks off everything else a search doesn't vouch for (the
  line-removal net and the stray-mark rule went), so what it leaves in quote
  marks is text a search returned word for word, checked by a property test
  on 3,000 made-up answers; dates no longer end a clause at an abbreviation,
  and "By September 25," reads as a date.

### 6 October

- **`main` merged into `fix/chatbot-answers`** (f2544fd): the teammate's
  broker research source (`sgx_research`, labelled "broker research" in
  `config/sources.yaml`) and its tests. It changed no chatbot code and added
  no results file under `data/eval/`; the line references its code moved in
  four diagram pages (03, 04, 06, 11) are updated.
- **Chatbot grounding checks, the fixes after the ninth validation** (not
  merged): applied as DESIGN decision 26 sets out, with the date rules on
  the evidence page. Checking the new strip mode also found that a quoted
  piece found inside a longer word kept its marks ('"... impressive"' when
  the source says "unimpressive"); pieces now count only as whole words, and
  the remaining quotation mark ornaments (❟ ❠ ❮ ❯) are read. Three of the
  ninth's ordinary dates and the seventh's merged nested quotes stay recorded
  limits (evidence page, Known limits). The replay then compared with
  f511f83 (on 5 Oct, with 31c7e98, where one answer's quotes differed) and
  printed a new line, the answers in which strip mode takes quote marks off
  words it keeps: two `phi4-mini` answers written as JSON, where an empty
  pair (`"aspect": ""`) loses its marks, which were also the two answers
  differing from f511f83's checks.
- **Chatbot grounding checks, the fixes after the tenth validation** (not
  merged): strip mode cuts a citation that would vouch for words no search
  returned (words that lost their quote marks, or a word or two in quote
  marks, which lose theirs too), every check reads a carriage return or
  other line separator as a line feed, a left-hand mark is never an
  apostrophe, and a figure in retrieved text vouches only for itself among
  its words (DESIGN decisions 25 and 26, evidence page). Against 03dc631's
  checks no strip result of the 670 recorded answers changes, and seven
  answers now flag a figure the model took from a retrieved sentence and
  wrote in other words, false alarms the evidence page lists.
- **Chatbot grounding checks, the fixes after the eleventh validation, the
  last fix round by the owner's decision** (not merged): a citation, a link
  among them, vouches for its own sentence, off mode flags exactly what strip
  mode would change, and a retrieved figure vouches for itself through two of
  its nearest words, common ones skipped, which clears the seven figure false
  alarms (DESIGN decisions 25 and 26). What is left stays under Known limits
  on the evidence page, with no further fix round.

The twelfth validation (`docs/validation/2026-10-06-chatbot-answers-twelfth-check.md`,
fix first) found four gaps after 174c77d, recorded as limits with strict
expected failures in `tests/test_validate_chatbot_off_mode_and_nearest_words_*.py`: a source note
after a quote keeps its citation (a regression from 174c77d), a retrieved
figure vouches for the same number counting something else, text in backticks
keeps its citation, and a blockquote's citation line is flagged in off mode.
API integrity was proven every round. The auditor's run returned no report,
so this round's docs were not re-audited.

Later on 6 Oct, by the owner's decisions: the live check (gold set 23/24
tool, 8/8 behaviour, 0/32 answers with an unreturned figure, median 47 s;
multi-turn 9/9; evidence page) and the Grounded chatbot claim reworded in
`CLAUDE.md` to what the checks prove, within the Known limits (the to-do page
republished). A final, thirteenth validation
(`docs/validation/2026-10-06-chatbot-answers-thirteenth-check.md`) found four
more gaps, all also on `main`, recorded as limits: a removed quote's citation
kept behind a dash or bold, figures skipped as years, durations or under 10,
"45 per cent" checked as a count, and ".87" unread. The branch was then
merged into `main` and pushed.

Evening, 6 Oct: the chatbot reports each step of a turn as it happens
(`chatbot/progress.py`; `answer_turn(..., on_step=)` and
`Conversation.ask(..., on_step=)`): reading the question, each tool call with
what it asked for and what came back, writing, and checking. On one live
question (DBS dividends) the intent check took about 15 s, the two tools
about 30 s and the writing about 25 s. Showing the steps on the Ask page is a
dashboard change for its owner (team to-do, with the code). Tests:
`tests/test_chatbot_progress.py`.

**Provider comparison, rate limits (6 Oct, branch `chatbot-provider-eval`, not merged):**
`chatbot/provider_eval.py` runs the evaluation through Ollama, Groq and Gemini and
`chatbot/provider_report.py` writes the report from the saved results; neither
sends a request without `chatbot/ratelimit.py` pacing it (budgets in
`config/chatbot.yaml`, rolling 24-hour count in `data/ratelimit_state.json`, a stop
after three final 429s, `--resume`). Nothing has been run end to end: a live check found
Groq working (one question took 2 requests) once optional tool arguments were allowed to be
null, which Groq's strict validation had refused (fix in `chatbot/backends/_openai_compat.py`
and `coerce_tool_arguments`), Gemini rejecting the key in `.env` with a 401 (it is 53
characters and does not start with `AIza`, so it is probably not an AI Studio key), and
Ollama not installed on the Windows PC. Tests: `tests/test_chatbot_ratelimit.py`,
`tests/test_chatbot_provider_eval.py`.

**Needs a human (6 Oct):** whether answers of about 47 seconds are
acceptable (speed options: share the cached prompt between the intent
classifier and the chatbot, skip the classifier for plain questions, stream
the answer).

### 7 October

Overnight, 6 to 7 Oct, at the owner's request: domain-adaptive pretraining
(`train/dapt.py`; `train/finetune.py --base-model`). FinBERT's masked-word
training continued on 43,036 corpus sentences, labelled sentences left out
by id and exact text only (a 7 Oct validation found 151 of them related to
test sentences; see below); then the 4 Oct fine-tuning configuration. On
5-fold cross-validation, seeds 42, 1 and 7, paired on identical folds: dev
macro-F1 0.663 from FinBERT, 0.701 adapted, better in 13 of 15 folds. Scored
once on the test split: 0.628 ± 0.022 over the seeds against 0.621 ± 0.027,
and 0.662 for the three averaged against 0.634
(`docs/evidence/dapt-2026-10-06.md`). Slang was checked first and is rare (27
of 1,280 labelled train/dev rows, an upper bound; `scripts/slang_share.py`),
so no slang dictionary was built. Docker
Desktop was stopped on 6 Oct to free memory for the run.

Broker research, reviewed 7 Oct: the 5 to 6 Oct work on the team's Windows
PC (merged in f2544fd) holds more than the source. The 280 train/dev rows are
human-labelled (annotator "A", who kept the LLM's suggested sentiment on
263 of 280 (94%) and its aspect on 266; the first round's training rows
kept it on 904 of 978, 92%). `was_corrected` compared with the pipeline's aspect, not the LLM's
suggestion; fixed on 7 Oct in `train.source_round merge` and in the
committed label files (that column only): 29 of 280 rows changed the
suggestion. `merge` now refuses labelled rows without an annotator. The 100 blind test rows are filled in and agree with the LLM's own
test labels far less (sentiment 77 of 100, aspect 65; the LLM flagged 4 rows
as not about the bank, the sheet none), so they were not copied; no code
path writes LLM labels into that sheet. Their `annotator` column is blank. A retrain with the 280 rows added was scored on the original 299,
the 100 and both (`docs/evidence/sgx-research-evaluation-2026-10-06.md`).
Only that PC's database holds the source's rows with the ids the labels
use: rebuilt on the Mac from the PDFs, 52 of the 380 labelled sentences came
out with different text (a stray bullet, a sidebar line) and so different
ids. `scripts/source_rows.py` copies one source's rows between databases;
the rebuild is kept apart in `data/run/sgx/` (gitignored) for pretraining
text only.

With the broker research labels: fine-tuned on all 1,258 train/dev rows on
the Mac, the adapted models led those from FinBERT on every test scope (three
averaged: 0.652 against 0.597 on the original 299, 0.751 against 0.698 on the
100 broker research rows, 0.690 against 0.649 on all 399;
`docs/evidence/dapt-2026-10-06.md`). The same training from FinBERT scored
about 0.03 higher on the Windows PC on 6 Oct, so models are compared on one
machine only. One run of three seeds: the gains are about one seed sd, so
they agree with the cross-validation rather than prove it again.

Validation, 7 Oct (`docs/validation/2026-10-07-pretraining-and-chatbot-steps.md`,
fix first): the pretraining filter let test text through (a test sentence
split in two by the rebuild, sentences holding or held in test sentences,
near-copies hidden by skipping common words, and broker test rows when only
one labels file was given). Fixed the same day: `train.dapt.NearCopies`
leaves out any sentence holding or held in a labelled one (letters only,
from 30 letters) or sharing 60% of all its words with one, and by default
every labelling sheet under `data/labeled/`. Both adapted models (6 and
7 Oct) were pretrained before the fix and must be pretrained again before
their figures can support the Fine-tuning lead claim; the 7 Oct run was
paused at the owner's request, to clear upstream items first. Also fixed:
`scripts/source_rows.py` refuses a source the target already holds;
fine-tuned models record their base model and a base without a sentiment
head is refused; the chatbot's step descriptions can no longer fail a turn;
README's checksum for `plp-2026-09-26-v2.db.gz`, corrupted by blanket
test-count replacements in b9aaa0f and d119675, is restored (all five
snapshots now match).

Later on 7 Oct, at the owner's request: the dapt-v2 run is paused until the
upstream items are cleared (no more retraining or evaluation before then);
chatbot speed work is on hold until performance is an issue (measurements in
`data/run/speed/`: writing 13 to 23 s, reading tool results 5 to 15 s,
re-reading instructions 12 to 15 s; a larger window was slower). Drafted for
the team (a6c7a07): the product-feature options, proposed local-context
answers, a glossary of 79 local terms and a blind active-learning sheet of
150 rows. The team to-do is consolidated and renamed
`docs/briefs/team-todo.html` (same published link), ordered by
what blocks what, with decided items in one list.

**Needs a human (7 Oct):** record who labelled the 100 broker research test
rows (the `annotator` column), an agreement figure for that round (one
annotator so far); both are on the team to-do. The 25 broker reports'
full text stays in git: the repository is private to the team (decided
7 Oct; remove them, with their history, before any public release).
The team's scoring-model decision now has three
candidates (the 1 Oct models, the 4 Oct retrain, the adapted models), for the
re-score week of 12 to 18 Oct; if the adapted models are adopted, the
Fine-tuning lead claim in `CLAUDE.md` should give their figures.


### 10 October

At the owner's request: a chatbot time-out fixed, its speed measured, the
team's six decisions of 10 Oct logged, Opus labels for every sentiment
sheet, and a check of a database copy from the team folder.

**The chatbot's time-out** (`docs/evidence/chatbot-timeout-and-speed-2026-10-10.md`).
The Ask page answered "Read timed out. (read timeout=120)". Ollama had
unloaded the model; the intent classifier gave up after 60 seconds of
loading and the chatbot's request after 120. Checked directly: a request
that gives up makes Ollama abandon the load, so the second request started
from nothing, on a Mac with 5,984 MB of 7,168 MB of swap in use. Fixed:
the model is loaded first by a request of its own with a 300-second limit
(`chatbot/ollama_load.py`), every request keeps it loaded for 30 minutes
(`OLLAMA_KEEP_ALIVE`), the answer is read as it is written so 120 seconds
is the longest silence and not the longest answer, and a time-out now says
the model is slow and memory is probably short. 29 tests added
(`tests/test_ollama_load.py`): 2491 in `tests/`, 2538 from the root; all
pass (2443 passed, 2 skipped, 46 expected failures).

**Speed.** Five questions took 25 to 105 seconds. The model's writing speed
fell from 11.4 to 5.2 tokens a second within three minutes while swap in
use rose from 7,170 to 8,052 MB, with no thermal warning: memory pressure
from other programs is the main cause, not the chatbot's code. The six
tool descriptions are 967 tokens that the model reads again for every
question (llama3.1's template writes them inside the newest question). An
option that writes them at the start of the instructions, where Ollama
caches them, is built and left off (`OLLAMA_TOOLS_IN_SYSTEM`): on gold set
v2 it scored right tool 22 of 24 against 23, behaviour 8 of 8 both ways,
no citation flagged either way, median 36.8 against 41.3 seconds and mean
42.9 against 42.3, in a run that shared the Mac with the test suite. One
run each, so neither difference is established.

**The team's decisions of 10 Oct** are in `docs/PLAN.md` (section 2) and on
the team to-do, republished to the same link: retail products carry
sentiment directed at the bank; wealth means the priority and private
tiers; the test rows are not relabelled; both aspect methods run and are
reported; Opus 5.5 labels every sentiment sheet; evaluation adds precision
and recall for each class, every model is re-run and the team picks one.
The meeting note said to declare the Opus labels as human labels. That was
not done: with the owner's agreement they are recorded and reported as LLM
labels, since the report declares its GenAI use.

**Opus labels under the new rules**
(`docs/evidence/llm-rater-new-rules-2026-10-10.md`,
`data/labeled/llm_rater/rules-2026-10-10/`). The two rules are written into
`docs/annotation-guideline.md`. 2,075 sentences (first round 1,277, top-up
268, active-learning 150, broker research 380), aspect blind and then
sentiment given Opus's own aspect, by 36 Opus subagents that read only
their instructions and input (191 tool calls audited). 757 positive, 879
neutral, 439 negative. Against people on the 1,277 rows: aspect κ 0.802,
sentiment κ 0.793 (1 Oct run: 0.801 and 0.790). The retail rule moved 34 of
280 neutral retail rows to positive or negative, and 28 rows went the other
way; the two Opus runs give the same sentiment on 87.9% of rows, so the
rule's effect is about the size of the difference between two runs. The
labels replace nothing: no other labelling file changed.

**The database.** `data/plp.db copy`, downloaded from the team folder at
23:07 and again at 23:57, is byte-identical to `data/plp.db` and to the
30 Sep snapshot unpacked (SHA-256 `7ea0da08…5734fb`; 28,002 documents,
44,345 sentences, no broker research rows). The first copy was removed as a
duplicate; the second is left where it is, untracked. No newer database
has reached this Mac.

**Needs a human (10 Oct):**
- Which labels train and test the models: the retail rule changed and the
  test rows keep their old labels, so train and test would follow different
  rules; and whether the 1,277 rows keep people's labels or take Opus's.
- Confirm the wording of the two rules (the retail rule is the "customer
  value" option; the wealth rule was extended to brokerage, regular savings
  plans, insurance and robo-advisers). `config/aspects.yaml` still has the
  old wealth definition: changing it redoes the corpus aspect run (about a
  day).
- `CLAUDE.md` and DESIGN decision 22 still say Opus labels never replace
  the human labels; the owner should change the rule to what the team now
  means.
- Which aspect method the product serves, now that both are reported.
- The newer database a teammate reports: the database is in write-ahead
  mode, so their new rows may be in `plp.db-wal` and missing from the
  uploaded `plp.db`. Stop the API and dashboard there, run
  `PRAGMA wal_checkpoint(TRUNCATE);`, then upload it under a dated name
  with its SHA-256.
- Dashboard owner: restart the dashboard to pick up the chatbot fix, and
  reword the error line that tells the reader to check `ollama serve`.
- Before a demo, close memory-heavy programs on the Mac.

### 11 October

At the owner's request, two naming and wording changes, neither of which
changes behaviour or any label.

- **Names** (`c640962`): `data/labeled/claude/` is now
  `data/labeled/llm_rater/`; files and CSV columns named `opus_*` are
  `rater_*`; `train/opus_labels.py` and its test are `rater_labels`; the
  broker research round's `claude_prelabels` and `claude_test_labels` are
  `llm_prelabels` and `llm_test_labels`; the two evidence notes are
  `docs/evidence/llm-rater-2026-10-01.md` and
  `llm-rater-new-rules-2026-10-10.md`. 163 files moved and 255 references
  updated in code, tests, docs, diagram tables and the team to-do
  (republished). The `rater` column still names the model, and the three
  merges reproduce their files byte for byte.
- **Comments and docstrings** (`a12606e`): the dates on which things were
  decided, found or fixed are gone from 91 Python files. Dates that are data
  stay (examples, formats, coverage, usage examples, file and folder names).
  Checked per file: the same line count and the same code once docstrings
  are removed. The code had no em dash in a comment or docstring already.

2538 tests pass after both. Not pushed yet.

**Needs a human (11 Oct):** anyone with local changes under
`data/labeled/claude/` or `data/labeled/sgx_research/claude_*` should commit
or stash them before pulling, since those paths have moved.

**The database from the Windows PC (11 Oct, afternoon).** A third file,
`data/plp.db copy 2` (119,750,656 bytes, SHA-256 `ba0590e0…29bb4031`), is
the PC's database: the 24 Sep corpus plus the broker research source. It is
not a newer version of `data/plp.db`. Against ours it has 25 more documents
(all `sgx_research`, 641 sentences, 4,533 scored pairs) and 265 fewer (207
CNA, 55 Google News, 3 Reddit); only 11,082 of its 43,331 sentences are
scored. All 380 labelled and 100 test broker research sentences are in it
under the ids the labels use. `scripts/source_rows.py` copied that source
into a copy of our database, `data/run/merge-2026-10-11/plp_merged.db`:
28,027 documents, 44,986 sentences, 286,277 scored pairs, integrity ok,
every existing row identical to `data/plp.db`, the new rows identical to
the PC's. `data/plp.db` itself is unchanged. Rebuilding the index on a
throwaway copy moved the all-time headlines from +0.122, +0.136 and +0.074
(DBS, OCBC, UOB) to +0.124, +0.139 and +0.077, and emptied the 7-day window
because the windows still count back from today.

**Needs a human:** approve swapping the merged copy in as `data/plp.db`,
together with the anchored-windows change and the index rebuild, in the
re-score week.

**One merged database (11 Oct, later).** The owner asked for a complete
database merged from both copies and named `plp.db`. The PC's file held
nothing our database lacked beyond the broker research source (no other
document, sentence, aspect pair, score or analyst row, and no shared row
differed), so the merged copy described above is the complete union. It is
now `data/plp.db`: 28,027 documents, 44,986 sentences, 286,277 scored pairs.

- The old file and both downloads are kept in `data/run/merge-2026-10-11/`
  (`plp_before_merge_2026-10-11.db`, `plp_windows_pc_2026-10-11.db`,
  `plp_team_folder_duplicate_of_30sep.db`).
- With new rows and the old index, three API integrity tests failed (the
  monthly series no longer added up to the stored all-time figures), so the
  index was rebuilt. A plain rebuild counts the 7- and 30-day windows back
  from today and empties the 7-day one, and the anchored-windows branch no
  longer merges cleanly (`chatbot/prompts.py`, `chatbot/tools.py`, nine
  diagram pages). The rebuild therefore held the windows at the moment the
  30 Sep index was computed (`rebuild_index_as_of.py` in the merge folder):
  all 407 earlier per-source cells are identical, 78 cells are new for the
  broker research source, and 78 of the 107 blended cells changed. Index
  rows: 514 to 592. All 2538 tests pass.
- Embedding cache: 641 sentences added (44,986 in all).
- Snapshot `data/snapshots/plp-2026-10-11.db.gz`: 42.4 MB, SHA-256
  `9ca50c4d95ec7d28cda35e0607dc6c138fa3ab2bb863f8099fcd6824b9472b37`;
  unpacked `27f0205f…f778eb62`. README, STATUS, RUNBOOK and the snapshot
  diagram updated.

**Needs a human:** upload the snapshot to the team folder. Still to do: the
local aspect model on the 641 new sentences; merging the anchored-windows
change; filtering broker-report boilerplate out of the chatbot's evidence.

**The three open points settled, and the repairs applied (11 Oct, later
still).** The owner decided: both indices stay (blended and per source);
the local-context questions are answered by web research; the three data
repairs go ahead.

- **Local-context questions.** A research pass answered all 23 questions in
  `docs/local-context-questions.md` with sources (banks' own pages, MAS, SGX,
  Singapore finance sites, Singlish dictionaries): 238 lines added, nothing
  removed. "xmm" is a young woman (the sentence is a joke, neutral); "Lobang
  Sis" is a third-party deals site; FHR is DBS's Fixed Deposit Home Rate.
  Seven answers are judgment calls marked as recommendations for the team.
  Two bank-recognition faults it reported were checked here on made-up
  sentences: "Development Bank of Singapore" resolves to OCBC, and PayLah,
  digibank or TMRW named alone resolve to no bank.
- **Repairs**, built in a working copy and then swapped in.
  `scripts/fix_earnings_dates.py --apply`: 6 documents, 114 sentences.
  `ingest.arctic_shift` for the three months: 120, 200 and 505 new documents
  (825), giving 858 sentences and 5,231 scored pairs through the usual
  pipeline. September 2021 now has 130 comments (10 before), May 2024 364
  (167) and March 2025 591 (89). No earlier row changed except the six
  re-dated documents and their sentences. `ingest/cna_articles.json` is no
  longer tracked (`708d798`); it stays in the history.
- **The database now:** 28,852 documents, 45,844 sentences, 291,508 scored
  pairs, index 580 rows (windows held as before). Blended all-time
  headlines: DBS +0.122, OCBC +0.136, UOB +0.074. UOB's 30-day headline went
  from +0.289 on 230 sentences to +0.215 on 116. All 2538 tests pass.
  Snapshot `data/snapshots/plp-2026-10-11-v2.db.gz`: 43.2 MB, SHA-256
  `f703d2da4c3ea7b45cfc20ff1dc1ec29425a4778e6473b4262d93dd66a44b310`;
  unpacked `97370949…885914e3`. The database before the repairs is in
  `data/run/repairs-2026-10-11/`.

**Needs a human:** upload the v2 snapshot; adopt or not the seven
recommended answers; approve the two bank-recognition fixes. The 1,499 new
sentences have no LLM aspect yet.

**The seven recommended answers checked (11 Oct, evening).** At the owner's
request the seven judgment calls among the researched local-context answers
were checked against the labelled rows outside the test splits (1,676, of
which 978 labelled by people), the corpus (45,844 sentences) and their
sources (`docs/evidence/local-context-validation-2026-10-11.md`). Six hold;
the sarcasm flag is not worth adding (7 marked sentences, none labelled).
Two answers were corrected: a quote the cited article does not contain, and
broker rating thresholds (buy above about 15%, not 10% to 15%). Found along
the way: Opus flags 134 rows as not about the bank and they are still
trained on; one chatbot answer misdescribed the analysts behind a consensus.

**The model re-run is running (started 11 Oct, 15:51).** At the owner's
word, with two defaults they were told of: rows Opus flagged as not about
the bank are left out of training, and models are ranked by test macro-F1
over three seeds.

- Label file: `data/labeled/llm_rater/rules-2026-10-10/training_set.csv`
  (`build_training_set.py`): 1,563 training rows on Opus's labels (616
  positive, 586 neutral, 361 negative; 112 flagged rows and 1 near-copy of a
  test sentence left out) and the 299 first-round test rows on the labels
  they have.
- Script: `data/run/rerun-2026-10-11/run.sh`, under `caffeinate -i`, pid in
  `pid` beside it. Steps: pretrain the adapted encoder with the fixed filter
  (`models/dapt-2026-10-11`); 5-fold cross-validation, seeds 42, 1 and 7,
  from FinBERT and from the adapted encoder; three final models from each
  (`models/experiments-2026-10-11/`); `score.py` for the test table with
  precision and recall per class. Each step skips what is done, so the
  script can simply be started again. Progress: `progress.log`; results:
  `results.md` and `test_results.json`. About eight hours.
- Before it started, `score.py` on the models that exist reproduced the
  known figures on the 299 test rows: base FinBERT macro-F1 0.571; the 1 Oct
  models 0.604 (sd 0.035); the 4 Oct retrain 0.621 (sd 0.027).

**Six items settled one by one (11 Oct, about 19:00).** The owner will fill
in the annotator of the 100 broker research test rows themselves. Adopted:
six of the seven recommended local-context answers, now in the guideline;
the sarcasm flag is dropped. Approved and made: the two bank-recognition
fixes (`8764d1a`; 18 tests added, 2509 in `tests/` and 2556 from the root;
the tests that use the code pass, and the full suite waits for the training
run to free the GPU). `CLAUDE.md`'s rule on Opus labels stays as written.
The re-score is rehearsed on a copy and shown to the owner first. The wealth
rule's extension to four more products was confirmed after a check of how
the banks classify them. Bank recognition scored against Opus's reference on
the 201-sentence sheet (accepted as an LLM reference) still matches it in
every case shown by `train.rater_labels extra score ner`.

**The broker research test rows have their annotator (11 Oct, evening).**
On the owner's word that the same person labelled them, `annotator` is `A`
on all 100 rows of `data/labeled/sgx_research/test_blind.csv` (no other
cell changed). `train.source_round merge` then accepted the round: 280
train/dev and 100 test rows, none dropped. They are not yet in the re-run's
label file, which the running job reads; they are added, as a second test
scope, once it finishes.

### 12 October

**The model re-run finished at 00:07** (`docs/evidence/model-rerun-2026-10-11.md`;
scripts and results in `data/eval/model-rerun-2026-10-11/`). About eight
hours, no step failed.

- Cross-validation, 15 paired folds, dev macro-F1 against Opus's labels:
  FinBERT 0.686, adapted encoder 0.700; +0.014 (sd 0.020), better in 11 of
  15, paired t = 2.75, p = 0.016.
- First round's 299 test rows, macro-F1 over three seeds: base FinBERT
  0.571; the 1 Oct models 0.604; the 4 Oct retrain 0.621; FinBERT on Opus's
  labels 0.631 (sd 0.020); adapted encoder on Opus's labels 0.649 (sd 0.018),
  0.670 for the three averaged with accuracy 0.716. Negative recall 0.21 for
  base and 0.61 for the adapted set.
- Broker research's 100 test rows: base 0.687; adapted set 0.740 (sd 0.021),
  0.770 averaged. Both scopes, 399 rows: 0.648 and 0.685.
- By the rule fixed beforehand (test macro-F1 over three seeds,
  cross-validation as the tie-breaker) the model for the dashboard and
  chatbot is the adapted encoder fine-tuned on Opus's labels,
  `models/experiments-2026-10-11/dapt/`. Its lead over FinBERT fine-tuned
  the same way is about one seed standard deviation.
- The full suite, held back while the GPU was busy, passes: 2508 passed, 2
  skipped, 46 expected failures (2556 collected).

**Needs a human:** the Fine-tuning lead claim in `CLAUDE.md` still gives the
1 Oct models' figures; the owner should say whether it changes to this
set's. Next: the re-score rehearsal on a copy, shown to the owner before
`data/plp.db` is touched.

**Model comparison report (12 Oct).** At the owner's request, a page that
walks through the comparison: what was compared, how it was tested, the
headline, the kind of error each model makes, precision and recall by
class, the broker research rows, adapted against plain FinBERT, the effect
on the index, limits and the decision. Standalone copy:
`docs/briefs/model-comparison-2026-10-12.html`; built by
`data/eval/model-rerun-2026-10-11/build_report.py` from `report_data.json`
(written by `report_data.py`), so every figure on it is computed.
Published privately at https://claude.ai/artifact/Q2GtRSPTiiX6WXnh8QDepR.
Two things it adds to the evidence note:

- Accuracy barely moves (209 against 214 of 299 right; row by row the
  adapted model fixes 41 and breaks 36, exact test p = 0.65). The gain is
  in which errors: base FinBERT calls 221 of 299 rows neutral and finds 8
  of 39 negatives; the averaged adapted model finds 23.
- Added up as an index, the adapted model is closer to the labels on the
  first-round rows (+0.174 against a true +0.184; base +0.161) and further
  on the broker research rows (+0.090 against +0.190; base +0.210). A
  neutral threshold has not been chosen for this model yet; that comes
  before the re-score.

**Report updated (12 Oct, later).** At the owner's request the model
comparison page gained a section on why the other tuning techniques are not
switched on (the 1 Oct one-change-at-a-time cross-validation, the 2 Oct
repeat on three seeds, and adapting on 6 and 11 Oct, against the noise
between two identical runs), and the page now says "LLM labels" throughout
in place of the model's name. The repository's evidence notes and label
files still name the model. Not yet run: a model with every technique
switched on, on the adapted encoder with the LLM's labels.

**Filling the two gaps the report names (12 Oct, from 08:30).**

- **Neutral threshold: not needed.** `neutral_margin.py` in
  `data/eval/model-rerun-2026-10-11/` chose it as on 4 Oct: each of the 601
  dev rows the three seeds held out (504 by one seed, 90 by two, 7 by all
  three) scored by the average of only the seeds that held it out. Macro-F1
  against the LLM's labels is 0.710 with no margin and 0.680 to 0.704 with
  any margin from 0.05 to 0.60, so the chosen margin is 0 and the averaged
  model is used as it is (`margin_adapted.json`). Reported, not used for
  choosing: on the 299 test rows the margins score 0.664 to 0.676.
- **The weighting techniques on the adapted encoder with the LLM's labels:
  running** (`data/run/rerun-gaps-2026-10-12/run.sh`, pid in `pid`). Balanced
  class weights with source weights on 15 folds, then its three final
  models, then each weighting alone on 15 folds; about eight hours. The rule
  is fixed in the script: a weighted variant replaces the chosen model only
  if its paired cross-validation gain is positive with p < 0.05 and its test
  macro-F1 over three seeds is higher. The source weights give broker
  research rows 0.08 and Reddit rows 1.52.

**Everything switched on, on the chosen setup (12 Oct, 12:35).** Balanced
class weights with source weights, adapted encoder, the LLM's labels.

- Cross-validation, the same 15 folds: 0.697 against the chosen model's
  0.700, a difference of -0.003 (sd 0.015), better in 6 of 15, p = 0.52.
- Test rows, mean of three seeds: 0.651 against 0.649 on the first round's
  299; 0.739 against 0.740 on broker research; 0.689 against 0.685 on all
  399. Averaged, the chosen model is ahead on each (0.670, 0.770, 0.709
  against 0.664, 0.746, 0.699). Row by row the two disagree on 29 of 399.
- By the rule fixed in `run.sh` before the run the chosen model stands.
- Balance: on all 399 test rows the weighted model's net balance is closer
  to the labels (+0.188 against +0.185; chosen +0.153). On the 601 held-out
  training rows it is closer overall (+0.140 against +0.131; chosen +0.108)
  but far off on broker research (+0.180 against +0.054; chosen +0.009),
  whose rows it weights at 0.08 (`dev_balance.json`). Not a reason to change.
- Its own dev-chosen neutral margin is 0.10, with no gain on the test rows
  (`margin_weighted.json`).

Still running: each weighting alone, 15 folds each.

**The weighting run finished at 19:16 (12 Oct): none of the three helps.**
45 cross-validation runs, no failures. Against the chosen model on the same
15 folds: both weightings together -0.003 (p = 0.52), balanced class
weights -0.002 (p = 0.41), source weights -0.004 (p = 0.39). The chosen
model stands, by the rule written into `run_weighting.sh` before the run.
The full suite passes afterwards (2508 passed, 2 skipped, 46 expected
failures). The evidence note has a section on both gaps and the model
comparison page carries the results. Next: the re-score rehearsal on a
copy, shown to the owner before `data/plp.db` is touched.

**The re-score rehearsal ran on a copy (12 Oct, 19:58 to 21:45).**
`data/plp.db` is unchanged (same SHA-256 before and after). On
`data/run/rescore-2026-10-12/plp_rescored.db`: the local model gave an LLM
aspect to the 1,499 sentences that had none, the chosen model scored all
45,844 sentences, and `scripts/rescore.py` wrote one aspect a sentence and
both models' scores side by side. The copy's index was rebuilt with the
windows held at 30 Sep.

- The aspect method alone leaves every headline unchanged. The model moves
  them: all time DBS 0.122 to 0.155, OCBC 0.136 to 0.143, UOB 0.074 to
  0.117, and DBS overtakes OCBC. Neutral falls from about two-thirds of
  sentences to about half; 13,154 of 45,844 labels change.
- By source: Reddit rises for every bank (neutral 88% to 57%), CNA turns
  negative for every bank, earnings reports barely move, and UOB's broker
  research falls from 0.236 to -0.026 on 239 sentences.
- Per aspect the figures change most, because a sentence had 6.4 aspects on
  average and now has one. Retail banking is 43% of sentences.
- Not covered: bank tags (nothing re-tags stored sentences), and the LLM's
  aspects still use the wealth definition from before the 10 Oct rule.
- Evidence: `docs/evidence/rescore-rehearsal-2026-10-12.md`; scripts and
  the full output in `data/eval/rescore-rehearsal-2026-10-12/`.

**Needs the owner:** the go-ahead to apply the re-score to `data/plp.db`.
Before that, the dashboard must filter on the model version. Also new and
not yet committed: a project writing skill, `.claude/skills/report-writer/`,
written after the owner said the prose is either too long or leaves out the
reader's context, and that the report must reach Bloom level 4 (analyse).

**The re-score was applied to `data/plp.db` (12 Oct, 22:16), on the owner's
go-ahead.** What changed, in the order it was done:

- **Served model and aspects.** `MODEL_VERSION` is
  `finbert-adapted-finetuned-2026-10-11-3seed-m0` and `assignment_method` is
  `llm`. The database matched the rehearsed copy row for row. The API and
  the chatbot serve the new rows; base FinBERT's stay beside them.
- **Tests no longer depend on which model is served.** `tests/conftest.py`
  pins base FinBERT for every test, because the tests build base-FinBERT
  databases; the tests that compare the API with `data/plp.db` ask for the
  real one (`served_version`).
- **PDF links are relative paths** (`decision/relative-pdf-paths`, merged).
  The rewrite was extended to broker research, whose links carried a
  Windows home folder, and no longer changes line endings: 203 documents and
  12,895 sentences in the database, 10,443 links in 46 committed files.
- **Recent windows end at the newest sentence, 25 Sep.** The
  `decision/anchor-windows` branch no longer merged (its chatbot half was
  written before the chatbot rewrite, which already reports
  `data_runs_to`), so the index anchor and an API field, `data_as_of`, were
  ported and the chatbot left alone. The 7-day window now holds 90, 42 and
  60 sentences for DBS, OCBC and UOB, where it held 40, 14 and 7.
- **A reviewer checked the switch.** No reader in the API or the chatbot
  mixes the two models. Fixed from its findings: `aggregate.preview` read
  the served model's scores as base FinBERT's; `DEFAULT_FINETUNED` named the
  1 Oct model; two docstrings and the API guide described the old state.
  Recorded, not fixed: on an old database `/sentiment/index` and
  `/sentiment/series` return empty lists with no reason, and
  `sentiment.score` would fine-tune-score every old pair; `--sources` limits
  only the base pass; an LLM answer that fails twice is cached as `other`.
- **Snapshot** `plp-2026-10-12.db.gz` (26.3 MB; checksum in the README).
  Three copies from before each step are in `data/snapshots/`
  (`plp-before-*.db`, about 200 MB each) and can be deleted once the team
  has the new snapshot.
- Tests: 2524 in `tests/`, 2571 from the root; all pass.

**Needs a person:** upload the 12 Oct snapshot and the three chosen models
to the team's stores; the dashboard owner adds the model-version filter
(the dashboard mixes both models' rows until then); decide whether to
re-classify the corpus with the new wealth definition. `CLAUDE.md` still
quotes the 1 Oct figures in its "Fine-tuning lead" claim.

**Clean-copy install test, third run (12 Oct, 23:23).** A fresh clone of
`main`, the README's steps and the 12 Oct snapshot: install, tests, API and
dashboard all came up, and `/sentiment?bank=DBS` returned the stored 0.1552.
Two findings, both fixed: the documented test counts were this Mac's (six
too high: six cases of one test read results files kept out of git), now
2519 in `tests/` and 2566 from the root; and a training test failed
intermittently because the tests trained on the GPU while the local model
was using it, so those tests now train on the CPU
([evidence](evidence/install-test-2026-10-12.md)).

**Trial of the new wealth wording (finished 13 Oct, 00:23).** The aspect
model's prompt was given the 10 Oct wealth rule and run on the 2,075
labelled sentences, in its own process and cache. Against the LLM rater's
new-rule aspects it agrees 79.4% of the time, where the wording the corpus
was classified under agrees 75.5% (148 sentences newly right, 67 newly
wrong, p < 0.001). Wealth precision rises from 0.36 to 0.70 and wealth
recall falls from 0.76 to 0.46; retail recall rises from 0.79 to 0.87.
Against people's first-round aspects, made under the older reading, nothing
changes (72.9% to 73.9%, p = 0.32)
([evidence](evidence/wealth-definition-trial-2026-10-12.md)).

**Running unattended from 13 Oct, 00:24:** the chatbot evaluations on the
re-scored database (`data/run/eval-2026-10-13/run.sh`: gold set, multi-turn,
retrieval, checklist judge), then the corpus under the new wording
(`data/run/wealth-corpus-2026-10-13/run.sh`, about a day, cache only,
resumable; stop it with `kill $(cat data/run/wealth-corpus-2026-10-13/run.pid)`).
**Needs the owner:** the go-ahead for a second re-score once that run ends.

**Chatbot evaluations on the re-scored database (13 Oct, 00:24 to 01:09).**
The gold set, the conversations, the retrieval measure and the checklist
judge, with `llama3.1:8b`.

- The automated checks are within one answer of the 6 Oct live check: tool
  selection 23/24, behaviour 8/8, no fabricated citation in 32 answers, one
  figure no tool returned (a sum the model made up; marked in the answer),
  conversations 9/9 turns. Median 59 seconds a question, against 47.
- The evidence search is far more precise with one aspect a sentence:
  precision at 5 is 0.779 with the stored-aspect filter, where it was 0.329
  with the centroid aspects. Most of the gain is the filter itself.
- One wrong answer passes the checks: asked for "the last 7 days", the model
  gave the all-time figure and the wrong year (the same question that missed
  tool selection on 6 Oct).
- `data/eval/ratings_sheet.csv` is re-exported for the human evaluation,
  ordered with the answers the judge doubts first; the earlier blank sheet
  is `ratings_sheet_2026-10-02.csv`. The results hold no CNA text and are
  committed, which adds one case to the per-file test: 2520 tests in a
  fresh clone, 2567 from the root.
- Evidence: `docs/evidence/chatbot-eval-rescored-2026-10-13.md`.

**Still running:** the corpus under the new wealth wording, started 01:09 on
13 Oct. When it ends: rehearse the second re-score on a copy, show the
owner, and after the go-ahead apply it, snapshot, and run the gold set and
the retrieval measure once more.

**Full report draft (13 Oct, morning).** `docs/report/report.html`, also
published as a private page (link in the owner's notes): all eight parts the
module asks for, drafted from the evidence files, with an amber box wherever
a figure will change or needs checking and a violet box wherever only the
team can write or decide. It supersedes `report-draft.md` as the working
draft. The auditor checked about 290 claims; its corrections are in:
bank recognition figures now follow the 4 Oct rule (DBS Vickers counts as
DBS; 200 against 154 of 201; 258 corpus sentences differ, counted on
13 Oct), the aspect taxonomy is described as AI-drafted cluster labels
merged with the proposal's aspects, and several causes are no longer stated
more firmly than their sources.

Two things the audit raised that are not report wording:
- The project's log (course-context, section 8) says that training a model
  on the LLM's labels needed a check of the provider's terms of use first.
  The chosen model is trained on those labels and no check is recorded.
  **Needs a person.**
- `docs/model-card.md`, `docs/spec/functional-spec.md` (the fine-tuned
  classifier row) and the "Fine-tuning lead" claim in `CLAUDE.md` still
  describe the 1 Oct model. They should change together when the chosen
  model's weights are uploaded.

**The report draft's figures validated against primary data (13 Oct).** 100
figures recomputed from the database, the label files, the models scored
again on the 399 test sentences and the chatbot transcripts; all 100 match
the report as it now stands
([evidence](evidence/report-figures-validation-2026-10-14.md), script in
`data/eval/report-validation/`). Three corrections came out of
it: bank recognition is now quoted from today's code (201 and 161 of 201,
with the caution that the last rules were written from this sheet's
errors); the LLM rater's aspect macro-F1 names its run; and the report says
the first-round test labels were not made blind to the suggestion. The
evidence note lists the figures that could not be recomputed and rest on
their evidence notes alone.

**Second re-score applied (14 Oct, 08:07): the aspects follow the wealth
rule of 10 Oct.** The corpus run under the new wording finished at 08:04
(45,844 sentences, a little over a day). The owner had agreed on 13 Oct
that it could be applied without a further review if the script's checks
passed, base FinBERT's headlines were identical and each bank's headline
moved by no more than 0.02; a rehearsal on a copy met all three, and the
database then matched the copy row for row.

- 6,914 sentences changed aspect; wealth went from 4,359 to 1,423.
- Headlines under the served model fell: DBS 0.155 to 0.143, OCBC 0.143 to
  0.129, UOB 0.117 to 0.107. The served model reads the aspect's name with
  the sentence, so an aspect change is not neutral for the headline; an
  earlier statement in this log and to the owner that it would be was wrong
  (true of base FinBERT only) and was corrected before the owner chose the
  condition.
- `config/aspects.yaml` carries the new wording; two tests that pin the
  prompt were updated. Tests pass (2520 in a fresh clone, 2567 from the
  root).
- Snapshot `plp-2026-10-14.db.gz` (checksum in the README). The files to
  share are in `data/run/share/` (1.4 GB, hard links), with
  `README-teams.md`, rewritten for teammates building a new feature.
- Evidence: `docs/evidence/rescore-wealth-wording-2026-10-14.md`.

**Running:** the chatbot evaluations on the 14 Oct database
(`data/run/eval-2026-10-14/run.sh`). **Then:** update the report draft's
tables from the new database and re-run its figure validation.
**Needs a person:** upload `data/run/share/`; teammates pull and restore.

**Chatbot evaluations and the report draft on the 14 Oct database
(14 Oct, 08:11 to 09:30).**

- Gold set 23/24 tool choices, 8/8 behaviour, no invented citation or
  figure in 32 answers, conversations 9/9, median 40 seconds on a quiet Mac.
  The one miss is the same question answered wrongly in the same way: an
  all-time figure reported as "the last 7 days"
  ([evidence](evidence/chatbot-eval-rescored-2026-10-14.md)).
- Evidence-search precision at 5 is 0.664, down from 0.779 on the first
  re-score, while the share of relevant sentences in the filtered pool rose
  from 0.722 to 0.738: ranking by the aspect's name no longer beats a random
  draw from the pool. Part is the reference (people's labels follow the
  older reading of wealth), part is 28 queries' noise.
- `data/eval/ratings_sheet.csv` exported again from this run's answers.
- The report draft's Tables 5 to 8 and sections 4.2, 4.4 and 4.5 are
  rewritten from the 14 Oct database, including a new paragraph on the
  served model's dependence on the aspect, and the two warnings about
  figures that would change are removed (11 remain). Its figure validation
  was run again: 105 of 105 match
  ([evidence](evidence/report-figures-validation-2026-10-14.md), script in
  `data/eval/report-validation/`).
- One more results file is committed, so a fresh clone collects 2521 tests
  in `tests/` and 2568 from the root.

**Model card and functional spec brought up to date (14 Oct).**
`docs/model-card.md` now describes the three models the product serves (the
adapted encoder fine-tuned on LLM labels): training in two stages, every
test table with precision and recall, the confusion matrix, the limits
(LLM labels, the two retail rules, negative precision 0.48, the score's
dependence on the aspect) and what to check before publishing the weights.
`docs/spec/functional-spec.md`: the classifier, the aspect and bank
recognition rows, the course-requirement paragraph, the first four limits,
the source table (now with broker research) and the "Frozen centroid" entry
describe the database of 14 Oct. Still describing the 1 Oct model: the
"Fine-tuning lead" claim in `CLAUDE.md`, which is the owner's to change.
The model card is also beside the models in `data/run/share/`.

**Three improvements before submission (14 Oct, afternoon).**

1. **Chatbot: an answer that reported the wrong period.** When the 7- and
   30-day windows are too thin, `chat_get_trend` now opens its result with a
   plain statement that there is no figure for those periods and names the
   months its monthly comparison covers, and keeps the all-time figure under
   `all_time_not_recent`. The gold-set question that reported the all-time
   figure as "the last 7 days" in every run is now answered correctly (3 of 3
   tries); the full gold set is unchanged on every automated check. A first
   version that only moved the all-time figure made the model report the
   latest month as the week instead. Two related faults remain and are in
   the report: "this week" trend questions get a two-month comparison, and
   "past month" questions get the all-time figure because the sentiment
   tool offers no window (the gap recorded in September; **a decision for
   the owner**) ([evidence](evidence/chatbot-trend-fix-2026-10-14.md)).
2. **Confidence intervals for the index.** All-time headlines are within
   about 0.01 by sampling; UOB is lowest beyond sampling error; DBS's lead
   over OCBC is not established; 7-day figures support no comparison. The
   model shows no significant bias against people's labels on the 399 test
   sentences, but that check is only good to about 0.06. Changing the
   index's constants moves no all-time headline by more than 0.011
   ([evidence](evidence/index-uncertainty-2026-10-14.md)).
3. **The examiner graded the report draft:** high credit as drafted, held
   down by the sections only the team can write. Its corrections are in the
   report: model selection did use the test rows (stated, with the two
   defences), OCBC's score fell rather than rose, the cross-validation
   p-value treats shared folds as independent, the Gemini and Groq backends
   and the LLM judge are declared, Table 8 separates what the model writes
   from what the reader sees and says the gold set was used for tuning, and
   section 3.1 has an architecture figure drawn for the current system.
   The report is now about 7,400 words outside the warning boxes; the
   examiner expects it to run over 20 pages once the team's sections are
   in, and suggests cuts in sections 4.2, 4.4 and 2.2.

The report's figure validation was run a third time: 115 of 115 match.
Two more results files are committed, so a fresh clone collects 2523 tests
in `tests/` and 2570 from the root. The conversation results of the final
run quote a CNA article and are kept out of git, as with earlier runs.

**Models on Hugging Face; the SharePoint folder without them (15 Oct).** The
three models in use are in the team's private repo
`plp-bank-sentiment/plp-finbert-absa`, folder `adapted-2026-10-11/`, beside
the earlier models (top level) and a teammate's 5 Oct retrain; all three
weight files match the local checksums, and the repo's README is the current
model card. The README's download and upload commands, the model card and
`scripts/share_bundle.sh` now point at them. The folder for the team's
shared drive is rebuilt by `scripts/share_bundle.sh data/run/share` (155 MB:
snapshot, embeddings, aspect answers, `README-teams.md`, `SHA256SUMS`);
`data/README-teams.md` is now tracked.

### 24 October

**Chatbot misdescriptions fixed, and measured on both models.** A person's
ratings of the 32 gold-set answers found 7 of the 26 the model wrote
contradicting the tool data although every number was a tool's: a wrong
year (3), a wrong period (2), a wrong rank (1), wrong topics (1)
([evidence](evidence/human-ratings-2026-10-24.md)). The tools now give the
data's end date, rank, ranking and topics as sentences to copy, a single
topic's score says it has no breakdown, and a year no tool returned is
flagged. Asked the 7 questions three times each, the local model was right
in 16 of 21 tries and OpenAI's gpt-6-luna (the default since the teammates'
OpenAI change, merged today) in 21 of 21, for US$0.0158 under a US$0.05 cap
([evidence](evidence/chatbot-fixes-2026-10-24.md)). The local model's
remaining fault: with too little recent data on a topic, it reports the
bank's overall score as the topic's.

**Evidence search: FinBERT replaced.** Within a topic, FinBERT similarity
ranked below a random draw, so the search orders by the question's words,
then newest (0.82 against 0.74). With no topic, FinBERT was no better than
random (0.12 against 0.10); all-MiniLM-L6-v2 now ranks those searches (0.31),
from its own store `data/search_embeddings.npz` (66 MB), refreshed by the
topic step. The search evaluation's precision at 5 divided by five even for
pools under five; fixed, which raises the report's within-topic figures by
about 0.03 ([evidence](evidence/search-models-2026-10-24.md), decision 27).

**Merged** the teammates' OpenAI change into `feat/chatbot-misdescription-fixes`;
diagrams brought up to date (343 rows check; Gemini gone, the dashboard reads
through the API). A fresh clone of the branch collects 2894 tests in `tests/`
and 2941 from the root; all pass on this Mac after Streamlit was upgraded
from 1.63.0 to 1.66.1, which the five dashboard navigation tests needed.
Replacement text for the Word report, now the master on SharePoint, is in
`docs/report/word-report-updates.md`.

**CNA and broker research cleared for the hosted model** (the team's
decision, DESIGN decision 28): both stay team-only, but `hosted_model: true`
in `config/sources.yaml` lets gpt-6-luna quote them; Reddit is still
withheld. Rerun on the 32 questions (US$0.0068): the same checks, and its
answers now quote CNA and broker research once each. CLAUDE.md's rules now
name the OpenAI key (Gemini is gone) and this exception.

**Needs a human:**
- Push the branch and merge it to `main` (not pushed).
- Upload the new `data/search_embeddings.npz` to SharePoint (or rebuild it:
  `python -m chatbot.search_vectors`, about 5 minutes).
- Rotate the OpenAI key: the one in `.env` was pasted into a chat session.
- Paste the replacement text into the Word report; a person to check the
  three-try answers the AI assistant read.
- CNA sentences appear in 97 tracked files, mostly the labelled data the
  project tracks by design, plus evaluation results (counted on 25 Oct by
  matching against the database; a count of 13 here on 24 Oct missed the
  labels and is withdrawn). The raw articles are not in git. Fine while the
  repo is private; remove with their history before any public release.
- `chatbot/retrieval_eval_with_recall.py` divides precision by k like the
  old evaluation did; its recall figures are unaffected.
- The gold-set check doesn't recognise gpt-6-luna's way of declining an
  out-of-scope bank ("I can't report …"), so it scores 6 of 8 where reading
  gives 8 of 8.

### 25 October

**Docker setup merged; the dataset is `data.zip`.** The teammates' Docker
setup (pull request 5) fast-forwarded onto `main`. It defines the dataset as
one file, `data/data.zip`, given to the team and to the assessors with the
project, and restores it with checks (integrity, the served model's rows,
vectors matching the sentences). `scripts/share_bundle.sh` now builds that
file from the latest snapshot, both vector files, the CNA cache and the
aspect answers; the setup's own validator accepted it (45,844 sentences,
45,844 vectors, six files restored), and its database is byte for byte the
14 Oct snapshot. Natively the same restore runs as
`python -m docker.bootstrap --data-only`. README, `data/README-teams.md`,
diagram 18 and replacement text for report section 2.3 describe it. The
models now download from a public Hugging Face repo whose card declares no
licence. A fresh clone collects 2956 tests in `tests/` and 3003 from the
root, all passing.

**The gpt-6-luna "figure no tool returned: 2 / 32".** The evaluation records
the first draft's flags (`chatbot/run_eval.py`, line 173); since 18 Oct a
draft that fails a check is rewritten before display. Re-checking the final
answers of both MacBook runs gives 0 of 32: a 24 and a 17 sat in first
drafts that were rewritten. The evaluation now records the flags of the
answer shown beside the first draft's, its summary reports both, and
`python -m chatbot.run_eval --recheck --tag <tag>` fills them in for older
results files without asking a model; every MacBook run since 18 Oct gives 0
answers shown with a figure no tool returned. Table 8 in the Word update file
has both rows. A rerun of the 32 questions and the conversations on
gpt-6-luna with the final code (US$0.0135) recorded both as it ran: right
tool 24 of 24, 3 first drafts and 0 answers shown with a figure no tool
returned, 9 of 9 conversation turns, a median 5.9 seconds an answer; a
recheck of a stripped copy matched the live record on all 32 answers.
The refusal check scored gpt-6-luna's correct refusals of two uncovered
banks as misses: it lacked their wording ("I only have sentiment data on
DBS, OCBC and UOB…") and didn't match the typographic apostrophe in "can't".
Both fixed; `--recheck` now re-scores the refusal check too, and every run
since 18 Oct gives 8 of 8.

**Needs a human:**
- CLAUDE.md's CNA rule needs the `data.zip` exception written in (the edit
  was refused to Claude as a change to its own instructions).
- A licence on the public model card (CC BY-NC-SA 4.0, from base FinBERT).
- Upload `data/run/share-2026-10-25/` (`data.zip`, its note, checksums).
- The 24 Oct commit of logs and results put `data/logs/plp.log`, the Word
  report and 13 results files in git; CLAUDE.md says never to stage the log.

(Both CLAUDE.md items above were settled later the same day: the CNA rule
now names `data.zip`, and the logs and Word copies are out of git; see the
next entry.)

**Documentation cleanup before the report and slides are written with AI.**
A teammate will hand the repository to an AI to draft the report and the
slides, so every stale statement is a likely error in them.
- *Audits.* Two read-only audits of the docs found about 70 statements that
  no longer matched the code or the database (the 1 Oct model's 0.604 in
  CLAUDE.md, DESIGN.md and the technical spec; "every stored score is base
  FinBERT"; the local model as the default; the dashboard reading the
  database; aspects not yet applied). A code review found 22 stale comments.
  All were fixed. A second audit of the rewritten text found no wrong
  headline figure and about 55 smaller faults, each fixed. The serious ones:
  - the RUNBOOK's only training recipe did not produce the model in use (the
    pretraining and LLM-label steps are now there);
  - three sentences of the Word update overstated a result (tool choice is
    the model's, not enforced by code; within a topic no vectors beat word
    matching; aspect agreement is 74%, not 73%);
  - several places dropped a caveat (the three-try retest was read by the
    AI assistant and is not held out; the human rating was of
    `llama3.1:8b`, not the default; kappa 0.93 is an upper bound; choosing
    the model on test macro-F1 makes 0.670 slightly optimistic);
  - "collection stopped 26 Sep" missed that 25 broker research reports
    (4 Oct) and 825 older Reddit posts (11 Oct) were added later; nothing
    published after 25 Sep was collected.
- *New and moved.* `docs/README.md` maps which docs are current, which are
  dated records and which are superseded, and gives every headline figure
  with its source. Fifteen superseded drafts and briefs, and the old STATUS,
  are in `docs/archive/`; STATUS.md is rewritten for the current state;
  dated records carry a banner. The Word-update file is now
  `docs/report/word-report-updates.md`; it also corrects three errors in the
  Word report itself (Table 3 holds the 399-sentence figures under text
  written for the 299; the amber box; the test count). The repository's copy
  of the Word report was deleted (the master is on SharePoint) and Word files
  under `docs/` are now ignored, since their cover pages carry names.
- *Diagrams.* All 23 checked; 18 redrawn, including the chatbot turn's
  empty-rewrite path; `check_sources.py` passes on 437 rows.
- *Tests.* The 15 files named by validation round (`round6` to `round13`)
  now carry topic names (for example `ellipsis_quotes_probes`); one new test
  for the evaluation summary's "(none)" line, which was printed even when
  failures were listed. 2957 tests in `tests/` and 3004 from the root: 2956
  passed, 2 skipped, 46 expected failures.
- *Repository hygiene.* Logs under `data/logs/` and `.project-context/` are
  out of git and ignored; absolute paths of this Mac were stripped from the
  tracked results and logs; the human ratings sheet is
  `data/eval/ratings_sheet_rater1.csv`, keeping the rater's name in its
  rater column, which the team asked for.
- *Rules.* Team decision of 25 Oct: development tools on the team's own
  accounts may read the data, Reddit and CNA included, and quote short
  extracts; the chatbot still never sends Reddit text to a hosted model.
  CLAUDE.md records it, with the rater-name exception and the logs rule.

**Needs a human:**
- Rotate the OpenAI key; add a licence to the Hugging Face model card;
  upload `data/run/share-2026-10-25/`; the two human ratings.
- Paste `docs/report/word-report-updates.md` into the SharePoint master,
  checking each block against the current text first.
- Hand the AI writing the report `docs/` without `docs/archive/`, plus the
  code and `config/`, and start it at `docs/README.md`.

**Rating sheets built** (no model called), in `data/eval/`
(`ratings_sheet_gpt-6-luna.csv`, `ratings_sheet_blind_llama3.1-8b.csv`), with
`README-ratings.md`; `data/eval/ratings_sheet.csv` is the old 14 Oct sheet. Sheet 1: gpt-6-luna's 26 model-written answers from the
final-code run (`luna_shown_v2`), as shown, with full tool data. Sheet 2: the
same 26 questions with the local model's answers and tool data from Rater 1's
sheet of 17 Oct, scores removed, for a blind second rater. Faithfulness is
required, relevance and correctness optional. The 6 fixed replies are left
out of both. The first rating sheet was the local `llama3.1:8b` run of
14 Oct (`rescored2_v2`; 31 of 32 answers identical), not gpt-6-luna.
- Needs a human: rate both sheets and commit the filled ones.
