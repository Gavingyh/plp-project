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
