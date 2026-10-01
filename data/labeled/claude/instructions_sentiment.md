# Rater instructions, pass 2: sentiment

You are labelling sentences about Singapore's three listed banks (DBS, OCBC,
UOB) for an investor-sentiment study. Each row gives a sentence and the aspect
it was assigned. The text below is the project's annotation guideline
(`docs/annotation-guideline.md`), quoted, plus the output format.

## Rules for this task

- Read only this file and the input file named in your task. Do not open
  any other file in the repository: other files hold human or model labels for these sentences.
- Judge each sentence yourself. Do not write code to classify, and do not call
  any model, API or search.
- Every row gets an answer. Take the row's aspect as given.

## From the guideline

**Choose one sentiment** toward the bank on that aspect: `positive`,
`neutral` or `negative`.

**The core question: sentiment toward the bank as an investment**, on this
specific aspect — not the writer's general mood, and not sentiment toward an
unrelated subject that happens to share the sentence.

> "UOB's provisioning jumped but honestly I'm just happy the coffee at the
> branch is free" → **negative** on `asset_quality` (provisioning rose — bad
> for the investment case), regardless of the writer's cheerful tone.

Decided edge cases:

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
- **Mixed sentiment across aspects in one sentence** ("NIM held up but
  provisions rose") — label strictly for the row's aspect, ignore the
  sentence's stance on other aspects.
- **Product/service complaints** (app crashed, branch queue was long) are
  usually `negative` toward the bank's service quality — but do NOT bleed
  that into `asset_quality`/`NIM`/etc.

## Output

Write the output file named in your task: one line per input row, in
input order, exactly

{"sentence_id": "<id>", "label": "negative"|"neutral"|"positive"}

No other fields, no commentary lines.
