# Second human rating of the chatbot's answers (27 Oct 2026)

**What this is.** A second team member rated both sets of 32 gold-set
answers the first rater had scored. This section covers the first set,
the one the first rater scored on 17 Oct: the local `llama3.1:8b` answers on the
code before the misdescription fixes, with the first rater's scores removed
(`data/eval/ratings_sheet_blind_llama3.1-8b.csv`). The purpose is to check
whether the first rating, 7 of the 26 model-written answers unfaithful
([human-ratings-2026-10-24.md](human-ratings-2026-10-24.md)), holds for a
second person.

**How it was done.** The second rater decided the scores and used an AI
assistant to check facts against the tool data (rater column: "rater 2
(AI-assisted fact-checking)"). The second rater had not seen the first
rater's scores or notes, or which answers were marked unfaithful. They did know the kinds of
fault the first rating found (a wrong year, a wrong period, a wrong rank,
invented topics), because they had worked on the fixes. The agreement below
is therefore probably higher than two fully independent raters would reach.

**Scales.** As in `data/eval/README-ratings.md`: faithfulness, relevance and
correctness, each 1 to 3. Faithfulness is the one the report relies on.

## Result

| | Faithfulness | Correctness | Relevance |
|---|---|---|---|
| Same score, all 32 answers | 31 | 27 | 24 |
| Weighted kappa (linear), all 32 | 0.96 | 0.76 | 0.41 |
| Same score, 26 model-written answers | 25 | 21 | 18 |
| Weighted kappa (linear), 26 model-written | 0.96 | 0.73 | 0.39 |

Faithfulness scores (3 / 2 / 1): first rater 19 / 6 / 7, second rater
19 / 5 / 8.

- Both raters marked the same seven answers unfaithful (`lookup-1`,
  `lookup-2`, `lookup-9`, `trend-2`, `thin-1`, `thin-2`, `compare-5`).
- The one difference is `lookup-7`: first rater 2, second rater 1. The answer
  ends "there isn't enough data to answer reliably" although the tool reports
  8,180 sentences and no shortage.
- Relevance agrees least. The repository had no written relevance scale when
  the first rater scored, so the two raters may have used different ones.

Quadratic-weighted kappa on faithfulness is 0.98 (all 32); unweighted, 0.95.

## Observations from the second rater's notes

- The local model put the data's end in September 2023 three times
  (`lookup-1`, `trend-2`, `lookup-9`), where the tool said 2026-09-24 or
  2026-09-25.
- Both questions about a recent window (`thin-1`, `thin-2`) failed the same
  way: the answer reported a wider period's figure as the period asked for.
- `consensus-2`: the tool's analyst rating breakdown sums to 7 against 17
  analysts. That is a fault in the consensus data, not in the answer.

## How it was computed

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -c "
import pandas as pd
from sklearn.metrics import cohen_kappa_score
a = pd.read_csv('data/eval/ratings_sheet_rater1.csv')
b = pd.read_csv('data/eval/ratings_sheet_blind_llama3.1-8b.csv')
m = a.merge(b, on='id', suffixes=('_1', '_2'))
print((m.Faithfulness_1 == m.Faithfulness_2).sum(), cohen_kappa_score(m.Faithfulness_1, m.Faithfulness_2, weights='linear'))
"
```

## The final answers from the hosted model

The second rater also rated the 32 answers shown on the final code
(`data/eval/ratings_sheet_gpt-6-luna_rater2.csv`), the set the first rater
had rated by confirming AI-prepared scores
(`data/eval/ratings_sheet_gpt-6-luna_SN.csv`), in the same way: the second
rater's scores, with an AI assistant checking facts. They had read, in the
report draft, that the first rater's two partly faithful answers lost a
point for adding "S$".

| | Faithfulness | Correctness | Relevance |
|---|---|---|---|
| Same score, all 32 answers | 27 | 28 | 29 |
| Same score, 26 model-written answers | 21 | 22 | 23 |

Faithfulness scores (3 / 2 / 1): first rater 30 / 2 / 0, second rater
29 / 2 / 1. Kappa is not reported: with nearly every answer scored 3 by both,
it moves a long way on one disagreement.

- The two raters' 2s fall on different answers. The first rater marked
  `consensus-1` and `consensus-2` (the currency "S$" is not in the tool
  data). The second marked `oos-1` and `oos-2`: the model checked coverage
  for DBS instead of the bank asked about, and its statement that it covers
  only DBS, OCBC and UOB comes from its instructions, not from a tool.
- The second rater marked `lookup-7` unfaithful for saying the Reddit
  entries' text was withheld, because the sheet shows that text. The sheet
  records tool results before the hosted model's privacy filter
  (`chatbot/backends/base.py`, `withhold_reddit`): the model received the two
  Reddit sentences as withheld, so its statement matched what it saw. On the
  model's input, no final answer was unfaithful to either rater.
- Fault in the rating sheets: they show the unfiltered tool results, so a
  rater cannot tell what the hosted model saw. A future sheet should show
  the filtered results the model received.

## What it supports

The finding that 7 of the 26 model-written answers were unfaithful, and that
the checks flagged none of them, does not rest on one person's judgement: a
second rater marked the same seven, with AI help limited to checking facts.
On the final answers, neither rater found an answer unfaithful to what the
model received; they disagree on which details count as loosely supported.
