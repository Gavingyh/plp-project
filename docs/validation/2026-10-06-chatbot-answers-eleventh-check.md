# Validation: chatbot answers branch, eleventh check, 2026-10-06
Verdict: fix first

Scope: `fix/chatbot-answers` against `main` (fourteen commits, fixes in f7a90fb), code and docs. The tenth check's line-ending and docs findings are closed. Its four other code findings are partly closed. The quote marks themselves now hold: the tester found every invented shape removed, de-quoted or flagged. What remains is about which words a citation vouches for: a link or a citation placed before the words still vouches for a two-word invented quote, and a correct citation is cut after a scare quote in the sentence before.

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | 642 stored index values compared, 0 mismatches; `main` and the branch give byte-identical tool outputs; 17 of 17 bad values get 422 |
| Grounded chatbot | DISPROVEN | 2146 tests pass in `tests/` (5 expected failures, all recorded limits); 25 invented shapes removed, de-quoted or flagged in strip mode, all flagged in off mode; but 14 strict-xfail tests keep a cited invented term, an invented passage with a citation, or an unchecked figure (tests/test_validate_chatbot_citation_vouching_probes.py, tests/test_validate_chatbot_citation_vouching_review_findings.py) |

## Confirmed issues
- Short quote cited by a link or a leading citation [high, also on `main`] chatbot/agent.py:1241: 'One user called OCBC "a scam" (https://news.example/x).' and 'According to CITE, one user called OCBC "a scam".' pass both modes unchanged
- A scare quote cuts the next sentence's citation [med, regression from f7a90fb]: 'DBS markets it as a "super app". Users complain the app is slow at night CITE.' loses its correct citation, and off mode flags it
- A returned term shields an invented passage's citation [med, from 03dc631] chatbot/agent.py:1337: 'One user: ‹INVENTED›, "slow" CITE' keeps the citation
- Figure vouched by common words [med, narrower than on `main`] chatbot/agent.py:672: evidence 'Around 37% of the bank's profit' lets '37% of the posts were negative' pass
- Glued quote across a line break [med] chatbot/agent.py:1122: "wrote’the bank will cut its\ndividend next year’ CITE" keeps the opening mark
- Smaller [low]: a real blockquote loses its citation after a de-marked line; [E1] markers with no search pass; off mode flags a returned blockquote with its citation (also on `main`)
- Replay: two recorded answers now flag a results-report figure the model reworded ('0.9%', '16%'); false alarms, the cost of the narrower figure rule
- Docs [med]: diagram 07 still describes the old one-or-two-word exception and doesn't say strip cuts citations; DESIGN's costs omit the new figure false alarms. [low] one of three answers quoted as '(20% of lending portfolio)' says 'approximately 20%'

## Open questions
- Keep going? Eleven checks; the last two rounds took about an hour and two and a half hours, and each closes the reported cases but finds new ones at the edges
- The claim's wording: still a decision on the team to-do (not yet republished)

## Top 3 fixes
1. Citations: a citation vouches for the words of its own sentence only (before or after it, a link included); a scare quote in another sentence never touches it: done when the round 11 citation tests pass and every earlier one still does.
2. Figures: a figure in evidence text vouches only when the words round it in the answer, apart from common words, match the sentence's: done when the common-words tests pass.
3. Docs: diagram 07 and DESIGN's costs: done when an auditor rerun finds nothing medium or worse.
