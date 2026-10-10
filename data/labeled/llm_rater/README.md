# Opus 5.5 labeller

An additional rater for the 27 Sep labelled round (DESIGN decision 22). These
files never replace the human labels in `../candidates.csv`.
Results: `docs/evidence/llm-rater-2026-10-01.md`.

| file | what |
|---|---|
| `rater_labels.csv` | one row per sentence: `rater_aspect`, `rater_not_about_bank`, `rater_label` |
| `review_aspect.csv` | sentences where Opus and the human aspect differ; `decision` for a reviewer to fill |
| `review_sentiment.csv` | the same for sentiment |
| `instructions_aspect.md`, `instructions_sentiment.md` | what each rater was given (the annotation guideline, quoted) |
| `pilot/`, `batches/` | each rater's input and raw answers |
| `rules-2026-10-10/` | a second run on 10 Oct under the team's two new rules, over all four sentiment sheets (2,075 sentences); its own README and `docs/evidence/llm-rater-new-rules-2026-10-10.md` |
| `topup/`, `ner/` | two later blind rounds (2 Oct): the top-up sheet's aspects and the bank-NER gold sheet; `rater_topup.csv` and `rater_ner.csv` merged, inputs and raw answers beside them. Don't open them before people label those sheets |

```bash
.venv-plp/bin/python3 -m train.rater_labels extra score topup   # the later rounds: also merge, batches; topup or ner
.venv-plp/bin/python3 -m train.rater_labels merge     # rebuild rater_labels.csv from pilot/ and batches/
.venv-plp/bin/python3 -m train.rater_labels score     # agreement and the review queues
```
