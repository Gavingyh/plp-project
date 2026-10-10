# Validation: pretraining and chatbot steps, 2026-10-07
Verdict: fix first

Scope: `main` since b9aaa0f (a00899d) plus local commits d748e1f and 222f753, code and docs. That covers the chatbot step reporting, domain-adaptive pretraining (`train/dapt.py`, `finetune --base-model`), `scripts/source_rows.py`, the `was_corrected` and annotator changes, the recomputed label files and their docs. The chatbot side is sound. The pretraining text-filter lets test text through in several ways, so the adapted models can't support the Fine-tuning lead claim until it is fixed and they are retrained.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED (the claim's 1 Oct models aren't in scope) | the adapted models break its rule that no test text informs training: `build_corpus` keeps a test row split in two, sentences holding or held in test rows, and near-copies the common-word filter hides (tests/test_validate_dapt_progress_*.py, strict xfail) |
| API integrity | PROVEN (not touched) | no diff under `api/` since b9aaa0f; 33 API tests pass |
| Grounded chatbot | PROVEN for this scope | the progress callback never changes a turn (5 cases × no callback, collecting, raising); chatbot suites 1115 passed, 46 expected failures (all recorded limits) |

## Confirmed issues
- Split test sentence reaches pretraining [high] train/dapt.py:80-88: broker research test row 89fa2e20… is two sentences in the rebuilt database, and both are kept
- Holding or held-in test text kept [high] train/dapt.py: 2 kept sentences contain a whole test sentence; 14 are word-for-word parts of 10 test rows (plp_sgx.db)
- Common words removed before overlap [med] train/dapt.py:72-73: 37 kept sentences reach a 0.6 word overlap with a test row once all words count
- Default labels leave broker test rows in [med] train/dapt.py:45,224: `--db` without both labels files keeps them
- The 6 Oct adapted model is used as a base and scored on test [med] data/run/dapt-v2: its text kept 103 near-copies and had no containment check
- Import doubles a rebuilt source [med] scripts/source_rows.py:57-72: no check that the target already holds the source
- Snapshot checksum corrupted [high] README.md:140: f6aac79a2123**98**747…, file is …2123**68**747… (my blanket count replacements, b9aaa0f and d119675)
- Docs overstate the 6 Oct exclusion [high/med] to-do:341, HANDOFF:1219, evidence:34 and 150: "near-copies left out", "No test text informs training"
- Wording and figures [med/low]: the slang count (27 of 1,280) has no committed script; "clear lead" and broker research "lead" sit inside seed noise; HANDOFF compares a training-row rate with the 89% test-row figure (92% is like for like); +0.041 should be +0.042
- Smaller [low]: `describe_call` runs unguarded when there is no callback (an odd tool result would raise; the real tools return numbers); `--base-model` isn't recorded and an MLM checkpoint is accepted; a row missing from llm_prelabels.csv counts as corrected

## Open questions
- None for the owner beyond the upstream items on the to-do; the working tree shows my own uncommitted to-do edit (the new upstream section), made while the agents ran

## Top 3 fixes
1. Pretraining filter: drop any corpus sentence that holds, or is held in, a labelled sentence (letters only, from 30 characters), overlap on all words, and require every labels file when `--db` is given; then retrain both adapted models: done when the five pretraining tests pass and the evidence is re-run.
2. Docs: restore the checksum, correct the exclusion and noise wording, commit the slang count's script: done when an auditor rerun finds nothing medium or worse.
3. source_rows import refuses a source the target already holds; describe_call guarded; base model recorded: done when their tests pass.
