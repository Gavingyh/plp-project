# Ratings of the chatbot's answers: Ollama run against gpt-6-luna run (25 Oct 2026)

**What this is.** The 32 gold-set answers from the `gpt-6-luna` run were scored
1 to 3 for faithfulness, relevance and correctness, and set beside the scores
for the earlier `llama3.1:8b` answers. **These are reference scores written by
an AI assistant in one pass, not ratings by a person.** They give the team a
point to compare its own ratings against; they do not replace them.

**Files.**

- Luna answers rated: `data/eval/ratings_sheet_gpt-6-luna.csv` (blank for
  people to fill in; from `data/eval/chatbot_eval_results_luna_t1_v2.jsonl`,
  run 25 Oct 07:44).
- Reference scores and the reasoning for each row, in the `notes` column:
  `data/eval/ratings_sheet_gpt-6-luna_CLAUDE_REFERENCE_v2.csv`.
- Ollama scores: `data/eval/ratings_sheet_rater1.csv` (answers from
  `chatbot_eval_results_rescored2_v2.jsonl`, 14 Oct, `llama3.1:8b`).
- Question-by-question comparison:
  `data/eval/ratings_compare_ollama_vs_luna_2026-10-25.csv`.

## Scales

Faithfulness is defined in `chatbot/judge.py` and in
[human-ratings-2026-10-24.md](human-ratings-2026-10-24.md): 3 if every claim
is supported by the tool data, 2 if only a detail is unsupported or the wording
is loose, 1 if a claim is contradicted or a figure, quote or source is
invented. No file in the repository defines the other two scales. These scores
use: **relevance**, whether the answer addresses what was asked (3 yes, 2
partly, 1 no); **correctness**, whether what it says is accurate and not
misleading (3, 2, 1 on the same pattern). The team should agree these before
anyone else uses them.

## Result

| Scale | Ollama answers (3 / 2 / 1) | Mean | Luna answers (3 / 2 / 1) | Mean |
|---|---|---|---|---|
| Faithfulness | 19 / 6 / 7 | 2.38 | 30 / 2 / 0 | 2.94 |
| Relevance | 27 / 4 / 1 | 2.81 | 29 / 3 / 0 | 2.91 |
| Correctness | 20 / 9 / 3 | 2.53 | 30 / 2 / 0 | 2.94 |

Question by question, faithfulness rose on 12 of 32 and fell on 1; correctness
rose on 12 and fell on 1; relevance rose on 3 and fell on 1.

## Why the scores differ

Every quote, figure, rank and date in the Luna answers was checked against the
tool data in the sheet. All quotes are verbatim and all figures match.

- **Wrong date or period** in the Ollama answers: "the data runs to September
  2023" (`lookup-1`, `trend-2`, `lookup-9`; the tool says 2026-09-25 or 24), an
  all-time figure given as "the last 7 days" (`thin-1`) and August's figure as
  "this week" (`thin-2`). The Luna answers give the date and say there is no
  7-day figure.
- **Wrong rank or reading**: OCBC called third (`lookup-2`), a neutral reading
  called "slightly negative" (`trend-2`, `evidence-2`), "improved slightly"
  where the tool said too close to call (`trend-1`).
- **Invented detail**: strongest and weakest topics that no tool returned
  (`compare-5`), sources named without a tool (`lookup-4`).
- **Answers that failed to answer**: `compare-3` ended "Let me call the tools
  again"; `lookup-7` said "not enough data" with n = 8,180.

Part of the gap comes from code changes between the two runs: the tools now
return the date, rank and trend as finished sentences
([chatbot-fixes-2026-10-24.md](chatbot-fixes-2026-10-24.md)). The same note
reports that the local model, with those changes, still failed 5 of 21
re-tries, so the gap is not due to the answer model alone.

## Where the Luna answers still fall short

| Question | Scale | Score | Reason |
|---|---|---|---|
| `consensus-1`, `consensus-2` | faithfulness | 2 | "S$" is not in the tool data (borderline; 3 if currency is taken as obvious) |
| `trend-2` | correctness | 2 | compares August 2026 with February 2026 and says "down"; the monthly series shows August 2025 at -0.31, so "getting worse" is not clear |
| `evidence-1` | correctness | 2 | pairs a 54-cent quarterly assumption (Aug 2024) with an 81-cent payout (Apr 2026); dates only in the source list |
| `lookup-4` | relevance | 2 | asked "right now"; the all-time score is given (period stated) |
| `evidence-2` | relevance | 2 | asked for "complaints"; the evidence is broker and company statements |
| `evidence-3` | relevance | 2 | asked what "people" say; one quote, from the bank's own report |


