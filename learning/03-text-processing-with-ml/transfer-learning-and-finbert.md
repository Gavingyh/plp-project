# Transfer learning and FinBERT

Subject: Text Processing using Machine Learning (module 3) · Bloom target: Analyze / Evaluate / Create
Prerequisites: [tfidf-versus-contextual-embeddings](../01-text-analytics/tfidf-versus-contextual-embeddings.md)

---

## 1. Why it matters here (Understand)

The project has roughly ten man-days per person and needs a deep neural
network that classifies financial sentiment. Training a language model from
scratch is out of the question at that budget. Transfer learning is what makes
the requirement achievable: start from a model that already understands
financial English, and spend the budget on the small labelled dataset that
adapts it to this specific task.

FinBERT is used here in two distinct ways, and confusing them is the most
common mistake when writing this project up.

---

## 2. The concept (Understand / Apply)

### The three-stage pipeline

| stage | what happens | data needed | who did it |
|---|---|---|---|
| **Pre-training** | A model learns general language by predicting masked words over a huge unlabelled corpus | Billions of words, unlabelled | Google, for BERT |
| **Further pre-training** (domain adaptation) | The same objective continues on domain text, so the model learns financial usage | Millions of words, unlabelled | Araci, on Reuters financial news |
| **Fine-tuning** | A task head is added and trained on labelled examples | Hundreds to thousands, labelled | **This project — not yet done** |

The economics: stage 1 costs thousands of GPU-hours, stage 3 costs minutes on
a laptop. Transfer learning means you inherit stages 1 and 2 for free.

### FinBERT's two jobs in this project

The proposal calls these Job 1 and Job 2, and the distinction is real.

**Job 1 — embeddings, no fine-tuning needed.** Feed a sentence in, take the
hidden-state vectors out, and use them to measure similarity. This is how
aspect assignment and chatbot retrieval work. No labels are required because
nothing is being judged, only compared.

**Job 2 — classification, fine-tuning required.** Feed a (sentence, aspect)
pair in, get positive/neutral/negative out. Knowing a sentence is *about*
asset quality does not tell you whether it is *good or bad news* about asset
quality, and that judgement is what needs supervised examples.

Today the project does Job 1 as designed and does Job 2 **zero-shot** with
base FinBERT, because no labelled data exists. Every sentiment number in the
system comes from a model that was never trained on this task or this corpus.

### Mean pooling, not CLS

`aspects/embed.py` averages the token embeddings rather than taking the `[CLS]`
token's vector. BERT's `[CLS]` is trained for next-sentence prediction, not to
be a sentence representation, so without a sentence-level objective of the
kind Sentence-BERT adds, `[CLS]` similarity is a poor signal. Mean pooling is
materially better and costs nothing.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| Embedding, mean pooling, MPS device selection | `aspects/embed.py` |
| Embedding cache (101 MB `.npz`) | `aspects/embed_store.py` |
| Zero-shot classification, `model_version = finbert-base-zeroshot-v1` | `sentiment/score.py` |
| Fine-tuning script, written and smoke-tested, never run for real | `train/finetune.py` |
| Baseline comparison harness | `train/evaluate.py` |

The `model_version` column in `aspect_sentiment` is part of that table's
primary key, so a fine-tuned model's scores can coexist with the zero-shot
ones rather than overwriting them. That is deliberate: it makes the before and
after comparison possible on the same rows.

---

## 4. Analyze

### What `ProsusAI/finbert` actually is

Be precise here, because the report will cite it.

Araci (2019) describes further pre-training BERT on **TRC2-financial**, a
corpus of Reuters financial news, then fine-tuning on **Financial
PhraseBank**, a set of sentences from financial news annotated for sentiment
by 16 annotators. The model on Hugging Face is the result: BERT, domain-adapted
to financial news, fine-tuned for three-way sentiment.

Two consequences follow directly, and both bite in this project:

1. **It was trained on financial news, not Reddit.** Applying it to
   `r/singaporefi` is a domain shift on top of a domain adaptation. That the
   Reddit corpus scores 94.8% neutral is consistent with a model encountering
   register it was not built for.
2. **Its notion of sentiment is the Financial PhraseBank's**, which asks
   annotators to judge sentiment from an investor's perspective. That happens
   to align well with this project's annotation guideline, which is
   convenient rather than accidental.

### The benchmark numbers, corrected

The project context recorded that FinBERT "benchmarks at ~88.2% accuracy vs
~62.1% for lexicon-only (Loughran-McDonald) scoring" and marked this
*verified, safe to cite in the report*. **It is not verified and should not be
cited.** Neither figure appears in the FinBERT paper.

