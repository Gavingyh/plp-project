# Learning folder

Study material for the concepts and techniques this project uses, written for
teammates who attended the lectures but have not read this codebase.

It exists because the report has to explain every technique used, the written
exam covers the four course modules, and four people need a shared vocabulary
for a system only some of them have worked on. Each topic is grounded in this
repository: the worked examples use this corpus, and the exercises produce a
number you can check.

---

## How to use it

Read the topic for whatever you are about to work on or write up. Each file
stands alone, so there is no required order, though the prerequisites at the
top of each file point to what helps.

If you are writing the report, sections 4 and 5 of each topic (Analyze,
Evaluate) are the ones that turn "we used X" into a defensible justification.
If you are revising for the exam, sections 1, 2 and 7 (Why, Concept,
Self-check) are the fast path.

**Do not treat these files as a citable source.** Where a claim comes from a
paper or a library's documentation, the URL is in section 8 of that file, and
that is what belongs in the report's reference list. Claims that could not be
verified are marked as such rather than quietly dropped.

---

## Bloom's taxonomy, and what "level 4" means here

These files target the revised taxonomy of Anderson and Krathwohl (2001),
which turned Bloom's original 1956 nouns into verbs and added a second
knowledge dimension:

| # | level | what it asks of you |
|---|---|---|
| 1 | Remember | Retrieve relevant knowledge from memory |
| 2 | Understand | Determine the meaning of instructional messages |
| 3 | Apply | Use a procedure in a given situation |
| 4 | **Analyze** | Break material into parts and determine how they relate |
| 5 | **Evaluate** | Make judgements based on criteria and standards |
| 6 | **Create** | Put parts together into something new |

Every topic here is written to at least level 4, and most reach 5 and 6. In
practice that means each file contains:

- **Analyze** — the technique broken into parts, compared against at least two
  alternatives on stated criteria, and traced through one real example from
  this corpus.
- **Evaluate** — a judgement on this project's choice, with the evidence, what
  that evidence does *not* show, and when the opposite choice would be right.
- **Create** — an exercise you can do against this repo in under two hours,
  with an expected outcome so you know whether you got it right.

A file that only defines a term and shows where it is used would be level 2 or
3, and would not meet the bar this folder is written to.

---

## Topics

### 01 · Text Analytics (course module 1)

| topic | covers | status |
|---|---|---|
| [CRISP-DM for text mining](01-text-analytics/crisp-dm-for-text-mining.md) | The six phases mapped onto this project's real sequence, and where it deviated | complete |
| [Text preparation and sentence segmentation](01-text-analytics/text-preparation-and-sentence-segmentation.md) | spaCy, financial abbreviations, per-source cleaning, near-duplicate hashing | complete |
| [TF-IDF versus contextual embeddings](01-text-analytics/tfidf-versus-contextual-embeddings.md) | Bag-of-words against FinBERT embeddings; why mean pooling and not CLS | complete |
| [Clustering with UMAP and HDBSCAN](01-text-analytics/clustering-with-umap-and-hdbscan.md) | What each does, noise points, why 281 clusters is not a taxonomy | complete |
| [Annotation and inter-annotator agreement](01-text-analytics/annotation-and-inter-annotator-agreement.md) | Guideline design, Cohen's κ, the 0.6 target, LLM-assisted annotation | complete |
| [LLMs as classifiers and raters](01-text-analytics/llms-as-classifiers-and-raters.md) | Zero-shot structured classification, an LLM as a blind second annotator, anchoring, two-model agreement as confidence | added 2026-10-01 |
| [Entity recognition and resolution](01-text-analytics/entity-recognition-and-resolution.md) | spaCy NER with an entity ruler, a resolution table, a gazetteer fallback, evaluating at the sentence level | added 2026-10-01 |

### 02 · Sentiment Mining (course module 2)

| topic | covers | status |
|---|---|---|
| [Levels of sentiment analysis and the opinion quintuple](02-sentiment-mining/levels-and-the-opinion-quintuple.md) | Document, sentence and aspect level; the quintuple mapped onto this schema | complete |
| [Aspect-based sentiment analysis](02-sentiment-mining/aspect-based-sentiment-analysis.md) | ABSA subtasks, the five aspect-extraction families, frozen-centroid assignment | complete |
| [Index aggregation and shrinkage](02-sentiment-mining/index-aggregation-and-shrinkage.md) | Why `score × n/(n+5)`, source weights, why earnings text reads positive | complete |

