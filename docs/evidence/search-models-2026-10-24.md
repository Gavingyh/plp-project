# Models built for search, against the chatbot's evidence ranking (24 Oct 2026)

**What this is.** The chatbot's evidence search ranks sentences by how close
their base FinBERT embedding is to the question's. FinBERT was trained to
classify sentiment, not to match sentences by topic, and on the search's own
test its ranking was no better than random. This test asks whether a small,
free model trained for matching sentences would do better.

**Result.** Within a topic, which is how the chatbot searches in practice, no
model beats the ordering in use (the question's words, then newest): the best
scored 0.80 against 0.82, short of the 0.85 the rule asked for. Without a
topic, all three models score about 0.30 against FinBERT's 0.12, which passes
the rule. In the newest test runs the chatbot never searched without a
topic, so this was first reported as a finding only. It was then adopted, so
that no search path the chatbot can take ranks at the level of a random draw:
see "Decision" below.

## Method

Script and outputs: `data/eval/search-models/compare.py`, `output.txt`,
`results.json`. The 28 queries and 1,277 hand-labelled sentences are those of
`chatbot/retrieval_eval.py`: one query per bank and topic with at least 3
labelled sentences, worded "What do people say about DBS's dividend policy?".
Precision at 5 is the share of the top five that people labelled with the
topic asked about. Two settings:

- **Within the topic filter:** only sentences stored under the asked topic are
  ranked, as when the chatbot passes a topic.
- **Without a topic:** all of the bank's labelled sentences are ranked.

Rule, fixed before any result: within a topic a model replaces the ordering in
use only at 0.85 or more; without a topic it replaces FinBERT if it is well
above FinBERT's 0.12. Each model was scored on similarity alone and with the
search's bonus for words shared with the question (weight 0.15).

## Precision at 5

| Ranking | Within a topic | Without a topic |
|---|---|---|
| Random draw from the same pool | 0.738 | 0.098 |
| Question's words, then newest (in use within a topic) | 0.818 | 0.207 |
| FinBERT similarity | 0.661 | 0.129 |
| FinBERT + word bonus (in use without a topic) | 0.668 | 0.121 |
| all-MiniLM-L6-v2 | 0.732 | 0.293 |
| all-MiniLM-L6-v2 + word bonus | 0.754 | 0.314 |
| bge-small-en-v1.5 | 0.696 | 0.307 |
| bge-small-en-v1.5 + word bonus | 0.754 | 0.300 |
| bge-base-en-v1.5 | 0.746 | 0.300 |
| bge-base-en-v1.5 + word bonus | 0.796 | 0.307 |

The words-then-newest figure without a topic uses the question's own words,
as a search without a topic would; ranked by the topic's name instead it
scores 0.436, but such a search has no topic name to use.

Within a topic the filter does most of the work (74% of the pool is on topic),
and every embedding ranks below the plain word ordering. Without a topic the
models built for search rank about two and a half times better than FinBERT,
and the three span 0.29 to 0.31, too close to separate on 28 queries.

## How often the chatbot searches without a topic

In the 32-question run on the fixed code (`chatbot_eval_results_fixes_v2.jsonl`)
the chatbot made 3 evidence searches, all with a topic; in the newest
conversation run (`chatbot_multiturn_results_trendfix2_mt.jsonl`), 1, with a
topic.

## Speed and memory on this Mac's processor

| Model | One question (ms) | Labelled sentences (s) | Corpus of 45,844, estimate (min) | Weights (MB) | Corpus vectors (MB) |
|---|---|---|---|---|---|
| FinBERT (in use) | 53.9 | | | | 141 |
| all-MiniLM-L6-v2 | 13.6 | 19.2 | 11.5 | 91 | 70 |
| bge-small-en-v1.5 | 50.2 | 33.3 | 19.9 | 133 | 70 |
| bge-base-en-v1.5 | 38.5 | 113.6 | 68.0 | 438 | 141 |

Measured while the chatbot evaluation was using the processor, so the times
are noisy: across two runs one question took 32 and 14 ms for
all-MiniLM-L6-v2 and 27 and 50 ms for bge-small. Each is tens of
milliseconds, small beside the seconds the language model takes to answer.
The corpus figures are extrapolated from the labelled sentences.

Qwen3-Embedding-0.6B was also tried and left out: it had not finished the
labelled sentences after about 15 minutes, where all-MiniLM-L6-v2 took under
half a minute.

## How sure: intervals over the 28 queries

From 10,000 resamples of the queries (gain over a random draw, precision at 5):

| Ranking | Gain over random | 95% interval |
|---|---|---|
| Within a topic: question's words, then newest | 0.080 | 0.012 to 0.145 |
| Topic filter and word ordering together, against five random sentences of the bank | 0.719 | 0.618 to 0.807 |
| No topic: FinBERT with the word bonus | 0.023 | -0.036 to 0.090 |
| No topic: all-MiniLM-L6-v2 with the word bonus | 0.216 | 0.108 to 0.329 |

Within a topic the word ordering beat random in 16 queries, tied in 5 and
lost in 7. It was chosen after seeing these same queries, so its gain is an
optimistic estimate. Recall at 5 within the pool is 0.453 for it against
0.399 for random, below random in 7 of the 28 queries. FinBERT's ordering by
the aspect's name scored 0.379, below random in 13
(`data/eval/retrieval_recall_per_query_2026-10-18.csv`, variant "aspect query +
stored-aspect filter").

## Decision

all-MiniLM-L6-v2 now ranks the searches that name no topic, from its own
store (`chatbot/search_vectors.py`, `data/search_embeddings.npz`, 66 MB for the
45,844 sentences, embedded in about 5 minutes on the processor). Within a topic
the search uses the word ordering and no vectors. FinBERT's store stays for
aspect discovery. Measured on the corpus store with `chatbot/retrieval_eval.py`
(`data/eval/search-models/retrieval_eval_search_model.txt`):

| Search | Precision at 5 | Random |
|---|---|---|
| No topic, by the question (the search as it now runs) | 0.314 | 0.098 |
| Within a topic, words then newest (as it now runs) | 0.818 | 0.738 |

## Limits

- 28 queries, each naming its topic in words. A real question without a topic
  is vaguer, and this test can't say how a model does on those.
- Relevance is judged by people's labels, made under the older reading of
  wealth, so a sentence the later ruling moved counts as a miss.
- No model was tuned or given a task instruction beyond its published query
  prefix.
