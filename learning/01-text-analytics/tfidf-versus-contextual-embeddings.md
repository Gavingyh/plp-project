# TF-IDF versus contextual embeddings

Subject: Text Analytics (module 1) · Bloom target: Analyze / Evaluate / Create
Prerequisites: none

---

## 1. Why it matters here (Understand)

Every text-mining technique needs numbers. How you turn a sentence into
numbers determines what the rest of the pipeline can possibly see.

This project uses **both** representations, for different jobs, and the
division is deliberate: TF-IDF labels clusters, embeddings do the semantic
work. Being able to say why each is used where is a straightforward mark in
the report.

---

## 2. The concept (Understand / Apply)

### Bag of words and TF-IDF

Represent a document as counts over a vocabulary, ignoring order. Weight each
term by how distinctive it is:

```
tf-idf(t, d) = tf(t, d) × log(N / df(t))
```

A term appearing in every document has `df = N`, so `log(N/df) = 0` and it
contributes nothing. A term appearing in few documents scores high. That is
what makes TF-IDF good at *characterising* a set of documents.

Properties: sparse (most entries zero), dimensionality equal to the
vocabulary, and directly interpretable — every dimension is a word you can
read.

Blind spots: "dividend was cut" and "dividend was raised" share most of their
terms; "payout" and "distribution" are unrelated dimensions; and word order is
gone entirely.

### Contextual embeddings

A transformer produces a dense vector per token, and crucially the vector
depends on the surrounding words. "Bank" in "the bank raised rates" and "the
river bank" get different vectors. Static embeddings like Word2Vec and GloVe
cannot do that — one word, one vector, regardless of sense.

Properties: dense (768 dimensions here, all non-zero), fixed size regardless
of vocabulary, and **not interpretable** — no dimension means anything you can
name.

### Mean pooling, not CLS

`aspects/embed.py` averages token embeddings to get a sentence vector, rather
than using the `[CLS]` token.

BERT's `[CLS]` is trained for next-sentence prediction, not to be a sentence
representation. Without a sentence-level similarity objective of the kind
Sentence-BERT adds, `[CLS]` similarity is a poor signal. Mean pooling is
materially better and costs nothing.

---

## 3. Where it lives in this repo (Apply)

| representation | where | job |
|---|---|---|
| **FinBERT embeddings**, mean-pooled | `aspects/embed.py` | Aspect assignment, clustering, chatbot retrieval |
| Embedding cache, 101 MB `.npz` | `aspects/embed_store.py` | Compute once, reuse four times |
| **TF-IDF** | `aspects/discover.py` | Naming clusters by their top distinctive terms |
| **TF-IDF + logistic regression** | `train/evaluate.py` | The classical ML baseline |
| Lexical overlap | `chatbot/retrieval.py` | A keyword bonus on top of semantic search |

---

## 4. Analyze

### The division of labour is the interesting design decision

TF-IDF is used in exactly the two places where its weaknesses do not matter
and its strengths are decisive.

**Naming clusters.** After HDBSCAN produces cluster 13, someone has to work
out what it is. TF-IDF over its member sentences returns `iii`, `basel iii`,
`final`, `final basel`, `reforms` — immediately legible as "Basel III
reforms". Embeddings cannot do this: the cluster centroid is 768 numbers that
mean nothing to a human. **Interpretability is the requirement here, and
TF-IDF is the only one of the two that has it.**

Note the domain adjustment in `aspects/discover.py`: bank names are excluded
from the TF-IDF vocabulary. Without that, "dbs", "ocbc", "uob" would dominate
every cluster's top terms while distinguishing none of them — a
textbook domain-specific stopword list, which module 1 covers directly.

**As a baseline.** `train/evaluate.py` includes TF-IDF plus logistic
regression precisely because it is the pre-transformer approach. If fine-tuned
FinBERT cannot beat it, that is worth knowing, and it is a cheap and honest
comparison.

