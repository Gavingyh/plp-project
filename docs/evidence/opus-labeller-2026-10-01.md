# Opus 5.5 as an additional labeller

Claude Opus 5.5 (`claude-opus-5-5`, through Claude Code on the project's
subscription) labelled all 1,277 sentences of the 27 Sep round, blind to
the human labels, as one more rater. It replaces nothing: the human labels
in `data/labeled/candidates.csv` are unchanged, and a disagreement changes a
gold label only if a person decides it should (DESIGN decision 22). Run
2026-10-01.

Two gaps made a second rater worth having. The aspect labels have one rater:
both annotators' files carry the same corrected aspect column, so aspect
agreement was never measured. And the sentiment labels were anchored: the
annotators saw a `llama3.2:3b` suggestion and their final labels match it
on 91.6% of rows
([annotation-agreement-2026-09-27.md](annotation-agreement-2026-09-27.md)).

## How it was run

Two passes, each by separate Opus subagents starting from an empty context:

1. **Aspect, blind.** Input: `sentence_id`, bank, source, text. The rater
   chooses one of the ten aspects or `other` and flags `not_about_bank`
   (always still choosing an aspect, so the answer compares with people who
   had no such flag).
2. **Sentiment, given the human aspect.** Input: the same plus the human
   aspect. The rater labels sentiment toward the bank on that aspect, so the
   answer compares like for like with the human label.

The instructions
([`instructions_aspect.md`](../../data/labeled/claude/instructions_aspect.md),
[`instructions_sentiment.md`](../../data/labeled/claude/instructions_sentiment.md))
quote `docs/annotation-guideline.md`: steps 1–2 and the aspect table for
pass 1; the core question and the decided edge cases for pass 2 (the
version-1 note that service complaints are `other` left out, as version 2
moved them to retail banking). Neither shows any human or model label.

A 50-sentence pilot (random, seed 2026) ran first; the remaining 1,227 rows
were shuffled (seed 2026) into 10 batches of 122–123 per pass, 20 subagents,
run five to ten at a time. The pilot's instructions differ from the batches'
only in naming the input and output files, so its 50 answers count.
Wall-clock time 17:22–17:35, about 1.34 million tokens in total.

**Blindness check.** Each rater was told to read only its instructions and
its input file and to label by reading, not by code or another model. Their
transcripts were audited: 22 raters, 108 tool calls, every one a read of the
rater's own instructions or input, a write of its own output (two wrote it
through a shell here-document), a shell command counting lines or matching
IDs in its own input and output, or its final reply. No rater opened another
file.

```bash
.venv-plp/bin/python3 -m train.opus_labels merge                 # answers -> opus_labels.csv, checked row for row
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m train.opus_labels score --centroid   # every figure below, and the review queues
.venv-plp/bin/python3 -m train.opus_labels audit --transcripts <subagent transcript folder>
```

The transcripts were in this session's temporary folder, so the audit can't
be re-run from the repository; its result is recorded here.

## Aspect

Against the human aspect, 1,277 sentences (test split = the 299 drawn at
random):

| rater | agreement | Cohen's κ | macro-F1 | test agreement | test κ |
|---|---|---|---|---|---|
| **Opus 5.5** | **0.842** | **0.801** | **0.789** | **0.856** | **0.789** |
| llama3.1:8b (J2) | 0.729 | 0.666 | 0.679 | 0.736 | 0.630 |
| qwen3:4b, no thinking (J2) | 0.719 | 0.655 | 0.671 | 0.746 | 0.649 |
| seed-centroid, floor 0.65 | 0.413 | 0.294 | 0.296 | 0.465 | 0.267 |

Opus agrees with llama3.1:8b on 0.751 (κ 0.687). Where llama and qwen agree
with each other (965 rows), Opus matches the human 0.878; where they
disagree (312), 0.731.

Per human aspect (llama3.1:8b recall from
[llm-aspect-classifier-2026-10-01.md](llm-aspect-classifier-2026-10-01.md)):

| human aspect | rows | Opus recall | Opus precision (uses) | llama3.1:8b recall |
|---|---|---|---|---|
| retail_banking_sentiment | 477 | 0.99 | 0.86 (549) | 0.86 |
| income_profit_results | 149 | 0.92 | 0.93 (148) | 0.85 |
| wealth_business | 129 | **0.36** | 0.90 (52) | 0.51 |
| other | 100 | 0.85 | 0.67 (126) | 0.36 |
| management_guidance | 93 | 0.55 | 0.78 (65) | 0.46 |
| investor_stock_sentiment | 89 | 0.91 | 0.90 (90) | 0.85 |
| asset_quality | 78 | 0.95 | 0.94 (79) | 0.76 |
| net_interest_margin | 58 | 0.93 | 0.68 (80) | 0.76 |
| capital_liquidity | 49 | 0.59 | 0.94 (31) | 0.76 |
| dividend_policy | 33 | 0.88 | 0.72 (40) | 0.55 |
| macro_market_environment | 22 | 0.68 | 0.88 (17) | 0.77 |

**Where Opus and the human differ** (202 rows; human → Opus):

