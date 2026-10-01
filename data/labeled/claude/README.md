# Opus 5.5 labeller

An additional rater for the 27 Sep labelled round (DESIGN decision 22). These
files never replace the human labels in `../candidates.csv`.
Results: `docs/evidence/opus-labeller-2026-10-01.md`.

| file | what |
|---|---|
| `opus_labels.csv` | one row per sentence: `opus_aspect`, `opus_not_about_bank`, `opus_label` |
| `review_aspect.csv` | sentences where Opus and the human aspect differ; `decision` for a reviewer to fill |
| `review_sentiment.csv` | the same for sentiment |
| `instructions_aspect.md`, `instructions_sentiment.md` | what each rater was given (the annotation guideline, quoted) |
| `pilot/`, `batches/` | each rater's input and raw answers |

```bash
.venv-plp/bin/python3 -m train.opus_labels merge     # rebuild opus_labels.csv from pilot/ and batches/
.venv-plp/bin/python3 -m train.opus_labels score     # agreement and the review queues
```
