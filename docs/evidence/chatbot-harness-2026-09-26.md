# Chatbot harness: before and after

Measured 2026-09-26 on the 23-question gold set (`chatbot/eval_gold_set.py`),
local `llama3.2:3b` via Ollama, database as of the 26 Sep snapshot. What
changed is DESIGN decision 19: conversation memory, an input guard for
advice-seeking and off-topic questions, an output check on every figure, a
check on cited sentence ids, evidence packaged for citing, and decoding
temperature set to 0.2 (it was Ollama's runtime default of 0.8, since
neither local model sets its own).

```bash
CHATBOT_TEMPERATURE=0.2 .venv-plp/bin/python3 -m chatbot.run_eval --backend ollama --tag <tag>
```

## Results

| | before (10 Sep, prompt only) | harness, 0.8 | harness, 0.2 (first run) | harness, 0.2 (final) |
|---|---|---|---|---|
| advice and out-of-scope questions handled correctly | 2 / 7 | 7 / 7 | 6 / 7 | 7 / 7 |
| answered by an input guard, without the model | — | 6 / 23 | 6 / 23 | 7 / 23 |
| correct tool chosen | 12 / 16 | 10 / 16 | 13 / 16 | 12 / 16 |
| invented citation flagged | 10 / 23 (43%) | 11 / 23 (48%) | 10 / 23 (43%) | 11 / 23 (48%) |
| answers carrying a figure no tool returned | not checked | 8 / 23 | 10 / 23 | 8 / 23 |
| backend errors | 2 (timeouts) | 0 | 0 | 0 |

Transcripts: `data/eval/chatbot_eval_results_llama3.2_3b_harness_*.jsonl`.
The "final" column is after fixing the false alarms described below, and
counts `oos-3` as handled: the guard answered it, but the automated checker
didn't know the guard's wording until it was taught (see below).

## What the numbers say

**Advice and scope are now handled by code, every time.** All seven
behaviour questions are answered by a guard before the model runs, so the
result no longer depends on the model or the temperature. Caveat: the advice
patterns were written and unit-tested on phrasings made up independently of
the gold set, but the off-topic rule was added *after* the first run showed
the weather question (`oos-3`) reaching the model, which answered with the
literal text `{}`. For that rule the gold set is not an independent test; the
planned frozen evaluation set (PLAN.md) is.

**Invented citations are detected, not prevented.** The rate stayed at
43–48% with evidence packaged for copying (a ready-made `cite_as` field),
a prompt rule to copy it, and a lower temperature. The 3B model writes
plausible-looking evidence (Bloomberg and Reuters URLs, numeric "sentence
ids" such as 123456) whether or not it retrieved anything. Only a stronger
model can reduce that; this makes the choice of demo model (PLAN.md, O3)
more important, not less.

**The number check catches inventions the other checks don't name.** In the
final run it flagged 19 figures in 8 answers. Checked by hand against the
raw tool output, 18 were invented: 17 fake numeric sentence ids and one
sentiment score (0.45) that no tool returned. The one false alarm was "19"
in "COVID-19", now excluded. In a live three-turn conversation it also
caught invented dividend yields ("around 3.5%", "4.1%"), which the citation
check would have flagged only as part of a wider warning.

**Temperature: no clear effect at this sample size.** Across one run at 0.8
and two at 0.2, tool selection was 10 / 16 against 13 and 12, and invented
citations 48% against 43% and 48%. Single runs of 23 questions can't
separate that from noise. 0.2 stays the default on the course's decoding
guidance for factual question answering (TPML Day 3), not on this evidence.

## Memory, tested live

```
Q: How is sentiment on DBS's dividends?   -> get_sentiment(DBS, dividend_policy); score 0.0285
Q: And OCBC?                               -> get_sentiment(OCBC, dividend_policy); score 0.0429
Q: Should I buy it?                        -> advice guard; no model call
```

The follow-up carried the aspect over from the first turn, and the scores
are the ones the tools returned. After this run the advice reply was changed
to name the bank from the conversation (it said "these banks").

## False alarms found and fixed during the evaluation

| alarm | cause | fix |
|---|---|---|
| "24" in "September 24th, 2026" | only ISO dates were excluded | dates written out in words are excluded |
| "$0.54 per share" quoted from real evidence | only numeric tool fields were accepted | figures inside retrieved text count as quotable (not as a basis for percentages) |
| an honest consensus answer flagged as a fabricated quote | the quote pattern matched the gap between two short quotes, `"buy". … "hold"` | a quote must open and close at a word boundary; this alarm predated the harness |
| "19" in "COVID-19" | a number glued to a word was read as a figure | excluded |
| the harness's own "couldn't answer" reply flagged as a fabricated quote | it contains a quoted example question | the checks now run on the model's text only |

Each has a regression test in `tests/test_chatbot_harness.py`.
