# Validation: chatbot answers branch, third check, 2026-10-04
Verdict: fix first

Scope: `fix/chatbot-answers` against `main` (7428beb, 8082469, b79fbc3), code and docs. All six findings of the second check are closed, but each round of fixes to the date and marker handling has opened new edges, two of them regressions from `main`.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | 231 calls of `main`'s and the branch's plain functions on a read-only DB copy: byte-identical output; API tests 434 passed, 2 skipped |
| Grounded chatbot | DISPROVEN | earlier-validation tests 63 passed, Gemini privacy 39, strip replays of 16 runs clean, but strip mode keeps an invented `"..."[2]-` quote unflagged, and the branch hides counts `main` checked (30 xfail tests in tests/test_validate_chatbot_marker_drop_probes.py and tests/test_validate_chatbot_third_review_findings.py) |

## Confirmed issues
- Marker drop hides a quote [high] chatbot/agent.py `_drop_bare_marks`: removing "[2]" from `"..."[2]-` (or before a letter, apostrophe or slash) leaves text the quote pattern no longer reads, so strip keeps the invented quote, unflagged (flagged with enforcement off)
- Monthly count lists hidden by dates [high] chatbot/guards.py:52: a month-first date may now end at a line break, so "July 18 / August 24 / September 29" one per line returns []; `main` flagged all three
- Counts before uncovered nouns hidden [low, regression] chatbot/guards.py `_COUNT_NOUN`: "21 Oct tweets", "23 Sep replies", "21 October negative sentences" return []; `main` flagged them
- Markers inside quotes point at wrong sources [med] chatbot/agent.py: an invented "[2]" inside a real quote reaches the reader beside a Sources [2] that is another sentence
- Marker pattern drops bracketed ranges [low] chatbot/agent.py `_BARE_MARK`: "range [12-45]" loses its figures before the number check
- Unclosed, mixed or em-dash-ended quotes are never checked [med, pre-existing on `main`] chatbot/agent.py `_QUOTE_PATTERN`
- Evidence page and DESIGN [med]: "answers say more" is contradicted (shorter on 2 of 3 timed questions); the block and 8,192 runs used the trimmed version, not the final one; the model still sees sentence ids inside `cite_as`; HANDOFF says "66 months of scores stored" (66 of 72 have 5 or more sentences, computed on request)
- Smaller [low]: token rate 7 to 11 for `main` in the block run; the replay sentence leaves out rounds 1 and 2 (round 1 now flags 3, by the intended fix); the new prompt's replay can't run on a clean clone (its results files hold CNA text and are untracked)

## Open questions
- Should the results files with CNA text be committed with that text redacted, so the replay can be reproduced?
- `chatbot/judge.py:123` falls back to the shown answer, with "[n]" markers (outside scope)

## Top 3 fixes
1. Dates: stop guessing dates by pattern; skip a day number only when its month and day match a date a tool returned (`data_runs_to`, a monthly period): done when all date tests in the four validation files pass, the counts-by-month xfail included.
2. Markers: run the checks on the model's own text first (with "[" accepted after a closing quote mark, and dashes and slashes too), strip what they find, and only then drop bare markers, outside quotes and in display; leave bracketed ranges alone: done when the marker-drop probes, the inside-quote and range tests pass without xfail.
3. Docs: state only the supported cause of the slowdown (longer tool results), name the version each timing run used, drop "no ids", fix HANDOFF's 66 months: done when an auditor rerun finds nothing medium or worse.
