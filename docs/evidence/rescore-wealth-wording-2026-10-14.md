# Second re-score: the corpus under the new wealth wording (14 Oct 2026)

**What this is.** On 10 Oct the team narrowed the wealth aspect to the
priority and private banking tiers, and a trial showed the local aspect model
follows that rule when it is written into its prompt
([wealth-definition-trial-2026-10-12.md](wealth-definition-trial-2026-10-12.md)).
The whole corpus was then classified again under that wording, and on 14 Oct
the result was applied to `data/plp.db`. This note records what changed.

**Result.** 6,914 of the 45,844 sentences (15%) changed aspect. The wealth
aspect fell from 4,359 sentences to 1,423; most of what left went to retail
banking and to "other". Each bank's headline score fell by 0.010 to 0.015,
because the served model reads the aspect's name with the sentence and is
less ready to call a sentence positive once it is no longer filed under
wealth. The order of the banks did not change.

## What was run

1. **The corpus run.** `data/eval/wealth-definition-trial-2026-10-12/corpus.py`,
   13 Oct 01:09 to 14 Oct 08:04, a little over a day of the MacBook: all 45,844
   sentences answered, none invalid after a retry. Answers in
   `data/aspect_llm/llama3.1_8b.eef9b342.jsonl`.
2. **The config.** `config/aspects.yaml` was given the same wording
   (`apply_wording.py`): two definitions and two examples. The answer file
   the code looks for is then the one the run filled.
3. **Rehearsal on a copy, then a check.** The owner had agreed beforehand
   that the re-score could be applied without a further review if the
   script's checks passed, base FinBERT's headline rows were identical, and
   each bank's all-time headline under the served model moved by no more
   than 0.02 (`rescore_check.py`; output in `rescore_check.txt`). All three
   held.
4. **Applied** to `data/plp.db` at 08:07 on 14 Oct; the copy before it is
   `data/snapshots/plp-before-rescore-20261014-000702.db`. The database then
   matched the rehearsed copy row for row (45,844 assignments, 91,688
   scores, 886 index rows) and passed SQLite's integrity check.
5. **Snapshot:** `plp-2026-10-14.db.gz`, 26.2 MB, SHA-256
   `2e42aafeaa9d1e219b00359e8b31e7219b0fe1824f0aaaf9b3d2598607a857f0`.

## Sentences per aspect

| Aspect | Before | After |
|---|---|---|
| retail_banking_sentiment | 19,684 | 20,877 |
| other | 4,298 | 6,786 |
| investor_stock_sentiment | 5,781 | 4,565 |
| income_profit_results | 3,672 | 3,834 |
| management_guidance | 2,154 | 2,184 |
| asset_quality | 1,632 | 1,699 |
| net_interest_margin | 1,407 | 1,425 |
| wealth_business | 4,359 | 1,423 |
| capital_liquidity | 1,252 | 1,262 |
| macro_market_environment | 942 | 1,175 |
| dividend_policy | 663 | 614 |

The largest moves: wealth to retail banking (1,333 sentences), wealth to
other (1,085), retail banking to other (940), investor and stock sentiment
to retail banking (766) and to other (484). So the new wording did more than
narrow wealth: its longer retail definition and two extra examples also
moved sentences between retail, investor sentiment and other, as the trial
on the labelled sentences had shown.

## Headline scores

All time, all sources, the served model.

| Bank | Sentences | Before | After | Change |
|---|---|---|---|---|
| DBS | 24,978 | 0.155 | 0.143 | -0.012 |
| OCBC | 7,774 | 0.143 | 0.129 | -0.015 |
| UOB | 13,092 | 0.117 | 0.107 | -0.010 |

- **Base FinBERT's headlines did not move at all**, as expected: it scores a
  sentence the same whatever its aspect.
- **The served model's did, because its input includes the aspect's name.**
  Of the 6,914 sentences that changed aspect, 896 (13%) changed label, and
  the movement is one-sided: 614 went from positive to neutral and 88 from
  neutral to positive. No sentence that kept its aspect changed label. The
  share of sentences labelled positive fell from 31.7% to 30.5%.
- **This is a property of the model worth stating in the report.** The same
  sentence is scored a little differently depending on the topic it is filed
  under, so an aspect change is not neutral for the headline. An earlier
  note in this project and the report draft said it was; that is true only
  of base FinBERT.
- **Recent windows:** over 30 days the three banks fell by about 0.010 each.
  Over 7 days UOB fell from 0.309 to 0.275 on 60 sentences; DBS and OCBC by
  0.003.

## Per-aspect scores

All time, all sources, the served model; sentences in brackets. The full
list for every aspect is in `rescore_check.txt`.

| Aspect | Bank | Before | After |
|---|---|---|---|
| Wealth business | DBS | 0.489 (2,154) | 0.459 (839) |
| Wealth business | OCBC | 0.476 (913) | 0.542 (271) |
| Wealth business | UOB | 0.368 (1,292) | 0.400 (313) |
| Retail banking | DBS | -0.046 (8,747) | -0.028 (9,099) |
| Retail banking | OCBC | -0.060 (3,288) | -0.029 (3,598) |
| Retail banking | UOB | 0.040 (7,649) | 0.064 (8,180) |
| Other | DBS | 0.043 (2,532) | 0.054 (3,877) |
| Other | OCBC | 0.084 (789) | 0.098 (1,220) |
| Other | UOB | 0.062 (977) | 0.073 (1,689) |

Most aspects' scores rose while every headline fell. The two are consistent:
a sentence that leaves wealth is usually less positive than the wealth
average but more positive than the retail or "other" average, so it lifts
the aspect it joins; meanwhile some of those sentences lost their positive
label in the move, which is what lowers the total.

## What follows

- The chatbot evaluations and the evidence-search measure are run again on
  this database, and the report draft's Tables 5 to 8 are updated from it.
- Teammates must restore `plp-2026-10-14.db.gz` with the code of 14 Oct; the
  12 Oct snapshot is superseded. The files to share are gathered in
  `data/run/share/`, with a note for teammates (`README-teams.md`).
