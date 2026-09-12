# Overnight prompt: docs refresh, start/stop scripts, functional + technical specs, learning folder

You are running unattended overnight in `/Users/gavin/Projects/plp-project`
(the NUS-ISS PLP practice-module project: aspect-based sentiment dashboard,
API and chatbot for DBS, OCBC and UOB). Nobody will answer questions until
the morning. Work through the sections below in order, keep a running log,
and finish with a verification pass. If you get interrupted or your context
is summarised, resume from `docs/HANDOFF.md` (section 9), which you keep
updated as you go.

Everything in the "Ground truth" block was checked by hand on 2026-09-11.
Re-verify anything you rely on, but do not re-derive it from scratch.

---

## 0. Ground rules

### Interpreter and environment

- Run every Python command as
  `/Users/gavin/Projects/plp-project/.venv-plp/bin/python3` (Python 3.14.0).
  Never `python3`, never `pip`. A conda Python 3.9 on this machine shadows
  the venv and fails every import with `TypeError: unsupported operand
  type(s) for |`. This has already wasted one overnight run.
- Prefix every FinBERT step (`preprocess.pipeline`, `aspects.*`,
  `sentiment.score`, `chatbot.*`, `pytest`) with `HF_HUB_OFFLINE=1`.
- Ollama was reachable at `http://localhost:11434` when this prompt was
  written. Check again before any Ollama job (`curl -s
  localhost:11434/api/tags`). If it is down, skip Ollama jobs, record the
  skip, and continue. Do not start `ollama serve` yourself unless the
  start script you write in section 4 does it.
- Port 8501 is currently held by a Streamlit process from a different
  project (`.venv-aegis`, `dashboard.py`, PID 97113). Do not kill it. Any
  dashboard you start must use another port.

### Do not touch

- `data/labeled/test_blind.csv`, the `label` column of
  `data/labeled/candidates.csv`, and the `split` assignments. The blind test
  set is what makes every headline metric honest.
- `config/aspects.yaml` taxonomy content and `similarity_floor`. The
  taxonomy decision belongs to the team and supervisor.
- `chatbot/eval_gold_set.py` questions.
- `.env` (untracked, contains keys). You may edit `.env.example` (tracked)
  as instructed in section 3.
- The database, except through the standard pipeline commands in section 2.

### No-hallucination protocol (applies to every file you write tonight)

1. **Every claim about this codebase** must be traceable to a file and line
   you read in this session. Cite it as `path/to/file.py:123`.
2. **Every number** (counts, scores, percentages, timings) must come from a
   command you ran in this session. Record the exact command and its output
   in `docs/verification-ledger.md`. Never copy a number from an existing
   doc without re-running its source; existing docs are known to be stale in
   places (see section 3).
3. **Every external fact** (a definition, a formula, a benchmark, a date, a
   regulatory detail, a survey figure) must come from a page you fetched in
   this session. Cite the URL and the access date. Prefer primary sources:
   the paper, the library's own documentation, the bank's own investor
   relations page, the regulator, the survey publisher. Wikipedia is
   acceptable only for uncontroversial definitions and must be marked as
   such.
4. If you cannot fetch a source, the claim goes under a heading **"Not
   verified"** with what you would need to verify it. Never present it as
   fact. Never invent a citation, DOI, arXiv ID, page number or author list.
   If you remember a paper but could not fetch it, say "recalled, not
   verified".
5. When two sources disagree (including two files in this repo), report the
   disagreement rather than picking one silently. Two known examples to
   handle this way: the FinBERT "88.2% vs 62.1%" claim in
   `.project-context/course-content/course-context.md` (find the primary
   source or mark it), and the `llama3.2:3b` citation-fabrication rate,
   which is 11/23 (48%) in `docs/STATUS.md` but 10/23 (43.5%) in the
   latest tagged run `data/eval/chatbot_eval_results_llama3.2_3b.jsonl`
   (the 48% appears to come from the earlier untagged run of 2026-09-08).
6. Before finishing, do the verification pass in section 7. A doc that has
   not been through that pass is not finished.

### Working conventions

- Create a branch `overnight/handoff-docs` from `master` and commit there.
  One commit per logical unit, message in the same style as `git log`
  (imperative subject, a body that explains why, the attribution trailer
  from your own instructions). **Do not push.**
