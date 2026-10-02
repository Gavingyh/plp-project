# Training and evaluation review, 3 Oct 2026

A read-only review of `train/labels.py`, `train/finetune.py`,
`train/evaluate.py`, `train/error_analysis.py` and
`preprocess/export_candidates.py`, looking for anything that would leak test
data or misstate the fine-tuning result. Each finding below was checked
against the files; the fixes have tests.

## The pretrained head was relabelled before fine-tuning

ProsusAI/finbert's classifier head is ordered positive 0, negative 1,
neutral 2 (its `config.json`, `id2label`). `train/finetune.py` loaded it with
`num_labels=3` and the project's order, negative 0, neutral 1, positive 2.
The shapes match, so the pretrained head weights were kept and only the
names changed: every fine-tuned model up to 3 Oct started training with
each output answering for the wrong class, and had to unlearn that on 831
rows. The saved models' configs show the project's order
(`models/experiments-2026-10-01/label/seed_42/final/config.json`).

This biases the fine-tuned scores down, not up, so the reported lead over
base FinBERT (0.604 ± 0.035 against 0.571) is not overstated. It may
explain part of the spread between seeds (seed 7 scored 0.565, below base).

**Fixed:** `train/finetune.py` now trains in the head's own order
(`head_label2id`), with class weights in the same order. Every reader
already maps outputs through the saved `id2label`, so models trained either
way load correctly. **Not done:** retraining the three seeds, which needs
the GPU (busy with the corpus aspect run until 3 Oct) and changes the
reported results; it is a team decision.

## A top-up row is a near-copy of a frozen test sentence

The unmerged top-up sheet holds `99159681c4e7379623c30c90` (CNA: "This
supplementary payout will be paid to about 6,000 employees … S$4 million,"
said UOB.), the same text as test sentence `39034e77ad43e4b157d19d32` (an
earnings PDF) apart from the attribution: word overlap (Jaccard) 0.93. The
leakage checks compared sentence ids only, so merging the labelled sheet
would have put test text into training.

**Fixed:** `train.labels.prepare` drops a top-up row that overlaps a test
sentence by 0.8 or more and reports it (`topup_rows_dropped_as_near_test`);
`check_splits` refuses any such pair in the labelled file. The current
`data/labeled/candidates.csv` passes.

## The margin's dev rows were rebuilt by reshuffling

`train/error_analysis.py` chose each seed's neutral margin on dev rows
rebuilt by reshuffling `candidates.csv` the way training did. That gives the
right rows only while train_dev is unchanged (978 rows); after the top-up
merge it would silently pick the margin on training rows.

**Fixed:** training now saves its exact dev rows (`dev_ids.json`) with each
model, and the error analysis reads them. For the three 1 Oct models, which
predate that file, it refuses to reshuffle once train_dev is not 978 rows.

## The export could overwrite the labels

`preprocess/export_candidates.py` wrote `data/labeled/candidates.csv` with no
check, so one re-run would replace the labelled file and its frozen test
split (recoverable only from git). **Fixed:** it refuses unless given
`--force`.

## Not changed

- The neutral margin is chosen on the same 147 dev rows that early stopping
  used, so its dev gain is optimistic (test is still scored once). Choosing
  it on out-of-fold predictions would be cleaner.
- The test labels match the suggestion model on 266 of 299 rows: known, in
  the decision brief.
- No exact or near-duplicate text (word overlap 0.7 or more) across the
  current splits; Opus labels are read by no training or evaluation code.
