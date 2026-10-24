# Domain-adaptive pretraining experiment (started 2026-10-06)

Owner's request: try idea 5 (domain-adaptive pretraining) after slang was measured as rare (27 of 1,280 labelled train/dev rows).
Branch `experiment/dapt` (commit 240144b: train/dapt.py, finetune --base-model, tests/test_dapt.py). Not merged, not pushed.

Run: `caffeinate -i data/run/dapt/run_dapt_experiment.sh` (resumable: skips finished pretraining and finished CV rows).
- progress: data/run/dapt/progress.log; CV scores: data/run/dapt/cv_results.jsonl; test: data/run/dapt/test_results.json; done marker data/run/dapt/done
- outputs: models/dapt-2026-10-06 (pretrained), models/experiments-2026-10-06/dapt/seed_*/final (final models)

Afterwards: compare paired CV dev macro-F1 (15 folds, FinBERT vs adapted, same folds) like docs/evidence/noise-floor-cv-2026-10-02.md; report the three final models' test macro-F1 against the retrained baseline 0.621 +/- 0.027 (docs/evidence/retrain-2026-10-04.md); write docs/evidence/dapt-2026-10-06.md; adoption is a team decision (re-score week 12-18 Oct). The test split is scored once, only for the final models.

- 6 Oct about 21:00: the first full run was stopped (steps slowed to 100 s under memory pressure); fixed in 1f3fbdf (64-token cap, fixed batch shapes, half-batches, cache release; memory flat at 1.30 GB). Docker Desktop stopped at the owner's request. Restarted as background shell bhen08631: about 1.6 s a step, pretraining about 1.8 h, then 30 CV runs and the final test scoring.

## Second run: with broker research (started 7 Oct 13:04)
`caffeinate -i data/run/dapt-v2/run.sh` (resumable). Pretraining on data/run/sgx/plp_sgx.db (corpus + rebuilt broker research), labelled sentences of data/labeled/candidates.csv and data/labeled/combined/candidates.csv left out with near-copies (word overlap 0.6): 42,923 sentences -> models/dapt-2026-10-07. Then 5-fold CV on the combined labels, seeds 42 1 7, bases finbert / v1 (models/dapt-2026-10-06) / v2, paired (data/run/dapt-v2/cv_results.jsonl); final v2 models models/experiments-2026-10-07/dapt2-combined; scores on the three test scopes in data/run/dapt-v2/scores.json beside this morning's finbert-combined and dapt-combined. Expected to finish around 23:00. Then add a section to docs/evidence/dapt-2026-10-06.md and the to-do scoring item.
Code: d748e1f (near-copy exclusion, --db/--labels), caveat 222f753. Not pushed yet.

## 7 Oct afternoon: paused, filter fixed
The dapt-v2 run was paused by the owner after its pretraining finished (14:55; models/dapt-2026-10-07 exists but was built with the old, leaky filter). A validation found the filter let test text through; fixed in b6d6e74 (NearCopies: held/holding from 30 letters, 60% of all words, every labelling sheet by default). Both adapted models must be pretrained again before adoption. The owner wants the upstream to-do items ("Clear before any more retraining or evaluation") settled before any more retraining or evaluation. Do not resume data/run/dapt-v2/run.sh as is: delete models/dapt-2026-10-07 first so pretraining reruns with the fixed filter.
