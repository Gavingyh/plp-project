# Validation: chatbot answers branch, tenth check, 2026-10-06
Verdict: fix first

Scope: `fix/chatbot-answers` against `main` (thirteen commits; the new strip design in 03dc631, after the merge of `main` in f2544fd), code and docs. The ninth check's quote findings are closed by the new design, and so are its abbreviation and comma findings. What is left are gaps in the design's own edges, not new quote shapes: a one- or two-word quote, or a de-marked passage, can keep a real citation; a mark glued to the word before it is read as an apostrophe; a carriage-return line ending hides a blockquote.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | 281 tool outputs of `main` and the branch: 0 differences; every bad bank, window or bucket value on every route that takes one gets 422; API tests 434 passed |
| Grounded chatbot | DISPROVEN | 2027 tests pass in `tests/` (5 expected failures, all recorded limits); about 70 invented-quote shapes and 17 correct answers through strip; replay: only the known changes; but 16 strict-xfail tests keep an invented quote, a cited invented passage or an unchecked figure (tests/test_validate_chatbot_round10_probes.py, tests/test_validate_chatbot_round10_review_findings.py) |

## Confirmed issues
- Two-word invented quote kept with a citation [high, also on `main`] chatbot/agent.py:1061: 'One user called OCBC "a scam" CITE' passes strip and off mode unflagged; the rule that keeps marks round a one- or two-word term doesn't look at the citation after it
- Blockquote after a carriage return [med, also on `main`]: 'He said\r> OCBC will cut its dividend next year\r' passes strip unchanged and unflagged, with or without a search
- Citation outlives a de-marked quote [med, from 03dc631] chatbot/agent.py:1080: an invented passage loses its marks but keeps the real citation after it, so it reads as sourced
- Glued opening mark read as an apostrophe [med] chatbot/agent.py:1053: 'One user wrote‘the bank will cut its dividend next year’ CITE' keeps the opening mark in strip mode
- Numbers in evidence text vouch for counts [med, also on `main`] chatbot/guards.py:279: a retrieved "I paid 37 dollars in fees" lets "37 negative posts" pass
- Docs [med]: RUNBOOK:549 gives one expected failure (there are five); HANDOFF:1157 says the replay is unchanged since 5 October, but the comparison commit and its output changed
- Docs [low]: a gap of 25 seconds subtracts a mean from a median; the evidence page calls "September 25 (45 posts)" both a count and a real date; DESIGN states the guarantee without the limits the evidence page lists

## Open questions
- The claim's wording: still a decision on the team to-do (not yet republished)

## Top 3 fixes
1. Citations: in strip mode, a citation right after a short pair or a de-marked passage stays only if that text was returned by the search; otherwise it goes with the marks: done when the two citation tests pass.
2. Edges of the design: turn every carriage return into a line break before the checks; a left-hand mark (“ ‘) is never an apostrophe; numbers in evidence text vouch only inside a quote of that text: done when the round 10 tests pass and every earlier test still does.
3. Docs: fix the RUNBOOK count, HANDOFF's replay sentence, the mean against median gap, the bracket wording and DESIGN's guarantee: done when an auditor rerun finds nothing medium or worse.
