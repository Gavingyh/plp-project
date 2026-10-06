# Validation: chatbot answers branch, thirteenth (final) check, 2026-10-06
Verdict: ship (known limits recorded; owner's decision to merge)

Scope: `fix/chatbot-answers` against `main` (eighteen commits, last 420ea79: the reworded Grounded chatbot claim), code and docs, judged against the reworded claim. No code changed since 174c77d. The twelfth check's four gaps are still open and recorded. This run found four more, all also on `main`, now recorded as limits too. The auditor's findings are fixed in the docs.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN (carried over) | this run's tester returned no report; `api/` has no diff against `main` and no tool code changed since the twelfth check, which proved it (48 of 48 outputs identical, 514 index rows, every bad value 422) |
| Grounded chatbot | PROVEN within the Known limits | the reworded claim (CLAUDE.md, 6 Oct) holds within the evidence page's Known limits; every finding of this run is on that list with a strict 'recorded limit:' xfail; full suite 2394 passed, 46 expected failures, all recorded limits |

## Confirmed issues (recorded as limits, all also on `main`)
- Removed quote leaves its citation [high] chatbot/agent.py:1022: a dash, bold, bracket, comma, table bar or line break between an invented quote and its citation keeps the citation in strip mode
- Figures skipped by design [high] chatbot/guards.py:364: whole numbers 1990 to 2100 (read as years), numbers before day/week/month/year, numbers under 10
- "45 per cent" checked as a plain number [med] chatbot/guards.py:367: a returned count vouches for it
- ".87" never read [low] chatbot/guards.py:25: no recorded answer writes one
- Docs, fixed in this commit: three docs still called the claim undecided; the claim omitted the tools' own wording; the spec quoted one zero run without its spread; the line count was stale; test counts followed untracked results files (now given for a fresh checkout)

## Open questions
- Whether a 47-second median answer is acceptable (speed options in HANDOFF, 6 October)

## Top 3 fixes (for whoever picks this up)
1. Strip: drop a removed quote's citation wherever it stands in that sentence: done when the round 13 citation tests pass.
2. Figures: check years and durations against the tools' date fields instead of skipping them: done when the year and duration tests pass without new false alarms in the replay.
3. Speed: keep the chatbot's prompt cached across the intent classifier's call: done when the gold set's median drops with tool 23/24, behaviour 8/8 and 0/32 flags unchanged.