- **Wealth → retail banking, 63 rows**, a third of all disagreements. They
  are retail investing services: buying bonds or ETFs through DBS Vickers,
  trading commissions, regular savings plans, portfolio financing, selling
  gold back to the bank. The guideline defines wealth as "wealth management
  and private or premier banking: AUM, wealth fee income, wealth targets"
  and retail banking as "products and service as customers experience
  them"; it doesn't say where a retail customer's investment products go.
  llama3.1:8b sided with Opus on 36 of the 63.
- **Management guidance → `other`, 26**: executives on technology and AI
  ("DBS Group Putting AI Into The Bank's DNA"), governance remarks.
- Then wealth → `other` 11, capital and liquidity → dividend policy 9,
  `other` → retail banking 8, income results → NIM 7, management guidance →
  NIM 7, capital and liquidity → NIM 7.

**Not about the bank.** Opus flagged 77 sentences (6.0%): Reddit 57, Google
News 15, Yahoo News 5, earnings 0. Its aspect agreement on them (0.831) is
about the same as on the rest (0.843). The human round had no such flag
(guideline step 1).

## Sentiment

Against the human label, the aspect given:

| comparison | agreement | Cohen's κ |
|---|---|---|
| **Opus 5.5 vs human** | **0.865** | **0.790** (macro-F1 0.871) |
| Opus vs human, test split | 0.876 | 0.790 |
| Opus vs human, train/dev | 0.861 | 0.788 |
| human A vs human B, 27 Sep (both saw the suggestion) | 0.952 | 0.926 |
| `llama3.2:3b` suggestion vs human | 0.916 | 0.872 |
| Opus vs the `llama3.2:3b` suggestion | 0.865 | 0.793 |

| human ↓ / Opus → | negative | neutral | positive |
|---|---|---|---|
| negative (275) | 255 | 20 | 0 |
| neutral (543) | 32 | 441 | 70 |
| positive (459) | 0 | 51 | 408 |

Opus never calls a human-positive sentence negative or the reverse: all 173
disagreements are about where neutral ends. In 118 of them the human label
is the suggestion the annotators were shown; Opus's label is the suggestion
in 52. Label counts: human 543 neutral, 459 positive, 275 negative; Opus
512, 478, 287. By source: Reddit 0.885 (617 rows), earnings 0.885 (477),
Google News 0.753 (166). Typical disagreements: product and offer
announcements ("UOB extends 60,000 miles Visa Infinite Metal sign-up bonus":
human positive, Opus neutral), and Reddit how-to comments ("Use OCBC 360 for
returns on 100k, but not more than that": human neutral, Opus positive).

## What it shows

1. **Aspect agreement can now be stated**: between the human labels and an
   independent Opus rater, κ 0.80, above the guideline's 0.6 bar. It is a
   human–LLM figure, not the human–human one the guideline asks for.
2. **The largest aspect disagreement is a guideline gap**, not noise:
   where a retail customer's investment products belong (wealth or retail
   banking). Deciding that boundary settles 63 rows at once and should go
   into the guideline before the next labelling round.
3. **Sentiment disagreements sit on the neutral boundary**, and the human
   side of them mostly matches the suggestion the annotators saw. That is
   consistent with the anchoring already recorded; it doesn't show which
   side is right.
4. **A ceiling for the local classifier.** Against the same human labels,
   Opus reaches 0.842 where llama3.1:8b reaches 0.729. Counted in rows, most
   of the gap is retail banking (Opus right on 62 more) and `other` (49
   more); on wealth Opus is behind (19 fewer), the boundary in point 2.

## Review queues (for people; nothing applied)

- [`review_aspect.csv`](../../data/labeled/claude/review_aspect.csv): 202
  rows (43 test), with the human aspect, Opus's, llama3.1:8b's and Opus's
  `not_about_bank` flag.
- [`review_sentiment.csv`](../../data/labeled/claude/review_sentiment.csv):
  173 rows (37 test), with the human label, Opus's and the suggestion the
  annotators saw.

Each has an empty `decision` column. A reviewer who changes a gold label
records it there; applying those decisions to `candidates.csv` is a
separate, reviewed step.

## Caveats

- Agreement with Opus is agreement with an LLM. Opus and the local models
  can share mistakes, and the human labels remain the reference.
- Not exactly reproducible: Claude Code sets no temperature, and each
  batch's answers depend on the batch around them. The inputs, instructions
  and raw answers are kept so the run can be inspected, not re-derived.
- The sentiment pass was given the human aspect, so Opus did not produce a
  fully independent (aspect, sentiment) pair; it was the fair comparison
  for sentiment.
- The sentences (Reddit, news and earnings text) were sent to Anthropic
  under the project's Claude subscription.
- The report's GenAI declaration must list this use.

## Files

`data/labeled/claude/`: `opus_labels.csv` (one row per sentence:
`sentence_id`, `rater`, `opus_aspect`, `opus_not_about_bank`,
`opus_label`), the two review queues, the instructions, and the raw inputs
and answers under `pilot/` and `batches/`.