What Araci (2019) Table 2 actually reports on Financial PhraseBank:

| model | accuracy (all data) | F1 (all data) | accuracy (100% agreement) | F1 (100% agreement) |
|---|---|---|---|---|
| LSTM | 0.71 | 0.64 | 0.81 | 0.74 |
| LSTM + ELMo | 0.75 | 0.70 | 0.84 | 0.77 |
| ULMFit | 0.83 | 0.79 | 0.93 | 0.91 |
| LPS | 0.71 | 0.71 | 0.79 | 0.80 |
| HSC | 0.71 | 0.76 | 0.83 | 0.86 |
| FinSSLX | — | — | 0.91 | 0.88 |
| **FinBERT** | **0.86** | **0.84** | **0.97** | **0.95** |

Three things to notice.

**There is no Loughran-McDonald baseline in this table.** The comparisons are
against two models the author implemented (LSTM, ULMFit) and three from prior
papers. The "versus lexicon-only" framing has no basis here at all, so the
comparison as recorded was not merely imprecise — it was against a baseline
the paper never ran.

**The two accuracy columns measure different things.** 0.97 is on the subset
where all annotators agreed, which is by construction the easy subset. Quoting
it as "FinBERT's accuracy" overstates the model. Quote 0.86, or quote both and
say which is which.

**The source is an MSc thesis.** arXiv:1908.10063 is submitted in partial
fulfilment of a University of Amsterdam master's degree, dated 25 June 2019.
It is a legitimate and heavily cited source, and it is not a peer-reviewed
conference paper. Cite it accurately.

### Comparing the alternatives that were available

| option | pre-training | cost to use here | why not chosen |
|---|---|---|---|
| **FinBERT** | BERT + financial news + PhraseBank | Download and run | Chosen. Financial domain, right task shape, small enough for a laptop |
| Base BERT | General English | Same | No financial language. Would need the domain adaptation stage the budget cannot afford |
| Sentence-BERT | General, with a sentence-similarity objective | Same | Better embeddings for Job 1, but no financial domain and no sentiment head for Job 2 |
| A general LLM, prompted | Vast, general | An API key or a slow local model | Does not satisfy the "self-built or fine-tuned DNN" requirement. Used for pre-labelling only |
| Train from scratch | — | Thousands of GPU-hours | Not remotely feasible at ten man-days |

The interesting near-miss is Sentence-BERT. For Job 1 alone it would likely
beat mean-pooled FinBERT, because it is explicitly trained so that cosine
similarity means something. Using FinBERT for both jobs buys consistency, one
model to explain and one embedding cache to maintain, at some cost in
retrieval quality. That trade was never measured here, which is a fair
criticism.

---

## 5. Evaluate

**FinBERT was right for the constraints.** It matches the
domain, satisfies the DNN requirement, runs on a laptop, and its two jobs map
cleanly onto the two text-mining tasks the rubric wants.

**What the evidence in this project does not show.** Nothing here demonstrates
that FinBERT is *good at this corpus*. Its 94.8% neutral rate on Reddit is
consistent with a well-calibrated model on genuinely neutral chatter and
equally consistent with a model out of its depth on informal register. Those
two readings cannot be separated without labelled data, which is exactly what
does not exist. Any report claim about FinBERT's suitability is currently an
assumption.

**The zero-shot gap is the project's central weakness.** Every sentiment
number in the dashboard, the API and the chatbot comes from a model applied to
a task it was not trained for, on a corpus it was not trained on. The
architecture for fixing this is written and smoke-tested. Only the labels are
missing.

**When the opposite choice would be right.** If the corpus were mostly
informal social text rather than earnings documents, a general sentiment model
fine-tuned on social data would likely beat FinBERT, whose advantage is
precisely the formal financial register that only half this corpus has.

---

## 6. Create

**Exercise (about ninety minutes).** Measure the domain-shift claim instead of
asserting it.

