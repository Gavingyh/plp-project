# Broker research as a fourth labelled source: extraction, sampling, suggestions

Run 2026-10-04 on the Windows PC (RTX 5070 Ti). The 25 PDFs in `data/sgx_research/`
(12 downloaded from SGX's research listing, 13 printed from sginvestors.io pages by
the user) were turned into a corpus source called `sgx_research` and a labelling round
drawn from it, by the same method as the Reddit, news and earnings rounds. **No model
has been trained yet.** The labels are an LLM's suggestions until the annotators have
corrected them (below), and the training run waits for that, as agreed.

## What the source is

Broker and sell-side analyst notes on DBS, OCBC and UOB (DBS Group Research, CGSI, and
RHB, Maybank, UOB Kay Hian and others via sginvestors.io), 2024-11 to 2026-09. The voice
is an analyst's, not a customer's or management's: "Maintain HOLD, TP SGD42.50", "we
remain watchful of asset quality risks". The guideline already covers it ("quoted analyst
opinion: label the analyst's stated view").

## Extraction (`ingest/sgx_research_extract.py`)

The PDFs are three different things, and a plain text dump of any of them was unusable:

| family | files | problem | handling |
|---|---|---|---|
| text-layer broker report | 5 DBS/CGSI | two-column pages: main text interleaved with the sidebar; two files print every capital twice ("SSIINNGGAAPPOORREE"); a long disclaimer whose "DBS Bank Ltd" is the publisher | page split at its column gutter and each column read in turn; doubled capitals collapsed; everything from the disclaimer heading onward dropped |
| scanned report | 7 DBS | no text layer at all (image pages) | rendered and read with RapidOCR; OCR drops spaces in tight text ("Refertoimportantdisclosures"), repaired by splitting lowercase runs of 12+ letters (`wordninja`) |
| sginvestors.io printout | 13 | page wrapped in site navigation and ads, some printed over the body text | the article body is one font at one indent and the ads are not, so lines are kept by font and indent; end of article cut at the site's "excerpt" and "related reports" markers |

Other decisions, each from a file that went wrong without it:

- `UOB Kay Hian` is a broker, not UOB: the name is neutralised before bank detection (it
  would otherwise be read as UOB). Reports whose subject is not a bank (the SGX Ltd and
  UOB-Kay Hian Holdings updates were downloaded and then removed from the folder) are
  skipped by filename if they come back.
- A report's subject bank comes from its filename or its web headline; a leading `DBS - ` in
  a DBS Group Research filename is the publisher. Sector reports are `MULTI` and need an
  explicit bank name in each sentence, as for CNA; a single-bank report passes its bank to
  sentences that do not name it, as earnings does.
- Publication dates: the web headline's date; else the filename's `DDMMYY`; but SGX's
  `070827 DBS - United Overseas Bank ...` decodes to 2027, so a filename date more than 45
  days from the PDF's own creation date is discarded (that file is 2026-08-07).
- The first extraction was not good enough and was redone: 817 sentences, of which a large
  share was disclaimer text and chart legends. Fixes (cut the disclaimer after repairing
  doubled capitals, drop emails/ads/share buttons, tolerate a few full-width lines when
  finding the column gutter) gave 641 sentences.

Result: 25 documents and 641 sentences (DBS 151, OCBC 251, UOB 239). The pipeline dropped
462 more for not naming a bank in sector reports, 39 as exact-text duplicates and 35 as
too short. OCBC and UOB dominate because most of the single-bank reports are on them.

## Pipeline

`preprocess.pipeline`, `aspects.assign` and `sentiment.score` were run on the new source
only (`--sources sgx_research` added to the first and last; assignment only processes
sentences it has not seen). Base FinBERT on the 641 sentences: 321 positive, 185 neutral,
135 negative (50% / 29% / 21%, against about 20% positive across the corpus), so analyst
text reads far more polar than Reddit. `data/plp.db` gained 25 documents, 641 sentences,
4,533 aspect assignments and 4,533 base-FinBERT scores. `aggregate.index` was **not**
re-run, so the dashboard's numbers are unchanged until someone decides to; its source
weight for `sgx_research` is 1.0, the same as earnings. The first `aspects.assign` also
built the embedding cache (`data/sentence_embeddings.npz`, 43,331 vectors, not in git),
which did not exist on this machine.

## The labelling round (`preprocess/export_source_round.py`)

The sampling design of `export_candidates.py`, on this source alone and written to its own
folder so no existing labelled file is touched:

- Plain debris is excluded first (45 too short, 18 run-ons, 15 legal text or chart legends):
  563 usable sentences.
- **Test: 100 sentences drawn at random first**, before any model screening, on a blind
  sheet (`test_blind.csv`) with no base FinBERT, no suggestion and not even the pipeline's
  aspect. DBS 23, OCBC 38, UOB 39.
- **Train/dev: 280 sentences**, stratified on base FinBERT's own call (98 positive, 94
  neutral, 88 negative), with the pipeline's aspect and base FinBERT shown, as in earlier
  rounds. 300 were drawn; 20 were dropped, not refilled: 10 are near-copies of a test
  sentence and 10 are near-copies of another train row. Broker reports repeat themselves
  with small edits ("...in an escalating trade war environment given the huge and broad US
  tariffs"), which the exact-text dedup misses, and a near-copy across the split would leak
  the answer. The train side is dropped, never the test side (word-set Jaccard 0.6 against
  test, 0.8 within train).
- One row is one sentence (guideline v2): the annotator sets the aspect, the sentiment and
  `not_about_bank`.

Per source, for scale: earlier rounds labelled Reddit 617, earnings 477, Google News 166.
This source's pool is 563 usable sentences, so 380 labelled is 67% of it. Increasing
`--train-dev` extends the sheet; the test draw does not change.

## The suggestions (`train/source_round.py prelabel`)

Claude Sonnet 5.5 (`claude-sonnet-5-5`, in Claude Code) read each of the 300 train/dev
sentences and gave an aspect, a `not_about_bank` flag and a sentiment, applying
`docs/annotation-guideline.md`. It saw only the sentence text and the bank name: not base
FinBERT, not the pipeline's aspect, not the source file. One rater, one pass, aspect and
sentiment together (the Opus round used two blind passes). Raw answers and the row order
are in `data/labeled/sgx_research/llm_prelabels/`; the merged table is
`llm_prelabels.csv`. The 280 rows kept after the near-copy filter carry them in the
sheet: aspect (asset quality 59, management guidance 41, income and profit 38, NIM 35,
dividends 30, investor/stock 27, other 16, macro 14, wealth 12, capital 7, retail 1),
sentiment (111 positive, 110 neutral, 59 negative), 9 flagged `not_about_bank` (disclaimer
boilerplate, a rating legend, a table row).

For orientation only, not a measure of quality (there are no human labels yet):

- Claude's sentiment agrees with base FinBERT on 59% of the 280 rows; most of the gap is
  neutral and positive sentences FinBERT calls negative, and facts with a clear valence that
  the guideline says are not neutral.
- Claude's aspect equals the pipeline's top-ranked aspect on 22% of rows. The nearest-
  centroid assignment is a weak aspect signal, which is why the aspect is now a human
  decision.

**The test rows have no suggestion of any kind.** `prelabel` refuses a sheet whose test
rows carry model output. Nothing in the code turns a suggestion into a label:
`merge` reads only the annotators' columns and drops unfilled rows.

## Update: Claude's labels for the test rows, and the silver files

Asked to label the whole dataset, Claude Sonnet 5.5 also labelled the 100 blind test
sentences, the same way as the train rows (text and bank only; aspect, flag, sentiment in
one pass). The answers are in `data/labeled/sgx_research/llm_test_labels.csv` (raw
answers in `llm_test_labels/`): asset quality 26, income and profit 15, NIM 12, dividends
11, management guidance 10, investor/stock 10, wealth 7, other 6, macro 3; 41 positive, 31
neutral, 28 negative; 4 flagged `not_about_bank`.

**This departs from the design, deliberately and visibly.** The test split is meant to be
labelled by people without model output (DESIGN decision 22, guideline "The test split is
frozen"). So the LLM's test labels are kept in their own file: `test_blind.csv`, the sheet
the annotators fill in, is untouched, and `label-test` never writes to it.

`train.source_round silver` turns the LLM's labels (the 280 train suggestions and the 100
test labels) into resolved files with the prefix `silver_`, dropping the 13 flagged rows
(271 train/dev and 96 test remain), and `combine --prefix silver` adds them to the original
round: `data/labeled/combined_silver/candidates.csv`, 1,249 train/dev and 395 test rows
(original 978 and 299, plus 271 and 96), through the same leakage check. Every SGX row in
it has `annotator = claude-sonnet-5-5`, so it cannot pass as human gold.

```bash
python -m train.finetune --labels data/labeled/combined_silver/candidates.csv --seed 42 --epochs 8 --aspect-text label --out-dir models/sgx_silver/label
python -m train.evaluate --labels data/labeled/combined_silver/candidates.csv --model-dir models/sgx_silver/label/seed_42/final
```

Read any number from that run as a silver result: the SGX train rows teach the model an
LLM's reading of analyst text, and the SGX test rows measure agreement with the same LLM,
not with people. It can say whether the pipeline works and how the model behaves on this
register; it cannot replace the human-labelled figure. The human files
(`resolved_candidates.csv`, `resolved_test_blind.csv`, `data/labeled/combined/`) are produced
only by `merge` and `combine` from the annotators' sheets.

The original resolved sheet had 1,300 rows before `train.labels.prepare` removed 5 train
rows that leaked into test and 18 duplicate pairs (1,277 left), which is the "around 1,300"
of the first round.

## What is waiting for people

1. Annotators correct `data/labeled/sgx_research/candidates.csv` (the 280 `train_dev`
   rows: `aspect`, `label`, `not_about_bank`, `annotator`) and fill in
   `data/labeled/sgx_research/test_blind.csv` (100 rows: `aspect`, `label`,
   `not_about_bank`, `annotator`). Two annotators on an overlapping ~100-row sample
   would give agreement figures; `train.agreement` measures sentiment only.
2. Then, in order:

```bash
python -m train.source_round merge --round data/labeled/sgx_research \
    --candidates <filled candidates.csv> --blind <filled test_blind.csv>
python -m train.source_round combine --round data/labeled/sgx_research
# builds data/labeled/combined/candidates.csv (original rounds + SGX), leak-checked; originals untouched
python -m train.finetune --labels data/labeled/combined/candidates.csv --seed 42 --epochs 8 --aspect-text label --out-dir models/sgx/label
python -m train.evaluate --labels data/labeled/combined/candidates.csv --model-dir models/sgx/label/seed_42/final
```

Training on this PC is quick: one epoch of the current set took 3.7 s on the RTX 5070 Ti
(the 8-epoch MacBook runs took 6 minutes), checked with a throwaway model on the existing
labels. Run three seeds as in the 1 Oct report.

## How to read the result when it comes

Adding the SGX test rows to the test split (the decision taken) makes the combined test set
about 399 rows, so its macro-F1 is not comparable with the 299-row figures in the earlier
reports. To keep the comparison, also score the new model on the original test set
(`train.evaluate --model-dir <new model>` with the default labels) and on the SGX test rows
alone; `train.evaluate` already prints accuracy by source. The SGX source is also
unlike the others in register, polarity (50% base-positive) and bank mix (DBS 23% of
test), so a result that moves on Reddit but not on SGX, or the reverse, is information
about the data, not noise.

## Caveats

- The suggestions are one model's reading and will share its mistakes; they are not
  checked against anyone. The annotators must not treat them as the answer (the
  earlier anchoring finding applies: human labels matched the suggestion on 91.6% of rows
  in the 27 Sep round).
- The sentences are extracted from PDFs, and some are still damaged: 7 of the 25 are OCR
  output with occasional run-together words, and printed web pages have a few lines where
  an ad overprinted the text. Annotators can flag these `not_about_bank`; the merge then
  drops them. The 100 test rows were not cleaned beyond the rules above, deliberately.
- Broker reports are third-party research. The 12 SGX files were downloaded from
  `api2.sgx.com` links the user supplied; the 13 web pages were printed by the user from
  sginvestors.io, which blocks automated access (the project decided not to defeat that).
  The PDFs and `plp.db` are not committed; check the sources' terms before the PDFs or
  extracted text leave the project.
- The GenAI declaration should list this use: the suggestions above, and the extraction
  and pipeline code written in a Claude Code session.
- `tests/test_scripts.py` fails 8 tests on this machine (it shells out to `bash`, which
  resolves to WSL here). Unrelated to this work; the other 463 tests pass.

## Environment changes on this PC

CUDA build of torch 2.14.0 (`+cu130`; the CUDA 12.8 index stops at 2.11 for this Python)
replacing the CPU build, `rapidocr-onnxruntime`, `wordninja`, the spaCy model
`en_core_web_sm`. Windows opens text files as GBK by default, which broke reading
`config/aspects.yaml`; the three places on the training path now pass `encoding="utf-8"`.

## Files

`ingest/sgx_research_extract.py`, `preprocess/export_source_round.py`,
`train/source_round.py`, `--sources` on `preprocess.pipeline` and `sentiment.score`,
`--labels` on `train.finetune` and `train.evaluate`, `tests/test_sgx_research_extract.py`,
`tests/test_source_round.py`, and `data/labeled/sgx_research/` (`candidates.csv`,
`test_blind.csv`, `llm_prelabels.csv`, `llm_prelabels/`).

## Retrain with the human-reviewed SGX sheet (5 Oct)

The annotator's sheet (`data/labeled/sgx_research/candidates.csv`, annotator A, all 280
train/dev rows) came back. Three things were repaired first:

- The sheet had been saved in a non-UTF-8 encoding, which replaced curly quotes, dashes and
  bullets in 30 sentences with `?€?`. The text was restored from the database (it is never
  an annotator's column); the file as saved is kept as
  `candidates.edited-2026-10-04.bak.csv` (not in git).
- The annotator had typed the sentiment into the `llm_prelabel` column as well as `label`.
  `llm_prelabel` was restored to the model's original suggestion
  (`llm_prelabels.csv`). Against those suggestions, the annotator's sentiment differs on
  17 of 280 rows (93.9% agreement) and the aspect on 14 (95.0%).
- `not_about_bank` was set to false on all 280 rows, as the annotator confirmed every sentence
  is about a bank. The 9 rows the model had flagged (disclaimer text, a rating legend, a table
  row) are therefore in the training data.

The SGX test sheet (`test_blind.csv`) is still empty, so the retrain uses no SGX test rows
and **has not been evaluated**: the annotator is labelling the test sheet first.

Code: the retrain ran on this branch after merging `origin/main`, so it uses the fixed
training code (the 3 Oct head-order fix; every model before it started with each output
answering for the wrong class). Conflicts in `aggregate/index.py`, `sentiment/score.py`,
`train/evaluate.py` and `train/finetune.py` were resolved by keeping upstream's settings and
both sides' flags. `sgx_research` is in `config/sources.yaml` with weight 1.0 and
`team_only: true`, which withholds its text from hosted chatbot backends the way CNA's is
(third-party research; the two config tests were updated to say so; reverse it if the team
decides otherwise).

```bash
python -m train.source_round merge --round data/labeled/sgx_research --candidates data/labeled/sgx_research/candidates.csv --blind data/labeled/sgx_research/test_blind.csv
python -m train.source_round combine --round data/labeled/sgx_research
for s in 42 1 7; do python -m train.finetune --seed $s --epochs 8 --aspect-text label     --labels data/labeled/combined/candidates.csv --out-dir models/sgx-retrain/label; done
```

Training data (`data/labeled/combined/candidates.csv`): 1,258 train/dev rows (the original 978
plus 280 SGX) and the original 299 test rows (Reddit 184, earnings 79, Google News 34, Yahoo
News 2). None of the 280 SGX rows is a near-copy (word-set Jaccard 0.6) of an original test
sentence. The configuration is unchanged from 1 Oct and 4 Oct (8 epochs at most, early stopping
with patience 2, learning rate 2e-5, batch 16, readable aspect label, plain cross-entropy). The
85/15 train/dev split is redrawn from the larger pool, so dev rows differ from the earlier
runs'. On the RTX 5070 Ti each seed took 14 to 39 seconds.

Dev macro-F1 of the best epoch (189 dev rows; not comparable with the test figures, and not
comparable across seeds since each seed's dev rows differ): seed 42 0.669 (ran all 8 epochs),
seed 1 0.635 (best epoch 1, stopped after 3), seed 7 0.655 (best epoch 4, stopped after 6).

| model | SHA-256 of `model.safetensors` |
|---|---|
| `models/sgx-retrain/label/seed_42/final` | `039fba7d3804f0c9e8abc09d58056c2668b5787dc01c6138872e5e65719473a8` |
| `models/sgx-retrain/label/seed_1/final` | `365de445f843938906be45d2e3196f82d0a52a6487f4a8ae54f5aac8ab19180b` |
| `models/sgx-retrain/label/seed_7/final` | `31355209ec0efd8ea0627fe527a129ca8ac26aee123969deaeb95b77d047e8f9` |

**Next:** when the SGX test rows are labelled, `merge` and `combine` again, then
`train.evaluate --labels data/labeled/combined/candidates.csv --model-dir models/sgx-retrain/label/seed_{42,1,7}/final`
for the combined test split, and the default labels for the original 299 rows alone, to compare
with the 1 Oct and 4 Oct models. Nothing is adopted: the database and reported results still use
the 1 Oct models.

## Evaluation with the human-labelled SGX test rows (6 Oct)

The annotator filled the blind test sheet (100 rows, no model output shown); `annotator` was left
empty. The sheet had again been saved in the Windows encoding, so 8 texts were restored from the
database (the edited file is kept as `test_blind.edited-2026-10-06.bak.csv`, not in git).
Against the model's labels for the same rows (kept in a separate file, never shown), the
annotator's sentiment agrees on 77.0% and the aspect on 65.0%. On the train rows, where the model's
suggestion was visible, the figures were 93.9% and 95.0%: the visible suggestion is most of the
difference, the anchoring the 27 Sep round found. These blind labels are the independent ones.

`merge` and `combine` rebuilt the combined file, written to `data/labeled/combined_sgx_test/`
because `data/labeled/combined/candidates.csv` was locked by another program (once it was closed,
`combine` rebuilt `data/labeled/combined/candidates.csv`, byte-identical to this copy, so either
path gives the same file; the scoring above used this one): 1,258 train/dev rows
and **399 test rows (the original 299 plus the 100 SGX)**; the leak check passes and no SGX test row
is a near-copy (Jaccard 0.6) of a train row. SGX test labels: 42 positive, 35 neutral, 23 negative
(DBS 23, OCBC 38, UOB 39).

One scoring run per configuration, chosen before any test score existed (the 1 Oct configuration,
unchanged); nothing was selected on these numbers. Macro-F1, `train.evaluate`; seeds in the order
42 / 1 / 7; "old" are the 1 Oct models from the Hugging Face repo (trained without SGX data, and
with the head-order flaw), "new" the three retrained seeds:

| test split | base FinBERT | old seeds (mean) | old, 3 averaged | new seeds (mean) | new, 3 averaged |
|---|---|---|---|---|---|
| original 299 | 0.571 | 0.630 / 0.617 / 0.565 (0.604) | 0.615 | 0.631 / 0.589 / 0.611 (0.610) | 0.631 |
| SGX 100 | 0.687 | 0.540 / 0.643 / 0.577 (0.587) | 0.596 | 0.696 / 0.665 / 0.687 (0.683) | **0.735** |
| combined 399 | 0.648 | 0.618 / 0.636 / 0.579 (0.611) | 0.620 | 0.665 / 0.622 / 0.647 (0.645) | **0.674** |

The old models' original-299 scores reproduce the 1 Oct report (0.630, 0.617, 0.565; average 0.615).
Accuracy of the new averaged model on the combined split is 0.71 (base 0.70), and on the SGX rows
0.74 (base 0.69).

What it shows:

1. **The SGX training rows help on analyst text.** On the SGX test rows the averaged model goes from
   0.596 (trained without SGX) to 0.735, and the seed mean from 0.587 to 0.683. That is the
   in-register effect one would expect from 280 in-register rows.
2. **They do not move the original 299.** The seed mean is 0.610 against 0.604 and the average 0.631
   against 0.615, differences well inside the seed-to-seed spread (about 0.03). The team's 4 Oct
   retrain without SGX data scored a seed mean of 0.621 and an average of 0.634
   ([retrain-2026-10-04.md](retrain-2026-10-04.md), upstream), so there is no sign of harm and no sign
   of a gain on the other sources.
3. **Base FinBERT is strong on analyst text** (0.687 on the SGX rows, accuracy 0.69): the report
   register is formal and polar, closer to what FinBERT was pretrained on. The new individual seeds
   only match it (0.683 mean); the averaged model is ahead (0.735).

Caveats: the SGX split is 100 sentences (23 DBS), so a difference of several points of macro-F1 is
inside the noise (one sentence moves a class's F1 by about 0.02 to 0.03), and the averaged-model gain
over base on SGX (+0.05) is the least certain figure here. The new models' dev rows differ from the
old ones'. Three seeds cannot separate the effect of the head-order fix from the effect of the added
data; the 4 Oct retrain isolates the fix, and the comparison in item 2 is across runs on different
machines. The 9 junk rows the model had flagged are in the training data.

Every other metric (precision, recall and F1 per class, macro and weighted averages, accuracy by source, and the error breakdown) is in [sgx-research-evaluation-2026-10-06.md](sgx-research-evaluation-2026-10-06.md).