- Run long compute jobs in the background with `nohup`, one at a time
  through a single queue script (section 2), so they do not contend for GPU
  memory with each other or with the test suite. Check on them between
  documentation tasks. Never block on them.
- Keep `docs/HANDOFF.md` section 9 ("Overnight run log") updated after
  every completed step: what was done, what was skipped and why, what needs
  a human. Write it incrementally; it is your resume point.
- If a task fails twice for the same reason, record it and move on. Finish
  every other task in full rather than stopping.
- Do not delete or rewrite existing content in `docs/` wholesale. Edit in
  place, keep the existing voice (plain, evidence-first, caveats up front).

### Ground truth (verified 2026-09-11)

- Branch `master`, HEAD `37d0a66`. Uncommitted: 12 modified files
  (`aggregate/index.py`, `api/main.py`, `chatbot/run_eval.py`,
  `chatbot/tools.py`, `dashboard/app.py`, `docs/DESIGN.md`,
  `docs/RUNBOOK.md`, `docs/STATUS.md`, `docs/data-viability.md`,
  `ingest/earnings_extract.py`, `ingest/earnings_fetch_ir.py`, `sentiment/score.py`)
  and 9 untracked (`chatbot/suggestions.py`, `ingest/earnings_fetch_uob.py`,
  `preprocess/export_blind_test.py`, `scripts/compare_chatbot_models.sh`,
  five `tests/test_*.py`). Plus an empty untracked directory
  `docs/implementation-plan/` (delete it).
- What the uncommitted code adds, none of it documented yet except UOB
  Wayback: continuous time series (`compute_time_series` in
  `aggregate/index.py`, `GET /sentiment/series`, a bucket selector on the
  dashboard's Time Series tab, `monthly_series` in the chatbot's
  `get_trend`); generated starter questions (`chatbot/suggestions.py`,
  `GET /suggestions`, a Chat tab in the dashboard); blind test export
  (`preprocess/export_blind_test.py`, `data/labeled/test_blind.csv`, a
  "leakage repair" backup `candidates.csv.pre-leakage-repair.bak`);
  `--tag` on `chatbot/run_eval.py`; UOB filename date parsing in
  `ingest/earnings_fetch_ir.py`; a fix in `ingest/earnings_extract.py` changing
  `text.split("")` to `text.split("\n")` (check `git show
  HEAD:ingest/earnings_extract.py` and `tests/test_earnings_extract.py` before
  describing what was broken).
- Tests: `grep -c 'def test_'` gives 200 functions across `tests/`;
  `docs/RUNBOOK.md` says 214. Run pytest to get the real collected count.
- Labelling state: `candidates.csv` has 998 rows (798 `train_dev`, 200
  `test`); **0 human labels**; `llm_prelabel` filled on 997 rows by
  `llama3.2:3b` (progress file: 999 ok, 1 failed). LLM label distribution:
  positive 464, negative 310, neutral 223. Aspect distribution: other 524,
  dividend_policy 200, net_interest_margin 119, management_guidance 97,
  asset_quality 58. `test_blind.csv`: 200 rows, 0 labels.
- Ollama models present: `llama3.1:8b`, `phi4-mini:latest`, `gemma3:4b`,
  `qwen3:4b`, `llama3.2:3b`. `qwen3:4b` has never been through the
  chatbot eval.
- `docs/annotation-guideline.md` references `train/agreement.py`, which
  does not exist.
- `.env.example` is tracked in git and contains what look like real
  NewsAPI and Alpha Vantage keys.
- Course modules (from `.project-context/course-content/`): 1 Text
  Analytics (TA), 2 New Media and Sentiment Mining (NMSM), 3 Text
  Processing using Machine Learning (TPML), 4 Conversational UIs (no
  context file exists for module 4). Deliverables due 2026-11-01: system
  plus code and docs, report under 20 pages, video. The report must contain
  business problem, datasets, solution approach, test results, conclusions,
  references to public libraries and models, individual contributions, and
  a GenAI/LLM usage declaration.
- `.claude/settings.local.json` only pre-approves `WebSearch` and
  `WebFetch` for `github.com` and `raw.githubusercontent.com`. Other
  domains prompt unless the session was launched with permissions handled.

---

## 1. Orientation and baseline (do first)

