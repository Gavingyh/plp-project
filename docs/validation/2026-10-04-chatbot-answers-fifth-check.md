# Validation: chatbot answers branch, fifth check, 2026-10-04
Verdict: fix first

Scope: `fix/chatbot-answers` against `main` (six commits, latest 6e8298b), code and docs. The fourth check's findings are closed, but quote detection by pairing marks in order (04af72a) breaks on a single missing or stray quote mark.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | `main`'s and the branch's plain functions: 252 calls, 0 differences; 523 index rows equal `sentiment_index`; 11 bad bank, window or bucket requests all 422 |
| Grounded chatbot | DISPROVEN | 755 grounding, harness, privacy and API tests pass, and the evidence context reaches Gemini with Reddit and CNA text withheld, but an unclosed or stray quote mark lets an invented quote through strip unflagged (13 xfail tests in tests/test_validate_chatbot_quote_pairing.py and tests/test_validate_chatbot_fifth_review_findings.py) |

## Confirmed issues
- Unclosed quote shifts every pair [high, regression from 04af72a] chatbot/agent.py `_QuoteSpans`: '... "a nightmare to use. Another wrote "<invented>" <real cite>' keeps the invented quote, unflagged; f4b9145's pattern caught it
- Stray mark shifts the pairing [med] same: an inch or ditto mark ('6" phone "<invented>"') or nested straight quotes hide the next quote
- Single-quoted evidence unchecked [med] same, by design ("mostly apostrophes"), but recorded in neither the to-do nor the brief
- Smaller code [low]: closing-mark-first quotes (»…«, ”…”) unchecked; a count equal to a returned day ("September 25 sentences" with data to 25 September) hidden; "[1[2]]" crashes enforcement (ValueError); "Sept 25-26" flagged; a neutral share the model works out is flagged (no `neutral_pct` in the evidence context)
- Docs [med]: the round-4 text still gives one cause for the slowdown (evidence:167-169); DESIGN:607 says flatly the answers weren't longer (true on two of three questions)
- Docs [low]: "gap between the medians" (the before figure is an average); HANDOFF omits the evidence context and the thousands-group date rule; committing this run's tests changes the test counts and "none now marked as expected to fail"

## Open questions
- The claim says "never". A checker reading quote marks can't promise that for every shape; should the claim name what is checked (quotes in double or curly marks of three words or more, links, sentence ids, figures), with single quotes and two-word quotes recorded as limits in the to-do?
- The live answer quoted in 6e8298b's message isn't saved (its figures match the database)

## Top 3 fixes
1. Quotes: take the spans the f4b9145 pattern finds, and add a span from ordered pairing only where it overlaps none of them: done when all 13 xfail tests of this run, the fourth check's quote-shape tests and the earlier validations' tests pass.
2. Small code: give `neutral_pct` in the evidence context, make `_drop_marks_noted` tolerate nested brackets, skip a returned day only when no count noun or "sentences" follows it: done when those xfail tests pass.
3. Docs and record: fix the two medium wordings and the low ones, record the remaining quote limits (or the reworded claim) in the to-do: done when an auditor rerun finds nothing medium or worse.
