# Validation: chatbot answers branch, ninth check, 2026-10-05
Verdict: rethink

Scope: `fix/chatbot-answers` against `main` (eleven commits, fixes in f511f83), code and docs. The eighth check's over-strips, cue nouns, replay and diagram findings are closed, and the four count shapes are flagged. But f511f83 opened two new ways for an invented quote to pass, and its comma rule both misses counts and flags ordinary dates. This is the ninth check in a row where fixing quote and date detection broke something else.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | 107 database rows match the endpoints, 0 mismatches (13 thin cells hold back the score by design); every bad bank, window or bucket value tried gets 422 |
| Grounded chatbot | DISPROVEN | 1783 tests pass in `tests/` before the new ones; but invented quotes after an opening mark at a line end, and words glued to a real quote's closing mark, pass unflagged; an invented count after "In September 25, vs." passes (tests/test_validate_chatbot_date_clauses_and_glued_words_probes.py, tests/test_validate_chatbot_date_clauses_and_glued_words_review_findings.py, strict xfail) |

## Confirmed issues
- Stray rule hides an opening mark [high, regression from f511f83] chatbot/agent.py:455-466: '"REAL" "' then an unclosed invented quote on the next line is neither flagged nor stripped; also after a citation, in a list, with curly marks
- Glued words after a real quote kept [high, regression from f511f83]: '“REAL”INVENTED.' and '"x"INVENTED' pass strip unflagged; 31c7e98 caught them
- Abbreviation ends the date clause [high, hidden since 7446c89] chatbot/guards.py:86: "In September 25, vs. 45 in August, posts were negative." hides the 25; also "approx.", "i.e."
- Ordinary dates flagged [med, regression from f511f83]: "By September 25, DBS scored 0.31.", "Up to September 25, the score was 0.31.", "Data to Sept 25 for all three banks." get the figure warning
- Smaller [low]: a bracket holding "of" after a date flags it ("September 25 (the end of the data)"); an inch mark after glued words still over-strips (also on 31c7e98)
- Docs [med]: the page's "no correct answer is changed" rests on generated answers saved nowhere; "16 minutes" for the before run is not cited to its source (plp.log timestamps)
- Docs [low]: HANDOFF's 5 October entry omits the citation cue for single quotes

## Open questions
- Keep patching the text checks, or change the design so the model never writes quote text (evidence shown from the search results by the system)?
- The claim's wording: still a decision on the team to-do (not yet republished)

## Top 3 fixes
1. Decide the design before another round: done when the owner has chosen between more patching, rendering evidence from tool results, and rewording the claim.
2. If patching: revert the stray-after-a-quote rule and the glued-words exemption to 31c7e98's behaviour, and end a clause only at sentence punctuation followed by a space and a capital or a line end: done when the round 9 tests pass and every earlier one still does.
3. Docs: save the generated answers behind any comparison the page cites, cite plp.log for the 16 minutes, add the citation cue to HANDOFF: done when an auditor rerun finds nothing medium or worse.
