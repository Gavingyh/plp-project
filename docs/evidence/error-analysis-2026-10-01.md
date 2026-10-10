# Error analysis of the fine-tuned model, and a neutral threshold

Follows [finetune-fixes-2026-10-01.md](finetune-fixes-2026-10-01.md): the
readable-label models (seeds 42, 1, 7) score test macro-F1 0.604 ± 0.035,
and their commonest error is a neutral sentence called positive or negative.
Two questions: where do the errors fall, and does a neutral threshold chosen
on dev data reduce them? Run 2026-10-01 on the CPU (the GPU was busy).

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m train.error_analysis --cpu
```

## The threshold

Predict neutral unless the stronger of positive and negative beats neutral
by more than a margin (margin 0 is the plain argmax). Each seed's margin is
the one with the best macro-F1 on **that seed's own dev split**, the same
147 rows `train/finetune.py` held out (reproduced exactly: seed 42's argmax
dev macro-F1 is 0.630, as in its training log). Margins tried: 0 to 0.60 in
steps of 0.05. The test split was scored once per rule.

| seed | margin chosen on dev | dev macro-F1, argmax → margin | test macro-F1, argmax → margin | test accuracy | neutral called polar | polar called neutral |
|---|---|---|---|---|---|---|
| 42 | 0.15 | 0.630 → 0.648 | 0.630 → **0.641** | 0.679 → 0.702 | 52 → 41 | 34 → 39 |
| 1 | 0.00 | 0.638 → 0.638 | 0.617 → 0.617 | 0.669 → 0.669 | 50 → 50 | 37 → 37 |
| 7 | 0.25 | 0.613 → 0.633 | 0.564 → **0.600** | 0.605 → 0.656 | 75 → 54 | 29 → 39 |
| mean ± sd | | | 0.604 ± 0.035 → **0.619 ± 0.021** | | | |

For the average of the three models, with the mean of the seeds' margins
(0.13): macro-F1 0.614 → **0.624**, accuracy 0.662 → **0.682**; neutral
called polar 57 → 44, polar called neutral 32 → 39, positive and negative
swapped 12 → 12. (The 0.614 here is the 0.615 of the earlier evidence before
rounding.)

**What it shows.** The margin trades one error for the other, and the
trade is favourable: 13 fewer neutral sentences called polar for 7 more
polar sentences called neutral, on the average of the models. It helps the
worst seed most (seed 7, +0.036) and leaves seed 1 alone (its dev split
preferred no margin). Against base FinBERT (0.571, accuracy 0.70) the
average model now leads on macro-F1 by 0.053 and trails on accuracy by about
0.02 (0.682 against 0.699). The margins were chosen on 147 dev rows each, so they are noisy; the
direction is consistent in the two seeds where dev chose one.

## Where the errors are

Average of the three models, argmax, test split:

| source | rows | accuracy | neutral called polar |
|---|---|---|---|
| Reddit | 184 | 0.63 | 39 |
| earnings | 79 | 0.73 | 13 |
| Google News | 34 | 0.71 | 4 |
| Yahoo News | 2 | 0.00 | 1 |

| human aspect | rows | accuracy | neutral called polar |
|---|---|---|---|
| retail_banking_sentiment | 148 | 0.65 | 31 |
| wealth_business | 40 | 0.60 | 9 |
| other | 22 | 0.77 | 1 |
| income_profit_results | 21 | 0.95 | 0 |
| investor_stock_sentiment | 18 | 0.61 | 3 |
| management_guidance | 13 | 0.69 | 3 |
| capital_liquidity | 10 | 0.70 | 1 |
| net_interest_margin | 10 | 0.40 | 5 |
| dividend_policy | 8 | 0.50 | 3 |
| asset_quality | 7 | 0.57 | 1 |
| macro_market_environment | 2 | 1.00 | 0 |

By length: 1–10 words 0.70 (66 rows), 11–20 0.66 (125), 21–35 0.69 (68),
36 or more 0.55 (40).

Two thirds of the neutral-called-polar errors (39 of 57) are Reddit, and
over half (31) are retail banking. Read, they are mostly **descriptions of
product features**, which the model reads as praise or complaint:

- "If you spend at least $500 on certain UOB cards, you get some bonus
  interest." (called positive)
- "Just to add on for ocbc 360, the interest is higher if you fulfil all the
  conditions." (positive)
- "I use OCBC Frank 6% for daily expense." (positive)
- "Considering your plan to close your UOB One Account, it sounds like you
  haven't." (negative)

These are the same boundary cases where the Opus labeller and the
annotators disagreed ([llm-rater-2026-10-01.md](llm-rater-2026-10-01.md):
every sentiment disagreement was on the neutral boundary, many on product
mentions). The guideline's rule that "factual statements with clear valence
are not neutral" doesn't say whether a product's feature is valence toward
the bank as an investment. Settling that in the guideline would help the
labels and the model together.

The small aspects (NIM 10 rows, dividend policy 8, asset quality 7) have
too few test rows to read an accuracy from.

## Caveats

The margin is a post-processing rule, not a retrained model. Each margin is
chosen on 147 dev rows, and the average model's margin is the mean of the
seeds' margins, each chosen on a dev split that the other seeds trained on;
none was chosen on test. The test labels carry the anchoring caveat of the
earlier evidence. Inference ran on the CPU, which can differ from the GPU in
the last decimal place.
