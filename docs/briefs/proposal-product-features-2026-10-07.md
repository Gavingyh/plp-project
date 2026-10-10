# Does a product's feature count as sentiment?

A decision paper for the team, 7 Oct 2026. Nothing in the labels or the
guideline has been changed; this paper proposes a rule for the team to choose.

## The question

When a sentence only states what a bank product offers, costs or requires
("UOB One 7.8% interest."), is that positive or negative sentiment toward the
bank, or neutral? The guideline's rule that "factual statements with clear
valence are not neutral" was written for results such as a rising NPL ratio,
and it doesn't say whether a product's feature carries valence.

It matters now because two things wait on it. The top-up labelling round
and any retraining would bake in whichever reading annotators happen to take.
And this boundary is where the model and the raters disagree most: the model's
commonest error is a neutral sentence called positive or negative (57 such
errors on the test split, averaged over three seeds); 31 of those 57 are
retail banking sentences, and read, they are mostly product-feature
descriptions (`docs/evidence/error-analysis-2026-10-01.md`). And all 173 sentiment
disagreements between Opus and the human labels sit on the neutral boundary,
many on product and offer mentions (`docs/evidence/llm-rater-2026-10-01.md`).
The error analysis quotes test sentences, so this paper uses none of them.
Every sentence and count below comes from train/dev rows only.

## Three candidate rules

Each is worded as it would read under "Decided edge cases" in
`docs/annotation-guideline.md`. In all three, a sentence where the writer
judges the product ("bad $5 rounding", "worth it", "damn confusing"), compares
it with another bank, recommends it, or reports a good or bad experience keeps
the sentiment of that judgement. They differ only on sentences without one.

**Judgements only.** "A product's feature is neutral unless the writer judges
it. A statement of what a product offers, costs or requires, how to use it, or
how the bank changed it is `neutral`, however good or bad the terms."

**Customer value.** "A product's feature carries the sentiment it has for the
customer: a feature clearly good for the customer (a high rate, a bonus, no
fee) is `positive`; one clearly bad (a fee, a rate cut, a perk removed) is
`negative`. A bare mention of a product, a question about it, a how-to, or
terms with both good and bad sides is `neutral`."

**Changes only.** "A standing feature is `neutral`: what a product offers,
costs or requires today. A change the bank makes or is expected to make (a
rate cut, a new or bigger offer, a perk removed, a promotion ended early)
carries the sentiment the change has for the customer."

Whichever is chosen, the guideline should also say whose side is meant: on
`retail_banking_sentiment` it is the customer's. A savings-rate cut is bad
for customers but can be good for the bank's margin; the top-up sheet has
such sentences, and if one is given `net_interest_margin` it should be judged
from the bank's side.

## Examples (train/dev rows only)

From `data/labeled/combined/candidates.csv`, split `train_dev`. "Now" is the
current label; the next three columns are the label under each rule.

| sentence | now | judgements only | customer value | changes only |
|---|---|---|---|---|
| UOB One 7.8% interest. | positive | neutral | positive | neutral |
| There's no annual fee for DBS LF Student credit card. | positive | neutral | positive | neutral |
| For example, UOB Lady's Solitaire card offers 4 mpd for travel expenses (or other categories which you can choose) up to $2,000. | positive | neutral | positive | neutral |
| If you're under 29, DBS Multiplier gives you 1.5%, just got to spend at least a cent on Paylah within the month. | positive | neutral | positive | neutral |
| The UOB interest rates for a cash advance (28% p.a.) is higher than that of a credit card (25.9% p.a.) | negative | neutral | negative | neutral |
| DBS Multiplier with just salary + card spend or Paylah (no minimum amount, just a single transaction will do) is 1.8-1.9%. | neutral | neutral | positive | neutral |
| Not sure which OCBC account you have but some e.g. 360 has a fall below fee of $2 if the average monthly balance falls below $3,000 so do take note of that. | neutral | neutral | negative | neutral |
| There are other cards like UOB Lady's Card that offers 6 miles/$, but these usually have a cap. | positive | neutral | neutral | neutral |
| DBS Altitude Card launches new welcome offer of up to 22,600 miles | positive | neutral | positive | positive |
| OCBC to cut interest rates for savings account from May 1 | negative | neutral | negative | negative |
| DBS ending Vantage Card 60,000 miles promo early – apply by 30 June | negative | neutral | negative | negative |
| Once above exceeded, will fallback to UOB PRVI Miles at 1.4mpd. | neutral | neutral | neutral | neutral |
| Uob stash 100k is at 2.04% but must maintain or increase monthly average balance. | neutral | neutral | neutral | neutral |
| UOB cards for miles also have a bad $5 rounding. | negative | negative | negative | negative |

## How many train/dev rows would change

**Method.** Two scripts, both under `data/run/upstream/` (gitignored, like
the rest of `data/run/`):

