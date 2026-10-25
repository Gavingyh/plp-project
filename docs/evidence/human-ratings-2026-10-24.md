# Human ratings of the chatbot's answers (rated 17 Oct, analysed 24 Oct 2026)

**What this is.** The automated checks verify the chatbot's quotes and
figures, not whether what it says is true of the data. A team member rated
the 32 gold-set answers from the run on the re-scored database
(`data/eval/chatbot_eval_results_rescored2_v2.jsonl`; the 32 answers in the
ratings sheet match it) on three scales: faithfulness to the
tool data, relevance to the question, and correctness. Sheet:
`data/eval/ratings_sheet_rater1.csv`.

**Result.** 7 of the 26 answers the model wrote (27%) state something the
tool data contradicts. The automated checks flagged none of the 7. The
errors are of a few kinds, the commonest a wrong year for the data. The AI
judge used to order the sheet agrees with the person only weakly (weighted
kappa 0.22), as its role assumed.

## Scores

Each answer scored 1, 2 or 3 on each scale: for faithfulness, 1 if a claim
contradicts or is absent from the tool data, 2 if only loosely supported, 3
if every claim is supported.

| Scale | 3 | 2 | 1 |
|---|---|---|---|
| Faithfulness | 19 | 6 | 7 |
| Relevance | 27 | 4 | 1 |
| Correctness | 20 | 9 | 3 |

Six of the 32 questions (advice and off-topic) are answered by a fixed reply
from code, never by the model, and all six score 3. Among the 26 the model
wrote: faithfulness 13 at 3, 6 at 2, 7 at 1.

By kind of question, faithfulness 1 / 2 / 3: lookups 3 / 2 / 4, comparisons
1 / 0 / 4, trends 1 / 1 / 1, thin-data questions 2 / 0 / 0, evidence
requests 0 / 2 / 1, analyst consensus 0 / 1 / 1.

## The seven unfaithful answers

From the rater's notes:

- **A wrong year for the data, three answers** (`lookup-1`, `trend-2`,
  `lookup-9`): "the data runs to September 2023" where the tool says
  2026-09-25. A fourth answer states 2023 too. The figure check skips years
  (a recorded limit), so nothing flags this.
- **The wrong period, two answers** (`thin-1`, `thin-2`): an all-time figure
  given as "the last 7 days", and a two-month comparison given as "this
  week". The first was fixed on 14 Oct, after these answers were made
  ([chatbot-trend-fix-2026-10-14.md](chatbot-trend-fix-2026-10-14.md)).
- **A wrong ranking, one answer** (`lookup-2`): OCBC called "third place"
  where the tool's ranking puts it second.
- **Wrong strongest and weakest topics, one answer** (`compare-5`).

Every number in these answers is one a tool returned. What is wrong is what
the model says about the numbers: their date, their period, their order.
This is the class of error the automated checks were never built to catch,
and the reason the report treats them as a floor, not a measure.

## The AI judge against the person

| | judge 1 | judge 2 | judge 3 |
|---|---|---|---|
| person 1 (7) | 5 | 0 | 2 |
| person 2 (6) | 5 | 0 | 1 |
| person 3 (19) | 5 | 5 | 9 |

Exact agreement 14 of 32 (0.44), linearly weighted kappa 0.22. The judge
caught 5 of the person's 7 unfaithful answers but also scored 10 others as
unfaithful. That supports its use only to decide which answers people read
first, never as a measurement.

## Limits

- **One rater.** The plan called for two, to give an agreement figure; with
  one, these are one person's judgements.
- **The answers predate the latest chatbot changes.** Since they were made,
  the 7-day fix above went in and teammates added a default time window, a
  period label and a check of score readings. Fixes aimed at the faults found
  here, and runs on the fixed code with the local model and with OpenAI's
  gpt-6-luna, are in [chatbot-fixes-2026-10-24.md](chatbot-fixes-2026-10-24.md);
  those answers have not been rated by a person.
- **The rater saw the tool data and the answer side by side,** with the
  judge's doubtful answers first, as the sheet was ordered.

## What follows

A check that flags any year in an answer that no tool returned now catches
the wrong-year fault, and the tools give the date, rank and topics as
sentences for the model to copy ([chatbot-fixes-2026-10-24.md](chatbot-fixes-2026-10-24.md)).
