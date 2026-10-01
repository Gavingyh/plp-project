# Overnight prompt, night 1: model fixes, LLM aspect classifier, preprocessing dry run, install test

You are running unattended in `/Users/gavin/Projects/plp-project` (NUS-ISS PLP
project: aspect-based sentiment for DBS, OCBC and UOB; submission 1 Nov
2026). Nobody answers questions until morning. Work through the jobs in
order, keep the run log current, finish with the verification pass, and
resume from the run log if interrupted.

Four jobs, all local:

- **J1. Fine-tuning fixes.** The 1 Oct error analysis found the model
  predicts polarity on neutral sentences far too often (48 of 115 test
  errors) and is weakest on Reddit. Test fixes for the train/population
  mismatch, plus cheap model changes.
- **J2. LLM aspect classifier (DESIGN 16).** Build it on local Ollama and
  evaluate it on the 1,277 human aspect labels against seed-centroid
  assignment (top-1 0.413). **Evaluate only: write nothing to the database.**
- **J3. Preprocessing dry run.** A filter for table and garbled fragments;
  report what it would remove. Don't change the database.
- **J4. Clean-copy install test.** Follow the README from a fresh clone.

Decide nothing: no change to `config/aspects.yaml`, no re-scoring, no
database writes, no push.

## 0. Ground rules

Same environment, do-not-touch list, no-hallucination protocol and working
conventions as the 30 Sep experiments run (in git history at `a6bad3d`,
`.project-context/prompt/overnight-experiments.md`). In short:
`/Users/gavin/Projects/plp-project/.venv-plp/bin/python3` by absolute path,
`HF_HUB_OFFLINE=1`, `caffeinate -i` for long runs, MPS GPU one job at a time,
stop any GPU step that makes no progress for 20 minutes; local models only
(the Gemini key is for the live chatbot); `data/plp.db` read-only; don't
touch `data/labeled/`, `data/snapshots/`, `.env`, `config/aspects.yaml` or
existing models (new models under `models/experiments-<date>/`); selection on
dev or CV, never on test; stage own files by path, one commit per job, never
`data/logs/plp.log`; run log at the end of `docs/HANDOFF.md` under
"Overnight run log — night 1 (<date>)"; **don't push**.

### Ground truth (verified 2026-10-01, HEAD `48e1853`)

- Labels: `data/labeled/candidates.csv`, 978 train/dev (neg 236, neu 377,
  pos 365) and 299 test (neg 39, neu 166, pos 94).
- Corpus, 44,345 sentences. Base FinBERT per sentence: negative 4,318
  (9.7%), neutral 31,031 (70.0%), positive 8,996 (20.3%). Source:
  arctic_shift 24,675 (55.6%), earnings 12,254 (27.6%), google_news 5,447,
  cna 1,599, yahoo_news 344, newsapi 26.
- Current best (`docs/evidence/finetune-experiments-2026-09-30.md`): 8
  epochs with aspect, test macro-F1 0.577 ± 0.027 (seeds 42/1/7), 5-fold CV
  dev 0.622 ± 0.028 (seed 42); base FinBERT test 0.571. Error analysis of
  seed 42 on test: neutral predicted polar 48, polar predicted neutral 41;
  accuracy Reddit 0.64 (base FinBERT 0.70), earnings 0.72 (0.73).
- `train/finetune.py`: sentence-pair input with the raw aspect key, padding
  to the longest sentence in the whole set (128 tokens), class-weighted loss
  (`compute_class_weight("balanced")`), options `--epochs --no-aspect
  --out-dir --folds --fold`.
- Seed-centroid aspect top-1 accuracy on the 1,277 labels: 0.413; always
  answering `retail_banking_sentiment`: 0.374
  (`docs/evidence/aspect-assignment-calibration-2026-09-30.md`).
- Ollama: `llama3.1:8b`, `llama3.2:3b`, `qwen3:4b`, `gemma3:4b`,
  `phi4-mini`; the chatbot's Ollama backend calls `POST /api/chat`.

## J1. Fine-tuning fixes

Code (with tests, before training), in `train/finetune.py` and
`train/evaluate.py`:

