# Levels of sentiment analysis and the opinion quintuple

Subject: New Media and Sentiment Mining (module 2) · Bloom target: Analyze / Evaluate / Create
Prerequisites: none

---

## 1. Why it matters here (Understand)

The single most consequential decision in this system is that **the sentence,
not the document, is the unit of analysis**. Everything downstream keys off
`sentence_id`. That choice comes directly from the theory in this topic, and
being able to justify it earns a paragraph in the report.

The opinion quintuple is also the cleanest way to explain what the database
schema is for. Each column exists because the quintuple says an opinion has
five parts, and you can point at where each one lives, including the one this
system does not really capture.

---

## 2. The concept (Understand / Apply)

### Three levels

| level | question answered | what is lost |
|---|---|---|
| **Document** | Is this whole review/article positive? | Any internal disagreement. A review praising the battery and damning the screen averages to nothing |
| **Sentence** | Is this sentence positive? | Which *entity* or *aspect* the sentiment is about, if the sentence mentions several |
| **Entity/aspect** | Is this sentence positive *about X's Y*? | Nothing structural, but it is the hardest to do and needs the most machinery |

This project operates at the entity/aspect level and implements it as
sentence-level scoring conditioned on an aspect.

### The opinion quintuple

Bing Liu's formalisation: an opinion is

> **(entity, aspect, sentiment, opinion holder, time)**

Worked through one real sentence from this corpus:

> "Net interest margin declined 4 basis points to 2.11%."

| element | value | how the system knows |
|---|---|---|
| entity | DBS | `sentences.bank`, resolved per sentence |
| aspect | `net_interest_margin` | `sentence_aspects.aspect`, by centroid similarity |
| sentiment | negative | `aspect_sentiment.label` |
| **opinion holder** | **DBS management** | **Only approximated**, by `sentences.source = 'earnings'` |
| time | 2026-02-01 | `sentences.published_at` |

Four of the five map to columns. The fifth does not, and that gap has
consequences.

---

## 3. Where it lives in this repo (Apply)

| quintuple element | column | assigned by |
|---|---|---|
| entity | `sentences.bank` | `preprocess/pipeline.py` via `ingest/base.py` `detect_banks` |
| aspect | `sentence_aspects.aspect` | `aspects/assign.py` |
| sentiment | `aspect_sentiment.label` + `confidence` | `sentiment/score.py` |
| holder (proxy) | `sentences.source` | denormalised from `documents` |
| time | `sentences.published_at` | the source, or parsed from the earnings filename |

The rationale for sentence-level analysis is decision 1 in `docs/DESIGN.md`.

---

## 4. Analyze

### Why document level was rejected, concretely

A single Reddit comment in this corpus can praise a bank's dividend and
criticise its app in consecutive sentences. Scoring the document as a whole
averages those into meaningless neutrality. Since the entire product promise
is an *aspect* breakdown, document-level scoring would not merely lose
precision, it would make the dashboard's central feature impossible.

The measurable consequence: 36,884 sentences produce 79,987 (sentence, aspect)
pairs, so the average scored sentence carries **2.2 aspects**. At document
level those 2.2 judgements collapse into one.

### The holder gap, and why it is the interesting one

`source` is a proxy for opinion holder, and a coarse one:

| source | actual holder | how good is the proxy? |
|---|---|---|
| `earnings` | Bank management, describing itself | Good, and important — management is not a neutral observer |
| `arctic_shift` | An anonymous Reddit user | Weak. One prolific poster and a hundred separate users look identical |
| `newsapi` | A journalist, sometimes quoting an analyst | Weak, and conflates reporter with quoted source |

This is not a pedantic point. The most significant measured finding in the
project follows directly from it: earnings text scores 24.7% positive against
Reddit's 2.3%. That is a *holder* effect. Management describing its own
results is a systematically different opinion holder from a retail investor
discussing the stock, and the system's response — carrying a `source`
dimension on every index row so blended figures are never opaque — is
essentially an admission that the holder matters and is only partly modelled.

A per-author dimension would let you ask whether one Reddit user drives a
bank's sentiment. The schema cannot answer that, deliberately: storing author
identity for public but user-authored content is a privacy decision, not just
a schema one.

### Comparing where the aspect could have come from

| approach | what it is | why not used here |
|---|---|---|
| **Assign from a frozen taxonomy** (used) | Match sentence embeddings to fixed centroids | Chosen. Stable categories between runs, no labels needed |
| Extract aspect terms from the sentence | Sequence labelling (IOB tags) to find explicit aspect mentions | Needs labelled training data the project does not have, and only finds *explicit* aspects |
| Treat the document's topic as the aspect | Inherit from the article or thread | Same failure as document-level sentiment: a thread covers several aspects |

The second is what module 2 teaches as aspect term extraction, and the report
should name it as the road not taken. Its fatal limitation here is
implicit aspects: "they're paying out too much of their earnings" is about
dividend policy and contains no aspect term to extract.

---

## 5. Evaluate

