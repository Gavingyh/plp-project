# Validation: chatbot answers branch, seventh check, 2026-10-05
Verdict: fix first

Scope: `fix/chatbot-answers` against `main` (nine commits, fixes in 7446c89), code and docs. The sixth check's findings are closed. But 7446c89's new date rule and its inch-mark rule each let invented content through, and three older gaps were found.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | 55 outputs of `main`'s and the branch's plain tool functions: identical; 11 bad bank, window or bucket requests over 9 routes: all 422 |
| Grounded chatbot | DISPROVEN | 1490 tests pass in `tests/` before the new ones; the replay over recorded answers shows only the known changes; but 10 strict-xfail tests keep an invented count or quote unflagged (tests/test_validate_chatbot_nested_quotes_and_inch_marks_review_findings.py, tests/test_validate_chatbot_nested_quotes_and_inch_marks_probes.py) |

## Confirmed issues
- Unlisted count noun hides a returned day [high, regression from 7446c89] chatbot/guards.py:117: with data to 25 September, "In September 25 customers complained about fees." flags nothing; so do "25 complaints", "25 DBS posts", "25 very angry posts", "25 or so posts"
- Inch-holding quote swallows the next opener [high, regression from 7446c89] chatbot/agent.py:121: 'One user said “my rate went up to 5" in one post CITE. Another wrote ”<invented>” CITE' keeps the invented sentence, unflagged, after strip; a list and an angle-quote form fail the same way
- Short single-quoted inventions pass [med, regression from 7446c89] chatbot/agent.py:171: "One user wrote 'banks secretly charge hidden fees' CITE" passes strip unchanged
- Low-9 quote marks unread [med, also on `main`] chatbot/agent.py:166: an invented quote in „...“ is neither flagged nor removed
- Real quote with a comma inside its marks is stripped [med, also on `main`] chatbot/agent.py:485: '"...night,"' quoting "...night." is removed as invented, under a note saying so
- Merged nested quotes strip a real quote [low, from 7446c89]: the safe direction, but correct evidence is lost
- Docs [med]: the evidence page's "differing from before.json: 1" (line 323) rests on a snapshot kept only in the session scratchpad
- Docs [low]: DESIGN decision 25 says any quote may hold an inch mark (the page: any but one left open); an ordinal day ("September 25th sentences") is always a date, and Known limits don't say so; 5 Oct work sits under HANDOFF's "4 October, afternoon"

## Open questions
- The claim's wording: still a decision on the team to-do (commit 7475804, not yet republished)

## Top 3 fixes
1. Quotes: make strip safe by construction: drop a line still holding a quote mark the checks couldn't place, and the text between two removed quotes; read „ marks; single quotes from three words after a quoting cue or before a citation; compare quotes without their end punctuation: done when the inch, single-quote, low-9 and comma tests pass and every earlier validation test still does.
2. Dates: skip a returned day after a month only where it clearly reads as a date (after "on", "as of" or "the"; before punctuation, a line end or a listed word); check it everywhere else: done when the five unlisted-count tests pass and the earlier date tests still do.
3. Docs: make the replay comparison re-runnable from a commit and quote that command; fix the inch-mark wording; put 5 Oct work under a 5 Oct entry: done when an auditor rerun finds nothing medium or worse.
