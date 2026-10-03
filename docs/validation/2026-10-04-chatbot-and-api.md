# Validation: chatbot and API after the 4 Oct fixes, 2026-10-04
Verdict: fix first

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | `tests/test_api.py` 30 passed; every index endpoint equals its stored rows on a database copy (39 passed); `tests/test_validate_api_input_checks.py` 177 passed: an unknown `aspect` is a 422 on all 7 routes that take it, readable forms of all 11 keys give the key's body, an unknown chat `backend` or `role` is a 422 |
| Grounded chatbot | DISPROVEN | the strip replay keeps no unretrieved evidence (8B citation flags 11→0, 3B 16→0; 62 harness and replay tests pass), but a confirmed finding lets an invented percentage through unflagged (timestamp digits) |

## Confirmed issues
- Timestamp digits still vouch figures [high] chatbot/guards.py:156: `earliest`, `latest`, `date`, `as_of_date` and sentence-id digits feed accepted figures; "56%" passes once a coverage timestamp holds 56 (tests/test_validate_chatbot_grounding_second_review.py)
- Window argument echoed in reason [med] chatbot/tools.py:110: get_sentiment's reason repeats the model's `window`, vouching for its "37.5%" and its quote (same file)
- Strip after search loses formatting [med] chatbot/agent.py:336: bold, bullets and indentation removed from correct lines; orphan "[E9]" left (same file)
- Blockquote notes flagged as invented [med] chatbot/agent.py:86: a model's own "> Note:" line is flagged and stripped (same file)
- Reddit text can still reach Gemini [med] chatbot/backends/gemini_backend.py:85: history quotes cut at 1,200 characters, wrapped, unquoted or with inner quote marks are sent (tests/test_validate_gemini_reddit_privacy.py, 8 cases)
- Source parameter accepts any value [low] api/main.py:99,230: `source=reddit` returns 200 with empty data (second-review file)
- Backend name now case-sensitive [low] api/main.py:265: "Gemini" is a 422, accepted before 4 Oct (second-review file)
- Every chat failure becomes 503 [low] api/main.py:278: harness bugs read as "backend unavailable" and return internal text (source)

## Open questions
- `/aspects` publishes labels ("Capital & Liquidity") that `aspect` rejects; accept labels too?
- CNA article text still goes to Gemini (not Reddit, but team-only material)
- The working tree also holds an uncommitted guardrail draft (chatbot/agent.py, eval_gold_set.py, guards.py, prompts.py, run_eval.py), made in parallel by the main session, not by this run

## Top 3 fixes
1. Number check reads only data fields: done when the four timestamp and sentence-id tests and the window-echo tests pass without xfail
2. Gemini sees no Reddit text from history: done when the 8 privacy cases pass without xfail
3. Strip edits only the lines it changes, and notes aren't quotes: done when the formatting and blockquote tests pass without xfail
