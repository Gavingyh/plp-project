# Chatbot evaluation, extended: gold set v2, conversations, retrieval, a judge

PLAN section 3 asks for a frozen ~30-question gold set, multi-turn
scenarios, retrieval Hit@K and MRR, and faithfulness via an LLM judge
calibrated on human ratings. Built 2026-10-01. The retrieval results are
below; the live runs of the gold set, the conversations and the judge are in
[Live runs](#live-runs).

## What was built

| piece | where | what it does |
|---|---|---|
| gold set v2 | `chatbot/eval_gold_set.py` `GOLD_SET_V2` | v1's 23 questions (frozen 26 Sep, so past runs stay comparable) plus 9 on the aspects added 30 Sep and one more uncovered bank: 32 |
| conversations | `MULTI_TURN` | 4 conversations, 9 turns, where a later turn omits the bank or aspect ("And OCBC?", "Has that improved lately?") or turns to advice mid-conversation |
| runner | `chatbot/run_eval.py --set v2`, `--multi-turn` | the same automated checks per question or turn; a conversation passes only if every turn does |
| retrieval metrics | `chatbot/retrieval_eval.py` | Hit@K, precision@K and MRR of evidence search against the human aspect labels |
| faithfulness judge | `chatbot/judge.py` | an LLM scores each answer 1–3 against the tool data; `sheet` exports the same answers blank for people; `calibrate` reports agreement and weighted κ |

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m chatbot.retrieval_eval
OLLAMA_MODEL=llama3.1:8b .venv-plp/bin/python3 -m chatbot.run_eval --backend ollama --set v2 --tag llama8b_v2
OLLAMA_MODEL=llama3.1:8b .venv-plp/bin/python3 -m chatbot.run_eval --backend ollama --multi-turn --tag llama8b
.venv-plp/bin/python3 -m chatbot.judge sheet --results data/eval/chatbot_eval_results_llama8b_v2.jsonl
.venv-plp/bin/python3 -m chatbot.judge judge --results data/eval/chatbot_eval_results_llama8b_v2.jsonl --model qwen3:4b --no-think
.venv-plp/bin/python3 -m chatbot.judge calibrate --ratings data/eval/ratings_sheet.csv --judged data/eval/judge_qwen3_4b.jsonl
```

The judge is a different model (`qwen3:4b`) from the one it judges
(`llama3.1:8b`), so it isn't grading itself.

## Retrieval: evidence search finds the topic only when the query names it

**Method.** Every relevance judgement is human: for each bank, and each
aspect with at least 3 labelled sentences for that bank (28 queries), the
bank's labelled sentences (197 for OCBC, 331 for UOB, 749 for DBS) are ranked with the score
`search_evidence` uses (FinBERT mean-pooled cosine plus 0.15 × word
overlap), and a sentence counts as relevant if people gave it that aspect.
Ranking the whole corpus would leave most retrieved sentences without a
judgement. A random ordering is the baseline, computed exactly.

| query | hit@1 | hit@5 | hit@10 | precision@5 | MRR |
|---|---|---|---|---|---|
| a user's question: "What do people say about DBS's asset quality / provisioning?" | 0.107 | 0.286 | 0.393 | 0.121 | **0.217** |
| random ordering | 0.098 | 0.319 | 0.478 | 0.098 | 0.217 |
| the aspect's name alone: "Asset Quality / Provisioning" | 0.464 | 0.679 | 0.750 | 0.293 | **0.559** |
| question, ranking only sentences stored under that aspect (`search_evidence(aspect=…)`) | 0.107 | 0.357 | 0.464 | 0.136 | 0.240 |
| random, within those | 0.136 | 0.399 | 0.564 | 0.136 | 0.269 |
| name alone, within those | 0.429 | 0.750 | 0.786 | 0.329 | 0.559 |

By aspect, for question queries without the filter, hit@5 is 1.00 for
investor stock sentiment and retail banking, 0.33 for dividend policy and
wealth, and 0.00 for the other six (asset quality, capital and liquidity,
income results, macro, management guidance, NIM), where random would find
one at least some of the time.

**What it shows.** Phrased as a question, a query embeds like a Reddit
question, so it pulls up Reddit chatter (stock and retail-banking talk)
whatever the topic: no better than random overall, and worse than random
for the six aspects that live in earnings text. Named plainly, the same
search is far better than random (MRR 0.56 against 0.22). FinBERT's
mean-pooled vectors weren't trained for similarity, which is the same
weakness behind seed-centroid aspect assignment (0.413,
[llm-aspect-classifier-2026-10-01.md](llm-aspect-classifier-2026-10-01.md)).
The stored-aspect filter adds little, because that assignment gives each
sentence 6.4 aspects.

**The cheap fix, built behind a flag.** With `CHATBOT_ASPECT_QUERY=1`,
when the model passes an aspect, `search_evidence` ranks by the aspect's
readable name plus the question's own topic words (question words, bank
names and words already in the name dropped), and uses the same text for
the word-overlap boost. The first version kept the original question for the
overlap boost and reached only MRR 0.337: question words ("what", "people",
"say") favour chatter in the overlap term too.

| query | hit@1 | hit@5 | hit@10 | precision@5 | MRR |
|---|---|---|---|---|---|
| question (today's default) | 0.107 | 0.286 | 0.393 | 0.121 | 0.217 |
| `CHATBOT_ASPECT_QUERY=1` | 0.464 | 0.679 | 0.750 | 0.293 | **0.559** |
| `CHATBOT_ASPECT_QUERY=1`, with the stored-aspect filter | 0.429 | 0.750 | 0.786 | 0.329 | 0.559 |

In this test the cleaned question is exactly the aspect's name, so the flag
equals the name-only row by construction; a live question with topic words
of its own ("a dividend cut") keeps them, and that case is unmeasured. The
flag stays off until the team chooses to switch it on and re-runs the gold
set with it. A sentence-similarity embedding model would likely do better
still, but it is a new dependency.

Caveats: 28 queries; the pool is the labelled sentences, which were sampled
(train/dev stratified, test random), not the whole corpus; relevance is the
human aspect, so a sentence on the asked topic labelled under a neighbouring
aspect counts as a miss.

## Live runs

Run on the evening of 2026-10-01, `llama3.1:8b`, temperature 0.2, database
as of 30 Sep. The first run shared Ollama with another job and lost 6 of 32
questions to timeouts, so it was repeated on an otherwise idle machine
(22:54–23:34). The repeat is the one reported; the first run's files are kept
for the record (`*_llama8b_v2.*`, `*_multiturn_*_llama8b.*`).

```bash
OLLAMA_MODEL=llama3.1:8b .venv-plp/bin/python3 -m chatbot.run_eval --backend ollama --set v2 --tag llama8b_v2_idle
OLLAMA_MODEL=llama3.1:8b .venv-plp/bin/python3 -m chatbot.run_eval --backend ollama --multi-turn --tag llama8b_idle
.venv-plp/bin/python3 -m chatbot.judge sheet --results data/eval/chatbot_eval_results_llama8b_v2_idle.jsonl
.venv-plp/bin/python3 -m chatbot.judge judge --results data/eval/chatbot_eval_results_llama8b_v2_idle.jsonl --model qwen3:4b --no-think
.venv-plp/bin/python3 -m chatbot.judge checks --results data/eval/chatbot_eval_results_llama8b_v2_idle.jsonl --judged data/eval/judge_qwen3_4b.jsonl
```

### Gold set v2 (32 questions)

| | v1's 23, 30 Sep | v1's 23, tonight | the 9 added, tonight | all 32, tonight |
|---|---|---|---|---|
| backend errors | 0 | 0 | 0 | 0 |
| answered by an input guard | 7 | 7 | 1 | 8 |
| correct tool | 13 / 16 | 13 / 16 | 7 / 8 | 20 / 24 |
| advice and no-data behaviour | 7 / 7 | 7 / 7 | 1 / 1 | 8 / 8 |
| citation warning | 4 | 5 | 6 | **11** |
| answers with a figure no tool returned | 3 | 6 | 5 | 11 |

On v1's 23 questions tonight's run is close to 30 Sep's (13/16 tools both
times; 5 citation warnings against 4). The 9 new questions, mostly lookups on
the aspects added on 30 Sep, are where the model invents most: 6 of the 8
that reached it.

**Every citation warning was read against the transcript.** All 11 are real
inventions, none a false alarm: fake sentence ids (12345 and 67890 in five
answers, 123456, 789012 and 345678 in one), URLs at Business Times, Straits
Times, CNA, Bloomberg, Reuters or DBS's own site that no tool returned, and
quotes attributed to Bloomberg, the Financial Times, Yahoo Finance and others
that appear nowhere in the tool data. **None of the 11 answers called
`search_evidence`.** Each looked up a score (`get_sentiment`,
`compare_banks`, `get_trend`, `get_coverage` or `get_analyst_consensus`) and
then wrote a "Supporting evidence" section anyway. Prompt rule 8 forbids
exactly that ("If you have not called search_evidence in this conversation,
do not write a supporting evidence section at all"), and rule 6 asks for that
section in every answer; the model follows rule 6.

**The figures.** 10 of the 11 answers with an unverified figure are among
those 11, and every flagged figure sits in the invented evidence section,
not in the answer's opening: the scores the answers lead with came from the
tools. The eleventh, evidence-2's "a relevance score of at least 0.58", is
a false alarm: the lowest relevance returned was 0.5853.

**The tool misses** (4 of 24): lookup-2 called `get_coverage` twice instead
of `get_sentiment`; thin-1 called `get_trend` instead of `get_sentiment`;
evidence-1 searched without the bank; evidence-3 looked up
the score and invented quotes instead of searching.

**Off-topic evidence that every check passes.** evidence-2 asked for
complaints about UOB's asset quality. `search_evidence` returned five
negative sentences stored under `asset_quality`: card annual fees, a fall in
a fund's value, account requirements, unauthorised card transactions and a
housing-loan court case. They are retail-banking complaints that
seed-centroid assignment filed under asset quality, and the model presented
them as asset-quality complaints. The citation check passes (every quote was
retrieved), the number check raises only the false alarm above, and the
judge scores it 3. The retrieval section above predicts this failure; here
it is in a live answer.

### Conversations

7 of 9 turns correct, 2 of 4 conversations correct, the same as the first
run. Both failures are fixable outside the model:

- mt-2, turn 3, "Has that improved lately?": refused by the scope guard
  before the model saw it ("That's outside what I can help with"). The guard
  looks only at the current message, which names no bank and no domain word,
  so a follow-up is treated as off-topic even mid-conversation.
- mt-3, turn 2, "Show me some evidence for DBS on that.": the model wrote
  the `search_evidence` call out as text (`{"name": "search_evidence", ...}`)
  instead of making it, the failure seen in lookup-2 on 30 Sep.

The carry-over itself works: "And OCBC?" and "What about its asset
quality?" were answered with the right bank and aspect.

### The judge

`qwen3:4b` without thinking scored all 32 answers 3 ("every figure and claim
is supported"), including the 11 with citations confirmed by hand as
invented, which its own scale scores 1, and evidence-2:

| harness | judge 1 | judge 2 | judge 3 |
|---|---|---|---|
| citation flagged | 0 | 0 | 11 |
| not flagged | 0 | 0 | 13 |

(Guard answers left out.) The first run gave the same result on its 8
flagged answers. Its reasons check the figures the answer leads with and
ignore the evidence section. As configured, it can't be used as a
faithfulness measure, alone or calibrated: a judge that never scores below
3 has nothing for human ratings to calibrate. What to try instead, in order
of cost: the same model with thinking on; a larger judge; or a judge asked
one narrow question at a time ("does every quote in the answer appear in the
tool data?"), which the harness already answers without a model.

The blank ratings sheet for people (`data/eval/ratings_sheet.csv`, 32
answers, no judge output in it) is from this run.

### What this changes

1. Invented evidence is the chatbot's main failure on the 8B model, and it
   happens when no search was made. Since the harness knows that, it can
   remove the evidence section, or run the search itself and show real
   quotes, instead of appending a warning. That is a code change, not a
   prompt change: the prompt already says it.
2. The scope guard needs the conversation's context.
3. The LLM judge is not yet a measurement; the harness's checks and people's
   ratings are.
