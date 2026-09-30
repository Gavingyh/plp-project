# Overnight prompt: model experiments, floor calibration, discovery sweep, chatbot evaluation

You are running unattended overnight in `/Users/gavin/Projects/plp-project`
(the NUS-ISS PLP practice-module project: aspect-based sentiment dashboard,
API and chatbot for DBS, OCBC and UOB; submission 1 Nov 2026). Nobody will
answer questions until the morning. Work through the jobs in order, keep the
run log current, and finish with the verification pass. If you are
interrupted or your context is summarised, resume from the run log.

Four jobs, all local, none of which changes the corpus:

- **A. Fine-tuning experiments.** The fine-tuned model (the rubric's DNN)
  scores macro-F1 0.547 ± 0.013 against base FinBERT's 0.571. Find out
  whether more epochs help and whether the aspect input helps at all.
- **B. Aspect-assignment calibration.** Measure seed-centroid assignment
  against the 1,277 human aspect labels, across similarity floors.
- **C. Discovery sweep.** Re-run clustering on the full current corpus at
  several `min_cluster_size` values.
- **D. Chatbot evaluation.** Re-run the gold set on the two local models
  against the rebuilt 10-aspect database.

The results are evidence for the team to decide on. **Decide nothing
yourself**: don't change `config/aspects.yaml`, don't re-score the corpus,
don't pick the demo model.

---

## 0. Ground rules

### Environment

- Python: `/Users/gavin/Projects/plp-project/.venv-plp/bin/python3` by
  absolute path, never `python3` (a conda Python 3.9 shadows the venv). Set
  `HF_HUB_OFFLINE=1` on every command that loads a model: FinBERT is cached
  and the Hub rate-limits unauthenticated calls.
- GPU is Apple MPS (`config/device.py` picks it). On 2026-09-30 a long MPS
  job once stalled for over an hour with no progress; every long step below
  logs progress, and **if a GPU step shows no progress for 20 minutes, stop
  it, record it in the run log, and move to the next job.**
- Wrap long runs in `caffeinate -i` so the Mac doesn't sleep.
- Ollama serves the local models (`ollama list`: `llama3.1:8b`,
  `llama3.2:3b`, `qwen3:4b`, `gemma3:4b`, `phi4-mini`). Start it with
  `ollama serve` if `ollama ps` fails.
- Nothing goes online except Ollama on localhost.

### Do not touch

- **The database is read-only.** `data/plp.db` may be read (SELECT, PRAGMA,
  and the modules named below, which only read it). No ingestion, no
  `preprocess.*`, `aspects.assign`, `sentiment.score` or `aggregate.index`.
- **No hosted model, ever.** `.env` holds a `GEMINI_API_KEY`, and while it is
  set the chatbot auto-detects Gemini. Always pass `--backend ollama`
  explicitly. The Gemini key is for the live chatbot only, and its free tier
  lets Google read inputs; the gold set includes evidence questions that
  would send Reddit text.
- Don't change `config/aspects.yaml`, `data/labeled/`, `data/snapshots/`,
  `.env`, or the existing models in `models/finbert-absa/seed_{42,1,7}`
  (the 30 Sep results; write new models elsewhere, see job A).
- Code changes are limited to what job A and job B specify, each with
  tests. Documentation edits are limited to new evidence files, the run log,
  and the pointer lines listed in section 5.
- `data/logs/plp.log` changes whenever tests run; it isn't yours, never
  stage it.

### No-hallucination protocol

1. Every number in an evidence file comes from a command run tonight; put
   the command in the file. Round only when reporting, and say how many
   rows each figure is over.
2. **Selection happens on dev or cross-validation, never on the test
   split.** The 299-row test split is frozen: report every configuration's
   test score, but choose between configurations using dev or CV scores
   only, and say which you used.
3. Report negative results plainly. "Fine-tuning still doesn't beat base
   FinBERT" is a result.
4. If you can't establish something, leave it out and list it in the run
   log under "Left out, and why".

### Working conventions

- Work on `main`. Check `git status` first; stage only your own files, by
  path, never `git add -A` or `git add .`. One commit per job, plus one for
  the verification pass. Imperative subject, a body saying why, the
  attribution trailer from your own instructions. **Do not push.**
- Run log at the end of `docs/HANDOFF.md` under a new heading
  "Overnight run log — experiments (<date>)": done, skipped and why,
  results in one line each, left out and why, needs a human. Update it after
  each job. It is your resume point.
- If a job fails twice for the same reason, record it and move on. Jobs are
  independent; one failing never blocks the next.

### Ground truth (verified 2026-09-30, HEAD `72805a4` on `main`)

- Corpus (snapshot `plp-2026-09-30.db.gz`): 28,002 documents, 44,345
  sentences, 281,744 sentence–aspect pairs under the 10-aspect taxonomy,
  514 index rows.
- Labels: `data/labeled/candidates.csv`, 1,277 rows, 978 `train_dev` and
  299 `test`, built by `python -m train.labels` from the resolved sheets.
  `train.finetune` and `train.evaluate` refuse a file with duplicate pairs or
  a sentence in both splits (`train.labels.check_splits`).
- `train/finetune.py`: `run(seed, epochs=4, lr=2e-5, batch_size=16)`,
  sentence-pair input `[CLS] sentence [SEP] aspect [SEP]`, random 85/15
  train/dev split of `train_dev` by seed, class-weighted loss, early stopping
  patience 2 on dev macro-F1, best epoch kept, checkpoints deleted after the
  final model is saved to `models/finbert-absa/seed_<seed>/final`. CLI:
  `--seed --epochs --lr --batch-size`.
- `train/evaluate.py --model-dir <dir>`: base FinBERT zero-shot, VADER,
  TF-IDF + logistic regression, and the fine-tuned model on the test split;
  prints per-class reports and a macro-F1 summary.
- 30 Sep results (`docs/evidence/finetune-2026-09-30.md`), test macro-F1:
  base FinBERT 0.571; fine-tuned, 4 epochs, seeds 42/1/7: 0.534, 0.560,
  0.548 (0.547 ± 0.013); TF-IDF 0.514; VADER 0.427. Dev macro-F1 was still
  rising at epoch 4 for every seed (seed 42: 0.41, 0.58, 0.66, 0.67).
- Timing on this Mac: one 4-epoch seed plus evaluation took about 5.3
  minutes. A saved model is 418 MB.
- `aspects/assign.py`: centroid = mean FinBERT embedding of an aspect's
  `seed_terms`; a sentence gets every aspect whose cosine similarity clears
  `similarity_floor` (0.65), else `other`. At 0.65 sentences average 6.4
  aspects and 4% fall to `other`. Embeddings are cached in
  `data/sentence_embeddings.npz` (`aspects.embed_store.load_for_search`).
- `aspects/compare_taxonomies.py --sweep` measures avg aspects per sentence
  and % other across floors; it reads `config/aspects.yaml` and writes
  nothing.
- `aspects/discover.py --min-cluster-size N`: UMAP (`n_neighbors=15`,
  `n_components=10`, cosine, `random_state=42`) then HDBSCAN; prints a
  report and writes nothing except the embeddings cache (already complete).
  The 25 Sep run on 42,690 sentences: 338 clusters, 65% noise.
- `chatbot/run_eval.py --backend ollama --tag <tag>`, model from
  `OLLAMA_MODEL`: 23 gold-set questions, writes
  `data/eval/chatbot_eval_results_<tag>.jsonl` and `_summary_<tag>.md`.
  A `llama3.2:3b` run took about 4–8 minutes on 26 Sep. The gold set's
  aspects (dividend policy, asset quality, NIM, management guidance) are
  still in the taxonomy. 26 Sep final (3B, 4-aspect database):
  `docs/evidence/chatbot-harness-2026-09-26.md`.

---

## 1. Orientation (do first, ~15 minutes)

Read `docs/HANDOFF.md` (the last three sections), `docs/PLAN.md` sections 3
and 5, `docs/evidence/finetune-2026-09-30.md`,
`docs/evidence/annotation-agreement-2026-09-27.md` and
`docs/evidence/aspect-taxonomy-2026-09-25.md`. Run the full test suite once
(`HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest -q`); it should pass. Start
the run log.

---

## 2. Job A: fine-tuning experiments (~2–3 hours)

### Code (with tests, before any training)

1. `train/finetune.py`:
   - `--no-aspect`: train on the sentence alone (single-segment input), so
     the aspect input can be tested. Record the input format in the saved
     model directory (for example `input_format.json`) so evaluation uses the
     same one.
   - `--out-dir`: where models go, default unchanged. Use it for every run
     tonight so the 30 Sep models are never overwritten.
   - `--folds K --fold I`: train on K-1 folds of `train_dev`, evaluate on
     fold I (stratified by label, seeded), report dev macro-F1. Keep the
     test split out of it entirely.
2. `train/evaluate.py`: read the saved input format and tokenize to match.
3. Tests in `tests/`: the input-format marker round-trips; `--no-aspect`
   tokenizes single-segment; folds partition `train_dev` exactly with no
   overlap and never include a test row. Follow the style of
   `tests/test_finetune_smoke.py`; no network.

### Runs

Write models under `models/experiments-<date>/`. Delete fold models once
their dev score is recorded (they're only for CV); keep the E1 and E2
finals.

| run | configuration | seeds | report |
|---|---|---|---|
| E1 | sentence + aspect, `--epochs 8` | 42, 1, 7 | dev and test macro-F1, per-class F1 |
| E2 | sentence only (`--no-aspect`), epochs = whichever of 4 or 8 had the better **mean dev** macro-F1 (4-epoch dev: see ground truth) | 42, 1, 7 | same |
| E3 | 5-fold CV on `train_dev`, both input formats, the E2 epoch setting | 42 | mean ± sd dev macro-F1 per format |

Evaluate every E1/E2 model with `train.evaluate`. Log progress per run.

### Evidence

`docs/evidence/finetune-experiments-<date>.md`: the commands; a table of
every configuration with dev and test macro-F1 (mean ± sd over seeds) and
per-class F1; the 30 Sep 4-epoch results as the reference row; which
configuration dev/CV selects and its test score; whether the aspect input
helps (E3 is the fairest comparison); the caveats already recorded in the
30 Sep file (test labels not independent of the LLM suggestion, 39 negative
test rows). No recommendation to re-score the corpus: that is PLAN's call.

Commit: code, tests, evidence.

---

## 3. Job B: aspect-assignment calibration (~30 minutes)

### Code (with a test)

A read-only script, `aspects/assignment_eval.py`, that for the 1,277
labelled rows (human aspect in `data/labeled/candidates.csv`) computes, at
floors 0.55 to 0.90 in steps of 0.05, using the cached embeddings and the
centroids exactly as `aspects/assign.py` builds them (import its functions,
don't copy them):

- top-1 accuracy: the most similar centroid is the human aspect (`other`
  when nothing clears the floor);
- recall: the human aspect is among the matched aspects;
- mean aspects matched per sentence, and % falling to `other`;
- the same on the whole corpus for the last two (from the cache).

It writes nothing. A test with a tiny synthetic embedding set checks the
metrics.

### Runs

Run the script, and `python -m aspects.compare_taxonomies --sweep`.

### Evidence

`docs/evidence/aspect-assignment-calibration-<date>.md`: commands, the table
by floor, the per-aspect top-1 confusion at 0.65 (which aspects the
centroids confuse), and what a floor change would and wouldn't fix. Say
plainly if no floor makes centroid assignment accurate: that is the case for
the LLM classifier (DESIGN 16), and this file becomes its baseline.

Commit: script, test, evidence.

---

## 4. Job C: discovery sweep (~1–2 hours)

Run `python -m aspects.discover --min-cluster-size N` for N = 10, 25, 50,
100, on the full current corpus, capturing each report.

- Save each raw report as
  `docs/evidence/aspect-discovery-<date>-mcs<N>.raw.txt` with every email
  address replaced by `[email redacted]` (sample sentences quote
  investor-relations PDFs that name staff).
- `docs/evidence/aspect-discovery-sweep-<date>.md`: per N, clusters, noise
  %, median cluster size, and the largest clusters' top terms; how the
  picture compares with the 25 Sep run (338 clusters, 65% noise); whether
  any N yields clusters that line up with the ten aspects. Don't relabel
  clusters or propose a taxonomy.

Commit: raw reports and the summary.

---

## 5. Job D: chatbot evaluation on the rebuilt database (~1 hour)

```bash
OLLAMA_MODEL=llama3.2:3b HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m chatbot.run_eval --backend ollama --tag llama3.2_3b_10aspects_<date>
OLLAMA_MODEL=llama3.1:8b HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m chatbot.run_eval --backend ollama --tag llama3.1_8b_10aspects_<date>
```

`docs/evidence/chatbot-eval-<date>.md`: for each model, the summary figures
(behaviour questions handled, answered by a guard, correct tool, invented
citations flagged, answers with unverified figures, backend errors), set
against the 26 Sep final (3B) and the 11 Sep 8B figures in
`docs/STATUS.md`. Read every answer that carries an unverified figure or a
citation warning and say, for each, whether it was a real invention or a
false alarm (the 26 Sep file shows how). This informs PLAN decision O3; it
doesn't make it.

Commit: the two result/summary pairs in `data/eval/` and the evidence file.

---

## 6. Verification pass

1. Full test suite green (`HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest -q`).
2. `.venv-plp/bin/python3 docs/diagrams/check_sources.py` exits 0. Your code
   edits move lines the diagram pages cite: where it reports a moved line,
   find the symbol's new line and update only the number in that page's
   sources table. If a cited symbol no longer exists, record it in the run
   log instead of guessing.
3. Every number in the four evidence files traces to a command in that file.
4. `git status` shows only `data/logs/plp.log` uncommitted; `models/` is
   gitignored and must not appear.
5. Pointer lines, one each and nothing more: add the four evidence files to
   the "Status on 30 Sep" paragraph in `docs/PLAN.md` section 5, and add a
   "Superseded by" line under the result table in
   `docs/evidence/finetune-2026-09-30.md` if job A produced new results.
6. Finish the run log: results in one line each, left out and why, and
   needs a human (at least: whether any fine-tuned configuration should
   replace base FinBERT for scoring; whether to change the floor; the O3
   demo model).

---

## 7. Deliverables checklist

- [ ] Job A: code + tests, E1–E3 run, `finetune-experiments-<date>.md`
- [ ] Job B: `aspects/assignment_eval.py` + test, `aspect-assignment-calibration-<date>.md`
- [ ] Job C: four redacted raw reports, `aspect-discovery-sweep-<date>.md`
- [ ] Job D: two eval result/summary pairs, `chatbot-eval-<date>.md`
- [ ] Tests green, diagram sources check clean, one commit per job + verification, nothing pushed
- [ ] Run log in `docs/HANDOFF.md`

If short of time: A, then B, then D, then C.
