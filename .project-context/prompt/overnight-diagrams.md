# Overnight prompt: Mermaid diagrams of the system, from the code and the database

You are running unattended overnight in `/Users/gavin/Projects/plp-project`
(the NUS-ISS PLP practice-module project: aspect-based sentiment dashboard,
API and chatbot for DBS, OCBC and UOB). Nobody will answer questions until
the morning. Work through the sections in order, keep the run log current,
and finish with the verification pass. If you are interrupted or your
context is summarised, resume from the run log (section 0, "Working
conventions").

Your job is to produce diagrams that are **true to the code and the
database as they are tonight**, readable in the project report, and easy to
keep true afterwards. A diagram that looks right but shows a function,
column or call that does not exist is worse than no diagram.

The "Ground truth" block was checked by hand on 2026-09-26. Re-verify
anything you draw from it.

---

## 0. Ground rules

### Environment

- Python: `/Users/gavin/Projects/plp-project/.venv-plp/bin/python3` by
  absolute path, never `python3` (a conda Python 3.9 shadows the venv).
- Node is installed (`/Users/gavin/.nvm/versions/node/v20.20.2/bin/node`,
  `npx` beside it). Render with the Mermaid CLI through npx:
  `npx -y -p @mermaid-js/mermaid-cli mmdc ...`. If its bundled Chromium
  download fails, point Puppeteer at the installed Chrome with a config file
  containing `{"executablePath": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}`
  and pass `-p <config>`.
- Network is needed only for the npx package. Nothing else goes online.

### Do not touch

- **Read-only on the database.** Use only `SELECT` and `PRAGMA` against
  `data/plp.db`. Never insert, update, delete, vacuum or checkpoint.
- **Run nothing that changes data**: no ingestion (`run_news_pull.py`,
  `run_daily_batch.py`, `ingest.*`), no pipeline step (`preprocess.*`,
  `aspects.*`, `sentiment.*`, `aggregate.*`), no training, no chatbot or
  Ollama calls. Everything you need is in the code, the docs and the schema.
- Don't modify existing code. The only code you add is the render script
  and its test (section 4). Documentation edits are limited to adding links
  (section 5).
- `data/labeled/`, `data/snapshots/`, `.env`: don't open or change.

### No-hallucination protocol

1. **Every element of every diagram traces to a source**: a module,
   function or class to the `path:line` where it is defined; a call or
   message to the line that makes it; a table or column to the live
   schema; a planned element to its DESIGN.md decision number; a date or
   task in the plan to its line in `docs/PLAN.md`. Each diagram file carries
   a sources table (section 2). No source, no element.
2. **The live database wins over code and docs for the data model.** Get
   tables, columns, types and keys from `PRAGMA table_info` and
   `PRAGMA foreign_key_list`. Where the code's `CREATE TABLE` differs (see
   ground truth), draw the live schema and note where each column is defined.
3. **The code wins over the docs for behaviour.** If a doc describes a flow
   the code doesn't implement, draw the code and record the mismatch in the
   run log under "Doc/code disagreements" rather than silently picking one.
4. **Numbers** (row counts, iteration caps, history length, ports,
   thresholds) come from a command or a code line read tonight; cite it.
   Keep numbers out of diagrams unless they explain behaviour (a
   tool-iteration cap does; a row count mostly doesn't: put counts in the
   caption, dated).
5. **Planned is not built.** Anything decided but not in the code
   (DESIGN decisions 16–18: LLM aspect classifier, aspect + sentiment
   labelling, bank NER; and fine-tuning, which is written but has never
   run because nothing is labelled) is drawn with the planned style
   (section 2) and labelled `(planned, DESIGN 16)` etc. Never draw a
   planned component as if it runs today.
6. If you can't establish something, leave it out and list it in the run
   log under "Left out, and why".

### Working conventions

- Create branch `overnight/diagrams` from `main` and commit there, one
  commit per diagram group (sections 3.A–3.F), plus one for the render
  script and one for the verification pass. Imperative subject, a body
  saying why, the attribution trailer from your own instructions.
  **Do not push.**