1. **Dynamic padding** (pad each batch to its own longest sentence). Speed
   only; check on one seed that dev scores match the old padding within
   noise before relying on it.
2. `--class-weights {balanced,none,prior}`: `balanced` is today's behaviour;
   `none` drops weighting; `prior` weights each class by
   corpus-prior ÷ training-prior, the corpus prior being base FinBERT's
   per-sentence distribution above (an estimate; no test data used).
3. `--source-weights`: weight each training row so the source mix matches the
   corpus mix above.
4. `--aspect-text label`: feed the aspect's readable `label` from
   `config/aspects.yaml` instead of the key; record it in the model's
   input-format marker so evaluation matches.
5. `train/evaluate.py --model-dir` accepting several directories: report each
   and their average (mean of softmax probabilities).

Runs (8 epochs, as chosen on 30 Sep), each variant one change from the 30
Sep configuration, compared by **5-fold CV on train/dev, seed 42**: `none`,
`prior`, `--source-weights`, `--aspect-text label`. Then combine the changes
that improved CV, and run that combination as 3 seeds (42, 1, 7) evaluated on
test, with the three-seed average. Report per-class F1 and accuracy by source
for the final configuration as well as macro-F1.

Evidence: `docs/evidence/finetune-fixes-<date>.md`, with commands, a CV table
per variant, the final configuration's test results against the 30 Sep best
and base FinBERT, per-source accuracy, and SHA-256 checksums of any saved
models. Commit.

## J2. LLM aspect classifier

`aspects/llm_classify.py`: for a sentence, ask a local model (default
`llama3.1:8b`, overridable) to choose exactly one aspect key from
`config/aspects.yaml` (the ten plus `other`), using a fixed prompt: role,
task, the schema of aspects with their labels and a one-line definition each
(from `docs/evidence/aspect-taxonomy-2026-09-25.md`), constraints (one key,
nothing else), a few examples, then the sentence. Ask for JSON and validate
it; on an invalid answer retry once, then record `other` and count it. Cache
answers to a gitignored file so a re-run resumes. **No database writes.**

Tests: prompt building, answer parsing and validation, the retry and
fallback, with a fake model; no network.

Run it on the 1,277 labelled sentences (time it). Report top-1 accuracy,
macro-F1 over aspects, per-aspect precision/recall, the confusion matrix,
invalid-answer rate, and seconds per sentence, against seed-centroid top-1
(0.413) and the majority answer (0.374). If time allows, repeat with
`qwen3:4b` and compare. Estimate the time a full-corpus run would take.

Evidence: `docs/evidence/llm-aspect-classifier-<date>.md`. Commit. Applying
it to the corpus is a separate, approved step.

## J3. Preprocessing dry run

A function (in `preprocess/clean.py` or a new module, with tests) that flags
sentences unlikely to carry sentiment: table and figure fragments (low share
of letters, mostly numbers and brackets), extraction debris, and fragments
under 6 words. A dry-run command reports, over the whole corpus and the
labelled set, how many would be flagged by source, with examples, and how
many labelled rows it would have removed, with their labels. Change no data.

Evidence: `docs/evidence/preprocessing-dry-run-<date>.md`. Commit.

## J4. Clean-copy install test

Clone the repository into a temporary directory, follow the README's setup
exactly (new virtual environment, `pip install -r requirements.txt`, restore
the latest snapshot from `data/snapshots/` as the README describes), run the
test suite, and start the API and dashboard on free ports (not 8501, which
another project uses), checking each answers. Record every step that failed
or needed something the README doesn't say. Delete the temporary copy.

Evidence: `docs/evidence/install-test-<date>.md`. Commit; README fixes go in
the run log as suggestions, not edits.

## Verification

Full test suite green; `docs/diagrams/check_sources.py` clean (update moved
line numbers only); every number in the evidence files traced to a command
in the file; `git status` shows only `data/logs/plp.log`; pointer lines to
the four evidence files in `docs/PLAN.md` section 5's status paragraph; run
log finished with "needs a human" (at least: whether the final fine-tuning
configuration should score the corpus; whether to run the LLM classifier on
the full corpus, and the threshold; README fixes).

If short of time: J1, then J2, then J4, then J3.
