# The chatbot evaluations again, on the re-scored database (13 Oct 2026)

**What this is.** On 12 Oct the database was re-scored: each sentence now has
one aspect, chosen by a local LLM, and the index is scored by the chosen
fine-tuned model ([evidence](rescore-rehearsal-2026-10-12.md)). The chatbot
reads that index and searches those sentences, so its evaluations were run
again to describe the system as it now stands. The chatbot's own code and
prompt did not change, apart from a filter that keeps six report disclaimer
lines out of its evidence search. The comparison is the live check of 6 Oct
on the old database ([chatbot-answers-2026-10-04.md](chatbot-answers-2026-10-04.md),
"Live check after the last round").

**Result.** The chatbot behaves as it did: the automated checks are within
one answer of the 6 Oct run on every line. What changed is the evidence
search, which is far more precise now that a sentence has one aspect. One
answer that the checks do not catch is wrong, and is described below.

All runs used `llama3.1:8b` through Ollama on the MacBook Air, started at
00:24 on 13 Oct by `data/run/eval-2026-10-13/run.sh`.

## The gold set and the conversations

| | Live check, 6 Oct | Re-scored database, 13 Oct |
|---|---|---|
| Tool selection | 23/24 | 23/24 |
| Behaviour (advice declined, no data said) | 8/8 | 8/8 |
| Citation fabrication flagged | 0/32 | 0/32 |
| Answers with a figure no tool returned | 0/32 | 1/32 |
| Evidence written without a search, removed | 3/32 | 4/32 |
| Answered by an input guard, without the model | | 6/32 |
| Median seconds per question | 47 | 59 |
| Scores stated, with their scale | 13 of 20 | 15 of 20 |
| Answers giving a share in % | 14 | 19 |
| Multi-turn turns correct | 9/9 (4/4 conversations) | 9/9 (4/4 conversations) |

Sources: `data/eval/chatbot_eval_summary_rescored_v2.md`,
`data/eval/chatbot_multiturn_summary_rescored_mt.md`,
`data/run/eval-2026-10-13/times_rescored_v2.jsonl` (median 58.9 s, mean
52.0 s, longest 115.8 s) and `data/run/overnight/readability.py` over the
results file (26 answers written by the model, median 72 words).

- **The one flagged figure was caught, as intended.** Asked whether
  sentiment on UOB's retail banking is improving, the model reported the
  7-day and 30-day figures correctly (17 and 43 sentences), then added that
  the answer was "based on 60 sentences overall". The tool returned no 60,
  and the sum is wrong anyway, since the 30 days include the 7. The figure
  check marked it in the answer.
- **The one tool-selection miss is the same question as on 6 Oct**, and its
  answer is wrong in ways the checks do not read. Asked for UOB's sentiment
  on net interest margin "in the last 7 days", the model called the trend
  tool, which had too few recent sentences and returned the all-time figure
  with a note saying so. The answer presented that all-time figure (-0.03 on
  190 sentences) as the last 7 days', and said the data runs to "September
  24th, 2023" where the tool said 2026. Neither is flagged: the figures are
  ones the tool returned, and the figure check skips years (a recorded
  limit). People rating the answers should expect this kind of error.
- **Answers are slower** (59 seconds against 47). The run followed a
  two-hour local-model job, and on 10 Oct the model's speed was shown to
  halve when the Mac is short of memory
  ([evidence](chatbot-timeout-and-speed-2026-10-10.md)); this run does not
  separate that from any effect of the new data.
- **Thin cells are more common now.** With one aspect a sentence, a bank's
  aspect can have a few hundred sentences all time and almost none in a
  week, so the fallback that tripped the second answer above will be reached
  more often than before.

## The evidence search

`chatbot.retrieval_eval` asks, for each bank and aspect, "What do people say
about <bank>'s <aspect>?", and counts how many of the top results people
labelled with that aspect (28 queries over the 1,277 labelled sentences).

| Search | hit@1 | hit@5 | precision@5 | MRR |
|---|---|---|---|---|
| By the aspect's name, no filter (unchanged) | 0.464 | 0.679 | 0.293 | 0.559 |
| With the stored-aspect filter, centroid aspects (1 Oct) | 0.429 | 0.750 | 0.329 | 0.559 |
| With the stored-aspect filter, LLM aspects (13 Oct) | **0.786** | **1.000** | **0.779** | **0.881** |
| Random order within the same filter, LLM aspects | 0.722 | 0.989 | 0.722 | 0.839 |

- **Precision more than doubles**: of the five sentences the chatbot is
  shown when it searches a bank's aspect, about four are ones people gave
  that aspect, where it was fewer than two.
- **The gain comes from the filter, not the ranking.** A random five from
  the filtered pool are already right 72% of the time, because the LLM's
  one aspect agrees with people far more often than the centroid method's
  six. Ranking by the aspect's name adds six points on top.
- **This is measured on labelled sentences only**, so it says how well the
  search finds sentences of the right aspect, not whether they are the most
  useful ones to quote.

## The checklist judge, and the ratings sheet

The judge (`qwen3:4b`, checklist prompt) scored the 32 gold-set answers:
17 as 1 (something invented), 5 as 2, 10 as 3. Its role is only to order
the answers people read first: it has caught every known invention in
earlier runs, but its reasons are often wrong, and the harness flagged no
fabricated citation in this run. Among the 26 answers the harness did not
flag, the judge scored 16 as 1 and 10 as 3.

`data/eval/ratings_sheet.csv` is the new blank sheet for the human
evaluation of 19 to 25 Oct: the 32 answers with the tool data behind each,
ordered with the judge's 1s first, then its 2s and 3s. The judge's scores
are not in the sheet. The earlier blank sheet, from the 2 Oct answers, is
kept as `ratings_sheet_2026-10-02.csv`.

## Not run again

- **The intent classifier and the provider comparison** (Ollama, Groq,
  Gemini): neither reads the index or the aspects, so the re-score does not
  change them.
- **The seven dashboard questions** of 6 Oct: the dashboard does not yet
  filter on the model version, so its Ask page was left until its owner has
  made that change.
- **A second re-score is likely** once the corpus has been re-classified
  under the new wealth wording
  ([evidence](wealth-definition-trial-2026-10-12.md)). It changes the
  wealth, retail and other aspects, so the gold set and the retrieval
  measure need one more run after it.

The results files hold no CNA text (they hold four broker research
passages), so, unlike the 4 to 6 Oct runs, they are committed.