### Where embeddings earn their place, and where they fail

The argument for embeddings is implicit aspects. "They're paying out too much
of their earnings" is about payout ratio and shares no vocabulary with
"dividend payout ratio". TF-IDF scores that pair at zero similarity;
embeddings place them near each other.

**But the same property causes the project's assignment failure.** The twenty
Reddit sentences most similar to the `net_interest_margin` centroid are all
retail banking products — "No fees for ocbc", "DBS Fixed deposit interest.",
"UOB credit card application." Embedding similarity decided these are about
margins because they share financial register with the seed terms.

TF-IDF would have made the opposite error. It would have assigned nearly
nothing from Reddit to `net_interest_margin`, because the phrase appears zero
times there. That would have been *wrong in a much more visible way*: an empty
aspect column prompts investigation, while a full column of plausible-looking
assignments does not.

That is the real lesson, and it generalises beyond this project: **the failure
mode of a dense representation is confident wrongness, and the failure mode of
a sparse one is obvious emptiness.** The second is easier to catch.

### Comparing four representations on this corpus

| | TF-IDF | Word2Vec / GloVe | FinBERT mean-pooled | Sentence-BERT |
|---|---|---|---|---|
| Handles paraphrase | No | Partly | Yes | Yes |
| Handles polysemy | No | **No** — one vector per word | Yes | Yes |
| Interpretable dimensions | **Yes** | No | No | No |
| Financial domain knowledge | No | Only if trained on finance | **Yes** | No |
| Trained for sentence similarity | n/a | No | **No** | **Yes** |
| Cost | Trivial | Cheap | An embedding pass | An embedding pass |

Two cells decide the project's choices. FinBERT is the only column with
financial domain knowledge, which is why it is used. Sentence-BERT is the only
one trained for sentence similarity, which is what mean-pooled FinBERT is
being asked to do.

That trade-off has never been measured here. FinBERT was chosen for both jobs
because it satisfies the DNN requirement and gives one model to explain and
one cache to maintain. It is entirely possible that Sentence-BERT would assign
aspects better, and given the assignment failure above, testing that would be
a genuinely useful experiment.

---

## 5. Evaluate

**Was the division right?** Yes. Using TF-IDF where interpretability is the
requirement and embeddings where semantic similarity is, is exactly right, and
it is the kind of choice that reads as deliberate rather than defaulted.

**Was mean-pooled FinBERT right for assignment?** Less clearly. The reasoning
was sound — financial domain knowledge, one model, satisfies the DNN
requirement — and the outcome is a taxonomy whose centroids barely separate
and Reddit assignments that are demonstrably wrong. Some of that is the
taxonomy's seed terms rather than the representation, and disentangling the
two would need the Sentence-BERT comparison nobody has run.

**What the evidence does not show.** No comparison of representations exists.
Nobody has measured whether Sentence-BERT, or FinBERT with `[CLS]`, or TF-IDF
similarity, would assign better. The mean-pooling choice is justified by a
general finding about BERT `[CLS]` vectors, not by a measurement on this
corpus.

**When TF-IDF would be the better primary representation.** If the corpus were
uniformly formal financial text where the analyst vocabulary is actually used,
sparse retrieval would work well and would be far more debuggable. Half this
corpus is exactly that. A hybrid — TF-IDF for earnings, embeddings for Reddit
— is not obviously worse than what is deployed, and nobody has tried it.

---

## 6. Create

**Exercise (about ninety minutes).** Test the claim that embeddings beat
TF-IDF for aspect assignment on this corpus.

