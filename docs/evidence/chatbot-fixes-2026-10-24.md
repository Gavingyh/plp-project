# The chatbot after the misdescription fixes, local and OpenAI (24 Oct 2026)

**What this is.** A person rated the 32 gold-set answers and found 7 of the 26
the model wrote unfaithful although every number in them was a tool's: a
wrong year for the data (3), a wrong period (2), a wrong rank (1), wrong
strongest and weakest topics (1) ([human-ratings-2026-10-24.md](human-ratings-2026-10-24.md)).
The fixes: the tools now give the data's end date, a bank's rank, a
comparison's ranking and a bank's strongest and weakest topics as sentences
for the model to copy; a score for one topic states that it has no breakdown;
and a year in an answer that no tool returned and the question didn't name is
flagged like any unverified figure (`tests/test_chatbot_misdescription_fixes.py`).
This note measures them on the local model and on OpenAI's `gpt-6-luna`, the
chatbot's default since the teammates' OpenAI change.

**Result.** The fixes removed the rated faults of date, rank and topics for
both models. Asked the 7 rated questions three times each, the local model
was right in 16 of 21 tries and `gpt-6-luna` in 21 of 21. The fault the
local model still makes is reporting a different score when a topic has too
little recent data; `gpt-6-luna` said there was not enough data in all six
such tries. The automated checks are unchanged or better for the local model
and the same for `gpt-6-luna` once two misread answers are allowed for.

## Gold set (32 questions), automated checks

Same database (data to 25 Sep 2026), same 32 questions. Before: the merged
code without the fixes. After: the fixed code.

| Check | Local, before | Local, after | gpt-6-luna, after |
|---|---|---|---|
| Right tool chosen | 24 / 24 | 24 / 24 | 23 / 24 |
| Advice declined, missing data admitted | 8 / 8 | 8 / 8 | 6 / 8 (8 / 8 on reading) |
| Citation fabrication flagged | 0 / 32 | 0 / 32 | 0 / 32 |
| Answered by an input guard, not the model | 6 / 32 | 6 / 32 | 6 / 32 |
| Answers carrying a figure no tool returned | 2 / 32 | 1 / 32 | 1 / 32 (a false alarm) |
| Conversation turns correct | not run | 9 / 9 | not run |
| Median seconds per model-written answer | 43 | 78 | 6.6 |

Sources: `data/eval/chatbot_eval_summary_merged_v2.md`,
`chatbot_eval_summary_fixes_v2.md`, `chatbot_eval_summary_luna_fixes_v2.md`,
`chatbot_multiturn_summary_fixes_mt.md`; times from
`data/run/eval-2026-10-24/times_merged_v2.jsonl`,
`data/run/eval-2026-10-24b/times_fixes_v2.jsonl` and
`data/run/eval-2026-10-24-luna/cost.jsonl`.

- The local run after the fixes shared the processor with an install test and
  a search-model test, so its time is not comparable with the run before.
- The local "after" flag is the year 2023 in `consensus-2`, caught by the new
  check; the answer the reader saw no longer contains it.
- `gpt-6-luna`'s tool miss is `compare-3`: it compared UOB and DBS with two
  `get_sentiment` calls instead of `compare_banks`, with every figure right.
  Its flagged figure is the 24 of "24 September 2026", a date.
- `gpt-6-luna`'s two behaviour misses (`oos-1`, `oos-2`) decline correctly
  ("I only have sentiment data for DBS, OCBC and UOB, so I can't report
  sentiment on Standard Chartered's dividend policy"), in wording the
  check's phrase list doesn't recognise.
- `gpt-6-luna` searched for evidence 18 times, once without a topic.

## The seven rated questions, three tries each

Each question asked three times in a fresh conversation. Read by the AI
assistant against the tool results, not rated by a person. A try counts as
right when it has neither the rated fault nor any other misdescription.

| Rated fault (question) | Local: tries right | gpt-6-luna: tries right |
|---|---|---|
| Wrong year (`lookup-1`, `trend-2`, `lookup-9`) | 8 / 9 (years right in 9) | 9 / 9 |
| Wrong rank (`lookup-2`) | 3 / 3 | 3 / 3 |
| Wrong strongest and weakest topics (`compare-5`) | 2 / 3 | 3 / 3 |
| All-time figure given as the last 7 days (`thin-1`) | 1 / 3 | 3 / 3 |
| Two months given as this week (`thin-2`) | 2 / 3 | 3 / 3 |
| **Total** | **16 / 21** | **21 / 21** |

The five local misses:

- `thin-1`, two tries: with no 7-day figure for UOB's net interest margin,
  the model fetched UOB's overall 7-day score (+0.275, 60 sentences) and
  presented it as the margin's, with the overall rank and topics.
- `thin-2`, one try: calls August's figure "this week". The other two give
  the right months but don't say there is no weekly figure.
- `compare-5`, one try: pairs the three banks' sentence counts with the wrong
  banks.
- `lookup-1`, one try: names a sub-topic ("payout ratio") the tools never
  returned.

In two `lookup-2` tries the local model also says, awkwardly but truly, that
the tool gives no sub-topics. `gpt-6-luna`'s answers to `thin-1` and `thin-2`
say there is not enough data for the period asked, and `thin-2`'s add that
the monthly comparison doesn't show this week's trend.

Answers: `data/run/eval-2026-10-24b/probe_rated.jsonl` (local),
`data/run/eval-2026-10-24-luna/probe_rated.jsonl` (`gpt-6-luna`). Kept out of
git with the gold-set results files, whose recorded tool results contain CNA
and broker-research text.

## Cost of the gpt-6-luna run

US$0.0158 in all: US$0.0089 for the 32 questions and US$0.0069 for the 21
tries, about US$0.0003 a model-written answer, from the token counts OpenAI
reported (`data/run/eval-2026-10-24-luna/cost.jsonl`), at US$0.10 a million
input tokens, 0.01 cached and 0.50 output, the prices in
[chatbot-benchmark-2026-10-24.html](chatbot-benchmark-2026-10-24.html). The
cap, US$0.05, was never reached.

## Limits

- The 32 questions were used while the fixes were made, and the seven are the
  ones the fixes target, so these are not held-out results.
- The three-try results are the AI assistant's reading, not a person's
  rating; a person should check them before the report relies on them.
- `gpt-6-luna` never sees Reddit, CNA or broker-research text (it sees that a
  sentence exists, its bank, date and sentiment), so its evidence comes from
  results reports and news only. The two models answered from different
  evidence.
