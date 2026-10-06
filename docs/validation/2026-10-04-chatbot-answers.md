# Validation: chatbot answers branch, 2026-10-04
Verdict: fix first

Scope: the changes on `fix/chatbot-answers` against `main` (chatbot code, config, tests and their docs).

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | API tests: 434 passed, 2 skipped. `main`'s and the branch's `chatbot/tools.py` on a read-only copy of plp.db: 297 comparisons, 0 differences. `api/main.py` imports only the plain functions |
| Grounded chatbot | DISPROVEN | 129 grounding, harness and privacy tests pass (strip replay: citation flags from 11 to 0), but three holes confirmed by xfail tests in `tests/test_validate_chatbot_reader_findings.py` and `tests/test_validate_chatbot_reader_grounding.py` (below) |

## Confirmed issues
- Year-less date pattern hides figures [high] chatbot/guards.py:38-39: "A score of 0.45 may suggest caution.", "Only 47 may be reliable." and "In September 45 sentences were negative." are flagged on `main` and not on the branch (test_a_figure_beside_a_month_word_is_still_checked)
- The model's own aspect exempts an invented quote [med] chatbot/tools.py `_topic_name`, chatbot/agent.py `_collect_wording`: a quote equal to an unknown aspect argument passes with no search, and strip keeps it (test_a_quote_of_the_models_own_aspect_argument_is_unverified)
- Numbered markers leak into API follow-ups [med] chatbot/agent.py `_strip_warnings`: the earlier answer's "[n]" markers and Sources links go back to the model; "As noted in [2], it fell." passes with no search (test_a_follow_up_citing_an_earlier_number_without_a_search_is_flagged)
- Trend sentence contradicts its figures [med] chatbot/tools.py `_month_on_month`: direction from unshrunk scores, figures shrunk; prints "(+0.27, 6 sentences) was up on (+0.44, 200 sentences)" (test_month_on_month_words_agree_with_the_figures_they_print)
- Evidence page misattributes and overstates [med] docs/evidence/chatbot-answers-2026-10-04.md: the invented rankings are put under round 3 (they were seen in the browser on round-1 code; ui_after.json shows them right); "12 of the 32" should be 13 of 33, or 10 of 30 named topics; the main-against-branch gaps include an uncached first call (14.6 to 26.1 s against 0.4 to 0.6 s); "68 to 61 seconds" is credited to hidden fields from one run each, and the committed version was never timed; the trimmed median is 41 s, not 42
- STATUS and HANDOFF overstate [med] docs/STATUS.md (the scale was given with 13 of 19 scores, not always, and the evidence answer had no numbered citation); docs/HANDOFF.md says five rounds (six on the branch, plus the before run)
- Smaller [low]: the polar boost does nothing without a filter (chatbot/tools.py:473; retrieval returns no label); `data_runs_to` isn't tied to the index build (chatbot/tools.py:340); "lifting" topics may all be negative (chatbot/tools.py:363); the 4,096-token window is cited without its source (the Ollama runner's command line); the before-run times come only from the browser

## Open questions
- `tests/test_scripts.py::test_start_refuses_a_port_it_does_not_own` fails whenever the project's API is running, and `test_stop_is_idempotent` stops it: add to the to-do (outside this scope)?
- Are answers of about a minute acceptable for the demo on this Mac?
- The gold set was used to tune the prompt: who writes fresh questions to measure it fairly?

## Top 3 fixes
1. Narrow the year-less date patterns (an ordinal day, or a day of 31 or less not followed by a decimal; "May" only capitalised): done when the three cases in test_a_figure_beside_a_month_word_is_still_checked pass without xfail and tests/test_chatbot_reader.py still passes.
2. Exempt only wording the model can't choose (`topic_name` only for known aspect keys), and drop "[n]" markers and the Sources list from history rebuilt from messages: done when the aspect-quote and follow-up tests pass without xfail.
3. Make `trend_in_words` agree with its figures (print the unshrunk scores, or state no direction when they disagree) and correct the evidence page, STATUS and HANDOFF as the auditor found: done when the trend test passes without xfail and an auditor rerun on those files finds nothing medium or worse.