```python
# .venv-plp/bin/python3, with HF_HUB_OFFLINE=1
import sqlite3
from collections import Counter
c = sqlite3.connect("data/plp.db")

# Base FinBERT's label distribution by source, from what is already scored.
rows = c.execute("""
    SELECT s.source, a.label, a.confidence
    FROM aspect_sentiment a JOIN sentences s ON s.sentence_id = a.sentence_id
""").fetchall()

by_source = {}
for src, label, conf in rows:
    d = by_source.setdefault(src, {"n": 0, "labels": Counter(), "conf": 0.0})
    d["n"] += 1; d["labels"][label] += 1; d["conf"] += conf

for src, d in sorted(by_source.items(), key=lambda kv: -kv[1]["n"]):
    n = d["n"]
    dist = {k: round(100 * v / n, 1) for k, v in d["labels"].items()}
    print(f"{src:14s} n={n:6d}  mean confidence={d['conf']/n:.3f}  {dist}")
```

Then extend it: split the confidence distribution for neutral predictions by
source. A model that is *confidently* neutral on Reddit is making a judgement;
one that is *barely* neutral is closer to abstaining.

**Expected outcome.** You already know the label split is roughly 2.3%
positive on Reddit against 24.7% on earnings. The question the exercise
answers is whether mean confidence differs materially between the two. If
Reddit neutrals come with visibly lower confidence than earnings neutrals,
that supports the domain-shift reading. If confidence is similar, the model
believes its neutrals and the "Reddit is genuinely neutral" reading gets
stronger.

**Write two or three sentences for the report** stating which reading your
numbers support, and what would settle it definitively. (The answer to the
second part is labelled data, which is the point.)

---

## 7. Self-check

1. Why does aspect assignment need no labelled data while sentiment
   classification does?
2. What is the difference between further pre-training and fine-tuning?
3. Why does `aspects/embed.py` mean-pool instead of using `[CLS]`?
4. FinBERT reports 0.97 accuracy in one column of Table 2. Why is quoting that
   as "FinBERT is 97% accurate" misleading?
5. Why is `model_version` part of the primary key of `aspect_sentiment`?

<details>
<summary>Answers</summary>

1. Assignment only measures whether two pieces of text are similar, which
   pre-trained embeddings already support. Classification makes a judgement
   (is this good or bad news about this aspect) that the base model was not
   trained to make for this task, so it needs supervised examples.
2. Further pre-training continues the original unsupervised objective on
   domain text and needs no labels; it teaches the model the domain's
   language. Fine-tuning adds a task head and trains on labelled examples; it
   teaches the model the task.
3. BERT's `[CLS]` token is trained for next-sentence prediction rather than as
   a sentence representation, so without a sentence-level similarity objective
   its vectors are a poor similarity signal. Mean pooling is materially better
   and free.
4. That column is measured only on the subset of Financial PhraseBank where
   every annotator agreed, which is the easiest subset by construction. The
   figure for the full dataset is 0.86.
5. So a fine-tuned model's predictions can be stored alongside the zero-shot
   ones for the same (sentence, aspect) pairs rather than overwriting them,
   which is what makes a before-and-after comparison on identical rows
   possible.

</details>

---

## 8. Sources

**Repository**

- `aspects/embed.py` — mean pooling, and its stated reason
- `sentiment/score.py` — zero-shot classification, `model_version`
- `train/finetune.py` — the fine-tuning configuration
- `docs/DESIGN.md` — decision log
- `docs/verification-ledger.md` — corpus figures

**External**

- Araci, D. (2019). *FinBERT: Financial Sentiment Analysis with Pre-trained
  Language Models.* arXiv:1908.10063.
  https://arxiv.org/pdf/1908.10063 — accessed 2026-09-11. **Table 2 was read
  directly from the PDF**, and is the source of every benchmark figure in
  section 4. The document identifies itself as an MSc thesis, University of
  Amsterdam, 25 June 2019.
- Devlin et al. (2018), *BERT: Pre-training of Deep Bidirectional Transformers
  for Language Understanding*, arXiv:1810.04805 — cited for the pre-training
  and fine-tuning framing. **Not fetched during this pass**; verify before
  citing specifics.

**Not verified**

- The exact size and composition of the TRC2-financial corpus, and the number
  of Financial PhraseBank sentences. Described qualitatively above; get the
  figures from the paper before putting them in the report.
- Malo et al. (2014), the Financial PhraseBank paper. Referenced by name only;
  not fetched.
- The claim that Sentence-BERT would outperform mean-pooled FinBERT for
  retrieval on this corpus. Plausible and untested here.
- **Withdrawn claim:** "FinBERT ~88.2% vs ~62.1% lexicon-only". Not in the
  FinBERT paper and not traced to any source. A separate paper
  (arXiv:2412.19245) reports 72.2% against Loughran-McDonald's 50.1% on a
  different task and dataset; that was seen in a search result summary and
  **not verified in the paper itself**, so it is not a substitute citation.
