# Validation: chatbot answers branch, eighth check, 2026-10-05
Verdict: fix first

Scope: `fix/chatbot-answers` against `main` (ten commits, fixes in 31c7e98), code and docs. All of the seventh check's findings are closed, except the date one (partly closed) and the replay comparison (partly closed). A quote mark the checks can't place now flags the answer, and strip drops its line. The tester's 124 probes for invented quotes found no miss outside the recorded limits. But the new date rule still hides a count before a comma, a bracket or "for", and the new quote rules strip correct text in four shapes.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | 63 tool calls of `main` and the branch identical; 223 index comparisons, 0 mismatches (13 null scores below the minimum count, by design); 15 of 15 bad bank, window or bucket values get 422 |
| Grounded chatbot | DISPROVEN | 1643 tests pass in `tests/` (2 expected failures, the recorded limit); 0 misses in 124 invented-quote probes outside the recorded limits; replay: only the 3 known changes; but an invented count after a returned day passes unflagged in 4 shapes (tests/test_validate_chatbot_round8_review_findings.py) |

## Confirmed issues
- Count before a comma, bracket or "for" hidden [high, from 7446c89, kept by 31c7e98] chatbot/guards.py:78: with data to 25 September, "In September 25, 31 and 40 posts were negative" and "September 25 for DBS against 40 for UOB" flag nothing
- Words after a closing mark stripped [med, regression from 31c7e98] chatbot/agent.py:356: 'One user: “REAL”DBS also scored 0.31.' loses the model's own correct sentence
- A word in quote marks before a letter drops its line [med, regression from 31c7e98]: '"DBS"and "OCBC" both rose.' comes back as only the removal note (tests/test_validate_chatbot_round8_probes.py)
- Replay reads untracked results [med] scripts/replay_checks.py:84: the page's `--against 7446c89` output counts five results files kept out of git (CNA text), so a checkout prints different lines
- Cue nouns make terms into quotes [low, from 31c7e98] chatbot/agent.py:200: "Users call the app 'buggy and slow' often." and "Users report 'long queue times'" lose the term
- A stray mark after a citation drops a correct line [low, a recorded class]: 'A user wrote "REAL" CITE."'
- Docs [low]: docs/diagrams/07-chatbot-turn.md doesn't show the new unplaced-mark trigger

## Open questions
- The claim's wording: still a decision on the team to-do (not yet republished)

## Top 3 fixes
1. Dates: treat a returned day as a date before a comma or bracket only when no number follows within the clause, and drop "for" from the words after a day (the "runs to", "on" and "the" rules already cover the tested dates): done when the four count tests pass and the earlier date tests still do.
2. Quotes: read words after a closing mark as a quote only when the quote before them was removed; take a short pair without inner spaces as a word in marks whatever follows; cue words are verbs of saying only: done when the round 8 strip tests pass and every earlier one still does.
3. Replay: read only tracked results by default (an option adds the rest), quote that output, update diagram 07: done when an auditor rerun finds nothing medium or worse.