### 03 · Text Processing with Machine Learning (course module 3)

| topic | covers | status |
|---|---|---|
| [Transfer learning and FinBERT](03-text-processing-with-ml/transfer-learning-and-finbert.md) | BERT pre-training, what `ProsusAI/finbert` actually is, corrected benchmarks | complete |
| [Evaluation, splits, leakage and macro-F1](03-text-processing-with-ml/evaluation-splits-and-leakage.md) | Why the test split is frozen, the leak that happened here, macro vs micro | complete |
| [Model selection under noise](03-text-processing-with-ml/model-selection-under-noise.md) | Cross-validation, paired fold differences, the noise floor, class weighting, a dev-chosen threshold | added 2026-10-01 |

### 04 · Conversational UI (course module 4)

| topic | covers | status |
|---|---|---|
| [Tool-calling agents](04-conversational-ui/tool-calling-agents.md) | The loop, tool schemas, why no framework, backend message-format differences | complete |
| [Retrieval-augmented generation and hybrid search](04-conversational-ui/rag-and-hybrid-search.md) | SQL pre-filter, cosine over cached embeddings, lexical boost, vs a vector DB | complete |
| [Grounding, hallucination and citation verification](04-conversational-ui/grounding-and-citation-verification.md) | Why prompt rules failed, the two code-level enforcements, results by model | complete |
| [Evaluating retrieval and chatbots](04-conversational-ui/evaluating-retrieval-and-chatbots.md) | Hit@K, MRR and an exact random baseline; why question-phrased retrieval fails here; multi-turn checks; a calibrated LLM judge | added 2026-10-01 |

*No course context file exists for module 4 in this repository, so these three
lean on the code and on primary documentation rather than lecture material.*

### 05 · Finance domain

| topic | covers | status |
|---|---|---|
| [Singapore banks, SGX and the STI](05-finance-domain/singapore-banks-sgx-and-sti.md) | D05, O39, U11; MAS; reporting cadence and what the PDF filenames mean | complete |
| [Bank earnings vocabulary](05-finance-domain/bank-earnings-vocabulary.md) | NIM, NPL, CET-1, credit cost, ROE and the rest, with corpus frequencies | complete |
| [Earnings releases, analyst calls and consensus](05-finance-domain/earnings-calls-and-consensus.md) | What each document type is, Yahoo's 1–5 scale, why full reports are unavailable | complete |

### 06 · Engineering practices

| topic | covers | status |
|---|---|---|
| [Idempotent ingestion and resumable jobs](06-engineering-practices/idempotent-ingestion-and-resumable-jobs.md) | Deterministic IDs, checkpointing, the overnight run that was lost | complete |
| [Testing against captured payloads](06-engineering-practices/testing-against-captured-payloads.md) | Why no network in tests, what each regression test is defending | complete |
| [Data access ethics](06-engineering-practices/data-access-ethics.md) | The WAF, the Wayback route, unofficial APIs, what "public" does not mean | complete |

---

## Rehearsing for the examiners

[docs/review/examiner-assessment-2026-10-01.md](../docs/review/examiner-assessment-2026-10-01.md)
puts thirteen questions to the project at Bloom levels 4–6, each with what a
strong answer would draw on, plus the threats to validity a marker will
raise. Read it alongside the Analyze and Evaluate sections here; the topics
added on 2026-10-01 answer most of its questions.

Topics written before 26 September carry a dated **Updated 2026-10-01** note
where a fact has since changed (labels now exist, results now exist); the
text under the note is kept as written.

---

## Verification status

Every figure drawn from this project traces to
[../docs/verification-ledger.md](../docs/verification-ledger.md). Every
external claim carries its source URL and access date in the file's Sources
section.

One correction found while writing this folder belongs here, because
it was about to go into the report as fact. The project context recorded
"FinBERT benchmarks at ~88.2% accuracy vs ~62.1% for lexicon-only scoring" and
marked it *verified, safe to cite*. It is neither. The FinBERT paper reports
0.86 accuracy on the full Financial PhraseBank and 0.97 on the
all-annotators-agree subset, and contains no Loughran-McDonald baseline at
all. Details in
[transfer-learning-and-finbert.md](03-text-processing-with-ml/transfer-learning-and-finbert.md).
