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
- Give run times as rough estimates ("about a day", "under an hour"), not
  exact hours.
- Use absolute dates, never "yesterday" or "next week".
