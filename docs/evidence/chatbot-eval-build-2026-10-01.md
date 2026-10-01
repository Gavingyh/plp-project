# Chatbot evaluation, extended: gold set v2, conversations, retrieval, a judge

PLAN section 3 asks for a frozen ~30-question gold set, multi-turn
scenarios, retrieval Hit@K and MRR, and faithfulness via an LLM judge
calibrated on human ratings. Built 2026-10-01. The retrieval results are
below; the live runs of the gold set, the conversations and the judge are in
[the next section](#live-runs) once they finish.

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

Pending: the gold set v2, the conversations and the judge run after the
GPU jobs ahead of them; results are added here when they finish.
