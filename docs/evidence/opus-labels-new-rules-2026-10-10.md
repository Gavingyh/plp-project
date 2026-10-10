# Opus 5.5 labels every sentiment sheet under the 10 October rules

On 10 Oct 2026 the team decided that Claude Opus 5.5 labels all the
sentiment sheets, to save people's labelling time, and changed two labelling
rules. This note records the run. The labels are **LLM labels**: they are
recorded and reported as Opus's, not as people's (the owner changed that part
of the meeting note the same day), and the report's GenAI declaration lists
the run. They sit in `data/labeled/claude/rules-2026-10-10/` and have
replaced nothing: `data/labeled/candidates.csv` and the other sheets are
unchanged, and which labels the models train and test on is still the
team's to decide (team to-do, section 1).

## The two rules

Written into `docs/annotation-guideline.md` ("Two rules decided on
2026-10-10") and quoted in the raters' instructions.

- **Wealth means the wealth tiers.** `wealth_business` covers the priority
  and private banking tiers and the wealth segment's own figures. Loans,
  mortgages and unit trusts are `retail_banking_sentiment` unless the
  sentence is about a wealth tier. The instructions apply the same reasoning
  to a brokerage account, a regular savings plan, insurance and a
  robo-adviser; that extension is not in the team's note.
- **A retail product's feature carries sentiment directed at the bank.** A
  feature clearly good for the customer is `positive`, one clearly bad is
  `negative`; a bare mention, a question, a how-to or mixed terms stays
  `neutral`. This is the "customer value" option of the 7 Oct paper, the
  nearest to the team's note; the team should confirm the wording.

## How it was run

As on 1 Oct ([opus-labeller-2026-10-01.md](opus-labeller-2026-10-01.md)),
with one difference in the second pass.

- **Rows:** 2,075 sentences, every sentence of four sheets once: the first
  round's 1,277, the top-up sheet's 268, the active-learning sheet's 150 and
  the broker research round's 380. No sentence is on two sheets.
- **Pass 1, aspect, blind.** Input: sentence id, bank, source, text.
- **Pass 2, sentiment, given Opus's own aspect from pass 1.** On 1 Oct the
  second pass was given the human aspect, to compare like with like; three
  of these sheets have no human aspect, and the wealth rule changed the
  aspects, so here each sentence's sentiment follows the aspect Opus gave it.
- A 50-row pilot (seed 2026), then 17 batches of 119 or 120 rows per pass
  (seed 2026): 36 Opus subagents, each starting from an empty context and
  told to read only its instructions and its input.
- **Audit:** the 36 transcripts hold 191 tool calls (72 reads, 36 writes, 41
  shell commands, 6 edits, 36 hand-backs). Every read, write and edit is of
  the rater's own instructions, input or output, and no shell command names
  another labelling file. The 6 edits correct a mistyped sentence id in the
  rater's own output.
- Inputs, raw answers, the two scripts and the merged
  `opus_labels.csv` are in the round's folder
  (`build_batches.py`, `merge_and_score.py`).

## Results

Printed by `merge_and_score.py`.

| | rows | positive | neutral | negative |
|---|---|---|---|---|
| first round | 1,277 | 447 | 570 | 260 |
| top-up sheet | 268 | 119 | 95 | 54 |
| active-learning sheet | 150 | 45 | 86 | 19 |
| broker research round | 380 | 146 | 128 | 106 |
| **all** | **2,075** | **757** | **879** | **439** |

Opus flagged 134 sentences as not about the bank (it still gave each an
aspect, as before).

Against the labels people gave the first round's 1,277 rows:

| | agreement | κ |
|---|---|---|
| aspect, this run against people | 0.842 | 0.802 |
| aspect, the 1 Oct run against people | 0.842 | 0.801 |
| aspect, this run against the 1 Oct run | 0.950 | 0.935 |
| sentiment, this run against people | 0.868 | 0.793 |
| sentiment, the 1 Oct run against people | 0.865 | 0.790 |
| sentiment, this run against the 1 Oct run | 0.879 | 0.813 |

On the broker research round's 280 labelled train/dev rows: aspect 0.861
(κ 0.840), sentiment 0.854 (κ 0.777).

By split of the first round: on the 299 test rows Opus differs from people
on 47 aspects and 42 sentiments; on the 978 train/dev rows, on 155 and 127.

## What the new rules changed

- **Wealth.** People labelled 129 first-round rows `wealth_business`; Opus
  gives 56 (52 on 1 Oct). Of people's 129, Opus now calls 63
  `retail_banking_sentiment`, 50 wealth and 16 something else. The wealth
  rule barely moved Opus (it already read investment products as retail);
  it mostly confirms that the disagreement with people on this line is the
  one the team has now settled Opus's way.
- **Retail features.** Of the 537 first-round rows both Opus runs call
  retail, 280 were neutral on 1 Oct. Under the new rule 34 of those became
  positive (28) or negative (6). In the other direction 28 rows that were
  positive (12) or negative (16) became neutral, which the rule does not
  ask for. So the rule's own effect is small, about the size of the
  difference between two Opus runs: the two runs give the same sentiment on
  87.9% of the 1,277 rows.

## Limits

- One rater, and an LLM. The κ figures are human against LLM, under
  different rules on the two sides for the 1,277 rows (people labelled under
  the older reading).
- The two runs differ on 12.1% of sentiments. Part is the rules, part is
  that pass 2 was given a different aspect, and part is the rater answering
  differently on a second reading; this run cannot separate them.
- The top-up, active-learning and broker research test rows have no human
  label to compare with, so nothing here measures Opus on them.
- The wording of the retail rule, and the wealth rule's extension to other
  investment products, are a reading of a one-line decision. If the team
  words either differently, the affected rows need another pass.
