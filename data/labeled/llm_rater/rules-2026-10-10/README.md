# Opus 5.5 labels under the rules of 10 Oct 2026

LLM labels for every sentence of the four sentiment sheets (2,075), made on
10 Oct 2026 after the team decided Opus labels the sheets and changed two
rules (wealth; retail product features). They are Opus's labels and are
reported as such. They replace nothing: no other labelling file was changed.
Results: `docs/evidence/llm-rater-new-rules-2026-10-10.md`.

| file | what |
|---|---|
| `rater_labels.csv` | one row per sentence: `rater_aspect`, `rater_not_about_bank`, `rater_label`, and the `sheet` it came from |
| `sheets.csv` | which sheet each sentence is on |
| `instructions_aspect.md`, `instructions_sentiment.md` | what each rater was given |
| `pilot/`, `batches/` | each rater's input and raw answers |
| `build_batches.py` | builds the inputs (aspect first; `sentiment` after the aspect answers are in) |
| `merge_and_score.py` | rebuilds `rater_labels.csv` and prints the comparison with the earlier labels |

The sentiment pass was given Opus's own aspect, not the human one.
