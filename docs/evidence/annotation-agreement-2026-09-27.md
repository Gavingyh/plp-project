# Annotation round, 2026-09-27: agreement and data quality

The first labelled data in the project: 1,300 candidate rows (1,000
train/dev, 300 test) under the 10-aspect taxonomy
([aspect-taxonomy-2026-09-25.md](aspect-taxonomy-2026-09-25.md)), each labelled
for sentiment by two annotators, with disagreements resolved. The team's
sheets were integrated on 2026-09-30; every figure below was recomputed from
them.

Files, in `data/labeled/`:

| file | what it is |
|---|---|
| `agreement/candidates_coder_a.csv`, `_coder_b.csv` | each annotator's labels on the 1,300 candidates (LLM suggestion visible) |
| `agreement/test_blind_coder_a.csv`, `_coder_b.csv` | each annotator's labels on the 300-row blind test sheet |
| `resolved/candidates_resolved.csv` | the candidates after resolving disagreements |
| `test_blind.csv` | the blind sheet after resolving disagreements |
| `candidates.csv` | what training and evaluation read, built by `python -m train.labels` |

Annotator names are not recorded (PLAN D4). One candidate sentence quoted a bank
staff member's email address from an investor-relations PDF; it is redacted in
every sheet.

## Sentiment agreement

```bash
.venv-plp/bin/python3 -m train.agreement --a data/labeled/agreement/test_blind_coder_a.csv --b data/labeled/agreement/test_blind_coder_b.csv
.venv-plp/bin/python3 -m train.agreement --a data/labeled/agreement/candidates_coder_a.csv --b data/labeled/agreement/candidates_coder_b.csv
```

| sheet | pairs compared | observed agreement | Cohen's kappa |
|---|---|---|---|
| blind test sheet | 299 | 0.977 | **0.960** |
| candidates, both splits | 1,277 | 0.952 | **0.926** |

Both clear the 0.6 target. The team's own run reported 302 and 1,350 pairs
compared: `train.agreement` joined duplicated pairs more than once. It now
keeps one copy of a pair listed twice (and refuses if the copies disagree);
kappa barely moved.

## Read the kappa as an upper bound

- **The annotators mostly accepted the LLM's suggestion.** On train/dev rows,
  where the suggestion was shown by design, annotator A's label matched it
  92.2% of the time and annotator B's 95.2%. Two people anchored on the same
  suggestion agree with each other partly because they both agree with it.
- **The test labels were not independent of the suggestion.** Each
  annotator's label on the blind sheet is identical, on all 299 test pairs,
  to the label they gave the same row in the candidates sheet, where the
  suggestion was visible. Labelling the same rows twice, once blind, would
  not normally reproduce every label; the blind sheet appears to have been
  filled from the candidates sheet. The test set is therefore not a blind
  test of the LLM's labels: any model resembling the suggester is favoured.
  Base FinBERT is not that model, and the fine-tuned model learns from these
  labels, so the comparison between them stands; the claim "labelled blind"
  does not.

## Aspect

Aspects were corrected once, before the sentiment pass: the two annotators'
aspect columns are identical, so **aspect agreement was not measured**
(PLAN section 3 asks for kappa on aspect as well as sentiment). The
corrections are large: the seed-centroid aspect was kept on 181 of 1,300
rows (14%). Most corrections moved rows into `retail_banking_sentiment`
(e.g. 80 from management guidance, 72 from dividend policy), the aspect the
centroids under-assign.

## Data problems found and fixed

Correcting aspects turned some pairs of candidate rows into the same
(sentence, aspect):

- 21 pairs appear two or three times, 23 surplus rows in all; no copies
  disagree.
- In 5 of them one copy is in train/dev and the other in test, so the same
  sentence was in both splits. Those 5 train/dev copies are dropped first;
  the other 18 surplus rows are plain duplicates.
- The two resolved sheets disagree on 2 test labels, both rows the
  annotators had disagreed on.

`python -m train.labels` builds `candidates.csv` without them: leaked
train/dev copies dropped (the test split stays frozen), one row per pair,
and test labels from the resolved blind sheet. `train.finetune` and
`train.evaluate` now refuse a file with duplicates or leakage.

| | negative | neutral | positive | total |
|---|---|---|---|---|
| train/dev | 236 | 377 | 365 | 978 |
| test | 39 | 166 | 94 | 299 |

Base FinBERT's label matches the final label on 59% of the 987 rows it
scored.
