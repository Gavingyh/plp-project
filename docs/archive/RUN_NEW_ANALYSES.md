# Run the new analyses (instructions for Claude Code)

Open Claude Code in the repo root (`C:\Users\Admin\plp-project-1`) and say:
"Follow docs/RUN_NEW_ANALYSES.md".

## Rules
- Do NOT commit, stage, push or delete anything. Do not edit `data/plp.db` (read only; open with `mode=ro`).
- Do not edit existing source files. If a new script fails, fix only the new file named in the error and say what you changed.
- Use the submitted database and the current `MODEL_VERSION` in `config/model_version.py`. If `data/plp.db` is not the submitted one, stop and ask.
- Every number you report must come from a command's output. Never write a number from memory.
- Run steps in order. After each step write one line: command, pass or fail, key result. Keep full output in the files named below.

## What was added (all new files, already in the repo)
`scripts/term_analysis.py`, `aspects/topic_model.py`, `aggregate/uncertainty.py`, `aggregate/price_check.py`,
`chatbot/summarise.py`, `train/baselines_classical.py`, `train/bilstm_baseline.py`, `aspects/extract_terms.py`,
`tests/test_new_analyses.py`, `docs/report/conversation-design.md`, `docs/report/additions-draft.md`.

## Step 0: environment
1. `python --version`; check `pip list` for torch (and `torch.cuda.is_available()`), scikit-learn, pandas, matplotlib, yfinance, requests.
   Install anything missing with pip (yfinance only if missing).
2. `ollama list`. Confirm the model named in `config/aspects.yaml` (`llm_model`, expected llama3.1:8b) is present; if Ollama is not running, tell me and skip Step 5.
3. Confirm `data/plp.db` exists and is not empty. Print row counts of sentences and aspect_sentiment for the current MODEL_VERSION. If the current model version has no rows, stop and tell me.

## Step 1: tests
`python -m pytest tests/test_new_analyses.py -q` then the full suite `python -m pytest -q`.
Report the pass count. Do not change test counts in docs; I will run /sync-docs.

## Step 2: no-GPU analyses (output under data/eval/)
```
python -m train.baselines_classical
python -m aggregate.uncertainty --bootstrap 2000 --unit document
python -m aggregate.uncertainty --bootstrap 2000 --unit sentence
python -m aspects.topic_model --k 11 --methods nmf lda
python -m scripts.term_analysis --charts
```
Outputs: `data/eval/baselines/`, `data/eval/uncertainty/`, `data/eval/topic_model/`, `data/eval/term_analysis/`.
Check the uncertainty run's "computed vs index formula vs stored" check passes for the current model version; if the stored table differs, report it (the index may need rebuilding by me).

## Step 3: neural baselines (GPU)
```
python -m train.bilstm_baseline --arch bilstm
python -m train.bilstm_baseline --arch cnn
```
Optional if I have a GloVe file at a path I give you: add `--glove <path>`.
Outputs in `data/eval/baselines/`. The test split is scored once per seed; do not rerun to improve scores.

## Step 4: share prices
1. Ask me for real results-release dates (bank, date) and create `data/prices/earnings_dates.csv` with columns `bank,date`.
   Without it, the monthly analysis still runs and the event study is skipped; say so.
2. `python -m aggregate.price_check --fetch`. If Yahoo is unreachable, say so and stop this step.
Output: `data/eval/price_check/`. Report each correlation with its interval and p-value, and state plainly if the interval includes zero.

## Step 5: Ollama jobs
```
python -m chatbot.summarise --all-aspects --limit 3     # try first; then without --limit
python -m aspects.extract_terms --sample 300 --export-gold data/eval/terms/gold_sheet.csv
python -m aspects.extract_terms --sample 3000 --summary
```
- Summaries: report points kept vs dropped by the checks. Outputs `data/eval/summaries/` (`rating_sheet.csv` is for two people to fill in).
- Gold sheet: for people to annotate (`gold_pairs`: `aspect term => opinion term ; ...`, plus `annotator`). Do NOT fill it yourself.
  After it is filled: `python -m aspects.extract_terms --evaluate data/eval/terms/gold_sheet.csv`.

## Step 6: paired comparison with FinBERT
Find the fine-tuned model's test predictions (see `train/evaluate.py` output for the current MODEL_VERSION). If they can be loaded as a CSV with `sentence_id` and a predicted label, compute
`train.baselines_classical.paired_bootstrap(y_true, finbert_pred, best_baseline_pred)` on the same test rows and report the difference and interval. If predictions are not saved, say how to produce them; do not retrain.

## Step 7: fill the report draft
Open `docs/report/additions-draft.md`. For each section A to G, replace each `<...>` with the value from the outputs above, keeping the wording cautions
(no "predicts prices" unless every tested lag's interval excludes zero; no "FinBERT is better" if the paired interval includes zero).
Leave a `<...>` in place wherever a number is not yet available (rating sheet or gold sheet unfilled) and list them.
Write the result to `docs/report/additions-filled.md`, not over the draft.

## Final message to me
1. A table of steps: done / skipped / failed, with the reason.
2. The key numbers, each with the file it came from.
3. The list of things I must do by hand: fill the rating sheet (two raters), annotate the gold sheet, supply earnings dates, replace placeholder dialogues in `conversation-design.md` with a real transcript, run /sync-docs.
4. Anything that looked wrong (stale index, mismatched counts, errors fixed in new files).
