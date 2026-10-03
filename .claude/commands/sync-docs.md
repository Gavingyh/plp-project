---
description: After a code change, bring the docs that track the code back in line (test counts, diagram line numbers, the API contract, rendered diagrams)
argument-hint: "[what changed, e.g. aggregate/index.py; empty = everything uncommitted]"
---

Sync the docs with the code after: $ARGUMENTS (if empty, everything in `git status`).

1. Tests: run `HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest tests/ -q` and `HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest -q`. If the counts changed, update every place that states them: `README.md`, `docs/STATUS.md`, `docs/RUNBOOK.md`, `docs/spec/technical-spec.md` (`git grep -n "tests in \`tests/\`"` finds them). Report failures; don't hide them by editing tests.
2. Diagrams: run `.venv-plp/bin/python3 docs/diagrams/check_sources.py`. For each failure, find the expected text in the named file; if it occurs once, update the line number in the page's sources table; if it moved into other code or was removed, update the row's symbol and element, or say why the row should go. If a `docs/diagrams/src/*.mmd` file changed, copy it into its page and run `docs/diagrams/render_diagrams.sh NN`, then `pytest -q docs/diagrams/test_diagrams.py`.
3. API: if `api/main.py` or an endpoint docstring changed, regenerate `docs/api/openapi.json` (command in `docs/api-integration.md`) and run `pytest tests/test_api.py -q`.
4. Facts: for each behaviour the change alters, `git grep` the docs (`docs/`, `README.md`, `CLAUDE.md`, `learning/`) for sentences that describe the old behaviour and correct them. The team pages are edited in their scratchpad source and copied to `docs/briefs/` (see CLAUDE.local.md).
5. Report what you changed, file by file, and anything you left for a person. Don't commit.