1. Read, in this order: `README.md`, `docs/STATUS.md`, `docs/DESIGN.md`,
   `docs/RUNBOOK.md`, `docs/data-viability.md`,
   `docs/annotation-guideline.md`, `config/aspects.yaml`,
   `.project-context/course-content/course-context.md`,
   `.project-context/proposal/banks-plp-proposal.txt`. Skim the three
   `*-context.txt` course files; you will read them properly in section 6.
2. `git status` and `git diff --stat`. Confirm the ground-truth list above.
3. Run the full test suite and record the collected count and pass/fail in
   the ledger:
   `HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest tests/ -q`
4. Commit the existing uncommitted work on the new branch in two or three
   logical groups (for example: ingestion fixes plus UOB Wayback; time
   series plus suggestions plus Chat tab plus eval tagging; blind test
   export). Do not agonise over hunk-level splits. Leave the four modified
   `docs/*.md` files uncommitted; they get committed with section 3.
5. Snapshot the corpus numbers with SQL and put the commands in the ledger:
   documents and sentences by source and bank, `aspect_sentiment` row
   count, `sentiment_index` all-time rows per bank and source, date range,
   earnings sentences by bank, analyst_consensus rows. Use
   `.venv-plp/bin/python3 -c "import sqlite3; ..."` or `sqlite3
   data/plp.db`. These are the only corpus numbers you may quote tonight.

---

## 2. Compute lane (background, one job at a time)

Write a small queue script in the scratchpad (not in the repo) that runs the
jobs below sequentially with `nohup`, each with its own log under
`data/logs/overnight_<job>.log`, and start it right after section 1. Poll it
between documentation tasks. Every job writes a dated report under
`docs/evidence/` (tracked) with the exact command at the top, because
`data/` is gitignored and the team needs to see the results.

Order and instructions:

