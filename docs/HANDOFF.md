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
through a dashboard, a REST API and a grounded chatbot.

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

scripts/start.sh              # dashboard + API + Ollama, with health checks
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

### 3. Settle the aspect taxonomy — team plus supervisor

> **Decided by the team 2026-09-26, to confirm with the supervisor.** Keep the
> proposal's four aspects plus `other`, assigned by a local LLM, one per
> sentence (DESIGN decision 16). The supervisor's input is still needed
> because the method differs from the proposal. Evidence as it stood on
> 2026-09-11:

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
| Interfaces | dashboard, API, chatbot and its evaluation |
| Report and video | everyone; each person writes their own contribution summary |

---

## Things that will waste your time if nobody warns you

| symptom | cause | fix |
|---|---|---|
| `TypeError: unsupported operand type(s) for \|` | conda's Python 3.9 shadowing the venv | Use `.venv-plp/bin/python3` by absolute path, always |
| `ModuleNotFoundError: torch` | System Python | Same |
| A step hangs at near-zero CPU | HuggingFace metadata check | `HF_HUB_OFFLINE=1` |
| `scripts/start.sh` refuses port 8501 | Another project's Streamlit is on it | Use `PLP_DASHBOARD_PORT`, or stop that process yourself. The script will not kill it for you |
| Chatbot answer carries a verification warning | The model cited evidence it never retrieved | Do not trust that answer |
| Dashboard says "No sentiment data yet" | Pipeline has not run, or `data/plp.db` is missing | See RUNBOOK |

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
  4. Confirm the taxonomy change with the supervisor (PLAN O1).
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
  specified; only the E1 and E2 finals are kept.
- `aspects.compare_taxonomies` measures its own hard-coded four-aspect
  candidate A, not the current config, despite its docstring. Recorded in the
  calibration file, not fixed (outside the run's scope).

Needs a human:
1. **Scoring model.** E1 (8 epochs, with aspect) is level with base FinBERT
   on macro-F1 (0.577 ± 0.027 against 0.571), better on negative sentences
   (0.44 against 0.30) and worse on neutral. Whether it replaces base
   FinBERT for the corpus is PLAN section 5's decision.
2. **Aspect assignment.** No floor makes centroid assignment accurate (top-1
   0.41); leave the floor at 0.65 and build the LLM classifier, whose
   baseline is now measured.
3. **Demo model (O3).** The 8B invents far less than the 3B (3 against 9
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
- J1 (fine-tuning fixes): done
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
- J2 (LLM aspect classifier): done
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
  sentiment rows in `data/labeled/claude/`; nothing applied to
  `candidates.csv` ([evidence](evidence/opus-labeller-2026-10-01.md)).
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
3. The four README fixes in
   [install-test-2026-10-01.md](evidence/install-test-2026-10-01.md),
   above all naming Python 3.10 or newer.
4. The Opus review queues (202 aspect, 173 sentiment rows; 43 and 37 on the
   test split), and where a retail customer's investment products belong,
   wealth or retail banking (63 rows), before the next labelling round.
5. Long runs need the Mac plugged in with the lid open: it slept twice on
   1 Oct (battery, then lid), pausing jobs for about an hour each time.
- J3 (preprocessing dry run): done, `606dde4`. 98 of 44,345 sentences
  (0.22%, all earnings PDFs) are debris; broader rules remove real
  sentiment, so preprocessing isn't where the model's errors are.
- J4 (install test): done, `1ff6c74`. With a Mac's default `python3`
  (Apple's 3.9) the install fails on `torch>=2.9.0` and the README never
  names the Python it needs; with 3.14 every step works, the snapshot
  checksum matches, 421 tests pass, and the API and dashboard answer on free
  ports ([evidence](evidence/install-test-2026-10-01.md), four README fixes
  listed there).