- Keep a run log at the end of `docs/HANDOFF.md` under a new heading
  "Overnight run log — diagrams (<date>)": done, skipped and why,
  doc/code disagreements, left out and why, needs a human. Update it after
  each group. It is your resume point.
- If a diagram fails to render twice for the same reason, simplify it
  (split it, or drop the feature that breaks), record that, and move on.
- Finish every core diagram before starting extended ones.

### Ground truth (verified 2026-09-26, HEAD `82149f8` on `main`)

- **Tables and primary keys** (live `PRAGMA`):
  `documents` (PK `doc_id`), `sentences` (PK `sentence_id`),
  `sentence_aspects` (PK `sentence_id, aspect`),
  `aspect_sentiment` (PK `sentence_id, aspect, model_version`),
  `sentiment_index` (PK `bank, aspect, window, source, model_version`),
  `analyst_consensus` (PK `bank, as_of_date`).
- **Declared foreign keys** (three): `sentences.doc_id → documents.doc_id`,
  `sentence_aspects.sentence_id → sentences.sentence_id`,
  `aspect_sentiment.sentence_id → sentences.sentence_id`. SQLite enforces
  them only with `PRAGMA foreign_keys=ON`; check whether the code turns it
  on (grep `foreign_keys`) and say so in the ER diagram's caption.
- **Relationships that are not keys**: `aspect_sentiment (sentence_id,
  aspect)` joins `sentence_aspects (sentence_id, aspect)` by convention;
  `sentiment_index` is computed from `aspect_sentiment` + `sentences`
  (derived, no key); `analyst_consensus` stands alone, linked to the rest
  only by the bank name.
- **Schema drift**: the live `documents` table has `has_analyst_view`,
  which is not in the `CREATE TABLE` in `ingest/db.py`. Find which module
  adds it and cite the line. The other tables' `CREATE TABLE` statements
  live in `ingest/db.py`, `aspects/assign.py`, `sentiment/score.py` and
  `aggregate/index.py` (`_SCHEMA` constants): verify each.
- **Row counts** on 2026-09-26: documents 27,795; sentences 42,746;
  sentence_aspects 90,117; aspect_sentiment 90,117; sentiment_index 257;
  analyst_consensus 14.
- **Runtime**: `scripts/start.sh` starts the dashboard (port
  `PLP_DASHBOARD_PORT`, default 8501), the API (`PLP_API_PORT`, default
  8000) and uses Ollama at `OLLAMA_BASE_URL` (default
  `http://localhost:11434`). The database, embeddings cache
  (`data/sentence_embeddings.npz`) and snapshots are local files, not in
  git. The daily launchd job (`scripts/com.plp.dailybatch.plist`) exists as
  a template and is not installed anywhere.
- **Chatbot turn** (`chatbot/agent.py`, `chatbot/guards.py`): input guards
  (advice, then scope) may answer without calling the model; otherwise the
  backend runs a tool-calling loop with an iteration cap; then output
  checks run (citations, cited sentence ids, figures); an empty answer is
  replaced. `Conversation` keeps recent turns and a state of banks, aspect
  and window. Read the code for the exact order, caps and names.
- **Where the design reasoning is**: `docs/DESIGN.md` (decisions 1–19),
  `docs/PLAN.md` (plan, decisions D1–D5, open O1–O5, sequence in section 5),
  `docs/news-data.md` (news filter rules), `docs/spec/technical-spec.md`
  (module map, data model, API), `docs/RUNBOOK.md` (commands).

---

## 1. Orientation (do first)

1. `git status`, `git log --oneline -5`; create the branch.
2. Dump the live schema to `docs/diagrams/schema-2026-<mm>-<dd>.txt`:
   for each table, `PRAGMA table_info`, `PRAGMA foreign_key_list`,
   `PRAGMA index_list`, and `SELECT COUNT(*)`. This file is the evidence the
   ER diagram is checked against.