```python
# .venv-plp/bin/python3, with HF_HUB_OFFLINE=1
import sqlite3, yaml, numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

cfg = yaml.safe_load(open("config/aspects.yaml"))
seeds = {a: " ".join(v["seed_terms"]) for a, v in cfg["aspects"].items() if a != "other"}

c = sqlite3.connect("data/plp.db")
rows = c.execute("""
    SELECT text FROM sentences WHERE source='arctic_shift' LIMIT 3000
""").fetchall()
texts = [r[0] for r in rows]

vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=20000)
X = vec.fit_transform(texts + list(seeds.values()))
S, A = X[:len(texts)], X[len(texts):]

sims = cosine_similarity(S, A)
names = list(seeds)
for i, name in enumerate(names):
    top = np.argsort(-sims[:, i])[:8]
    print(f"\n=== {name} (TF-IDF top matches)")
    for j in top:
        print(f"  [{sims[j, i]:.3f}] {texts[j][:100]}")
```

Compare the `net_interest_margin` results against the embedding-based ones in
[aspect-based-sentiment-analysis](../02-sentiment-mining/aspect-based-sentiment-analysis.md),
section 4.

**Expected outcome.** TF-IDF should return either very few matches or
sentences that literally contain seed words, and its similarity scores should
be far lower overall. Judge which set of top matches is *more correct* — not
which has higher scores, since the two scales are not comparable.

**For the report:** side-by-side top-8 lists for one aspect and two or three
sentences on which representation you would trust for assignment on this
corpus, and why. Given the embedding failure documented elsewhere, this may
not come out the way the pipeline's design assumes.

---

## 7. Self-check

1. Why does TF-IDF give a term appearing in every document a weight of zero?
2. Why can't Word2Vec distinguish "bank" the institution from "bank" the
   riverside?
3. Why does `aspects/discover.py` use TF-IDF rather than embeddings to label
   clusters?
4. Why are bank names excluded from that TF-IDF vocabulary?
5. TF-IDF would have assigned almost no Reddit sentences to
   `net_interest_margin`. Why might that failure have been preferable?

<details>
<summary>Answers</summary>

1. Because the inverse document frequency term is `log(N/df)`, and a term in
   every document has `df = N`, so `log(1) = 0`. A term that appears
   everywhere distinguishes nothing.
2. Because it assigns one vector per word type, learned from aggregate context
   across the whole corpus. Both senses collapse into a single averaged
   representation. Contextual models compute a vector per occurrence, so the
   surrounding words change it.
3. Because the requirement is interpretability. A human has to read a
   cluster's label and understand what the cluster is; TF-IDF returns actual
   words, whereas a centroid is 768 uninterpretable numbers.
4. Because "dbs", "ocbc" and "uob" appear across all clusters, so they would
   dominate every cluster's top terms while distinguishing none of them. It is
   a domain-specific stopword list.
5. Because an obviously empty aspect column prompts someone to investigate,
   whereas a full column of plausible-looking but wrong assignments does not.
   The dense representation failed confidently, which is harder to notice than
   failing visibly.

</details>

---

## 8. Sources

**Repository**

- `aspects/embed.py` — mean pooling and its stated reason
- `aspects/discover.py` — TF-IDF cluster labelling, bank-name exclusion
- `train/evaluate.py` — TF-IDF plus logistic regression baseline
- `chatbot/retrieval.py` — the lexical overlap boost
- `docs/DESIGN.md` decision 1

**Measured in this repository**

- The `net_interest_margin` assignment examples, from `sentence_aspects` on
  2026-09-11, reproduced in the ABSA topic.

**Course material**

- `.project-context/course-content/TA-context.txt` day 1 — TDM, tf-idf with
  its formula, lookup versus contextual embeddings, domain stopword lists

**Not verified**

- No comparison of representations has been run on this corpus. The claim that
  Sentence-BERT would assign better than mean-pooled FinBERT is plausible and
  untested; the exercise in section 6 tests only the TF-IDF comparison.
- The general finding that BERT `[CLS]` vectors are poor similarity
  representations is taken from the reasoning recorded in `aspects/embed.py`.
  **No paper was fetched for it during this pass** — the usual citation is the
  Sentence-BERT paper (Reimers and Gurevych, 2019), which should be checked
  before being cited.
