# Aspect-based sentiment analysis

Subject: New Media and Sentiment Mining (module 2) · Bloom target: Analyze / Evaluate / Create
Prerequisites: [levels-and-the-opinion-quintuple](levels-and-the-opinion-quintuple.md)

---

## 1. Why it matters here (Understand)

ABSA is the project's central technique. The dashboard's promise is not "DBS
sentiment is +0.06" but "DBS dividend sentiment differs from DBS asset-quality
sentiment", and delivering that requires knowing which aspect each sentence is
about before scoring it.

It is also where the project's most significant unresolved problem lives.

---

## 2. The concept (Understand / Apply)

### The subtasks

Module 2 decomposes ABSA into named pieces. The ones that matter here:

| subtask | what it does | this project |
|---|---|---|
| Aspect term extraction (AE) | Find the words naming an aspect | **Not done** — no aspect terms are extracted |
| Aspect category assignment | Map a sentence to a predefined category | **This is what the pipeline does** |
| Aspect-level sentiment classification (ALSC) | Given a sentence and an aspect, classify sentiment | Done, zero-shot |
| Opinion term extraction | Find the words carrying sentiment | Not done |
| Triplet extraction | Produce (aspect, opinion, sentiment) jointly | Not done |

The system does category assignment plus ALSC. That distinction matters for
the report: the pipeline never identifies *which words* make a sentence about
dividends, only that the whole sentence is close enough to a dividend
centroid.

### Explicit versus implicit aspects

| type | example | findable by extraction? |
|---|---|---|
| Explicit | "Their **dividend yield** is attractive" | Yes |
| Implicit | "They're paying out too much of their earnings" | **No** — no aspect term present |

This is the decisive argument for the approach taken. Retail investors write
implicitly. A method that finds aspect terms would miss most of the Reddit
corpus, because the corpus rarely uses the terms.

### How assignment works here

1. Embed each aspect's `seed_terms` with FinBERT, average them: that is the
   aspect's **centroid**.
2. Embed each sentence.
3. Compute cosine similarity to every centroid.
4. Assign every aspect above the **similarity floor** (0.65).
5. A sentence clearing no floor falls to `other`.

Multiple assignment is deliberate. "NIM held up but provisions rose" is
genuinely two aspects, and the corpus averages 2.17 aspects per scored
sentence.

### Frozen, not re-clustered

Clustering runs once, offline, to *derive* a taxonomy. Assignment then matches
against those frozen centroids every batch. Re-clustering per batch would
renumber and rename aspects between runs, so a dashboard user would watch
categories shift underneath them.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| The taxonomy, seed terms, `similarity_floor: 0.65` | `config/aspects.yaml` |
| Nearest-centroid assignment | `aspects/assign.py` |
| Embeddings, mean-pooled | `aspects/embed.py` |
| Offline discovery | `aspects/discover.py` |
| Quantitative taxonomy comparison and floor sweep | `aspects/compare_taxonomies.py` |
| Sentiment per (sentence, aspect) | `sentiment/score.py` |

---

## 4. Analyze

### The five aspect-extraction families, and why this project uses none of them

Module 2 lists five approaches. Assessed against this corpus:

| family | how it works | why not here |
|---|---|---|
| Frequency-based | Count noun phrases, filter by co-occurrence | Finds explicit terms only. Would return "account", "card", "interest rate" from Reddit — real topics, not the proposal's aspects |
| Lexico-syntactic / dependency | Rules over parse trees (double propagation) | Needs opinion words adjacent to aspect words. Fails on "NPL ratio rose to 1.4%", which has no opinion word at all |
| Supervised sequence labelling | IOB tagging, CRF or BERT | Needs labelled aspect spans. The project has zero labels and its labelling budget is spent on *sentiment* |
| Deep learning (LSTM, transformers) | Learned extraction | Same labelling problem |
| LLM prompting | Ask a model zero-shot | Viable and used for *pre-labelling sentiment*. Not used for aspects because assignment must be deterministic and cheap over 36,884 sentences every batch |

**Centroid assignment is not on that list**, and the report should say so. It is closest to the "aspect grouping" family the module covers
separately — mapping text to predefined categories by similarity — and it was
chosen because it handles implicit aspects, needs no labels, and is
deterministic.

### The problem, stated precisely

Reddit sentences are assigned to `net_interest_margin`. The Reddit corpus
contains:

| term | Reddit | earnings |
|---|---|---|
| "net interest margin" | **0** | 375 |
| `NIM` (word-boundary) | 4 | 300 |

