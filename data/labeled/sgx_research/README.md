# Broker research round (sgx_research), for the annotators

Two sheets, both guideline v2 (`docs/annotation-guideline.md`): one row is one sentence.
Fill `aspect`, `label`, `not_about_bank` and `annotator` on each row.

- `candidates.csv`, rows with `split = train_dev` (280). `aspect`, `llm_prelabel` and
  `llm_not_about_bank` hold **Claude Sonnet 5.5's suggestions**. They are a starting point to
  correct, not an answer. `original_aspect` is the pipeline's nearest-centroid aspect and
  `base_finbert_label` is the zero-shot baseline, both for reference. Leave `label` empty
  until you have decided.
- `test_blind.csv` (100 rows). **No model output of any kind.** Label it without looking at
  the other sheet, and do not let it change how you label the train rows. The same
  sentences appear in `candidates.csv` with `split = test` and empty columns; ignore those.

Some sentences are damaged by PDF extraction (run-together words, a fragment of an
advertisement, a table row). If you cannot tell what a sentence says, or it is not about the
bank, tick `not_about_bank` (`true`) and move on; the merge drops those rows.

Rows left without a `label` are dropped, never filled from the suggestions.
Method, numbers and the next commands: `docs/evidence/sgx-research-round-2026-10-04.md`.

## LLM labels (silver), kept apart from yours

`claude_test_labels.csv` holds Claude's labels for the 100 test sentences. They are not in
`test_blind.csv` and must not guide how you label it. `silver_candidates.csv` and
`silver_test_blind.csv` are the LLM's labels in the resolved format, for training while the
human labels are pending; their `annotator` column is `claude-sonnet-5-5`.