**Sentence-level is the least contestable decision in the project.** Aspect-based sentiment is impossible without it.

**The cost is real though.** Sentence-level analysis loses cross-sentence
context. "DBS reported record profit. That won't last." Sentence two is
negative and its target is only recoverable from sentence one. The pipeline
scores them independently, so this fails silently. Nobody has measured how
often it happens, which would make a good report limitation with a number
attached.

**What the quintuple framing does not capture.** It assumes an opinion has one
holder and one target. A sentence like "analysts think DBS is overvalued but I
disagree" has two holders and two opposing sentiments. The schema stores one
row.

**When document level would be right.** If the product were "is this news
article about DBS positive or negative", document level would be correct and
far cheaper. The aspect breakdown is what forces the sentence.

---

## 6. Create

**Exercise (about an hour).** Measure what sentence-level analysis loses.

```python
# .venv-plp/bin/python3
import sqlite3
from collections import defaultdict
c = sqlite3.connect("data/plp.db")

rows = c.execute("""
    SELECT s.doc_id, s.sentence_id, a.aspect, a.label
    FROM aspect_sentiment a JOIN sentences s ON s.sentence_id = a.sentence_id
    WHERE s.source = 'arctic_shift'
""").fetchall()

per_doc = defaultdict(lambda: defaultdict(set))
for doc_id, sid, aspect, label in rows:
    per_doc[doc_id][aspect].add(label)

mixed = {d: {a: ls for a, ls in asp.items() if len(ls) > 1}
         for d, asp in per_doc.items()}
mixed = {d: a for d, a in mixed.items() if a}
print(f"documents with internally conflicting sentiment on the SAME aspect: "
      f"{len(mixed)} of {len(per_doc)}")

# Multi-aspect documents: what document-level scoring would have flattened
multi = sum(1 for asp in per_doc.values() if len(asp) > 1)
print(f"documents covering more than one aspect: {multi} of {len(per_doc)}")
```

**Expected outcome.** You should find a substantial share of documents cover
more than one aspect, which is the quantified argument for sentence-level
analysis, and a smaller share carry conflicting sentiment on the *same*
aspect, which is the quantified argument that document-level averaging
destroys information.

**Then extend it** to answer the harder question: pick 15 documents with
conflicting labels on one aspect and read them. How many are genuine
disagreement within one comment, and how many are the missing-context problem
from section 5 ("That won't last")? Report the split. That number does not
exist anywhere yet and belongs in the report's limitations.

---

## 7. Self-check

1. Give the quintuple for "OCBC's provisions rose sharply this quarter",
   taken from an OCBC results release.
2. Which element does this system approximate rather than capture, and with
   what?
3. Why is 79,987 aspect rows from 36,884 sentences an argument for
   sentence-level analysis?
4. Why can't aspect term extraction handle "they're paying out too much of
   their earnings"?
5. Earnings text is 24.7% positive against Reddit's 2.3%. Which quintuple
   element best explains that?

<details>
<summary>Answers</summary>

1. Entity: OCBC. Aspect: `asset_quality`. Sentiment: negative (rising
   provisions signal expected losses; a bare fact with clear valence).
   Holder: OCBC management, approximated by `source='earnings'`. Time: the
   release's `published_at`.
2. The opinion holder, approximated by `sentences.source`. It is a good proxy
   for earnings (management) and a weak one for Reddit, where every user
   collapses into one label.
3. Because it means the average scored sentence carries about 2.2 aspects.
   Document-level scoring would collapse those separate judgements into a
   single number, which is exactly the information the dashboard exists to
   show.
4. Because the aspect is implicit. There is no aspect term in the sentence to
   tag — "paying out too much of their earnings" describes payout ratio
   without naming it. Extraction methods find explicit mentions; this needs
   inference, which is why embedding similarity is used instead.
5. The opinion holder. Management describing its own results is a
   systematically more positive holder than a retail investor discussing the
   stock. That is why the index carries a `source` dimension so blended rows
   are never opaque.

</details>

---

## 8. Sources

**Repository**

- `docs/DESIGN.md` decision 1 — the sentence as unit of analysis
- `ingest/db.py` — the schema each quintuple element maps to
- `preprocess/pipeline.py`, `ingest/base.py` — per-sentence bank attribution
- `docs/data-viability.md` — the 24.7% vs 2.3% source comparison
- `docs/verification-ledger.md` — corpus counts

**Course material**

- `.project-context/course-content/NMSM-context.txt` — day 1 covers the
  quintuple, the three levels, and the eight sentiment sub-tasks; day 1 PM
  covers ABSA subtasks and the five aspect-extraction families

**External**

- Bing Liu's formulation of the opinion quintuple is standard in the ABSA
  literature and is taught in the NMSM module. **The primary source (Liu,
  *Sentiment Analysis and Opinion Mining*, 2012) was not fetched during this
  pass** — cite it directly rather than citing this file.

**Not verified**

- How often the missing-cross-sentence-context problem actually occurs. The
  exercise in section 6 is designed to produce that number; it has not been
  run.
