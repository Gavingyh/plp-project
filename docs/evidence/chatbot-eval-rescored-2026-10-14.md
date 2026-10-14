# The chatbot evaluations on the database of 14 Oct 2026

**What this is.** On 14 Oct the corpus's aspects were made again under the
team's wealth ruling and the database re-scored
([evidence](rescore-wealth-wording-2026-10-14.md)). The chatbot's code and
prompt did not change. Its evaluations were run once more so that the
report describes the database as submitted. The earlier runs are the live
check of 6 Oct on the old database and the run of 13 Oct on the first
re-score ([chatbot-eval-rescored-2026-10-13.md](chatbot-eval-rescored-2026-10-13.md)).

**Result.** The chatbot's behaviour is unchanged on every automated check.
The evidence search's precision is lower than on 13 Oct (0.66 against 0.78)
while the share of relevant sentences in the pool it ranks is a little
higher (0.74 against 0.72): ranking by the aspect's name no longer adds
anything to the stored aspect's filter.

All runs used `llama3.1:8b` through Ollama on the MacBook Air, started at
08:11 on 14 Oct by `data/run/eval-2026-10-14/run.sh`, with nothing else
running.

## The gold set and the conversations

| | 6 Oct, old database | 13 Oct, first re-score | 14 Oct, submitted database |
|---|---|---|---|
| Tool selection | 23/24 | 23/24 | 23/24 |
| Behaviour (advice declined, no data said) | 8/8 | 8/8 | 8/8 |
| Citation fabrication flagged | 0/32 | 0/32 | 0/32 |
| Answers with a figure no tool returned | 0/32 | 1/32 | 0/32 |
| Evidence written without a search, removed | 3/32 | 4/32 | 4/32 |
| Answered by an input guard, without the model | | 6/32 | 6/32 |
| Median seconds per question | 47 | 59 | 40 |
| Scores stated, with their scale | 13 of 20 | 15 of 20 | 12 of 18 |
| Answers giving a share in % | 14 | 19 | 17 |
| Multi-turn turns correct | 9/9 | 9/9 | 9/9 |

Sources: `data/eval/chatbot_eval_summary_rescored2_v2.md`,
`data/eval/chatbot_multiturn_summary_rescored2_mt.md`,
`data/run/eval-2026-10-14/times_rescored2_v2.jsonl` (median 39.75 s, mean
38.5 s, longest 94.1 s) and `data/run/overnight/readability.py` over the
results file (26 answers written by the model, median 69 words).

- **The same question fails in the same way.** Asked for UOB's sentiment on
  net interest margin "in the last 7 days", the model again called the trend
  tool, received the all-time figure with a note that the recent windows
  were too thin, and reported it as the last 7 days' (-0.07 on 188
  sentences). It is the one tool-selection miss, as on 6 and 13 Oct, and
  the quote and figure checks pass it because every number was returned by
  a tool. A wrong answer that repeats is a fault to fix or to declare, not
  a chance error.
- **Speed follows the machine, not the data.** 40 seconds on a quiet Mac,
  59 on 13 Oct straight after a two-hour local-model job, 47 on 6 Oct.
- **Two answers say "out of 1"** for the score's scale, wording the prompt
  discourages; none did on 13 Oct.

## The evidence search

`chatbot.retrieval_eval`: 28 queries, one for each bank and aspect with
enough labelled sentences, judged against the aspect people gave each of
the 1,277 first-round sentences.

| Search, with the stored-aspect filter | hit@1 | precision@5 | MRR |
|---|---|---|---|
| Centroid aspects (1 Oct), by the aspect's name | 0.429 | 0.329 | 0.559 |
| First re-score (13 Oct), by the aspect's name | 0.786 | 0.779 | 0.881 |
| the same, random order within the filter | 0.722 | 0.722 | 0.839 |
| Submitted database (14 Oct), by the aspect's name | 0.679 | 0.664 | 0.810 |
| the same, by the question's words | 0.500 | 0.621 | 0.698 |
| the same, random order within the filter | 0.738 | 0.738 | 0.853 |

Precision at 5 by aspect, by the aspect's name with the filter (mean over
the banks), against a random five from the same pool:

| Aspect | 13 Oct | random | 14 Oct | random |
|---|---|---|---|---|
| asset_quality | 1.00 | 0.96 | 0.87 | 0.89 |
| capital_liquidity | 0.87 | 0.87 | 0.80 | 0.85 |
| dividend_policy | 0.60 | 0.73 | 0.60 | 0.83 |
| income_profit_results | 0.80 | 0.87 | 0.60 | 0.80 |
| investor_stock_sentiment | 0.87 | 0.47 | 0.87 | 0.54 |
| macro_market_environment | 0.70 | 0.67 | 0.40 | 0.55 |
| management_guidance | 0.53 | 0.59 | 0.33 | 0.58 |
| net_interest_margin | 0.60 | 0.63 | 0.60 | 0.66 |
| retail_banking_sentiment | 0.87 | 0.86 | 0.73 | 0.84 |
| wealth_business | 0.87 | 0.51 | 0.73 | 0.75 |

- **The filter got slightly better; the ranking stopped helping.** The
  share of the filtered pool that people labelled with the asked aspect rose
  from 0.72 to 0.74, and for wealth from 0.51 to 0.75, which is the ruling
  doing its work. The top five by the aspect's name went from six points
  above a random five to seven below.
- **Part of the fall is the reference, not the search.** Relevance is judged
  by people's labels, made under the older reading of wealth. A sentence the
  ruling moved, such as a bank's reported wealth income now filed under
  results, counts as a miss wherever it is ranked high. The falls sit in the
  aspects that received such sentences: results, macro, guidance, retail.
- **Part is noise.** 28 queries of five sentences each is 140 judgements; a
  change of 0.11 is about 16 of them.
- **What stands either way:** precision is about twice what it was when a
  sentence carried six aspects (0.66 against 0.33), the gain comes from the
  stored aspect, and ranking by FinBERT similarity within the pool is not
  reliably better than chance.

## The judge and the ratings sheet

The checklist judge (`qwen3:4b`) scored the 32 answers 15 as 1, 5 as 2 and
12 as 3; among the 26 the harness did not flag, 14 as 1 and 12 as 3.
`data/eval/ratings_sheet.csv` is exported again from this run's answers,
with the judge's 1s first, for the human evaluation. It replaces the sheet
of 13 Oct, which was blank. The results files hold no CNA text and are
committed.
