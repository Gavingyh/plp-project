# Project plan to submission

Written 2026-09-26, after all four course modules had been delivered. This is
the working plan from here to submission. It supersedes the plans in
`.project-context/plan/`, which describe how the system was first built.

What is true today is in [STATUS.md](STATUS.md); why the system is built the
way it is, in [DESIGN.md](DESIGN.md). This file says what happens next, in what
order, and who can do it. A tickable version is
[submission-checklist.html](submission-checklist.html).

---

## 1. Deliverables

All due **Sunday 1 November 2026**.

| deliverable | weight | notes |
|---|---|---|
| System, source code, datasets, documentation | 20% | the repository plus the database snapshot |
| Report, under 20 pages | 20% | business problem, datasets, solution approach, test results, conclusions, references to public libraries and models, individual contribution summaries, GenAI usage declaration |
| Video, about 20 minutes | 5% | system demo, every member presents |
| Peer review | 5% | ongoing |

The course rubric requires: a conversational UI or sentiment mining (this
project has both); at least two text-mining tasks; at least one self-built or
fine-tuned deep neural network; Python.

---

## 2. Decisions

### Made on 2026-09-26

| # | decision | why | consequence |
|---|---|---|---|
| D1 | **A local LLM assigns each sentence one aspect**: one of ten (DESIGN decision 21; the proposal's four until 30 Sep) or `other` | Seed-centroid assignment gives 46% of sentences three or four aspects at once and sends evaluative sentences to `other` ([evidence](evidence/aspect-sentiment-concentration-2026-09-24.md)). An LLM prompted with a fixed schema reads meaning, not vocabulary (NMSM Day 2, zero-shot ABSA) | Changes the method; the taxonomy changed separately on 30 Sep (DESIGN 21). Replaces DESIGN decisions 4 and 5. Evaluated against the 1,277 human aspect labels (D2) |
| D2 | **Annotators record aspect and sentiment for each sentence** | Labels no longer depend on the automatic assignment being right, and the human aspect choices become the gold set that evaluates D1 | Candidates are re-drawn to include news; the annotation guideline gains aspect definitions ([annotation-guideline.md](annotation-guideline.md)) |
| D3 | **Four text-mining tasks**: aspect discovery (clustering), aspect categorisation (D1), bank entity recognition (new), sentiment classification (the fine-tuned DNN) | All four are real and evaluable. NER is scoped narrowly so it doesn't compete with labelling | The course notes' earlier NER claim becomes true. See section 7 |
| D4 | **No personal names in the repository** | Team preference; work is split offline | Ownership is recorded by role (section 4); contribution summaries go in the report only |
| D5 | **The daily ingestion job is not running on any machine** | Stopped on 26 Sep at the team's request. Over its three runs Yahoo added nothing and one run failed at wake-up before the network was up | The corpus is frozen at 26 Sep unless someone runs `run_news_pull.py` / `run_daily_batch.py` by hand. `scripts/com.plp.dailybatch.plist` remains as a template |

### Still open

| # | decision | who | by |
|---|---|---|---|
| O1 | Confirm D1 with the supervisor. It keeps the proposal's aspects but changes how they are assigned, which the report must explain | team, supervisor | 5 Oct |
| O2 | One blended index, or per-source indices shown side by side. UOB has the highest earnings-only score and the lowest blended one, purely because it publishes less earnings text | team, supervisor | 5 Oct |
| O3 | Default chatbot model for the demo: `llama3.1:8b` fabricates citations 13% of the time, `llama3.2:3b` 43–48%, but the 8B is slower. The harness now detects fabrication but can't prevent it, so this choice decides how many flagged answers a demo shows | team | 19 Oct |
| O4 | OpenAI backend: provide a key to verify it, or stop claiming it works (Gemini verified 30 Sep) | team | 19 Oct |
| O5 | Stricter relevance filtering for passing mentions ("paid via DBS PayNow"). It changes the data, so it must be decided before the final pipeline run | team | 12 Oct |

---

## 3. How the project uses the course

Every component, the module it draws on, and how it is evaluated. This table
is the backbone of the report's solution-approach section.

| component | rubric item | course source | evaluation |
|---|---|---|---|
| Corpus: Reddit, earnings PDFs, news, analyst consensus | data | TA Day 1 (CRISP-DM, text preparation); NMSM Day 2 PM (5-step system design) | coverage by source, bank and month ([data report](data-report-2026-09-24.html)); filter decisions logged in `data/news_flagged.csv` |
| Sentence segmentation, bank attribution | preprocessing | TA Day 1 (text preparation), Day 3 (IE pipeline) | counts; attribution errors surfaced in STATUS |
| **Bank entity recognition and resolution** | text-mining task 3 | TA Day 3 (NER, entity resolution); NMSM Day 1 PM (entity extraction, polysemy/synonymy) | precision, recall, F1 against a ~200-sentence gold set; baseline: today's alias matching |
| **Aspect discovery** (FinBERT embeddings → UMAP → HDBSCAN) | text-mining task 1 | TA Day 2 (clustering, topic modelling); NMSM Day 1 PM (aspect grouping) | cluster count and noise; cluster-to-aspect correspondence; informs whether `other` hides a missing aspect |
| **Aspect categorisation** (local LLM, fixed schema) | text-mining task 2 | TA Day 2 (text categorisation); NMSM Day 2 AM (structured ABSA prompt: role, task, schema, constraints, examples) | accuracy and macro-F1 against human aspect labels (D2); confusion matrix; baseline: seed-centroid assignment |
| **Sentiment classification** (fine-tuned FinBERT) | the DNN; text-mining task 4 | TPML Day 3 (transfer learning, BERT fine-tuning); NMSM Days 1–3 (ABSA, lexicon and supervised approaches) | per-class precision, recall, F1 and macro-F1 on a frozen random test split, mean ± sd over ≥3 seeds; baselines: base FinBERT zero-shot, VADER lexicon, TF-IDF + logistic regression |
| Annotation | labels | TA Day 1 (annotation methodology, Cohen's κ); TA Day 1 (LLMs as annotators with human correction) | κ ≥ 0.6 on a shared 150-row sample, for aspect and for sentiment |
| Sentiment index, served by the API | sentiment mining | NMSM Day 2 PM (aggregation by holder, time, aspect; heat maps; time series) | shrinkage and volume floors already in `aggregate/index.py` |
| **Chatbot** (tool calling over the index and evidence) | conversational UI | CNI Day 1 (design process, grounding, tool calling, state, guardrails, evaluation); CNI Day 2 (grounded-generation contract, evaluation discipline) | frozen ~30-question gold set; retrieval Hit@K and MRR; faithfulness via an LLM judge calibrated on human ratings; SASSI questionnaire with 5–8 users; multi-turn scenarios |

Course modules: TA = Text Analytics, NMSM = New Media and Sentiment Mining,
TPML = Text Processing using Machine Learning, CNI = Conversational UIs. The
speech content of CNI Days 3–4 is out of scope: the chatbot is text-only.

---

## 4. Workstreams

Owners are roles, filled offline (D4). One person can hold more than one role.
"AI" means work an AI coding assistant can do with a person reviewing it; the
split is detailed in the checklist.

**Data and NER**
- ~~Load the CNA feed through `ingest/news_filter.py`~~ Done 2026-09-26:
  207 articles from 2023 on (DESIGN decision 20)
- Bank NER: gold set of ~200 sentences (people), the recognition and
  resolution step and its evaluation (AI)
- Final data snapshot and dataset description for submission (AI, reviewed)

**Labelling** (critical path)
- Agreement round, full labelling, test split from the blind sheet (people)
- Re-drawn candidate set and pre-labels (AI)

**Modelling**
- LLM aspect classifier: prompt, validation sample, full run (AI; a person
  checks the validation sample)
- Aspect discovery re-run now that CNA is loaded, with a `min_cluster_size` sweep
  (AI runs it; people interpret it)
- Fine-tuning across three seeds, evaluation against baselines, re-scoring
  the corpus (AI, after labelling)

**Interfaces**
- Chatbot, from CNI: conversation memory, advice and off-topic guards, and
  the number check are **done** (26 Sep; [evidence](evidence/chatbot-harness-2026-09-26.md)).
  Still to do: a larger frozen evaluation set with multi-turn scenarios,
  retrieval metrics and a calibrated judge (AI)
- SASSI user study and transcript reading (people)
- ~~Dashboard: remove stale text, check every tab~~ The dashboard is now a
  teammate's separate project on the API (DESIGN decision 23); its contract
  is [api-integration.md](api-integration.md)

**Report and video** (everyone)
- Structure, datasets and methods drafts, results tables, script (AI)
- Conclusions, contribution summaries, GenAI pros and cons, recording (people)

---

## 5. Sequence

**Status on 30 Sep.** The text-analytics workstream ran ahead of this
sequence, without waiting for the aspect classifier: the 10-aspect taxonomy
(DESIGN 21), one labelling round of 1,300 rows by two people (sentiment
κ 0.93), and a first fine-tuning run all happened 25–27 Sep. What that
changes below: labelling no longer gates the DNN; the aspect classifier is
still to build, and is now evaluated against the human aspect labels instead
of feeding the labelling; aspect agreement was not measured and the five
smallest aspects are below 80 rows, so a top-up round is worth planning;
fine-tuning results are in [evidence/finetune-2026-09-30.md](evidence/finetune-2026-09-30.md).
Overnight experiments on 30 Sep–1 Oct:
[longer training and the aspect input](evidence/finetune-experiments-2026-09-30.md),
[centroid assignment against the human aspects](evidence/aspect-assignment-calibration-2026-09-30.md),
[the discovery sweep](evidence/aspect-discovery-sweep-2026-09-30.md) and
[the chatbot gold set on the rebuilt database](evidence/chatbot-eval-2026-09-30.md).
Overnight run, night 1 (1 Oct):
[fine-tuning fixes](evidence/finetune-fixes-2026-10-01.md),
[the LLM aspect classifier against the human aspects](evidence/llm-aspect-classifier-2026-10-01.md),
[a preprocessing dry run](evidence/preprocessing-dry-run-2026-10-01.md) and
[a clean-copy install test](evidence/install-test-2026-10-01.md).
Also 1 Oct: [Opus 5.5 as an additional labeller](evidence/opus-labeller-2026-10-01.md)
(DESIGN 22), which gives the first aspect agreement figure (human–LLM κ 0.80).

The original ordering: labelling gates the DNN, and aspects gate labelling
(D2 attaches sentiment to an aspect), so the aspect classifier comes first.

| week | gate at the end of the week | people | AI |
|---|---|---|---|
| 28 Sep – 4 Oct | Candidates re-drawn and pre-labelled | Rotate API keys; fill roles; check the aspect classifier's 100-sentence validation sample; book the supervisor meeting | Aspect-classifier prompt and validation run; full run overnight; re-draw candidates; update the labelling sheet and tools for aspect + sentiment |
| 5 – 11 Oct | κ ≥ 0.6 on the shared sample; decisions O1, O2 made | Agreement round (two people, 150 rows), then full labelling; supervisor meeting; NER gold set; CNA load reviewed (loaded 26 Sep) | Discovery re-run and sweep; NER step; frozen chatbot evaluation set; report structure and datasets/methods drafts |
| 12 – 18 Oct | ~1,000 rows labelled; model trained | Finish labelling; decide O5 | Fine-tune (3 seeds); evaluate sentiment, aspect categorisation and NER; re-score the corpus |
| 19 – 25 Oct | Results frozen | Interpret results; transcript reading; SASSI sessions; decide O3, O4; rehearse | Chatbot evaluation; results tables and figures; video script; clean-copy install test |
| 26 Oct – 1 Nov | Submitted | Conclusions, contribution summaries, GenAI declaration; record the video; final read-through; submit | Final snapshot and data report; second clean-copy test |

If labelling slips, the fallback is to fine-tune on whatever is labelled by
18 Oct with k-fold cross-validation instead of a fixed split (the proposal
allows either) and report the smaller set honestly.

---

## 6. Labelling design

- **Unit.** One sentence per row. The annotator chooses its aspect (one of
  the ten, or `other`) and its sentiment toward the bank as an investment on
  that aspect, or flags it as not about the bank. The 27 Sep round corrected
  the aspect on exported (sentence, aspect) rows, which produced duplicates
  that `train/labels.py` now removes, and had no not-about-the-bank flag.
- **Volume.** About 1,000 rows. The proposal's target is 200–300 rows per
  *sentiment* class; that is an overall target, not a per-aspect one. The
  re-drawn set also aims for at least ~80 rows per aspect so aspect
  categorisation can be evaluated on every class.
- **Sources.** Stratified across Reddit, earnings and news, and across banks.
  The 27 Sep round: 617 Reddit, 477 earnings, 183 news rows.
- **Test split.** Rows drawn at random before any model-based selection,
  labelled only from the blind sheet, which shows no model output. The 27 Sep
  round drew 300; its blind-sheet labels are identical to the same
  annotators' labels on the candidates sheet, where the suggestion was
  visible, so they cannot count as blind
  ([evidence](evidence/annotation-agreement-2026-09-27.md)).
- **Pre-labels.** The local LLM's suggestions are shown for the train/dev
  split only.
- **Agreement.** Two people label the same 150 rows first. Cohen's κ is
  computed separately for aspect and sentiment, targeting ≥ 0.6 each; below
  that, the guideline is tightened before the rest is split up.

## 7. Scope of the NER task

Recognise mentions of organisations and resolve each to DBS, OCBC, UOB or
"not the bank". spaCy's pretrained English model is already installed; its
NER is currently switched off. Resolution handles what alias matching gets
wrong or can't express: POSB (part of DBS), lowercase "dbs" in Reddit text,
UOB Kay Hian and DBS Vickers (brokers, not the bank's own business), Bank of
Singapore and Great Eastern (OCBC subsidiaries), and ambiguous "DBS"
(Aston Martin, deep brain stimulation). Evaluated against a ~200-sentence
gold set weighted towards those cases, with alias matching as the baseline.
Estimated at half a day of AI work plus about two hours of annotation.

---

## 8. Risks

| risk | effect | mitigation |
|---|---|---|
| Labelling finishes late | No trained model, no DNN result | Start the agreement round in week 2 at the latest; fallback in section 5 |
| Aspect classifier is poor on Reddit text | Weak aspect results | The validation sample shows this in week 1; the human aspect labels measure it either way, and a poor result is still a reportable finding |
| The local LLM run is slow | Week 1 slips | Batch several sentences per prompt; run overnight; news and earnings first if time is short |
| API keys still exposed | Misuse of the team's keys | Rotate them now (still not done on 26 Sep) |
| Demo machine differs from the development machine | A tab or backend fails live | Clean-copy test twice; record the demo rather than run it live where possible |
| Unofficial data endpoints change | No new data | The corpus is frozen for analysis; snapshots are the record of the data used |
