# Trial of the new wealth wording in the aspect model's prompt (12 Oct 2026)

**What this is.** A local LLM (`llama3.1:8b`) gives every sentence its one
aspect. On 10 Oct the team narrowed what counts as the wealth aspect: it
means the priority and private banking tiers and the wealth segment's own
figures, and an investment product any customer can hold (a unit trust, a
brokerage account, a regular savings plan, insurance, a robo-adviser) is
retail ([annotation guideline](../annotation-guideline.md)). The prompt the
corpus was classified under still carries the older, broader definition.
This trial asks whether writing the new rule into the prompt makes the model
follow it, before a day of the MacBook is spent re-classifying the corpus.

**Result.** It does. On the 2,075 labelled sentences the new wording agrees
with the labels made under the new rule 79.4% of the time, against 75.5%
for the old wording, and the difference is not chance (p < 0.001). The gain
is where the rule changed: the model stops calling ordinary investment
products "wealth". The cost is that it now misses about half of the true
wealth sentences. On balance the new wording is the better fit to the rule
the team decided, so the corpus run has been started; applying its answers
to the database is a second re-score and needs the owner's go-ahead.

## What was run

`data/eval/wealth-definition-trial-2026-10-12/trial.py`, on 12 Oct 2026.
Nothing in `config/` or the database changed: the new wording was set in
the trial's own process and its answers went to their own cache file.

- **The wording.** Two definitions changed and two invented examples were
  added. Wealth: "the bank's wealth business: its priority and private
  banking tiers (such as DBS Treasures, OCBC Premier, UOB Privilege) and
  what they offer, assets under management, wealth management fee income,
  wealth targets. Not an investment product any customer can hold". Retail
  gained "loans and mortgages, unit trusts, brokerage accounts, regular
  savings plans, insurance, robo-advisers". The examples are a unit trust's
  sales charge (retail) and a priority tier's perks (wealth).
- **The sentences.** All 2,075 that carry a label: the first round's 1,277,
  the top-up sheet's 268, the active-learning sheet's 150 and the broker
  research round's 380.
- **Two references.** The LLM rater's aspects of 10 Oct, made under the new
  rule (all 2,075 rows), and people's aspects on the first round (1,277
  rows), made under the older reading. The first measures whether the model
  follows the new rule; the second shows what happens against labels that
  do not.
- The wording was written once and not adjusted after seeing results, so
  the labelled rows are a fair test of it.

## Agreement with the labels

| Reference | Rows | Old wording | New wording | Newly right | Newly wrong | Exact McNemar p |
|---|---|---|---|---|---|---|
| LLM rater, new rule | 2,075 | 75.5% | **79.4%** | 148 | 67 | 3.4e-08 |
| the same, rows where either answer or the label is wealth or retail | 897 | 69.8% | **78.8%** | | | |
| People, older reading | 1,277 | 72.9% | 73.9% | 79 | 66 | 0.32 |
| the same, wealth or retail rows | 688 | 69.0% | 70.9% | | | |

The model's answer changed on 268 of the 2,075 sentences (13%).

- **Against the new-rule labels the gain is real and sits where the rule
  changed.** Twice as many sentences became right as became wrong, and on
  the wealth and retail rows agreement rose nine points.
- **Against people's labels nothing changes** (p = 0.32). That is expected,
  not a failure: people labelled many investment products as wealth under
  the older reading, so a model that now follows the new rule gains and
  loses about equally against them.
- **By sheet, against the new-rule labels:** first round 75.1% to 80.5%,
  active-learning sheet 83.3% to 90.0%, top-up sheet 77.6% to 78.4%, broker
  research 72.4% to 72.4%. Broker reports rarely mention retail investment
  products, so the rule has nothing to change there.

## Where the change comes from

Precision is the share of the model's calls for an aspect that the new-rule
label agrees with; recall is the share of that label's sentences the model
finds.

| Aspect (sentences with that label) | | Called | Right | Precision | Recall |
|---|---|---|---|---|---|
| Wealth (83) | old | 176 | 63 | 0.36 | 0.76 |
| | new | 54 | 38 | **0.70** | 0.46 |
| Retail (711) | old | 603 | 561 | 0.93 | 0.79 |
| | new | 656 | 619 | 0.94 | **0.87** |
| Other (148) | old | 94 | 63 | 0.67 | 0.43 |
| | new | 158 | 103 | 0.65 | **0.70** |

- **Under the old wording, two of every three "wealth" calls were wrong.**
  The model called 176 sentences wealth where the labels have 83. The new
  wording calls 54 and is right on 70% of them.
- **Most of what leaves wealth goes where the rule sends it.** Of the 48
  sentences moved from wealth to retail, 36 became right and 3 became wrong.
  Of the 35 moved from wealth to other, 24 became right and 5 wrong.
- **The cost is recall on true wealth sentences**, which falls from 0.76 to
  0.46: 25 sentences the old wording had right are now filed elsewhere. The
  moves from wealth to income and results (6 newly right, 8 newly wrong) and
  to management guidance (4 and 7) are where this shows: sentences where the
  bank reports or plans its wealth business. The guideline files those
  under wealth only when the figure is stated as wealth management income,
  so some of these are a fine line and some are the prompt's "not an
  investment product" clause over-reaching.
- **Two side effects, both helpful.** "Other" is found far more often
  (recall 0.43 to 0.70 at the same precision), and 18 sentences moved from
  investor and stock sentiment to retail, 17 of them correctly. The longer
  retail list and the two extra examples changed more than the wealth line.

## How far to trust it

- **The reference is an LLM's labels, not people's.** The new-rule labels
  came from the LLM rater; no person has labelled these rows under the new
  rule. The rater's aspects agree with people's at kappa 0.802 on the 1,277
  first-round rows ([evidence](llm-rater-new-rules-2026-10-10.md)), but the
  trial measures agreement between two models told the same rule.
- **The labelled rows are not a random sample of the corpus**: they were
  drawn for labelling in four rounds, two of them chosen for being hard or
  from one source. The size of the shift in the corpus will differ.
- **One wording was tried.** A wording that keeps the precision and gives
  back some recall may exist; none was searched for, to keep the labelled
  rows a fair test.

## What it means for the corpus

The stored aspects give wealth 4,359 of 45,844 sentences
([re-score rehearsal](rescore-rehearsal-2026-10-12.md)). In the labelled
rows the new wording makes about a third as many wealth calls (54 against
176), so the corpus's wealth aspect will shrink by a similar order, with
most of the difference moving to retail and other. Headline figures do not
depend on the aspect, so they will not move; the wealth, retail and other
rows of the index will.

The corpus run under the new wording started on 13 Oct
(`data/eval/wealth-definition-trial-2026-10-12/corpus.py`, cache
`data/aspect_llm/llama3.1_8b.eef9b342.jsonl`): about a day of the MacBook,
resumable, writing only the cache. To apply it: give `config/aspects.yaml`
the same wording (the cache name must come out the same), rehearse
`scripts/rescore.py` on a copy, and re-score with the owner's go-ahead.
The chatbot evaluations then need one more run.

## Files

`data/eval/wealth-definition-trial-2026-10-12/`: `trial.py`, `corpus.py`,
`results.json` (every figure above) and `answers.csv` (each sentence's old
and new answer beside both references, without its text).