3. Read, in this order: `docs/spec/technical-spec.md` sections 1–4 and 8;
   `docs/DESIGN.md` "What the system does" and decisions 13–19;
   `docs/PLAN.md` sections 2, 3 and 5; `docs/news-data.md` "Filtering and
   dedup rules". Then the entry-point code each diagram needs.
4. Check the render toolchain once on a trivial diagram (section 4) before
   drawing anything, so a broken toolchain is found in minute one.

---

## 2. Conventions for every diagram

**Files.** For each diagram `NN-name`:

- `docs/diagrams/src/NN-name.mmd`: the Mermaid source, the single source
  of truth.
- `docs/diagrams/NN-name.md`: the page people read, containing, in order:
  a title; one or two sentences on what question the diagram answers and
  for whom; the legend; the Mermaid block (identical to the `.mmd`,
  enforced by a test); "What this shows and doesn't show"; the sources
  table; for diagrams with planned parts, a planned-elements table.
- `docs/diagrams/img/NN-name.svg` and `.png`: rendered by the script.

**Sources table** (one row per node, edge or message that isn't obvious):

| element | source | symbol checked |
|---|---|---|
| `answer_turn` | `chatbot/agent.py:154` | `def answer_turn` |

The "symbol checked" column is the literal text that must appear on that
line; the verification script checks it.

**Mermaid features.** Use only diagram types GitHub and VS Code render
reliably: `flowchart`, `sequenceDiagram`, `erDiagram`, `classDiagram`,
`stateDiagram-v2`, `gantt`. Avoid beta types. Start every diagram with
`accTitle:` and `accDescr:` lines. Quote labels containing punctuation.
Keep node ids short and stable (`ingestNews`, not `n1`).

**Planned style.**
- Flowcharts and state diagrams: `classDef planned stroke-dasharray: 5 5,
  color:#555, fill:#fafafa;` on planned nodes, and `-.->` for planned edges,
  with "(planned, DESIGN nn)" in the label.
- Sequence diagrams: wrap planned steps in `rect rgb(245,245,245)` with a
  `Note over` reading "Planned — DESIGN nn", so the difference survives
  printing in greyscale.
- Never rely on colour alone.

**Readability.** Aim for at most about 20 nodes or 12 participants/messages
per diagram, so it reads on an A4 page. Split a busy diagram into an
overview plus details rather than shrinking it. Name things as a reader of
the report would ("sentiment scoring"), with the module in a smaller second
line where it helps (`sentiment.score`).

**Honesty in captions.** Each diagram page ends its "What this shows and
doesn't show" with anything simplified (e.g. "retry loops omitted").

---

## 3. The diagrams

Core (A–E) first, in order; then extended (F) as time allows.

### A. Overview

- **01-system-context** (flowchart). The system as one box; around it the
  people (retail investor using the dashboard and chat; team members who
  ingest, label and train; a grader running it from the README) and the
  external services it depends on: Arctic Shift (Reddit), Google News RSS,
  Yahoo Finance (news and consensus), NewsAPI, Alpha Vantage (contributes
  nothing: say so), bank IR sites and the Wayback Machine (earnings PDFs),
  the LLM backends (local Ollama; hosted Claude, OpenAI, Gemini, of which
  only Claude has been verified). Label each edge with what flows.
- **02-runtime** (flowchart). What runs where on one machine: Streamlit
  dashboard, FastAPI, Ollama, their ports; the files (`data/plp.db`,
  embeddings cache, logs, `data/news_flagged.csv`, snapshots); which
  process reads or writes which file; batch scripts as separate processes;
  the launchd template marked as not installed. Cite `scripts/start.sh`.

### B. Data

- **03-data-model** (erDiagram). All six tables with every column and type
  from the live schema, PKs marked. Declared foreign keys as solid
  (identifying) relationships; the conventional join
  (`aspect_sentiment`–`sentence_aspects`) and the derived table
  (`sentiment_index`) as dashed relationships whose labels say "join by
  convention" / "derived". Caption: row counts with the date, whether
  foreign keys are enforced, and the schema drift (`has_analyst_view`).
- **04-pipeline** (flowchart, left to right). Sources → ingest adapters →
  `documents` → sentence splitting and bank attribution → `sentences` →
  embeddings → aspect assignment → `sentence_aspects` → sentiment scoring
  → `aspect_sentiment` → index aggregation → `sentiment_index` →
  dashboard, API, chatbot. The news filter sits between the news adapters
  and `documents`. Planned, dashed: LLM aspect classifier replacing
  seed-centroid assignment (DESIGN 16), bank NER in attribution (DESIGN
  18), fine-tuned FinBERT replacing zero-shot scoring (PLAN section 3).

### C. Ingestion and batch runs

- **05-news-ingestion** (sequence). `run_news_pull.py` → each adapter in
  its real order → external service → `news_filter.filter_and_dedup`
  (bank mention after masking, duplicate check, flags) → `upsert_documents`
  → `data/news_flagged.csv`. Show Google News' month loop and the window
  split when a response is near the cap as a `loop`/`alt`. Cite line
  numbers for the order and the cap.
- **06-batch-pipeline** (sequence). An operator running the RUNBOOK
  pipeline: ingestion, then `preprocess.pipeline`, `aspects.assign` (which
  refreshes the embeddings cache first), `sentiment.score`,
  `aggregate.index`, each reading and writing its tables. Mark that each
  step processes only new work (cite the query that makes it so).

### D. Chatbot

- **07-chatbot-turn** (flowchart). One turn: question → advice guard →
  scope guard → model with tools (loop with its cap) → empty-answer
  replacement → citation check → sentence-id check → figure check →
  answer with any warnings. Decision diamonds for each guard and check;
  where each returns early.
- **08-chatbot-sequence** (sequence). User → Streamlit Chat tab →
  `Conversation.ask` → `answer_turn` → guards → backend → LLM → tool
  executor → tools → SQLite / retrieval → back, then the output checks and
  the state update. Use `alt` for "guard answers" versus "model answers",
  and `loop` for the tool calls.

### E. Labelling and training

- **09-labelling-training** (flowchart). As built (v1): export candidates
  → LLM pre-label → blind test sheet → annotation → agreement → fine-tune
  → evaluate against the three baselines. Planned (v2, DESIGN 16–17):
  LLM aspect classifier run → re-drawn candidates → aspect + sentiment
  labelling → κ for aspect and for sentiment → fine-tune across ≥ 3 seeds
  → evaluate all four text-mining tasks → re-score the corpus. Make clear
  that nothing downstream of annotation has ever run, because nothing is
  labelled.
- **10-plan** (gantt). The five weeks in `docs/PLAN.md` section 5, from
  28 Sep to 1 Nov 2026: one section for people and one for AI work, gates
  as milestones, 1 Nov as the final milestone. Every bar cites its PLAN
  line.

### F. Extended (only after A–E are rendered and committed)

In this order, stopping when time runs out:

- **11-news-filter** (flowchart). The filter's decision order for one
  article, from `ingest/news_filter.py`: already stored → masking of
  broker, venue, research, rating-call and market-note phrases → bank
  mentioned? → duplicate by URL or title similarity? → commentary flag →
  keep. Each exit labelled with the reason written to the flagged CSV.
- **12-index-computation** (flowchart). How one `sentiment_index` row is
  made: windows, the per-source rows plus the blended `ALL` row, source
  weights, the volume floor and the shrinkage formula, from
  `aggregate/index.py`.
- **13-api-chat** (sequence). A client calling `POST /chat` with
  `history`: `Conversation.from_messages` rebuilding state, then the same
  turn as 08, and the response fields.
- **14-chatbot-components** (classDiagram). `LLMBackend` and its four
  implementations; `Conversation`, `TurnResult`, the tool-call tracker;
  the guard functions as a module; tools; with the methods the turn uses.
- **15-conversation-state** (stateDiagram-v2). How the state (banks,
  aspect, window) changes across turns: set from tool calls, from a
  bank named in a question answered by a guard, carried into the next
  turn's system prompt.
- **16-label-lifecycle** (stateDiagram-v2, planned). One candidate row
  under v2: drawn → pre-labelled (train/dev only) → labelled or flagged
  not-about-bank → in the agreement sample or not → used for training or
  held out as test.
- **17-rubric-map** (flowchart). Rubric requirements → the components that
  satisfy them → the course module each draws on, from `docs/PLAN.md`
  section 3. Planned components dashed.
- **18-snapshots** (flowchart). Checkpoint → gzip → verify → checksum in
  the README → shared folder → teammate restores. From RUNBOOK
  "Snapshot the database".
- **19-dashboard-journey** (flowchart). What an investor can do from each
  dashboard tab, from `dashboard/app.py`, including where the Chat tab
  hands off to the chatbot.
- **20-chatbot-evaluation** (flowchart). How `chatbot/run_eval.py` runs
  the gold set and what it checks automatically versus what it leaves to a
  person.

---

## 4. Render script and test

- `scripts/render_diagrams.sh`: for every `docs/diagrams/src/*.mmd`,
  render SVG and PNG into `docs/diagrams/img/` with a white background
  (`-b white`) and a PNG width that reads on an A4 page (`-w 1600`,
  scale 2). Stop with a non-zero exit and the file name on the first
  failure. Idempotent.
- `tests/test_diagrams.py`: for every `docs/diagrams/NN-*.md`, the Mermaid
  block equals `src/NN-*.mmd` exactly; every `.mmd` has a page; every page
  has a sources table. No rendering in the test (no Node dependency in
  pytest).
- Document the script in `docs/RUNBOOK.md` with one short section:
  "Diagrams: edit the `.mmd`, copy it into the page, run the script".

---

## 5. Index and links

- `docs/diagrams/README.md`: a table of every diagram (number, title, type,
  question it answers, core or extended, status: rendered / not reached),
  the legend, how to regenerate, and a **report shortlist**: the five or six
  diagrams the report should use and the section each belongs in
  (suggested: 01, 03, 04, 07 or 08, 09, 10).
- Add one row for `docs/diagrams/README.md` to the documentation table in
  `README.md`, and one line linking it from `docs/spec/technical-spec.md`
  section 1. Change nothing else in existing docs.

---

## 6. Verification pass (mandatory)

1. **Render everything** with the script. Every core diagram must render.
2. **Sources check**: write a small script (commit it under `scripts/`)
   that reads every sources table and confirms each `path:line` exists and
   that line contains its "symbol checked" text. Fix every failure.
3. **Schema check**: confirm every entity and attribute in
   `03-data-model` matches the schema dump from section 1: same tables,
   same columns, same types, same PKs, no extras.
4. **Name check**: every module, function and class name appearing in a
   diagram exists in the code (grep). Every planned element carries a
   DESIGN or PLAN reference.
5. **Look at every PNG** once. Fix clipped labels, overlapping edges and
   unreadable text; split diagrams that don't read at A4 width.
6. Run the full test suite:
   `HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest -q`. It must be green;
   if not, record the output in the run log.
7. Finish the run log: diagrams done, extended ones not reached,
   doc/code disagreements, left out and why, and what needs a human
   (for example: confirm the report shortlist; check that GitHub renders
   the pages after a push).

---

## 7. Deliverables checklist

- [ ] Branch `overnight/diagrams`, logical commits, nothing pushed
- [ ] Schema dump `docs/diagrams/schema-<date>.txt`
- [ ] Core diagrams 01–10: `.mmd`, page with sources table, SVG, PNG
- [ ] Extended diagrams 11–20 as far as time allowed, same form
- [ ] `scripts/render_diagrams.sh`, the sources-check script,
      `tests/test_diagrams.py`, RUNBOOK section
- [ ] `docs/diagrams/README.md` with the index, legend and report shortlist
- [ ] Links added in `README.md` and the technical spec, nothing else changed
- [ ] Verification pass done; tests green; run log in `docs/HANDOFF.md`

If short of time: core A–E rendered and verified beats any extended diagram.
