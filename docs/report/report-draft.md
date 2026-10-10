# Report draft: Retail Investor Sentiment for DBS, OCBC and UOB

*Draft of 2026-10-01, updated 2 October, written from the repository's
evidence for the team to edit and own. The method in full, with diagrams, is
in [approach.md](approach.md); findings, limits and fixes in one place, in
[findings-limitations-solutions.md](findings-limitations-solutions.md). Every figure links to the evidence file it comes from; re-check
each against the final database before submission (results will move when
the team re-runs the pipeline). Sections marked **[team]** must be written
by people. The submission limit is 20 pages.*

---

## 1. Business problem

Singapore's retail investors are interested in local equities but short of
research they can use. In the SIAS–Beansprout Pulse Survey (March 2025,
1,011 respondents), over 80% remained interested in Singapore stocks; 55%
cited a lack of attractive stocks and 57% low returns as barriers; 24% cited
a lack of guidance or research and 19% unfamiliarity. Among investors with a
small Singapore allocation, 31% named unfamiliarity as the main reason, and
81% read an analyst report before investing. In an MDRT survey (April 2025,
2,000 Singapore adults), 34% rated their own financial literacy good and
15% excellent. *(Survey figures as recorded in the proposal; cite the
original reports.)*

DBS, OCBC and UOB are the default entry point: together they are roughly
half of the Straits Times Index *(proposal figure; update the market
capitalisation at submission)*. Investors read scarce analyst PDFs rather
than a regularly updated view of what is being said about each bank and on
which topic. The project builds that view: aspect-based sentiment per bank,
from public text, with the evidence behind every number and a chatbot that
answers questions from the same store.

## 2. Datasets

### 2.1 The corpus

Public text about the three banks, collected in batches, frozen on
26 September 2026 ([STATUS.md](../STATUS.md), "Current corpus"):
28,002 documents and 44,345 sentences, 6 January 2020 to 25 September 2026.

| source | what | documents | sentences |
|---|---|---|---|
| Reddit `r/singaporefi`, via the Arctic Shift archive | posts and comments | 21,805 | 24,675 |
| Earnings PDFs (bank IR sites; UOB via the Wayback Machine) | results releases, presentations, DBS analyst-call transcripts | 178 | 12,254 |
| Google News RSS | headlines, January 2023 onward | 5,685 | 5,447 |
| CNA | full articles found through the Wayback Machine | 207 | 1,599 |
| Yahoo Finance news | headlines and summaries | 114 | 344 |
| NewsAPI | titles and descriptions | 13 | 26 |
| Yahoo Finance consensus | analyst counts, ratings, price targets (structured, not text) | — | — |

By bank: DBS 24,431 sentences, UOB 12,502, OCBC 7,412. Two properties the
results must be read against: DBS carries about six times the earnings text
of the other two, and earnings text, written by the banks, scores far more
positive than Reddit; and Google News favours recent articles, so news
volume rises towards the present. Source decisions and their evidence are
in [data-viability.md](../data-viability.md) and DESIGN decisions 2, 3, 14
and 20; the news filter and its rejections in [news-data.md](../news-data.md).

**Collection ethics.** Only free, public endpoints; no paywalled content; no
vendor sentiment used as a label; CNA fetched at its robots.txt crawl delay
and kept out of git; UOB's PDFs taken from the Wayback Machine rather than
defeating its site's bot protection (DESIGN decision 3).

### 2.2 The labelled set

Two annotators labelled 1,300 sentences on 27 September for aspect and
sentiment; after removing 5 train/dev copies of test sentences and 18
duplicates, 1,277 remain: 978 train/dev (stratified) and 299 test (drawn at
random, frozen). Sentiment: 275 negative, 543 neutral, 459 positive.
Sentiment agreement between the two annotators was κ 0.93
([annotation-agreement-2026-09-27.md](../evidence/annotation-agreement-2026-09-27.md)).
Two limits: the aspect labels came from one corrected column, so aspect
agreement between people was not measured; and the annotators saw a local
model's suggested sentiment, which the final labels match on 91.6% of rows.

An independent rater, Claude Opus 5.5, labelled the same sentences blind
(DESIGN decision 22): against the human labels, aspect κ 0.80 and sentiment
κ 0.79, every sentiment disagreement on the neutral boundary
([llm-rater-2026-10-01.md](../evidence/llm-rater-2026-10-01.md)).
These are human–LLM figures. A blind top-up sheet of 268 sentences for the
five aspects with fewer than 80 labels is ready for people
([labelling-topup-2026-10-01.md](../evidence/labelling-topup-2026-10-01.md)).

### 2.3 Reproducibility

The database is distributed as a dated, checksummed snapshot (README,
"Getting the database"); every figure in this report traces to a command in
an evidence file under `docs/evidence/`.

## 3. Solution approach

### 3.1 Pipeline

