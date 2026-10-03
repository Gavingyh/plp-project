# PLP project: sentiment index for DBS, OCBC and UOB

A practice-module project, due 1 Nov 2026. It turns Reddit posts, CNA news
and the banks' earnings reports into a sentiment index per bank and aspect,
served by a FastAPI API, a Streamlit dashboard and a tool-calling chatbot.

## Start here

- `docs/HANDOFF.md`: the session log and what needs a human. Read the latest
  entries first, and add one at the end of every session.
- `docs/STATUS.md` (what's done), `docs/PLAN.md` (sequence and open
  decisions), `docs/DESIGN.md` (decision log), `docs/RUNBOOK.md` (how to run
  everything).
- `docs/evidence/`: dated outputs behind every claim in the docs.
- `docs/briefs/`: the team to-do page and the decision brief.

## Commands

Always use the project's interpreter and work offline from Hugging Face:

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest tests/ -q     # unit tests
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest -q            # adds the diagram and notebook checks
.venv-plp/bin/python3 docs/diagrams/check_sources.py           # diagram tables still point at the right lines
docs/diagrams/render_diagrams.sh [NN]                          # re-render diagrams after editing docs/diagrams/src/
scripts/start.sh | scripts/stop.sh | scripts/status.sh         # API and dashboard
```

- When tests are added or removed, update the counts in `README.md`,
  `docs/STATUS.md`, `docs/RUNBOOK.md` and `docs/spec/technical-spec.md`.
- When an endpoint or an API docstring changes, regenerate
  `docs/api/openapi.json` (command in `docs/api-integration.md`); a test
  fails otherwise.
- When code lines move, rerun `check_sources.py` and fix the line numbers it
  reports in `docs/diagrams/*.md`.

## Rules

- **The database is read-only for experiments.** Ask before dropping or
  altering a table or deleting rows. Applying LLM aspects, fine-tuned scores
  or NER changes to `data/plp.db` is a team decision; build and test such
  steps on a copy.
- **Stage files by path.** Never `git add -A` or `git add .`. Never stage
  `data/logs/plp.log` (tracked, but changes on every run). The database,
  snapshots, embeddings, model weights, caches and `.env` are gitignored;
  keep them that way. Labels and evaluation results under `data/labeled/`
  and `data/eval/` are tracked.
- **Never edit `.env`.** It holds API keys.
- **No personal names** anywhere in the repository: code, docs, commit
  messages.
- **Ask before adding any paid API.**
- **The Gemini key is for the chatbot backend only.** It is a free tier whose
  inputs may be reviewed by people: never send it personal data or Reddit
  evidence text, and never use it for labelling, classification or judging.
- **CNA articles (`data/cna/`) stay within the team.** Never commit or share
  them.
- **Opus labels never replace the human labels.** They are an additional
  rater, kept in `data/labeled/claude/`.
- **`dashboard/` belongs to a teammate.** Don't edit it; report problems in
  the to-do instead.
- **Push only completed, tested features** to `main`.

## Success claims

The project must prove these; `/validate` reports each as PROVEN, DISPROVEN
or UNTESTED. They come from `docs/spec/functional-spec.md`.

- **Fine-tuning lead** (functional spec 4.4 and 4.5: the fine-tuned
  classifier, sentiment classification, the frozen test split): fine-tuned
  FinBERT scores above base FinBERT on the frozen random test split (299
  rows): three seeds' mean macro-F1
  0.604 ± 0.035 against 0.571. The gap is about one seed standard deviation
  and seed 7 is below base, so it is a modest lead, not a clear win. No test
  row, and no test text, informs training, dev or any choice of threshold.
- **API integrity** (functional spec 4.2: every number fetchable, invalid
  input rejected): the index endpoints (`/sentiment`, `/sentiment/compare`,
  `/sentiment/index`, `/sentiment/trend`, `/sentiment/series`) return the
  stored index unchanged, and every endpoint that takes `bank`, `window` or
  `bucket` rejects a bad value with HTTP 422.
- **Grounded chatbot** (functional spec 4.3: no unretrieved evidence, every
  number matches a tool result): the chatbot never presents evidence or a
  figure that no tool call returned: such answers are flagged, and with
  `CHATBOT_ENFORCE_EVIDENCE=strip` the evidence is removed.

Add a fourth claim, Aspect accuracy (the aspect method against the human
labels), once the team decides the aspect method.

## Validation

- `/validate <scope>` runs the reviewer and tester (code) or the auditor
  (docs), then triage, and writes `VALIDATION.md` plus a copy in
  `docs/validation/`. Run it on a feature before pushing it.
- A `tests/test_validate_*.py` test marked `xfail(strict=True)` is a
  confirmed bug. Remove the marker in the commit that fixes the bug; the
  test then guards against its return.
- The register of known issues is the team to-do page
  (`docs/briefs/team-todo-*.html`) and the decision brief. An issue that is
  in neither is not "known".
- The `examiner` agent grades a report section or the whole submission
  against the module's requirements; use it from mid-October.

## Long-running jobs

- One local-model (Ollama) job at a time: two at once slow each other and
  cause timeouts.
- Run long jobs under `caffeinate -i`, with the Mac on power and the lid
  open.
- Check a job with `kill -0 <pid>`; `pgrep -f` matches the checking command
  itself.
- If the GPU returns probabilities that don't sum to 1, rerun with `--cpu`
  (it happened on 1 Oct under memory pressure).
- The LLM aspect cache is `data/aspect_llm/<model>.<prompt>.jsonl`; the
  `<prompt>` hash changes when an aspect, definition or example changes, so
  a new wording starts a new file. A full corpus run takes about a day.

## Writing docs

- Every number must come from a file or a command run in the session.
  Dated evidence goes in `docs/evidence/<topic>-YYYY-MM-DD.md`. When a claim
  turns out wrong, correct it everywhere it appears.
- Plain English. No AI-style jargon; em dashes only inside regexes and text
  sent to a model.
- No code labels (S1, T4, O3, R2, E1) for claims, requirements, decisions,
  findings, experiments or questions: call each by a short plain name, in
  docs, agent output and test names alike.
- Give run times as rough estimates ("about a day", "under an hour"), not
  exact hours.
- Use absolute dates, never "yesterday" or "next week".