1. `product_feature_rows.py` reads the 1,258 train/dev rows and keeps a row
   when its text names a retail product or product term (One Account, 360,
   Frank, Multiplier, card, account, fixed deposit, Vickers, promo, sign-up
   and others) and a feature (a percentage, interest, rate, cashback, miles,
   mpd, bonus, rebate, fee, waiver, minimum spend, cap, salary credit,
   conditions, tier, perks and others), and does not use results wording
   (net profit, fee income, NIM, quarter, dividend, NPL and others). It
   matches 107 rows: 98 retail banking, 8 wealth, 1 asset quality; 97 Reddit,
   9 Google News, 1 broker research.
2. `judgements.py` holds my reading of each of the 107 rows, keyed by
   `sentence_id`: a standing feature description (55), a change or offer by
   the bank (13), a judgement, comparison or experience (36), or not a
   product sentence (3); and, for the first two, whether the feature is good,
   bad or neither for the customer. It applies each rule and counts the
   changes. It also checks what the pattern misses: in 40 unmatched retail
   and wealth train/dev rows (random seed 2026, out of 325), it finds 7
   product-feature rows and scales the changes among them up to the 325.

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 data/run/upstream/product_feature_rows.py
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 data/run/upstream/judgements.py
```

| | judgements only | customer value | changes only |
|---|---|---|---|
| matched rows that change (of 107) | 26 | 4 | 13 |
| of which polar to neutral | 26 | 1 | 13 |
| of which neutral to polar | 0 | 3 | 0 |
| unmatched rows that change, scaled from the sample of 40 | about 24 | about 0 | about 16 |
| rough total, of 1,258 train/dev rows | about 50 | about 4 | about 30 |
| agreement with the Opus label on the 106 matched rows it rated | 0.755 (80) | 0.868 (92) | 0.840 (89) |

The current labels agree with the Opus label on 0.849 (90) of those 106 rows.
The customer-value rule's edge over the current labels and the changes-only
rule is 2 and 3 rows of 106, and the rule labels come from one reader's
judgements made with the current labels visible (see Caveats), so this is
no real evidence that one rule fits Opus better.

**What this shows.** The train/dev labels already follow the customer-value
rule: the annotators labelled 10 of 11 favourable feature descriptions
positive, all 9 bank changes that are bad for customers negative, and 39 of 40
bare mentions, questions and how-tos neutral. Only 4 matched rows depart from
it. But the annotators labelled with an LLM's suggested label in view, and
the final label equals that suggestion on 60 of the 68 matched feature or
change rows (88%) and on 98 of all 107 matched rows (92%). So the fit may
reflect the suggestion model's reading as much as the annotators' own; the
labels show what was accepted, not necessarily what people would choose
unprompted. The other two rules would turn polar labels into neutral ones, which
would lower the share of polar labels the model learns from on retail rows.

## Recommendation

**Adopt the customer-value rule** and write it into the guideline with its
neutral cases spelled out (bare mentions, questions, how-tos, mixed terms).
It matches the current labels, so it costs about 4 relabelled rows,
keeps the existing "facts with clear valence are not neutral" rule
consistent, and lets the top-up round and retraining go ahead without a
relabelling pass. The caveat: the current labels largely kept the LLM's
suggested label (88% of the matched feature or change rows), so the rule
being matched may be the suggestion model's rather than one the annotators
reached on their own; the team should confirm it is the rule they want, not
only the one the labels show. Agreement with the Opus rater does not
separate the rules (2 to 3 rows of 106).

**The trade-off.** Under this rule the retail aspect of the index counts
favourable product facts as positive sentiment: a promotion announcement or a
Reddit comment quoting a good rate raises a bank's score as much as praise
does, so the retail index partly measures how attractive the banks' offers
are, not only how people feel about them. If the team wants the index to
measure opinion only, the changes-only rule is the better fit, at the cost of
relabelling about 30 train/dev rows and briefing the annotators on a rule
that differs from the labels so far. The judgements-only rule changes the most rows
(about 50) and calls even a rate cut neutral, which seems hard to defend for
a sentiment index.

## Caveats

- The 107 judgements and the 40-row sample are one reader's (Claude's),
  made with the current label visible, so they may lean towards the current
  labels; the customer-value count is the one most at risk of being too low.
  A person should check the `judgements.py` list before the decision.
- The pattern list is hand-written and misses rows: 7 of the 40 sampled
  unmatched retail and wealth rows are product-feature sentences, which
  scales to about 57 of 325. The scaled counts rest on 0 to 3 sampled rows
  each, so they are rough.
- Rows in other aspects were not sampled for misses.
- Agreement with Opus is agreement with an LLM rater, not with ground truth,
  and the gaps between the rules are 2 to 3 rows.
- The human labels were made with an LLM prelabel visible and equal it on
  98 of the 107 matched rows, so they are not an independent read of which
  rule people hold.
- Whether the frozen test labels follow the same rule is not checked here,
  because this paper reads no test rows. The blind test-relabel decision on
  the to-do covers it.