Ingest → clean and split into sentences (spaCy with financial abbreviation
handling) → attribute each sentence to a bank → assign aspects → score
sentiment → aggregate into an index → serve through a REST API and a
chatbot. The sentence is the unit of analysis throughout (DESIGN decision 1).
Diagram: [docs/diagrams/04-pipeline.md](../diagrams/04-pipeline.md).

### 3.2 Text-mining task 1: aspect discovery

FinBERT sentence embeddings (mean-pooled), reduced with UMAP and clustered
with HDBSCAN. The 25 September run produced 338 clusters; the team labelled
them by hand into ten aspects plus `other`, which became the taxonomy
(DESIGN decision 21,
[aspect-taxonomy-2026-09-25.md](../evidence/aspect-taxonomy-2026-09-25.md)).
A sweep of `min_cluster_size` on the full corpus showed the structure is
fine-grained or nothing: 358 clusters (65% noise) at 10; at 25 and 50 one
cluster holding nearly every sentence; 25 clusters (52% noise) at 100
([aspect-discovery-sweep-2026-09-30.md](../evidence/aspect-discovery-sweep-2026-09-30.md)).

### 3.3 Text-mining task 2: aspect categorisation

Baseline: seed-centroid assignment (cosine similarity to each aspect's seed
sentences above a floor of 0.65). Replacement: a local LLM chooses one
aspect per sentence from a fixed zero-shot prompt (role, task, the eleven
definitions, constraints, eleven invented examples) with structured output
(DESIGN decision 16,
[llm-aspect-classifier-2026-10-01.md](../evidence/llm-aspect-classifier-2026-10-01.md)).

### 3.4 Text-mining task 3: bank entity recognition

spaCy's pretrained NER with an entity ruler in front and a gazetteer
fallback, resolving each organisation mention to DBS, OCBC, UOB or "not the
bank" (POSB → DBS; Bank of Singapore and Great Eastern → OCBC; UOB Kay Hian,
DBS Vickers and Aston Martin → not the bank), against alias matching as the
baseline (DESIGN decision 18,
[bank-ner-2026-10-01.md](../evidence/bank-ner-2026-10-01.md)).

### 3.5 Text-mining task 4: sentiment classification (the DNN)

Baseline: base FinBERT zero-shot, which scores everything in the database
today. The deep neural network: FinBERT fine-tuned on (sentence, aspect)
pairs, the aspect given as its readable name ("Dividend Policy"), up to 8
epochs with early stopping, three seeds; the configuration was chosen by
5-fold cross-validation, never on the test split. Repeated on two more
seeds, the chosen input (the readable name) proved no better than the aspect
key: +0.005 dev macro-F1 over 15 paired folds
([noise-floor-cv-2026-10-02.md](../evidence/noise-floor-cv-2026-10-02.md)). Other baselines: VADER
(lexicon) and TF-IDF with logistic regression
([finetune-fixes-2026-10-01.md](../evidence/finetune-fixes-2026-10-01.md)).

### 3.6 The sentiment index

Each label counts +1, 0 or −1, weighted by the model's confidence and by
source, and shrunk towards zero for small samples; rows spanning aspects
count each sentence once. Windows of 7 days, 30 days and all time, per
bank, aspect and source, and a continuous series by week, month or quarter
([diagrams/12-index-computation.md](../diagrams/12-index-computation.md)).

### 3.7 The conversational interface

A tool-calling chatbot (sentiment, comparison, trend, coverage, evidence
search, analyst consensus) over the same store, with conversation memory,
guards that answer advice and off-topic questions without the model, and
checks that flag citations and figures the tools never returned (DESIGN
decision 19). Local models through Ollama by default; hosted backends
optional. A Streamlit dashboard presents the index, and a REST API serves
every view to any other frontend (DESIGN decision 23,
[api-integration.md](../api-integration.md)).

## 4. Test results

*As of 1 October 2026; re-run before submission.*

### 4.1 Sentiment classification

Test split, 299 sentences (39 negative, 166 neutral, 94 positive):

| model | macro-F1 | accuracy |
|---|---|---|
| VADER lexicon | 0.427 | 0.49 |
| TF-IDF + logistic regression | 0.515 | 0.57 |
| base FinBERT, zero-shot | 0.571 | 0.70 |
| fine-tuned FinBERT, three seeds | 0.604 ± 0.035 | 0.61–0.68 |
| fine-tuned, the three averaged | 0.615 | 0.66 |
| the average, with a neutral margin chosen on dev | 0.624 | 0.68 |

Sources: [finetune-fixes-2026-10-01.md](../evidence/finetune-fixes-2026-10-01.md),
[error-analysis-2026-10-01.md](../evidence/error-analysis-2026-10-01.md).
The fine-tuned model leads on macro-F1 by about one seed standard deviation
and trails base FinBERT on accuracy: it calls more neutral sentences
positive or negative, and finds far more of the negative ones. Most of its
errors are Reddit descriptions of retail products.