So sentences containing no form of the term are being classified as being
about it. Embedding similarity has decided they are *about* margins on the
basis of general financial-sounding language.

Two readings, and they have opposite implications:

1. **Working as intended.** Implicit aspects are the whole point. A sentence
   about interest rates on deposits genuinely relates to margins without
   naming them.
2. **Failing.** The centroids do not discriminate, so everything
   financial-sounding matches everything.

**The measurement favours reading 2.** From the taxonomy comparison at the
production floor of 0.65 over all 36,884 sentences:

| candidate | aspects | avg matched/sentence | % other | centroid separation |
|---|---|---|---|---|
| A — the proposal's four | 4 | 1.80 | 37.3% | **0.1125** |
| B — data-derived coarse | 2 | 1.69 | 7.7% | 0.1695 |
| C — data-derived fine | 3 | 2.38 | 8.5% | 0.2222 |

Centroid separation is mean pairwise cosine *distance* between centroids. The
proposal's four aspects are the **least** distinct of the three candidates,
and because that figure is computed from seed embeddings alone, **no threshold
change can improve it.**

Sweeping the floor confirms there is no rescue: at 0.60 candidate A still
matches 2.55 of 4 aspects per sentence; at 0.65 it discards 37.3% of the
corpus; at 0.70 it discards 57.9%. Either most sentences match most aspects,
or most match nothing.

### Reading the actual assignments settles it

The geometry above is suggestive. Looking at what is assigned is conclusive.
The twenty Reddit sentences with the **highest** similarity to the
`net_interest_margin` centroid, from `sentence_aspects`:

```
[0.860] No fees for ocbc
[0.857] DBS Fixed deposit interest.
[0.851] DBS My Account: no minimum balance and fees.
[0.847] UOB one savings terms and conditions
[0.840] Checking Account(for daily expenses) 2) OCBC
[0.835] 1.5% fixed for 3 years, UOB.
[0.834] Normal bank savings account and UOB One (5.2% interest).
[0.834] UOB Absolute Amex, 1.7% unlimited cashback
[0.834] UOB credit card application.
[0.832] Fees for outgoing DBS transfer.
```

Not one is about net interest margin. Every one is a retail banking product:
fees, credit cards, fixed deposits, transfers, minimum balances. These are the
*best* matches, so the rest are worse.

**And the polarity inverts.** Several do mention interest — "UOB One (5.2%
interest)", "3% interest rate 360 OCBC bank account". That is a *deposit rate
paid to a customer*, which is a **funding cost** to the bank. A depositor
posting enthusiastically about 5.2% is describing something that compresses
the bank's margin. So even granting the assignment, the sentiment label points
the wrong way for an investor.

This resolves the two readings: **reading 2, decisively.** The centroids are
not discriminating, and the resulting Reddit rows in
`sentiment_index[net_interest_margin]` measure retail enthusiasm for deposit
products, not sentiment about bank margins.

### Why the floor was moved, and what that taught

The original floor was 0.35, and at that value even a deliberately coarse
two-aspect candidate matched *both* aspects on essentially every sentence —
2.00 out of 2. The floor was not discriminating between anything, for any
taxonomy.

That is a general lesson about similarity thresholds: **a threshold that
admits everything is indistinguishable from no threshold**, and you only find
out by sweeping it against a deliberately bad alternative. Testing a
threshold against the taxonomy you hope is right tells you much less than
testing it against one you know is wrong.

---

## 5. Evaluate

**Centroid assignment was right for the constraints.** It
handles implicit aspects, needs no labels, runs deterministically over the
whole corpus every batch, and produces stable categories. The alternatives all
founder on the same rock: no labelled aspect spans exist and none are planned.

**The current taxonomy is not defensible on the evidence.** The four
proposal aspects have the worst centroid separation of three candidates
tested, no floor gives them a usable operating point, and their vocabulary
appears in one source only. The tooling to decide this exists and has been
run; the decision is a team and supervisor call because dropping the four
a-priori aspects changes what was proposed.

**What the evidence does not show.** Everything above is geometry. Nothing
measures whether an assignment is *correct*, because that needs labelled
aspect judgements and none exist. It is possible — unlikely, but possible —
that the poorly-separated centroids nonetheless assign sensibly. Nobody knows,
and the honest report sentence is that aspect assignment is unvalidated rather
than that it is wrong.

