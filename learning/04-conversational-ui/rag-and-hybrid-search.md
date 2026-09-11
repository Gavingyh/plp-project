# Retrieval-augmented generation and hybrid search

Subject: Conversational UI (module 4) · Bloom target: Analyze / Evaluate / Create
Prerequisites: [tfidf-versus-contextual-embeddings](../01-text-analytics/tfidf-versus-contextual-embeddings.md)

---

## 1. Why it matters here (Understand)

The chatbot has two kinds of answer to give. "What is DBS's dividend
sentiment?" is a **lookup**: a number from the index, fetched by a SQL query.
"What are people actually saying about it?" is a **retrieval**: find the
sentences and quote them.

Retrieval is what makes the answer checkable. A score of −0.0015 means nothing
to a retail investor on its own; three real sentences with dates and links
mean something. It is also the mechanism the grounding check depends on — if
`search_evidence` was never called, any citation in the answer is fabricated
by definition.

---

## 2. The concept (Understand / Apply)

**Retrieval-augmented generation** means fetching relevant documents and
putting them in the model's context so it answers from them rather than from
its parameters.

The naive version is pure vector search: embed the query, embed every
document, return the nearest by cosine similarity. It has a well-known
weakness — exact identifiers. A query for "DBS Multiplier" should return
sentences containing that exact product name, but semantic similarity happily
returns sentences about savings accounts in general, because in embedding
space they are close.

This project uses **hybrid retrieval** in three stages:

| stage | what it does | why |
|---|---|---|
| **1. SQL pre-filter** | Narrow by bank, aspect, sentiment, date range | Cheap and exact. Does most of the work before any embedding maths |
| **2. Semantic ranking** | Cosine similarity between query and cached FinBERT embeddings over the survivors | Finds paraphrase: "payouts are getting stingy" matches a dividend query |
| **3. Lexical boost** | Add a small bonus for literal word overlap | Rescues exact identifiers that stage 2 alone would miss |

The lexical boost weight is 0.15 relative to cosine similarity — a nudge, not
a re-ranking.

### Why the order matters

Filtering first means the expensive comparison runs over a small candidate
set. If a user asks about UOB's asset quality, there is no reason to compute
similarity against 36,884 sentences when the SQL filter reduces it to the
relevant few thousand first.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| The three-stage retrieval | `chatbot/retrieval.py` |
| `_LEXICAL_WEIGHT = 0.15` | `chatbot/retrieval.py` |
| Cached embeddings (101 MB `.npz`) | `aspects/embed_store.py` |
| The tool the model calls | `chatbot/tools.py`, `search_evidence` |
| Why calling it matters for grounding | `chatbot/agent.py` |
| Reasoning | `docs/DESIGN.md` decision 10 |

Every result carries its `sentence_id`, `url` and date. The citation
requirement is enforced by *what the function returns*, not left to the
model's discretion.

---

## 4. Analyze

### Brute force, and why it is the right call here

There is no vector index. Retrieval computes cosine similarity against an
in-memory matrix and sorts.

At this corpus size that is not a compromise:

| approach | correctness | infrastructure | complexity to explain |
|---|---|---|---|
| **Brute-force cosine** (used) | **Exact** | A NumPy array | One line of linear algebra |
| FAISS | Approximate, tunable | A library and an index to build and keep in sync | An index type, a metric, a nprobe parameter |
| Chroma / a vector DB | Approximate | A service or embedded store, plus a schema | A whole component in the architecture diagram |

Approximate nearest-neighbour indexes exist to make search sub-linear when
linear is too slow. Over roughly 36,000 vectors of 768 dimensions, a single
matrix multiply is milliseconds. **An approximate index would be slower to
build, harder to keep consistent with SQLite, and less accurate.** The only
thing it would add is a more impressive-sounding architecture.

The threshold where this reverses is somewhere in the millions of vectors, or
wherever the matrix stops fitting comfortably in memory. State that boundary
in the report rather than implying brute force is always fine.

### What the lexical boost actually buys

Consider the query "DBS Multiplier interest rate".

| stage | behaviour |
|---|---|
| Semantic only | Returns sentences about savings-account interest generally. "DBS Multiplier" and "OCBC 360" sit close together in embedding space because they are the same *kind* of thing |
| With lexical boost | Sentences literally containing "Multiplier" get a bonus and rise above generic savings-account chatter |

This is the standard sparse-plus-dense retrieval pattern, right-sized. A full
implementation would run BM25 alongside the vector search and fuse the
rankings. Here it is a keyword-overlap term, because the corpus does not
warrant a second index and BM25 would be another component to explain.

**A weakness worth admitting:** 0.15 was chosen, not tuned. There is no
retrieval evaluation set — no queries with known-relevant sentences — so
nobody has measured whether 0.15 is better than 0.05 or 0.3. The gold set
(`chatbot/eval_gold_set.py`) checks whether `search_evidence` was *called*,
not whether what it returned was *relevant*. Retrieval quality is genuinely
unmeasured in this project.

### The embedding reuse that ties the system together

The same cached FinBERT embeddings serve four consumers: aspect assignment,
taxonomy discovery, taxonomy comparison, and this retrieval. One embedding
pass, four uses.

That is efficient and it has a consequence worth noticing. Retrieval inherits
whatever FinBERT's representation is good and bad at. If FinBERT poorly
represents informal Reddit register — which the 94.8% neutral rate hints at —
then retrieval over Reddit inherits that weakness. A retrieval-specific
embedding model such as Sentence-BERT would likely do better at this one job,
at the cost of a second model and a second cache.