### 4.2 Aspect categorisation

Against the 1,277 human aspect labels:

| method | top-1 | macro-F1 |
|---|---|---|
| always the commonest aspect | 0.374 | 0.049 |
| seed-centroid (current pipeline) | 0.413 | 0.296 |
| `qwen3:4b` | 0.719 | 0.671 |
| `llama3.1:8b` | 0.729 | 0.679 |
| Opus 5.5 (reference rater) | 0.842 | 0.789 |

Sources: [llm-aspect-classifier-2026-10-01.md](../evidence/llm-aspect-classifier-2026-10-01.md),
[llm-rater-2026-10-01.md](../evidence/llm-rater-2026-10-01.md).

### 4.3 Bank entity recognition

On the corpus, NER and alias matching attribute 763 sentences differently,
mostly DBS Vickers, UOB Kay Hian and POSB. Against Opus 5.5 as a provisional
reference on the 201-sentence gold sheet, NER names exactly the right banks
for 200 sentences, alias matching for 126
([bank-ner-2026-10-01.md](../evidence/bank-ner-2026-10-01.md)). **[team]**
The figures to report come from the gold sheet once people label it
(`python -m preprocess.bank_ner evaluate`).

### 4.4 The chatbot

Gold set v2, 32 questions, on the two local models
([chatbot-eval-build-2026-10-01.md](../evidence/chatbot-eval-build-2026-10-01.md)):

| | `llama3.2:3b` | `llama3.1:8b` |
|---|---|---|
| correct tool | 18 / 24 | 20 / 24 |
| advice and no-data questions handled | 8 / 8 | 8 / 8 |
| answers citing evidence no tool returned | 15 | 11 |
| the same, with evidence written without a search removed | 0 real (2 false alarms) | 0 |
| conversations, every turn right (after two fixes) | 4 / 4 | 4 / 4 |

Every invented citation came from an answer that never searched for
evidence; removing such evidence in code (`CHATBOT_ENFORCE_EVIDENCE=strip`)
ended them without changing tool choice. Retrieval ranks the asked-about
topic no better than random when the query is phrased as a question (MRR
0.217, random 0.217), and far better when it names the aspect (0.559). An
LLM judge asked for one faithfulness score passed every answer; asked to list
unsupported quotes, sources and figures, the same model caught all 11 known
inventions. **[team]** Add the human faithfulness ratings and the SASSI user
study.

## 5. Conclusions **[team]**

To write: what the results support and what they don't; the limits
(STATUS.md, "Before you trust any number"); what you would do with more
time. Points the evidence raises: the neutral boundary is the hardest call
for people, the LLM rater and the model alike; aspect assignment by
embedding similarity fails and an LLM classifier fixes most of it;
retrieval needs the topic named.

## 6. References

*Verify every entry and its details before submission.*

- Araci, D. (2019). FinBERT: Financial Sentiment Analysis with Pre-trained
  Language Models. arXiv:1908.10063. (Model: `ProsusAI/finbert`.)
- Hutto, C. J., & Gilbert, E. (2014). VADER: A Parsimonious Rule-based Model
  for Sentiment Analysis of Social Media Text. ICWSM.
- Landis, J. R., & Koch, G. G. (1977). The Measurement of Observer Agreement
  for Categorical Data. Biometrics, 33(1), 159–174.
- McInnes, L., Healy, J., & Melville, J. (2018). UMAP: Uniform Manifold
  Approximation and Projection for Dimension Reduction. arXiv:1802.03426.
- McInnes, L., Healy, J., & Astels, S. (2017). hdbscan: Hierarchical density
  based clustering. Journal of Open Source Software, 2(11).
- Pedregosa, F., et al. (2011). Scikit-learn: Machine Learning in Python.
  JMLR, 12.
- Wolf, T., et al. (2020). Transformers: State-of-the-Art Natural Language
  Processing. EMNLP: System Demonstrations.
- Honnibal, M., & Montani, I. spaCy (`en_core_web_sm`).
- Meta AI (2024). The Llama 3 Herd of Models. arXiv:2407.21783.
  (`llama3.1:8b`, `llama3.2:3b` through Ollama.)
- Qwen Team (2025). Qwen3 Technical Report. (`qwen3:4b` through Ollama.)
- Libraries: FastAPI, PyTorch, pandas, pdfplumber, trafilatura.

## 7. Individual contribution summaries **[team]**

One paragraph per member, written by that member.

## 8. GenAI usage declaration

The running log is in `.project-context/course-content/course-context.md`,
section 8: Claude Code for documentation, code, evaluation runs and the
Opus labelling, with what it did well, what went wrong and was caught, and
where people stayed in control. **[team]** Add the pros and cons as you
experienced them.
