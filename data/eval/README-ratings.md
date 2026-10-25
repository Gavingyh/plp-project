# Rating the chatbot's answers

Two sheets, each with the chatbot's answers to the same 32 gold-set
questions as the first sheet (`ratings_sheet_rater1.csv`). Six of them
(`advice-1` to `advice-4`, `oos-3`, `oos-4`) get a fixed reply that no model
writes, identical whichever model runs; rate them like the rest. The write-up
reports the 26 model-written answers separately, as the first rating did.

| Sheet | Who rates it | What it holds | What it measures |
|---|---|---|---|
| `ratings_sheet_gpt-6-luna.csv` | Rater 1 | The default model's answers (OpenAI `gpt-6-luna`), from the run on the final code (25 Oct 2026, `luna_shown_v2`), exactly as a reader saw them | How faithful the default model is, against the 7 of 26 model-written answers found unfaithful for the local model before the fixes |
| `ratings_sheet_blind_llama3.1-8b.csv` | A second team member, who has not seen Rater 1's scores | The same answers and tool data Rater 1 scored on 17 Oct (the local `llama3.1:8b`, before the fixes), with the scores removed | Whether two people agree (weighted kappa between the raters) |

## How to rate

Each row has the question, the tool data the chatbot got back (every tool
call and its raw result), and the answer. Read the answer against the tool
data only: what the database says, not what you know about the banks.
Score each answer's **faithfulness** 1, 2 or 3, put your initials in
`rater`, and say in `notes` what is wrong whenever you give a 1 or a 2.
Faithfulness is the score the report needs; relevance and correctness are
optional, so skip them if time is short.

| Scale | 3 | 2 | 1 |
|---|---|---|---|
| **Faithfulness** (needed): is what it says supported by the tool data? | every claim is supported | only loosely supported | a claim contradicts or is absent from the tool data |
| Relevance (optional): does it answer the question asked? | answers it | answers part of it, or adds much that wasn't asked | doesn't answer it |
| Correctness (optional): is what it tells the reader right? | right | right, but incomplete or slightly off (a period or a rank, say) | wrong in a way that would mislead |

The faithfulness scale is the one used on the first sheet
(`docs/evidence/human-ratings-2026-10-24.md`). The other two are written
here for the second rater; Rater 1, check they match what you meant on the
first sheet if you fill them in.

Things that are not faults:
- Rounding a figure the tool returned (+0.0625 given as +0.06).
- Quoted words without quote marks: the chatbot takes the quote marks off
  any words it can't confirm a search returned, word for word. Judge the
  words themselves against the tool data.
- A line under the answer naming the days searched.

## Returning the sheets

Fill in the score columns, keep the file name and the columns, and save as
CSV (UTF-8). Commit the filled sheet to `data/eval/` in place of the blank
one, or send it to whoever commits. The repository is private; the tool data
holds CNA and broker research sentences and Reddit posts, so don't post the
sheets anywhere public. Then ask Claude to write up the result: the share of `gpt-6-luna` answers rated unfaithful against 7 of 26,
and the agreement between the two raters on sheet 2.