**The most defensible position given the deadline.** Keep the four aspects,
report them for earnings text where the vocabulary genuinely lives, and state
plainly that Reddit populates mainly `dividend_policy` and `other`. That
matches the evidence, requires no re-labelling, and is honest.

---

## 6. Create

**Exercise (about ninety minutes).** Test reading 1 against reading 2 directly.

```python
# .venv-plp/bin/python3, with HF_HUB_OFFLINE=1
import sqlite3
c = sqlite3.connect("data/plp.db")

rows = c.execute("""
    SELECT s.text, sa.similarity
    FROM sentence_aspects sa JOIN sentences s ON s.sentence_id = sa.sentence_id
    WHERE sa.aspect = 'net_interest_margin' AND s.source = 'arctic_shift'
    ORDER BY sa.similarity DESC LIMIT 30
""").fetchall()

for text, sim in rows:
    print(f"[{sim:.3f}] {text[:130]}")
```

Read all 30 and mark each: **genuinely about margins or interest rates**,
**about banking but not margins**, or **not about banking at all**. Then run
the same query for the 30 *lowest*-similarity assignments above the floor.

**Expected outcome.** Section 4 shows the top 20; you will reproduce them.
The point of the exercise is to go further than that spot check and produce a
*rate*: over 30 high-similarity and 30 low-similarity assignments, what
fraction are genuinely about margins?

Then do the same for the other three aspects. `dividend_policy` is the
interesting comparison, because dividends are the one analyst topic Reddit
genuinely discusses (561 sentences), so its assignments may be far better. If
so, the finding is not "assignment is broken" but "assignment works where the
corpus has the vocabulary and fails where it does not" — a more precise and
more useful claim.

**For the report:** a per-aspect table of assignment precision on a hand-judged
sample, with your criterion stated. This would be the project's first
**quantified** measurement of assignment quality, which STATUS currently lists
as unvalidated with no number attached.

---

## 7. Self-check

1. What is the difference between aspect term extraction and aspect category
   assignment, and which does this system do?
2. Why would frequency-based aspect extraction fail on this corpus?
3. Why can a similarity-floor change not fix candidate A's poor centroid
   separation?
4. Why is a sentence allowed to have more than one aspect?
5. At floor 0.35 a two-aspect taxonomy matched both aspects on ~100% of
   sentences. What does that tell you?

<details>
<summary>Answers</summary>

1. Extraction finds the words in the sentence that name an aspect; assignment
   maps the whole sentence to a predefined category. This system does
   assignment, by cosine similarity to frozen centroids, and never identifies
   which words made the sentence match.
2. Because it finds explicit terms only. Retail investors write implicitly —
   "they're paying out too much of their earnings" is about payout ratio and
   contains no aspect term — and the analyst vocabulary is nearly absent from
   Reddit anyway.
3. Because separation is computed from the seed-term embeddings themselves,
   independently of any threshold. The floor decides how close a sentence must
   be to count as a match; it cannot move the centroids further apart.
4. Because sentences are. "NIM held up but provisions rose" is about
   two aspects, and forcing a single label would discard half the information.
   The corpus averages 2.17 aspects per scored sentence.
5. That the floor was not discriminating between anything, for any taxonomy —
   not that the taxonomy was good. Testing a threshold against a deliberately
   bad candidate is what revealed it.

</details>

---

## 8. Sources

**Repository**

- `config/aspects.yaml` — taxonomy, seed terms, floor, and the header
  documenting both discovery runs
- `aspects/assign.py` — frozen-centroid assignment and multi-assignment
- `aspects/compare_taxonomies.py` — the comparison and sweep
- `docs/DESIGN.md` decisions 4 and 5
- `docs/evidence/taxonomy-comparison-2026-09-11.md`
- `docs/STATUS.md` — the unvalidated-assignment problem

**Measured in this repository (2026-09-11)**

- Separation, average-matched and percent-other figures over 36,884 sentences.
- Term frequencies by source, word-boundary matched.
- 2.17 aspects per scored sentence, from 79,987 pairs over 36,884 sentences.

**Course material**

- `.project-context/course-content/NMSM-context.txt` day 1 PM — the ABSA
  subtask table and the five aspect-extraction families; day 2 AM — sequence
  labelling and training-free approaches

**Not verified**

- Whether assignments are *correct*. No labelled aspect judgements exist, so
  every figure here is geometric. The exercise in section 6 would produce the
  first evidence.
- Bing Liu's and the module's ABSA subtask taxonomy is reproduced from the
  course context file; **the primary literature was not fetched** during this
  pass.
