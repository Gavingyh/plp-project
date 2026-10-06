# Validation: chatbot answers branch, fourth check, 2026-10-04
Verdict: fix first

Scope: `fix/chatbot-answers` against `main` (four commits, latest f4b9145), code and docs. The third check's findings are closed; the new date rule has one regression, and some quote shapes were never checked, on `main` either.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | `main`'s and the branch's plain functions byte-identical over 376 calls; /sentiment/index equals `sentiment_index`; 13 bad requests all 422; API tests 434 passed, 2 skipped |
| Grounded chatbot | DISPROVEN | earlier-validation tests 190 passed, strip replays of 16 runs unchanged from b79fbc3, but a tool's date now hides an invented figure beside a month, and odd quote shapes go unchecked (23 xfail tests in tests/test_validate_chatbot_tool_date_findings.py) |

## Confirmed issues
- Tool date hides invented figures [high, regression] chatbot/guards.py `_YEARLESS_DATE`: the day match ends at `\b`, so with `data_runs_to` 2026-09-25 (in every sentiment result) "In September 25.7% were negative", "25% of sentences", "25,000 sentences" pass unchecked (`main` flags them); dates in the model's own search query or a link count as tool dates
- Date tests miss realistic tool data [high] tests/test_validate_chatbot_reader_fix_probes.py:40-47, tests/test_validate_chatbot_reader_grounding.py:93-97: the invented-figure tests give the tools no `data_runs_to`, so the regression passed the suite
- Quote shapes unchecked [high, also on `main`] chatbot/agent.py `_QUOTE_PATTERN`: '"..."(Reddit)', '"..."…', '|"..."|', a letter after the closing mark, a space inside the marks, single or angle quotes; none appears in 812 recorded answers
- Superseded rules described as current [med] docs/evidence/chatbot-answers-2026-10-04.md:199-229, docs/DESIGN.md:573-592: the capitalised-month and day-first date rules and "markers now go first" read as current
- Speed explanations [med] evidence:280-293, DESIGN:611-613: the cache reason for the cold start isn't shown (`main` stayed cached between branch runs); longer tool results explain 2.5 to 12 s of a 26 s median gap
- Smaller [low]: a real unclosed quote with its citation on the line is removed; a removed marker of 10 or more draws a figure warning; correct ranges ("Sept 25-26") are flagged; "[12-45]" vanishes from the shown text; the evidence lift condition (DESIGN:602), "no ids" (evidence:169) and "of 72 stored" (evidence:28) are misstated; the turn diagram omits strip mode (also on `main`)

## Open questions
- Quote shapes: broaden detection to any paired quote marks around three or more words (rare false flags), or record the shapes as a known limit in the to-do and word the claim to match?
- chatbot/agent.py docstrings say enforcement is off by default; config sets strip (outside scope)

## Top 3 fixes
1. Dates: read tool dates only from date fields (`data_runs_to`, `date`, `earliest`, `latest`), and never skip a day followed by `%`, `.` and a digit, or `,` and a digit: done when the 23-case file's date tests pass without xfail and the realistic-date variants are added to the two older tests.
2. Quote shapes: settle the open question, then make the chosen rule hold: done when the shape tests pass, or are recorded as a known limit in the to-do with the claim's wording changed.
3. Docs: rewrite the superseded passages in the past tense, state the measured causes of the slowdown without the cache inference, fix the low wordings: done when an auditor rerun finds nothing medium or worse.
