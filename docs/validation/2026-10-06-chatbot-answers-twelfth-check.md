# Validation: chatbot answers branch, twelfth check, 2026-10-06
Verdict: fix first (no further fix rounds, by the owner's decision; what is left is recorded)

Scope: `fix/chatbot-answers` against `main` (fifteen commits, fixes in 174c77d), code and docs. Most of the eleventh check's findings are closed: link and leading citations, scare quotes in another sentence, a returned term next to an invented passage, a glued quote across a line, `[E1]` markers with no search, the reworded-figure false alarms. Four gaps remain and are recorded as known limits: the strict expected failures, and the list on the evidence page. The auditor's run returned no report this round, so the docs weren't re-audited.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | 48 of 48 tool outputs identical on `main` and the branch; 514 index rows, 0 mismatches; every bad bank, window or bucket value tried gets 422 on every route that takes one; `api/` unchanged |
| Grounded chatbot | DISPROVEN | 2280 tests pass in `tests/` (5 expected failures, recorded limits); 20 invented-quote shapes stripped and flagged in off mode, 7 of 7 correct answers kept; replay: the reworded-figure false alarms cleared, nothing else changed; but 25 strict-xfail cases remain (tests/test_validate_chatbot_round12_probes.py, tests/test_validate_chatbot_round12_review_findings.py), now marked as recorded limits |

## Confirmed issues (recorded limits)
- Source note after a quote keeps its citation [high, regression from 174c77d] chatbot/agent.py:1449: 'One user called OCBC "a scam". (Reddit, CITE)' passes both modes; f7a90fb cut it
- Nearest-word figure rule vouches counts [med, from 174c77d; `main` vouches for any figure in retrieved text] chatbot/agent.py:747: "DBS raised fees by 45 dollars" vouches for "45 posts about DBS fees"; "the DBS app had 30 minutes of downtime" for "30 negative posts"
- Invented text in backticks keeps its citation [med, also at f7a90fb]
- A returned blockquote with its citation on its own '>' line is flagged in off mode [low]

## Open questions
- The claim's wording ("never", or what is checked plus the Known limits list): a decision on the team to-do, not yet republished
- Whether answers of about a minute are acceptable; merging and pushing the branch

## Top 3 fixes (for whoever picks this up)
1. Citation reach: a source note in the sentence right after a quote vouches for that quote: done when the source-note tests pass.
2. Figures: a figure in evidence text vouches only for the same kind of quantity (its unit or noun matches): done when the subject-word tests pass and the replay shows no new flags.
3. Backticks: read a code span holding three or more words as a quote: done when the backtick test passes.
