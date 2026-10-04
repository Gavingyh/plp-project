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
are in `data/labeled/sgx_research/claude_prelabels/`; the merged table is
`claude_prelabels.csv`. The 280 rows kept after the near-copy filter carry them in the
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
one pass). The answers are in `data/labeled/sgx_research/claude_test_labels.csv` (raw
answers in `claude_test_labels/`): asset quality 26, income and profit 15, NIM 12, dividends
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
`test_blind.csv`, `claude_prelabels.csv`, `claude_prelabels/`).
