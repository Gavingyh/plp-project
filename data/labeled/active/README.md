# Active-learning sheet (built 7 Oct 2026)

`active_sheet.csv` holds 150 unlabelled Reddit sentences about retail banking
or wealth for the team to label. They are the sentences the 1 Oct fine-tuned
models are least sure of, so labelling them should teach the model more per
row than a random sample would.

**Do not label yet.** Labelling waits for the team's decision on the
product-feature guideline (whether describing a product's feature counts as
sentiment). Most of these sentences are about products, so labels made
before that rule is settled would have to be redone.

**Label blind.** Do not open `selection.csv` before or while labelling: it
holds the models' probabilities and the pipeline's aspect, which would anchor
the labels. The sheet itself holds no model output: its `aspect` column is
empty, for the labeller to fill.

## Files

- `active_sheet.csv`: sentence_id, bank, source, text, then aspect, label,
  not_about_bank, annotator and notes (empty, to fill in), and split
  (`train_dev` for every row). Rows are in sentence_id order, which says
  nothing about the models' certainty.
- `selection.csv`: per sentence, the pipeline's top-similarity aspect
  (`pipeline_aspect`, the aspect the models scored it with), the margin
  between the two most likely classes, the mean probability of each class
  (rounded to four places) and the rank by margin in the pool (1 = least
  sure). For analysis after labelling only.

## How it was selected

Command (under half an hour on the Mac GPU; add `--cpu` if the GPU returns
probabilities that don't sum to 1):

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 data/run/upstream/active_select.py
```

1. Pool. `train.dapt.build_corpus` on `data/plp.db` (read-only) left 41,923
   of 44,345 corpus sentences after leaving out the 2,120 sentences in the 58
   labelling files under `data/labeled` and their near-copies (same text,
   one holding the other, or 60% or more shared words). The script repeats
   that filter by sentence id and checks it gives the same sentences. These
   counts were taken before this sheet existed; `train.dapt.labelled_files()`
   now returns 59 files (it includes `active_sheet.csv`), so to reproduce
   them, leave `data/labeled/active/` out of the labels. Of
   these, 23,827 are Reddit (source `arctic_shift`); 16,316 of those have
   `retail_banking_sentiment` (15,680) or `wealth_business` (636) as their
   top-similarity aspect in `sentence_aspects`. By bank: DBS 7,389, UOB
   6,436, OCBC 2,491.
2. Scores. The three 1 Oct fine-tuned models
   (`models/experiments-2026-10-01/label/seed_{1,7,42}/final`, labels
   negative, neutral, positive; input: sentence with the aspect's readable
   label) scored each pool sentence with its pipeline aspect through
   `train.evaluate.finetuned_probs`; the three models' probabilities were
   averaged. No labelled row was scored.
3. Selection. Sentences were sorted by margin (top class minus second
   class), lowest first. Each bank first got its 40 least certain sentences,
   then the rest were filled by lowest margin overall, skipping any sentence
   sharing 60% or more of its words with one already chosen.

## Result (from the run's output and `selection.csv`)

- 150 sentences: DBS 59, UOB 51, OCBC 40. Pipeline aspects: retail banking
  142, wealth 8.
- Margins run from 0.0000 to 0.0213 (median 0.0053). The run also printed
  the pool's median margin, but the pool's scores were not saved, so that
  figure can't be checked and is not given here. The 124 least certain sentences in the pool were all taken; the
  other 26 are OCBC sentences (ranks up to 302) added to reach OCBC's 40.
- The averaged models' most likely class, from `selection.csv`: neutral 84,
  positive 43, negative 23. One row (rank 1) ties neutral and positive at
  0.4835 after rounding; it is counted here as neutral, the first of the
  tied classes in the order negative, neutral, positive (counted as
  positive, the split is 83, 44, 23). The two most likely classes are neutral and positive for
  102 rows, negative and neutral for 46, negative and positive for 2: mostly
  the neutral-or-positive call behind the model's commonest error and the
  product-feature question.
- Sentences run from 4 to 50 words (median 16).

Once labelled, the rows can be merged as extra train/dev data. They never
enter a test split.