---

## 5. Evaluate

**Hybrid retrieval was the right design.** The SQL pre-filter is
straightforwardly correct: structured constraints belong in a database, not in
an embedding space. The lexical boost addresses a real, documented failure
mode of pure vector search.

**Avoiding a vector database was right, and the reasoning generalises better
than the decision itself:** choose infrastructure for the scale you have,
and say what would change your mind. Reaching for FAISS at 36,000 vectors
would have added a component to the architecture diagram, a dependency, a
consistency problem, and approximation error, in exchange for nothing.

**What the evidence does not show.** Retrieval quality is not measured
anywhere. There is no relevance judgement set, so:

- whether 0.15 is a good lexical weight is unknown;
- whether `k=5` returns enough context is unknown;
- whether cited evidence is *relevant to the question asked* is explicitly
  listed in `docs/STATUS.md` as needing a human, and no human has done it.

The system can prove a citation is real. It cannot yet show it is apposite.
That distinction belongs in the report's limitations, because "the chatbot
cites its sources" reads as a stronger claim than the evidence supports.

**When to change the design.** Beyond roughly a million sentences, or if
retrieval latency became visible to a user, an approximate index earns its
place. If the corpus became mostly informal text, a retrieval-specific
embedding model would probably matter more than the index.

---

## 6. Create

**Exercise (about ninety minutes).** Build the retrieval evaluation this
project lacks.

```python
# .venv-plp/bin/python3, with HF_HUB_OFFLINE=1
from chatbot.retrieval import search_evidence

QUERIES = [
    ("DBS Multiplier account interest", "DBS"),
    ("dividend cut", None),
    ("non-performing loans rising", None),
    ("net interest margin compression", None),
    ("scam calls and fraud", None),
]

for q, bank in QUERIES:
    print(f"\n=== {q!r} bank={bank}")
    for r in search_evidence(q, bank=bank, k=5):
        print(f"  [{r.get('score', 0):.3f}] {r['text'][:110]}")
```

Judge each of the 25 results as relevant or not, by hand. That gives you
precision at 5 per query. Then change `_LEXICAL_WEIGHT` in
`chatbot/retrieval.py` to 0.0 and to 0.4, re-run, and re-judge.

**Expected outcome.** At 0.0 the "DBS Multiplier" query should drift toward
generic savings-account sentences. At 0.4 you may see keyword matches
outranking better semantic matches. Whether 0.15 is the sweet spot is the
thing you are measuring, and you may well find the three settings
indistinguishable on five queries — which is itself the useful finding, since
it tells you the parameter is not where the quality problem lives.

**For the report:** the precision-at-5 table across three weights, your
relevance criterion stated explicitly, and one sentence on whether the lexical
boost is doing measurable work. This is the first retrieval measurement the
project would have.

---

## 7. Self-check

1. Why does the SQL filter run before the embedding comparison rather than
   after?
2. What failure mode does the lexical boost address, with an example?
3. Why is brute-force cosine the right choice at 36,000 sentences, and what
   would change that?
4. Retrieval and aspect assignment share one embedding cache. Give one benefit
   and one risk.
5. The chatbot can prove a citation is real. What can it not prove?

<details>
<summary>Answers</summary>

1. Because filtering is cheap and exact, and it shrinks the candidate set the
   expensive similarity computation runs over. Filtering afterwards would
   compute similarity against the whole corpus and then discard most of it.
2. Exact identifiers. A query for "DBS Multiplier" is semantically close to
   any savings-account discussion, so pure vector search returns generic
   results. A literal-overlap bonus lifts sentences that actually name the
   product.
3. Because a single matrix multiply over roughly 36,000 vectors takes
   milliseconds, so an approximate index would add build cost, a consistency
   burden and approximation error for no speed benefit. Millions of vectors,
   or memory pressure, would change it.
4. Benefit: one embedding pass serves four consumers, so there is one cache to
   maintain and no possibility of two components disagreeing about what a
   sentence means. Risk: retrieval inherits FinBERT's weaknesses, and FinBERT
   was trained on financial news rather than informal social text.
5. That the citation is *relevant* to the question asked. A genuine
   `sentence_id` quoted in support of an unrelated claim passes every
   automated check in the system.

</details>

---

## 8. Sources

**Repository**

- `chatbot/retrieval.py` — the three stages and `_LEXICAL_WEIGHT`
- `aspects/embed_store.py` — the shared cache
- `chatbot/tools.py` — `search_evidence`
- `chatbot/agent.py` — why calling it is what makes a citation legitimate
- `docs/DESIGN.md` decision 10
- `docs/STATUS.md` — citation relevance listed as outstanding human work

**Measured in this repository**

- 36,884 sentences, 101 MB embedding cache, from
  `docs/verification-ledger.md`.

**Not verified**

- Retrieval quality. No relevance judgements exist, so precision and recall
  are unmeasured and `_LEXICAL_WEIGHT = 0.15` is a chosen value rather than a
  tuned one. The exercise in section 6 is designed to produce the first real
  measurement.
- The claim that Sentence-BERT would retrieve better than mean-pooled FinBERT
  on this corpus. Plausible and untested.
- The "sparse plus dense" hybrid retrieval pattern is described here from
  general practice; **no paper was fetched for it during this pass.** Cite one
  directly if the report leans on it.
