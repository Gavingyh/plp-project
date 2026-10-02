---
description: Multi-agent validation of the PLP project, or of one scope, against success claims S1–S3; writes VALIDATION.md and a dated copy in docs/validation/
argument-hint: "[scope: a path like api/ or docs/model-card.md, a claim like S2, or a feature; empty = whole project]"
---

Validate: $ARGUMENTS (if empty, the whole project).

The success claims are defined in CLAUDE.md, "Success claims": S1 Fine-tuning lead, S2 API integrity, S3 Grounded chatbot. A scope may name a claim by code or by name.

1. Record `git status --short --untracked-files=all`. Name the files in scope, the claims they touch, and whether the scope is code, documentation (`docs/**`, `README.md`, other `*.md`, `docs/briefs/*.html`) or both. Pass only that scope to every agent; a scoped run never reviews or tests outside it.
2. Run the agents for the scope, in parallel:
   - code: `reviewer` on the scope, and `tester` for steps 1–2 of its brief (baseline and claims). When the reviewer returns, send the tester its high and med findings, and low findings that touch S1–S3, for step 3 (SendMessage to the same tester; if that isn't available, a second tester run).
   - documentation: `auditor` on the scope.
3. Give every finding and the tester's table to `triage`.
4. Decide the `judgment` items yourself, reading the code or source where needed. A claim is DISPROVEN if any confirmed finding contradicts it, whatever the tester's checks showed. Consult the advisor, if it is on, when a finding would change the plan.
5. Run `git status --short --untracked-files=all` again. Any change other than new `tests/test_validate_*.py` files, `VALIDATION.md` and the dated copy (ignore `data/logs/plp.log`, which every run appends to) is a failure of this run: report it.
6. If the advisor is on, consult it once more before calling the run done.
7. Write `VALIDATION.md` at the repository root, one screen, in this order, and the same text to `docs/validation/<YYYY-MM-DD>-<scope>.md`, where `<scope>` is a plain name (`api-integrity`, `model-card`), never a claim code:

```
# Validation: <scope>, <date>
Verdict: ship | fix first | rethink

| claim | result | evidence |
|---|---|---|
| S1 Fine-tuning lead | PROVEN / DISPROVEN / UNTESTED | test or command, numbers seen |
| S2 API integrity | … | … |
| S3 Grounded chatbot | … | … |

## Confirmed issues
- R<n> or A<n> [high|med|low] path:line: what is wrong (test or source that proves it)

## Open questions
- one line each

## Top 3 fixes
1. fix: done when <measurable condition>
```

Claims outside the scope are UNTESTED. Do not fix source code or docs, and do not commit, in this command: report only.
