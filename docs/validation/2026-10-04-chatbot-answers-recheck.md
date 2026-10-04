# Validation: chatbot answers branch, recheck after fixes, 2026-10-04
Verdict: fix first

Scope: `fix/chatbot-answers` against `main` (commits 7428beb and 8082469), code and docs. The first run's four code findings and nine doc findings are closed.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | API tests 434 passed, 2 skipped; `main`'s and the branch's plain functions on a read-only DB copy: 217 calls, 0 differences; `api/main.py` imports only those |
| Grounded chatbot | DISPROVEN | 143 grounding, replay and privacy tests pass (strip replay: flags 11 to 0, figures 10 to 0), but with strip (the default) an invented quote beside a "[2]" stays in the answer, flagged, not removed (test_strip_removes_an_invented_quote_beside_a_bare_marker, xfail) |

## Confirmed issues
- Strip keeps quotes beside markers [high] chatbot/agent.py:428-430: spans are found in the original answer, removal runs on the marker-stripped text; '"... for sure [2]"' and '"... for sure"[2]' survive (tests/test_validate_chatbot_reader_review_findings.py)
- Bare marker flags real quotes [med] chatbot/agent.py:283: any "[n]" flags, even after a search with verbatim quotes; a recorded unflagged answer (evidence-1, 2026-09-30 run) would now carry the warning, and strip appends an untrue "were removed" note (same file)
- Date patterns, edge cases [low] chatbot/guards.py:45-46: a count before a month word goes unchecked ("27\nSeptember", "21 Oct sentences"); lower-case dates are flagged ("september 25th"); "July 18, August 24, September 29." reads as dates (inherently ambiguous) (tests/test_validate_chatbot_reader_fix_probes.py, review_findings)
- Other markers [low] chatbot/agent.py `_BARE_MARK`: "[2, 3]", "[2-3]", "[100]" neither flagged nor stripped; a stored sentence with "[1]" in it is flagged and altered when quoted (fix_probes)
- Unclear trend still gives the raw change [low] chatbot/tools.py `chat_get_trend`: with "unclear", `delta_7d_vs_30d` or `change_from_previous_month` still reaches the model and passes the figure check if quoted
- Speed section figures [med] docs/evidence/chatbot-answers-2026-10-04.md:238-257: the cold start is 55% and 87% of two gaps and more than the third, not "about half of each"; the 8,192 window was slower on all three questions against the block run; 3.5-8.5 vs 6-17 s are prompt-reading times, not whole calls
- Smaller doc points [low]: "66 months" are the 66 of 72 with 5 or more sentences (evidence:28, DESIGN, HANDOFF); the Python rerun's OCBC answer had a wrong aside (evidence:156); the cause of the slowdown lacks the cache caveat (evidence:164, DESIGN); the `ps` output for the Ollama window wasn't saved; diagram 07 doesn't link the new evidence page; STATUS's line count is stale (already on `main`)

## Open questions
- `chatbot/judge.py:123` falls back to the shown answer, which now carries "[n]" markers and sources, for records without `model_answer` (outside scope)
- `test_start_refuses_a_port_it_does_not_own` fails while the API runs (known); `data/logs/plp.log.3` appeared during the run (log rotation)
- Are answers of about a minute acceptable for the demo? Fresh test questions, written apart from the prompt, are still needed

## Top 3 fixes
1. Strip: find the spans to remove in the text after markers are removed: done when both cases of test_strip_removes_an_invented_quote_beside_a_bare_marker pass without xfail.
2. Markers: flag a bare "[n]" only when it doesn't sit beside a verbatim retrieved quote (or drop it silently, with no warning or "removed" note), and cover "[2, 3]", "[2-3]": done when the review_findings marker tests and the fix_probes marker cases pass without xfail.
3. Date check edges and the Speed section: add a trailing guard to the day-first pattern and accept lower-case month names in a date; correct the evidence page's Speed figures: done when the date cases in both probe files pass (the comma-list case may stay a recorded limit) and an auditor rerun of the Speed section finds nothing medium or worse.
