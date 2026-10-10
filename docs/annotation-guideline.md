# Annotation Guideline — Aspect-Sentiment Labeling

## Version 2 — read this first

The labelling design changed on 2026-09-26 (DESIGN decision 17, PLAN.md
section 6): annotators set the aspect as well as the sentiment. The first
round under it was labelled on 2026-09-27 with the 10-aspect taxonomy
(DESIGN decision 21); its results are in
[evidence/annotation-agreement-2026-09-27.md](evidence/annotation-agreement-2026-09-27.md).
Everything after this section still applies, except where it says a row is a
fixed (sentence, aspect) pair.

**Each row is one sentence.** For each one:

1. **Is it about the bank?** If the bank is named only in passing ("I banked
   in via DBS PayNow" in a thread about something else), or the name refers
   to something else entirely (UOB Kay Hian the broker, Aston Martin DBS),
   set `not_about_bank` and stop. Don't force an aspect or a sentiment onto
   it. (The 2026-09-27 sheet had no `not_about_bank` column; add it next
   round.)
2. **Choose one aspect**: the one the sentence is mainly about, from the ten
   below or `other`. If it touches two, choose the one its sentiment is about.
3. **Choose one sentiment** toward the bank on that aspect: `positive`,
   `neutral` or `negative`. The rest of this guideline is about that choice.

### The aspects

Derived from the clustered corpus; definitions and counts in
[evidence/aspect-taxonomy-2026-09-25.md](evidence/aspect-taxonomy-2026-09-25.md).

| aspect | covers | not here |
|---|---|---|
| `asset_quality` | non-performing loans, allowances and provisions, credit costs, exposure to troubled borrowers or sectors | scams against customers (`retail_banking_sentiment`) |
| `capital_liquidity` | CET1 and capital ratios, leverage, LCR/NSFR, Basel rules, capital instruments and bond issuance | dividends and buybacks (`dividend_policy`) |
| `dividend_policy` | dividends paid or expected, DPS, payout ratio, ex-dividend dates, dividend yield, capital returned to shareholders | interest a customer earns on deposits (`retail_banking_sentiment`) |
| `net_interest_margin` | NIM and net interest income, loan and deposit growth as a driver of them, the effect of rate moves on the bank's earnings | rates offered to customers (`retail_banking_sentiment`) |
| `management_guidance` | forward-looking statements by the bank: targets, outlook, guidance raised or cut, strategy, earnings-call answers | results already reported (`income_profit_results`) |
| `income_profit_results` | reported income and profit: total income, net profit, fee and trading income | results that are specifically NIM, asset quality or wealth (those aspects) |
| `wealth_business` | the banks' wealth segments: the priority and private banking tiers (DBS Treasures and Treasures Private Client, OCBC Premier Banking, UOB Privilege Banking, the private banks), AUM, wealth fee income, wealth targets | products ordinary customers also hold, such as loans, mortgages, unit trusts and savings accounts, unless the sentence is about a wealth tier (`retail_banking_sentiment`) |
| `investor_stock_sentiment` | the stock itself: buy, sell or hold views, share price and valuation, target prices, returns against alternatives | the bank's own results (`income_profit_results`) |
| `retail_banking_sentiment` | products and service as customers experience them: cards, cashback, savings accounts, fees, app outages, scams, rejected applications | — |
| `macro_market_environment` | GDP, rate cuts and hikes, geopolitics and trade, the macro outlook as it affects the banks | — |
| `other` | appointments and pay, awards, M&A and partnerships, CSR, careers, regulatory boilerplate, anything else | — |

### Two rules decided on 2026-10-10

The team decided these on 10 October 2026. Labels made before that date
followed the older reading; see the note under each.

- **Wealth means the wealth tiers.** `wealth_business` covers the priority
  and private banking tiers (DBS Treasures, priority banking and the like)
  and the wealth segment's own figures. Loans, mortgages and unit trusts are
  not unique to wealth customers, so a sentence about one of them is
  `retail_banking_sentiment` unless it is about a wealth tier or the wealth
  segment. The same reasoning is applied to other products an ordinary
  customer can hold (a brokerage account, a regular savings plan, insurance,
  a robo-adviser); that extension is not in the team's note, so confirm it.
  Before this, people labelled many investment products `wealth_business`
  (29 of the 48 Reddit wealth rows in train/dev,
  [local-context-proposals](briefs/local-context-proposals-2026-10-07.md)).
- **A retail product's feature carries sentiment directed at the bank.** On
  `retail_banking_sentiment`, what a product offers, costs or requires is no
  longer kept `neutral`. Judge it from the customer's side: a feature clearly
  good for the customer (a high rate, a bonus, no fee) is `positive`; one
  clearly bad (a fee, a rate cut, a perk removed) is `negative`. A bare
  mention of a product, a question about it, a how-to, or terms with both
  good and bad sides stays `neutral`. A sentence where the writer judges the
  product, compares it, recommends it or reports an experience keeps that
  judgement's sentiment, as before. The wording is the "customer value"
  option of
  [proposal-product-features](briefs/proposal-product-features-2026-10-07.md),
  the nearest to the team's note ("include sentiment directed at the bank as
  opposed to keeping it neutral"); confirm it.

### What the sheet looks like

Columns you fill: `aspect`, `label`, `not_about_bank`, `annotator`. On
`train_dev` rows only, a model's suggested aspect and sentiment are shown for
reference; correct them freely. The `test` rows come on a separate blind sheet
with no model output (see "The `test` split is frozen" below).

### Agreement

The agreement round is the same as below, but κ is computed twice, once for
the aspect and once for the sentiment, and both should reach 0.6.
`train.agreement` measures sentiment by default; `--field aspect` measures
aspect agreement, joining the two sheets on `sentence_id` alone (added
2026-10-01). The
2026-09-27 round measured sentiment only: the aspects were corrected once and
shared.

On 2026-10-01 Opus 5.5 labelled the same rows as an additional rater, with
this guideline as its instructions (DESIGN decision 22): against the human
labels, aspect κ 0.80 and sentiment κ 0.79
([evidence](evidence/opus-labeller-2026-10-01.md)). Its disagreements are in
`data/labeled/claude/review_*.csv` for people to settle. The largest is a gap
in the aspect table above: where a retail customer's investment products
(brokerage trades, regular savings plans, gold, portfolio financing) belong,
`wealth_business` or `retail_banking_sentiment` — 63 rows. Decided on
2026-10-10: see "Two rules decided on 2026-10-10" above.

---

## Version 1 (superseded)

For labeling `data/labeled/candidates.csv` (generated by
`python -m preprocess.export_candidates`). Each row is one (sentence, aspect)
pair. Fill in the `label` column with exactly one of: `positive`, `neutral`,
`negative`.

## The core question

**Sentiment toward the bank as an investment**, on this specific aspect —
not the writer's general mood, and not sentiment toward an unrelated subject
that happens to share the sentence.

> "UOB's provisioning jumped but honestly I'm just happy the coffee at the
> branch is free" → **negative** on `asset_quality` (provisioning rose — bad
> for the investment case), regardless of the writer's cheerful tone.

