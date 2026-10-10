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
| `rules-2026-10-10/` | a second run on 10 Oct under the team's two new rules, over all four sentiment sheets (2,075 sentences); its own README and `docs/evidence/opus-labels-new-rules-2026-10-10.md` |
| `topup/`, `ner/` | two later blind rounds (2 Oct): the top-up sheet's aspects and the bank-NER gold sheet; `opus_topup.csv` and `opus_ner.csv` merged, inputs and raw answers beside them. Don't open them before people label those sheets |

```bash
.venv-plp/bin/python3 -m train.opus_labels extra score topup   # the later rounds: also merge, batches; topup or ner
.venv-plp/bin/python3 -m train.opus_labels merge     # rebuild opus_labels.csv from pilot/ and batches/
.venv-plp/bin/python3 -m train.opus_labels score     # agreement and the review queues
```