**A. Aspect discovery on the enriched corpus.**
`HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.discover`
Last run was on 2,888 sentences; the corpus is now ~36,900. Save the full
console report to `docs/evidence/aspect-discovery-<date>.md`. Do not change
`config/aspects.yaml`. Summarise in `docs/STATUS.md` section 3 ("Aspect
taxonomy not validated") what the re-run found, in three to five sentences,
as input to the team's decision.

**B. Similarity-floor re-sweep.**
`HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.compare_taxonomies`
`docs/DESIGN.md` decision 5 says to re-sweep when the corpus changes
materially; it has. Save to `docs/evidence/taxonomy-comparison-<date>.md`.
Do not change the floor. Note in DESIGN decision 5 that a re-sweep exists
and where it is.

**C. Chatbot evaluation, two runs.**
`CHATBOT_BACKEND=ollama OLLAMA_MODEL=qwen3:4b HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m chatbot.run_eval --tag qwen3_4b`
then the same with `OLLAMA_MODEL=llama3.1:8b --tag llama3.1_8b_rerun`
(to see whether its 3 errors were transient). Copy the two summary files
into `docs/evidence/` and add `qwen3:4b` as a row in the STATUS evaluation
table, with the run file and date the row was drawn from. Note that
`qwen3:4b` emits a reasoning chain first, per DESIGN decision 11, so its
timing is relevant.

**D. Incremental data refresh (only if A to C finished with hours to spare).**
`.venv-plp/bin/python3 run_daily_batch.py` then `preprocess.pipeline`,
`aspects.assign`, `sentiment.score`, `aggregate.index`, each with
`HF_HUB_OFFLINE=1`. If you run this, re-take the section 1 snapshot
afterwards and use the new numbers everywhere, or do not run it at all.
Never quote numbers from a half-refreshed database.

**Not tonight:** fine-tuning (no labels exist), GPT/Gemini verification
(no keys), any second-model pre-labelling run over the candidates
(`train/llm_prelabel.py` keys its progress file by sentence and aspect, not
by model, and its merge step writes into `candidates.csv`; running another
model would need code changes and must never touch `split=test` rows).
Record these as "could run overnight once X exists" in HANDOFF.

---

## 3. Documentation refresh (`docs/`, `README.md`, `.env.example`)

Bring the existing docs in line with the code as committed in section 1.
Specific items, all verified stale or missing on 2026-09-11:

1. **Time series.** RUNBOOK gets `GET /sentiment/series` (params, bucket
   values, `sufficient` flag, `min_n`) next to `/suggestions`. DESIGN
   "Deliberate scope limits" and STATUS "Smaller gaps" and "How to improve"
   item 6 still say `get_trend` is two discrete windows; update them to
   describe the monthly series and the design choice that it reuses the
   index's `_summarize` so a chart cannot disagree with the headline.
2. **Chat tab and suggestions.** RUNBOOK already has the API side
   (uncommitted). Add the dashboard side: the Chat tab, that suggestions are
   generated from the index, and that advice-seeking questions are excluded
   by design (`chatbot/suggestions.py` docstring).
3. **Blind test export.** Add to RUNBOOK's labelling workflow: why the
   blind sheet exists (`preprocess/export_blind_test.py` docstring), the
   `--merge` and `--check-leakage` commands, and that `llm_prelabel` was run
   over 199 of the 200 test rows before the leak was noticed and repaired.
   State plainly in STATUS section 1 what that repair did and did not undo.
   Also add the candidate aspect distribution (asset_quality has 58 rows)
   because it affects whether the proposal's 200 to 300 per class is
   reachable per aspect.
4. **Stale "trust" caveats.** DESIGN "Before you trust any number" item 1
   and README "Read this before quoting any number" still say the blended
   comparison is invalid and UOB blocks automated access. STATUS says it is
   resolved. Make STATUS the single source of truth for these caveats and
   have README and DESIGN carry a two-line summary plus a link, not a
   competing version. `config/aspects.yaml` header and the "Earnings PDFs —
   not yet started" section of `data-viability.md` are also stale; mark
   them resolved with a date rather than deleting the history.
5. **Eval table.** Reconcile the 48% versus 43.5% discrepancy as described
   in the protocol. Add a sentence on run-to-run variance.
6. **Counts.** Test count (from pytest), line count (state the command,
   for example `find . -name '*.py' -not -path './.venv*' | xargs wc -l`,
   with and without `tests/`), corpus numbers from the section 1 snapshot.
7. **`train/agreement.py`.** Either write it (Cohen's kappa over two
   annotator columns or two CSVs, using
   `sklearn.metrics.cohen_kappa_score`, with a test in `tests/`, usage in
   RUNBOOK) or change the guideline to say it does not exist yet. Writing
   it is preferred; it is small and the guideline promises it.
8. **`API_KEYS.md`.** It still describes four credentials including Reddit.
   Reddit now comes from Arctic Shift with no key, and Alpha Vantage
   contributes nothing (DESIGN "Deliberate scope limits"). Rewrite the
   summary to match RUNBOOK's key table and mark the Reddit section as
   historical.
9. **`.env.example`.** Replace the two key values with placeholders. Add to
   HANDOFF, under "needs a human", that the keys have been in git history
   since the initial commit and should be rotated; do not rewrite history.
10. **GenAI usage declaration.** Append tonight's work to section 8 of
    `.project-context/course-content/course-context.md`: what Claude Code
    was used for (documentation, specs, learning material, scripts, eval
    runs), and that all model-written text was verified against the ledger.
    The report needs this near-verbatim.
11. **README.** Update the layout block (`learning/`, `docs/spec/`,
    `docs/evidence/`, new scripts), the documentation table (HANDOFF,
    specs, learning), and the quick start once section 4's scripts exist.

Commit as one or two commits ("Refresh docs for time series, chat tab,
blind test export..." and "Add train/agreement.py").

---

## 4. Start and stop scripts (`scripts/`)

Write three Bash scripts and document them. They must work when run from
any directory (resolve the project root from the script's own path).

**`scripts/start.sh [all|dashboard|api|ollama]`** (default `all`)
- Uses the venv interpreter by absolute path, exports `HF_HUB_OFFLINE=1`,
  and sources `.env` if present (`set -a; . ./.env; set +a`).
- Fails fast with a clear message if the interpreter is below Python 3.10
  or `torch` is not importable (same reasoning as
  `scripts/overnight_backfill.py`).
- Ports from `PLP_DASHBOARD_PORT` (default 8501) and `PLP_API_PORT`
  (default 8000). If a port is in use by a process this script did not
  start, print the owning command (`lsof -nP -iTCP:<port> -sTCP:LISTEN`)
  and exit non-zero. Never kill a process it did not start. Port 8501 is
  the live test case for this.
- Starts each service with `nohup`, PID file in `data/run/<service>.pid`,
  log in `data/logs/<service>.log`. Idempotent: if the PID file points at a
  live process, say so and do not start a second copy.
- Waits for health before reporting success: API `GET /health`, dashboard
  `GET /_stcore/health` (verify this Streamlit endpoint against the
  installed version's docs and record the source), up to a timeout, then
  prints the URLs.
- Ollama: if `localhost:11434` answers, leave it alone and say so. If not,
  start `ollama serve` the same way and write a marker so stop knows it
  owns it.

**`scripts/stop.sh [all|dashboard|api|ollama]`**
- Reads PID files, sends SIGTERM, waits up to 10 s, then SIGKILL, removes
  the PID file. Stops Ollama only if start.sh's marker says it started it.
  Never stops by port scan.

**`scripts/status.sh`**
- One line per service: running or not, PID, port, last log line.

Checks: `bash -n` on all three; run `shellcheck` if installed (record
whether it was); a real smoke test with the API on a free port (start,
curl `/health`, status, stop, confirm PID file removed) recorded in the
ledger; a pytest that runs `bash -n` over `scripts/*.sh`. Document in
RUNBOOK (new "Start and stop" section at the top of "Interfaces", keeping
the manual commands as the reference for what the scripts do) and in the
README quick start. Commit separately.

---

## 5. Functional and technical specifications (`docs/spec/`)

The existing docs already explain *why* (DESIGN), *how to run* (RUNBOOK)
and *what is unfinished* (STATUS). The specs fill what a teammate joining
now still lacks: what the system is supposed to do for whom, and the exact
contracts between parts. Link to DESIGN for rationale; do not duplicate it.
Every statement must trace to code, the proposal, or the course context.

**`docs/spec/functional-spec.md`**
1. Purpose and users: the retail-investor problem from the proposal (with
   the SIAS-Beansprout and MDRT figures cited as the proposal cites them,
   marked "as cited in proposal" unless you fetch the surveys), and the
   three user types: retail reader of the dashboard, API consumer,
   teammate or grader.
2. Scope and non-goals. Non-goals include: no investment advice, batch not
   streaming, no full analyst reports, no fine-tuned model yet.
3. Data sources as features: for each source, what it provides, cadence,
   caveats (Reddit via Arctic Shift, earnings PDFs from IR sites and
   Wayback for UOB, NewsAPI free tier, Yahoo consensus as an unofficial
   endpoint, Alpha Vantage retained but empty).
4. Functional requirements by interface, each as a user story with
   acceptance criteria that can be checked against the code or a test:
   dashboard (five tabs; name them from `dashboard/app.py`), REST API
   (every endpoint in `api/main.py`), chatbot (tools, grounding rules from
   `chatbot/prompts.py`, refusal behaviour, verification warning,
   backends), labelling workflow (export, blind test, pre-label, merge,
   agreement).
5. Requirement traceability matrix: course rubric rows (conversational UI,
   two text-mining tasks, sentiment mining, one DNN) and proposal
   commitments (four streams, aspect taxonomy, ~1,000 labels, macro-F1,
   chatbot with evidence) mapped to the feature, the code, the evidence
   file, and status (done, partial, blocked, with the blocker).
6. Known limitations, in the voice of STATUS, as a short list linking to
   STATUS rather than restating it.
7. Glossary of product terms (aspect, sentiment index, volume floor,
   shrinkage, blended versus per-source, verification warning).

**`docs/spec/technical-spec.md`**
1. Architecture: reuse DESIGN's diagram by reference, add a one-paragraph
   walkthrough of one sentence's journey from ingestion to a chatbot
   citation, with the `sentence_id` as the thread.
2. Module map: every package and its entry points (`python -m ...`), one
   line each, generated from the actual tree.
3. Data model: all six tables with every column, type and meaning. Take
   the DDL from `ingest/db.py`, `aspects/assign.py`, `sentiment/score.py`,
   `aggregate/index.py`, `ingest/yahoo_analyst.py`, and confirm against
   `sqlite3 data/plp.db .schema`. Note the `doc_id` hashing and
   `INSERT OR IGNORE` idempotency, `norm_hash` deduplication, the
   `source` dimension on `sentiment_index`, and the `published_at` string
   comparison caveat in `aggregate/index.py`.
4. Pipeline contracts: for each step, input table, output table, what
   "already processed" means, expected timing (from RUNBOOK, marked as
   measured on an M-series Mac), and the environment variables it needs.
5. Model and library inventory: `ProsusAI/finbert` (embeddings with mean
   pooling, and zero-shot classification), spaCy `en_core_web_sm`,
   UMAP + HDBSCAN, scikit-learn, Ollama models with sizes, hosted backends.
   Versions from `requirements.txt` and `.venv-plp/bin/python3 -m pip
   freeze` for the ones that matter.
6. Configuration reference: every variable in `.env.example` and every key
   in `config/aspects.yaml`, with defaults and where each is read.
7. API contract: table of endpoint, method, query parameters with
   validation patterns, response shape (from the code and `tests/test_api.py`),
   error codes. Chatbot tool schemas summarised from `chatbot/tools.py`.
8. Chatbot design: the tool-calling loop, backend abstraction
   (`chatbot/backends/base.py` explains why each backend owns its loop),
   hybrid retrieval (`chatbot/retrieval.py`), grounding enforced in code
   (volume floor, citation verification), evaluation harness.
9. Evaluation methodology: sampling design for train_dev versus test,
   blind labelling, inter-annotator agreement target, baselines required
   by `train/evaluate.py`, metrics, seeds. State what has and has not been
   run.
10. Testing strategy: how external APIs are mocked with captured payloads,
    the `temp_db` fixture, the collected test count, runtime.
11. Operations: start/stop scripts, logging configuration, overnight
    backfill, expected failure modes (RUNBOOK troubleshooting table by
    reference).
12. Security, compliance and ethics: keys in `.env`, the `.env.example`
    incident, the WAF stance and Wayback transport (DESIGN decision 3),
    Yahoo's unofficial endpoint, archive.org rate limits, the
    not-financial-advice position.
13. Ownership and open decisions: a table with columns area, owner (leave
    blank for the team), and the open decisions from STATUS (taxonomy,
    blending, default local model, advice-declining fix).

Commit as "Add functional and technical specifications".

---

## 6. Learning folder (`learning/`)

Purpose: study material for the four teammates, who must pass a written
exam on the four course modules and write a report that explains every
technique used. Audience: someone who has attended the lectures but has not
read this codebase.

### Bloom's taxonomy requirement

Use the revised taxonomy (Anderson and Krathwohl, 2001): Remember,
Understand, Apply, Analyze, Evaluate, Create. Fetch and cite one reputable
source for the levels before you rely on them. The user's requirement is
**at least level 4 (Analyze)** for every topic, which means every topic
file must contain real Analyze, Evaluate and Create sections, not only
definitions. Concretely:

- *Analyze* means breaking the technique into parts and showing how they
  relate, comparing it with at least two alternatives on stated criteria,
  and tracing one real example from this corpus through it. Example of the
  standard: mapping Liu's opinion quintuple (entity, aspect, sentiment,
  holder, time) from NMSM Day 1 onto the columns of `sentences`,
  `sentence_aspects` and `aspect_sentiment`, and explaining which element
  the schema approximates (holder is only known as source type).
- *Evaluate* means judging this project's choice with evidence from the
  ledger, saying what the evidence does not show, and stating when the
  opposite choice would be right.
- *Create* means one exercise a teammate can do against this repo in under
  two hours with an observable result (a number, a plot, a diff), plus a
  short expected outcome so they know if they got it right.

### Per-topic template (use exactly this structure)

```
# <Topic>
Subject: <module or domain> · Bloom target: Analyze / Evaluate / Create
Prerequisites: <links to other topics>

## 1. Why it matters here (Understand)
## 2. The concept (Understand / Apply)        definition, formula, worked example from THIS corpus
## 3. Where it lives in this repo (Apply)      table of file:line references
## 4. Analyze
## 5. Evaluate
## 6. Create (exercise + expected outcome)
## 7. Self-check (5 questions; answers in a collapsed <details> block)
## 8. Sources
   Repo: file:line
   Course context: file and section
   External: URL, accessed <date>, what it supports
   Not verified: <claims you could not confirm>
```

### Categories and topics

Directory per category, one Markdown file per topic, kebab-case names.
Write the **core set** first, then the extended set as time allows. Each
file is independently useful, so partial completion is still a deliverable.

**`learning/README.md`**: how to use the folder, the Bloom legend, a table
of every topic with its category, status (complete or draft), and the
verification status from the ledger.

**01-text-analytics** (Module 1, TA)
- core: `crisp-dm-for-text-mining.md` (map the six phases onto this repo's
  phases; where the project deviated and why)
- core: `text-preparation-and-sentence-segmentation.md` (spaCy, the
  financial abbreviation exceptions, per-source cleaning, near-duplicate
  hashing; compare with NLTK punkt and a regex splitter)
- core: `tf-idf-versus-contextual-embeddings.md` (bag-of-words and tf-idf
  from the lectures versus FinBERT mean-pooled embeddings; why mean
  pooling and not CLS, per `aspects/embed.py`)
- core: `clustering-with-umap-and-hdbscan.md` (what each does, the
  min-cluster-size and noise fraction, the 52% noise finding; compare
  with k-means and LDA topic modelling)
- core: `corpus-annotation-and-inter-annotator-agreement.md` (guideline
  design, Cohen's kappa with the formula and the Landis and Koch
  thresholds, the kappa 0.6 target, the LLM-as-annotator workflow)
- extended: `information-extraction-and-entity-detection.md` (bank
  attribution rules in `ingest/base.py` and `preprocess/pipeline.py` as a
  rule-based NER; when a statistical NER would be needed)

**02-sentiment-mining** (Module 2, NMSM)
- core: `levels-of-sentiment-analysis-and-the-opinion-quintuple.md`
- core: `aspect-based-sentiment-analysis.md` (ABSA subtasks, the five
  aspect-extraction families, where frozen-centroid assignment sits among
  them, the similarity-floor sweep as calibration)
- core: `sentiment-index-aggregation-and-shrinkage.md` (score × n/(n+5),
  source weights, per-source dimension, why earnings text skews positive;
  compare with a plain mean and with a Bayesian prior interpretation)
- extended: `llm-assisted-pre-labelling.md` (structured prompting with a
  JSON schema, why `llama3.2:3b` beat `qwen3:4b` for this task, the
  anchoring risk, the test-set leak and its repair)
- extended: `sarcasm-negation-and-financial-valence.md` (the guideline's
  edge cases; why "beat lowered guidance" defeats general lexicons;
  Loughran-McDonald versus VADER)

**03-text-processing-with-ml** (Module 3, TPML)
- core: `transfer-learning-and-finbert.md` (BERT pre-training, FinBERT's
  further pre-training and Financial PhraseBank fine-tuning, what
  `ProsusAI/finbert` actually is; verify every claim against the FinBERT
  paper and the Hugging Face model card)
- core: `fine-tuning-for-aspect-conditioned-classification.md`
  (sentence-pair input, class-weighted loss, learning rate, warmup, early
  stopping on macro-F1, seeds; from `train/finetune.py`)
- core: `evaluation-splits-leakage-and-macro-f1.md` (why the test split is
  random and frozen, what leakage happened here, precision, recall, F1 per
  class, macro versus micro, the required baselines in
  `train/evaluate.py`)
- extended: `regularisation-and-overfitting-at-small-data.md` (L1, L2,
  dropout, early stopping from TPML Day 1, applied to a ~800-example
  fine-tune)
- extended: `attention-and-why-context-changes-a-vector.md`

**04-conversational-ui** (Module 4; no course context file exists, so
lean on the code and on primary documentation, and say so)
- core: `tool-calling-agents.md` (the loop in `chatbot/agent.py`, tool
  schemas, backend differences in message format, why no framework)
- core: `retrieval-augmented-generation-and-hybrid-search.md` (SQL
  pre-filter, cosine over cached embeddings, lexical boost; compare with a
  vector database and BM25)
- core: `grounding-hallucination-and-citation-verification.md` (the two
  code-level enforcements, the eval results by model, why prompt rules
  failed)
- extended: `evaluating-a-chatbot-with-a-gold-set.md` (categories in
  `chatbot/eval_gold_set.py`, what is automated and what needs a human,
  run-to-run variance)

**05-finance-domain**
- core: `singapore-banks-sgx-and-the-sti.md` (D05, O39, U11; STI weight
  and market cap claims from the proposal must be verified against a
  current SGX or index-provider page or marked as proposal figures;
  MAS as regulator; reporting cadence: check each bank's IR site for
  whether it reports quarterly or half-yearly with business updates, since
  that affects what the `1Q`/`2Q` filenames in `data/earnings_pdfs/` mean)
- core: `bank-earnings-vocabulary.md` (net interest margin, net interest
  income, non-performing loan ratio, specific and general allowances,
  credit cost, CET1 ratio, cost-to-income, return on equity, dividend
  payout ratio and yield, fee income, wealth management; define each from
  a primary source, then show its frequency across the Reddit, earnings
  and news sentences with a SQL query, as the Analyze section)
- core: `earnings-releases-analyst-calls-and-consensus.md` (what a results
  announcement, CEO presentation and analyst-call transcript are, what
  Yahoo's recommendation mean 1 to 5 and price target mean, why full
  analyst reports are unavailable)
- core: `financial-sentiment-resources.md` (Loughran-McDonald 2011,
  Financial PhraseBank, FinBERT; verify the "88.2% versus 62.1%" claim or
  mark it)
- extended: `retail-investor-context-in-singapore.md` (SIAS-Beansprout and
  MDRT survey figures: fetch the originals or mark as cited in proposal)
- extended: `why-management-text-reads-positive.md` (the 24.7% versus 2.3%
  positive rate; disclosure incentives; how the project handles it)

**06-engineering-practices**
- core: `idempotent-ingestion-and-resumable-batch-jobs.md`
- core: `testing-against-captured-payloads.md`
- extended: `data-access-ethics-waf-wayback-and-unofficial-apis.md`
- extended: `logging-for-unattended-runs.md`

### Sources to start from (verify each before citing; drop what you cannot fetch)

Papers and model cards: the FinBERT paper by Araci (2019, arXiv), the
`ProsusAI/finbert` Hugging Face model card, Financial PhraseBank by Malo et
al. (2014), Loughran and McDonald (2011, Journal of Finance), BERT by Devlin
et al. (2018), UMAP by McInnes, Healy and Melville (2018), the `hdbscan`
library documentation and its cited papers by Campello et al., Cohen's
kappa (Cohen 1960) and Landis and Koch (1977), Bing Liu's sentiment analysis
book or survey for the opinion quintuple. Library docs: spaCy, scikit-learn,
Streamlit, FastAPI, Ollama, Anthropic tool use. Domain: each bank's
investor-relations page, SGX, MAS, the SIAS and MDRT survey pages. Do not
cite anything from memory alone.

Commit per category ("Add learning material: text analytics"), so a
partial run still lands cleanly.

---

## 7. Verification pass (mandatory)

Do this after sections 3 to 6, before the final commit.

1. Re-read every file you created or changed tonight. For each factual
   claim, find its ledger entry. If there is none, either produce the
   evidence now or move the claim under "Not verified".
2. Run every command that appears in a fenced block in RUNBOOK, README,
   the specs and the learning exercises at least once (`--help` or
   `--dry-run` is enough for slow or network commands). Record which ran,
   which were skipped and why.
3. Check every relative link and file reference in the new docs resolves
   to a real path. A script to do this is fine.
4. Consistency check: the "trust" caveats, the eval table, the corpus
   numbers and the test count must be identical wherever they appear
   (README, DESIGN, STATUS, specs, learning). One source, others link.
5. Run the full test suite again. It must be green; if it is not, say so
   in HANDOFF with the output rather than hiding it.
6. Grep your new files for hedges that hide an unverified claim
   ("typically", "it is known that", "studies show") and either cite or
   remove.
7. Finish `docs/verification-ledger.md` with a summary table: file, claims
   checked, claims verified, claims marked not verified.

---

## 8. Deliverables checklist

- [ ] Branch `overnight/handoff-docs` with logical commits, nothing pushed
- [ ] Pre-existing code committed (section 1)
- [ ] `docs/evidence/` reports from the compute lane, and STATUS updated with them
- [ ] `docs/` refresh items 1 to 11 (section 3)
- [ ] `train/agreement.py` with tests, or the guideline corrected
- [ ] `scripts/start.sh`, `scripts/stop.sh`, `scripts/status.sh`, documented and smoke-tested
- [ ] `docs/spec/functional-spec.md` and `docs/spec/technical-spec.md`
- [ ] `learning/README.md` plus every core topic; extended topics as time allows
- [ ] `docs/verification-ledger.md`
- [ ] `docs/HANDOFF.md`: read order for a new teammate, ownership table
      (blank), open decisions, "needs a human" list (key rotation, taxonomy
      decision, labelling, model default), and section 9 "Overnight run
      log" with what was done, skipped and why
- [ ] GenAI usage declaration appended (section 3, item 10)
- [ ] Tests green, and the count recorded

If you run short of time, the priority is: section 3, then 4, then 5, then
6 core topics, then 6 extended topics. Whatever the compute lane finished is
reported; whatever it did not is listed in HANDOFF as runnable next.
