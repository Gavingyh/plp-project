# Validation: chatbot answers branch, sixth check, 2026-10-05
Verdict: fix first

Scope: `fix/chatbot-answers` against `main` (eight commits, fixes in 6e1560f), code and docs. The fifth check's high and medium findings are closed; two quote shapes still let an invented quote through strip mode, one of them a regression from 6e1560f.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | 224 tool calls of `main`'s and the branch's plain functions: 0 differ; 12 of 12 bad bank, window or bucket requests got 422 |
| Grounded chatbot | DISPROVEN | full suite 1409 passed before the new tests; the replay over recorded answers is unchanged; but 6 probes keep an invented quote unflagged or strip a correct one (tests/test_validate_chatbot_round6_probes.py, tests/test_validate_chatbot_round6_review_findings.py, strict xfail) |

## Confirmed issues
- Nested quote leaves the invented tail [high, regression from 6e1560f] chatbot/agent.py:217: '“I asked them "<real>" and they said <invented>”' checks only the nested part; a straight outer with a curly inner fails the same way
- Unclosed quote before a '"..."(Reddit)' quote [high, also on `main`] chatbot/agent.py:170: the real quote is removed and the invented one kept, unflagged
- Single quotes strip scare quotes [med, from 6e1560f]: "DBS's 'customer first digital approach' is praised." loses the phrase and gets a removal note
- Smaller [low]: a closing-mark-first quote beside a table bar or bracket (|”...”|) is unchecked; "In September 25 to 30% of posts" hides the 25 when that date was returned; "On September 25 for DBS" is flagged when it was (regression from 6e1560f)
- Docs [med]: the evidence page's "317 of the 334 answers" and the single-quote catch in one replayed answer trace to no saved output
- Docs [low]: two of the fifth check's findings are tested only in tests/test_chatbot_reader.py, not in a test_validate_chatbot_* file as the page says; the page says the curly and angle branches need a space or punctuation around them, which they don't

## Open questions
- The claim's wording: now a decision on the team to-do (commit 7475804, not yet republished); the evidence page's Known limits list is what a reworded claim would cite

## Top 3 fixes
1. Quotes: let the straight and closing-mark-first branches open after and close before anything but a letter or digit, and let a quote hold one nested quote in the other style; single-quoted passages only from six words: done when the nine round-6 xfail tests pass and every earlier validation test still does.
2. Dates: after a month, skip a returned day unless a count word or a share ("to 30%", "%") follows: done when both date xfails pass and the earlier date tests still do.
3. Docs: save the script and output behind any figure the page cites, or drop the figure; fix the two wordings: done when an auditor rerun finds nothing medium or worse.