## Decided edge cases

- **Factual statements with clear valence are not neutral.** "NPL ratio rose
  to 1.4%" is `negative` on `asset_quality`, even with no adjectives. Don't
  require an opinion word to mark non-neutral sentiment — the fact itself
  carries the valence.
- **Sarcasm**: label the intended meaning, not the literal words. "Great,
  another dividend cut" is `negative`.
- **Forward-looking guidance**: management raising guidance is `positive` on
  `management_guidance` even if current-quarter numbers were flat.
- **Quoted analyst opinion**: label the analyst's stated view, not your own
  assessment of whether they're right. "Maintains SELL on valuation concerns"
  is `negative`.
- **Incidental bank mentions**: if the sentence names the bank only as an
  incidental detail (e.g. "I banked in via DBS PayNow" in a thread about
  something else, or "DBS Altitude card" discussed purely as a rewards
  product, not the bank-as-investment), this pair should probably not have
  been assigned this aspect at all — see `docs/data-viability.md` and
  `docs/DESIGN.md` for this known relevance-filtering limitation. If you hit
  many of these, flag it; don't force a sentiment label onto genuinely
  off-topic content.
- **Mixed sentiment across aspects in one sentence** ("NIM held up but
  provisions rose") — you're only labeling ONE aspect per row here; label
  strictly for the aspect column on that row, ignore the sentence's stance on
  other aspects.
- **Product/service complaints unrelated to the bank's financial
  performance** (app crashed, branch queue was long) are typically `other`-
  aspect and usually `negative` toward the bank's service quality — but do
  NOT bleed that into `asset_quality`/`NIM`/etc. rows for the same sentence.

## Columns you should NOT need to touch

`base_finbert_label` / `base_finbert_confidence` are base FinBERT's own
zero-shot guess, shown for reference only (useful context, not ground truth —
it's frequently wrong, that's the whole point of fine-tuning). Do not anchor
on it; label independently, then it's fine to glance at it afterward.

## Inter-annotator agreement check

Before splitting up the full labeling workload, two annotators should
independently label the same ~150-row sample. Compute Cohen's κ
(`train/agreement.py`). **Target κ ≥ 0.6.** Below that,
this guideline is ambiguous somewhere — find the disagreements, tighten the
guideline, and re-label that sample before dividing up the rest.

```bash
# two annotators' sheets, joined on (sentence_id, aspect)
.venv-plp/bin/python3 -m train.agreement --a alice.csv --b bob.csv

# where you disagreed, so you can argue about specific rows
.venv-plp/bin/python3 -m train.agreement --a alice.csv --b bob.csv --show-disagreements 20
```

**Watch the gap between raw agreement and κ, not just κ.** This corpus is
heavily neutral, and two annotators who both default to `neutral` will agree
most of the time while sharing no judgement at all about the hard cases. κ
subtracts that. If raw agreement is 0.90 and κ is 0.46, the distribution is
doing the work, not you.

### A worked example from this project's own data

Running the same tool over the two *model* opinions already in
`candidates.csv` — the local model's `llm_prelabel` against base FinBERT's
`base_finbert_label`, 997 rows:

| | |
|---|---|
| Observed agreement | 0.462 |
| Cohen's κ | 0.215 (fair) |

They disagree more than half the time. The pattern is one-directional and
explains itself: the local model called 208 sentences `positive` and 135
`negative` that FinBERT called `neutral`. It was prompted with this
guideline's rule that a factual statement with clear valence is not neutral;
FinBERT was not. So the disagreement is substantially by design.

Two things follow. The pre-labels are *not* just a copy of the baseline, so
correcting them is real work rather than rubber-stamping. And neither column
is ground truth — that is what you are creating.

## The `test` split is frozen

Rows marked `split=test` were sampled purely at random, before any model
screening. **Label these with the same care as everything else, but do not
let them influence how you label `train_dev` rows, and do not resample or
swap rows between splits.** This set is what every headline metric in the
report gets computed against — its integrity is the whole point.
