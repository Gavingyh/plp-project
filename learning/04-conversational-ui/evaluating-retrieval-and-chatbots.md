# Evaluating retrieval and chatbots

Subject: Conversational UI (module 4) · Bloom target: Analyze / Evaluate / Create
Prerequisites: [rag-and-hybrid-search](rag-and-hybrid-search.md),
[grounding-and-citation-verification](grounding-and-citation-verification.md).

---

## 1. Why it matters here (Understand)

A grounded chatbot can fail in three places: it can call the wrong tool,
retrieve the wrong evidence, or say something its evidence doesn't
support. The project's first evaluation (23 questions) measured the first
and flagged invented citations. It did not measure whether retrieval finds
relevant evidence, or whether answers are faithful. On 1 October it did,
and retrieval turned out to be the weakest link
([chatbot-eval-build-2026-10-01.md](../../docs/evidence/chatbot-eval-build-2026-10-01.md)).

---

## 2. The concept (Understand / Apply)

**Ranking metrics.** For a query with known relevant items:

- **Hit@K**: 1 if any relevant item is in the top K, else 0.
- **Precision@K**: the share of the top K that are relevant.
- **Reciprocal rank**: 1 / (rank of the first relevant item); its mean over
  queries is **MRR**.

**A random baseline, computed exactly.** For n items with r relevant, a
random ordering has expected precision r/n at every K; its expected Hit@K
is 1 − C(n−r, K)/C(n, K); its expected reciprocal rank sums 1/i times the
probability the first relevant item sits at position i. Any metric means
little without it.

**Relevance judgements.** Metrics are only as good as the judgements. Here
they come from the human aspect labels, so retrieval is ranked within the
labelled sentences, where every item has a judgement.

**Multi-turn evaluation.** A follow-up ("And OCBC?") is only right if the
conversation carried the aspect over, so conversations are scored turn by
turn and pass only if every turn does.

**An LLM judge, calibrated.** A model scores each answer's faithfulness to
its tool data (1–3); people score the same answers blind; agreement and
weighted κ decide whether the judge can be used alone.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| retrieval metrics and baseline | `chatbot/retrieval_eval.py` |
| gold sets v1 (23) and v2 (32), conversations | `chatbot/eval_gold_set.py` |
| the runner | `chatbot/run_eval.py --set v2`, `--multi-turn` |
| the judge, the ratings sheet, calibration | `chatbot/judge.py` |
| the search being evaluated | `chatbot/retrieval.py` `search_evidence` |

---

## 4. Analyze

**The result.** 28 queries (each bank × each aspect with at least 3
labelled sentences), each ranking that bank's labelled sentences:

| query | hit@5 | MRR |
|---|---|---|
| question: "What do people say about DBS's asset quality / provisioning?" | 0.286 | 0.217 |
| random | 0.319 | 0.217 |
| the aspect's name: "Asset Quality / Provisioning" | 0.679 | 0.559 |

**Why the wording matters so much.** `search_evidence` scores by cosine
similarity between FinBERT mean-pooled vectors plus a small word-overlap
term. FinBERT wasn't trained to make similar meanings close; its vectors
carry the *register* of a text strongly. A question embeds like a Reddit
question, so it retrieves Reddit-style sentences (investor and
retail-banking chatter, hit@5 1.00) whatever the topic, and misses the six
aspects mostly written about in earnings and news prose (hit@5 0.00). A bare topic name
has no question register, so the topic dominates.

**How it reaches a user.** The model passes its own question as the
query; off-topic evidence comes back; the citation check confirms the quote
was retrieved, not that it is relevant. So an answer can pass every
automated check while citing the wrong evidence.

**The same weakness, seen twice.** Seed-centroid aspect assignment uses the
same vectors and picks the human's aspect 41% of the time. Two experiments,
one cause.

---

## 5. Evaluate

The evaluation design is strong where judgements are human and baselines
exact, and limited where it is narrow: 28 queries, relevance as the human
aspect (a sentence on-topic but labelled with a neighbouring aspect counts
as a miss), and a sampled pool rather than the corpus.

The finding is robust to those limits because the gap is large (MRR 0.56
against 0.22) and has a mechanism. It changes the priority list: a cheap
fix (rank by the aspect's name when the model passes an aspect) should be
tried and re-measured before any further prompt work on grounding.

What the evaluation does not show: whether users would notice; whether a
better embedding model (one trained for sentence similarity) would fix
question queries too; and how often the live chatbot sends question-like
queries at all.

---

## 6. Create

**Exercise (≈ 90 minutes).** Implement the cheap fix behind a flag and
measure it. In `chatbot/retrieval.py`, when `aspect` is given, build the
query from the aspect's label plus the user query's nouns; add the same
option to `chatbot/retrieval_eval.py` and rerun it.

*Expected outcome:* question-style MRR rising from 0.217 towards the
label-only 0.559; if it doesn't, the nouns are re-introducing the question
register, which itself is a finding.

---

## 7. Self-check

1. Why compute a random baseline for MRR, and why exactly rather than by
   simulation?
2. Why rank only labelled sentences instead of the whole corpus?
3. The citation check passes. Why can the evidence still be wrong?
4. Why does a conversation pass only if every turn passes?
5. When may an LLM judge replace human ratings?

<details>
<summary>Answers</summary>

1. Because MRR's scale depends on how many items are relevant: 0.217
   sounds poor or good only against chance for that pool. Exact values
   avoid simulation noise and are cheap here.
2. So every retrieved item has a human judgement; over the corpus most
   items would be unjudged and counted as irrelevant.
3. It verifies that a quoted sentence was retrieved, not that it answers
   the question.
4. A follow-up only works if the memory carried the earlier context; one
   wrong turn breaks the conversation for the user.
5. When its scores agree with people's on a calibration set well enough
   (weighted κ above an agreed bar), and only for the kind of answers that
   set covered.

</details>

---

## 8. Sources

**Repository**

- `chatbot/retrieval_eval.py`, `chatbot/retrieval.py`, `chatbot/judge.py`,
  `chatbot/run_eval.py`, `chatbot/eval_gold_set.py`
- `docs/evidence/chatbot-eval-build-2026-10-01.md`,
  `chatbot-eval-2026-09-30.md`

**Measured in this repository (2026-10-01)**

- The retrieval table and per-aspect figures, from `retrieval_eval`.

**External**

- Manning, C. D., Raghavan, P., and Schütze, H. (2008), *Introduction to
  Information Retrieval*, ch. 8, "Evaluation in information retrieval".
  **Not fetched during this pass.**
- Reimers, N., and Gurevych, I. (2019), "Sentence-BERT", EMNLP: why BERT
  vectors need similarity training. **Not fetched.**

**Not verified**

- The query fix (exercise 6) has not been implemented or measured.
