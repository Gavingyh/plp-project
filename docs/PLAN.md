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

| decision | why | consequence |
|---|---|---|
| **A local LLM assigns each sentence one aspect**: one of ten (DESIGN decision 21; the proposal's four until 30 Sep) or `other` | Seed-centroid assignment gives 46% of sentences three or four aspects at once and sends evaluative sentences to `other` ([evidence](evidence/aspect-sentiment-concentration-2026-09-24.md)). An LLM prompted with a fixed schema reads meaning, not vocabulary (NMSM Day 2, zero-shot ABSA) | Changes the method; the taxonomy changed separately on 30 Sep (DESIGN 21). Replaces DESIGN decisions 4 and 5. Evaluated against the 1,277 human aspect labels (next row) |
| **Annotators record aspect and sentiment for each sentence** | Labels no longer depend on the automatic assignment being right, and the human aspect choices become the gold set that evaluates the LLM's aspects | Candidates are re-drawn to include news; the annotation guideline gains aspect definitions ([annotation-guideline.md](annotation-guideline.md)) |
| **Four text-mining tasks**: aspect discovery (clustering), aspect categorisation (the LLM aspects above), bank entity recognition (new), sentiment classification (the fine-tuned DNN) | All four are real and evaluable. NER is scoped narrowly so it doesn't compete with labelling | The course notes' earlier NER claim becomes true. See section 7 |
| **No personal names in the repository** | Team preference; work is split offline | Ownership is recorded by role (section 4); contribution summaries go in the report only |
| **The daily ingestion job is not running on any machine** | Stopped on 26 Sep at the team's request. Over its three runs Yahoo added nothing and one run failed at wake-up before the network was up | The corpus is frozen at 26 Sep unless someone runs `run_news_pull.py` / `run_daily_batch.py` by hand. `scripts/com.plp.dailybatch.plist` remains as a template |

### Made on 2026-10-04

By the project owner, from the decision brief (`docs/briefs/decisions-2026-10-02.html`, numbers in brackets). Each is built on its own branch and applied in the re-score week, not before.

| decision | evidence | consequence |
|---|---|---|
| **DBS Vickers counts as DBS** (6) | DBS Group's list of subsidiaries, 31 Dec 2024 (section 7) | Bank recognition resolves "DBS Vickers" to DBS; UOB Kay Hian stays a separate broker. About 456 sentences change attribution if NER is applied |
| **POSB counts as DBS at collection** (14) | DBS acquired POSBank in 1998, and POSB runs as a DBS brand | "POSB" joins the DBS aliases in `ingest/base.py`. Affects future collection only: POSB-only posts and sentences missed so far come back only if collection is run again |
| **Hosted backends never receive Reddit, CNA or unlisted-source text** (13) | The safe default; Reddit's developer policy restricts third-party use of its content | The Claude and OpenAI/Groq backends withhold that evidence and earlier answers, as Gemini does since 4 Oct |
| **Earnings PDF links become relative paths** (10) | The developer's macOS username is in 178 document and 12,254 sentence URLs, every snapshot and 29 committed files (audit, 4 Oct) | Code first; the database rewrite runs in the re-score week, with a backup |
| **The 7- and 30-day windows count back from the newest sentence**, labelled "as of" its date (12) | The newest sentence is from 25 Sep and collection is stopped, so a rebuild after 12 Oct would leave the 7-day window empty (`aggregate/index.py`) | The tools, the prompt, the starter questions and the API say "as of <date>"; the dashboard owner adds the label to the dashboard |
| **Demo chatbot model: `llama3.1:8b`** (11) | On 4 Oct the 3B was not faster (median 20.7 s a question against 22.2 s) and called the wrong tool for the trend question ([chatbot-intent](evidence/chatbot-intent-2026-10-04.md)) | The default chatbot model changes from `llama3.2:3b` |
| **Chatbot evidence settings on: `CHATBOT_ENFORCE_EVIDENCE=strip`, `CHATBOT_ASPECT_QUERY=1`** (8) | With strip, no invented citation in the 4 Oct live run; ranking by the aspect's name lifts retrieval MRR from 0.217 to 0.559 ([chatbot-eval-build](evidence/chatbot-eval-build-2026-10-01.md)) | Both become the defaults in `config/chatbot.yaml` |
| **Labels: the human labels stay where Opus disagrees** (202 aspects, 173 sentiments); no full relabel | Opus is an additional rater, never the gold label (DESIGN decision 22) | Only the rows on the economist and wealth-or-retail boundaries are fixed, after the team decides those two rules |
| **Passing mentions stay** (9) | The default; they are about 6% of sentences | No filtering; the report gives the 6% |

### Made on 2026-10-10

By the team. Recorded from the meeting note; the follow-on work and the points left open are on the team to-do (`docs/briefs/team-todo-2026-10-07.html`).

| decision | consequence |
|---|---|
| **Retail products carry sentiment directed at the bank**; a product's feature is no longer kept neutral | A rule in `docs/annotation-guideline.md`, worded as the "customer value" option of the 7 Oct paper; the team should confirm the wording |
| **Wealth means the priority and private tiers** (Treasures, priority banking and the like); loans, mortgages and unit trusts are not wealth by themselves | The `wealth_business` row and a rule in the guideline. `config/aspects.yaml` still has the old definition: changing it means redoing the corpus aspect run (about a day) |
| **The test rows are not relabelled** | The 299 test labels stay; the report should say annotators saw a model's suggestion |
| **Aspects: both methods run and are reported**, the centroids and the LLM | Which one the index, dashboard and chatbot serve is still open (below) |
| **Opus 5.5 labels every sentiment sheet** | Done 10 Oct, 2,075 rows ([evidence](evidence/llm-rater-new-rules-2026-10-10.md)). The labels are reported as LLM labels, not human labels (the owner's change to the meeting note, for the GenAI declaration). This replaces the 4 Oct decision above that the human labels stay where Opus disagrees; `CLAUDE.md` and DESIGN decision 22 still state the old rule until the owner changes them |
| **The models train on Opus's labels; the test rows keep their labels** (from the two decisions on labelling and on the test rows) | Train and test follow different retail rules, which can lower test scores for a reason unrelated to the model; the report says so. On the 299 test rows Opus differs from the kept labels on 42 sentiments |
| **Evaluation reports precision and recall for positive, negative and neutral** beside macro-F1 and accuracy; every model is re-run and the team links the superior one to the chatbot and dashboard | `train/evaluation_report.py` already writes them; the re-run is in the 12 to 18 Oct week |

### Still open

| decision | who | by |
|---|---|---|
| **Aspects shown by the product:** both methods are run and reported (10 Oct); the re-score applies the LLM's, with llama's answer where the two local models disagree, unless the team says otherwise (brief, 1) | team | before the re-score |
| **Blended index:** one blended index, or per-source indices shown side by side. UOB has the highest earnings-only score and the lowest blended one, purely because it publishes less earnings text (brief, 3) | team | 5 Oct |
| **Bank economists:** whether a bank economist's macro forecast is "about the bank" (brief, 4) | team | 5 Oct |
| **Scoring model:** chosen from the re-run table of every model, with precision and recall for each class (10 Oct); say what "superior" means first (brief, 7) | team | 12 to 14 Oct |
| **OpenAI backend:** provide a key to verify it, or stop claiming it works (Gemini verified 30 Sep). Since 1 Oct it takes `OPENAI_BASE_URL`, so a free Groq key can verify it ([RUNBOOK](RUNBOOK.md), Chatbot backends) | team | 19 Oct |

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
| **Aspect categorisation** (local LLM, fixed schema) | text-mining task 2 | TA Day 2 (text categorisation); NMSM Day 2 AM (structured ABSA prompt: role, task, schema, constraints, examples) | accuracy and macro-F1 against human aspect labels (section 2); confusion matrix; baseline: seed-centroid assignment |
| **Sentiment classification** (fine-tuned FinBERT) | the DNN; text-mining task 4 | TPML Day 3 (transfer learning, BERT fine-tuning); NMSM Days 1–3 (ABSA, lexicon and supervised approaches) | per-class precision, recall, F1 and macro-F1 on a frozen random test split, mean ± sd over ≥3 seeds; baselines: base FinBERT zero-shot, VADER lexicon, TF-IDF + logistic regression |
| Annotation | labels | TA Day 1 (annotation methodology, Cohen's κ); TA Day 1 (LLMs as annotators with human correction) | κ ≥ 0.6 on a shared 150-row sample, for aspect and for sentiment |
| Sentiment index, served by the API | sentiment mining | NMSM Day 2 PM (aggregation by holder, time, aspect; heat maps; time series) | shrinkage and volume floors already in `aggregate/index.py` |
| **Chatbot** (tool calling over the index and evidence) | conversational UI | CNI Day 1 (design process, grounding, tool calling, state, guardrails, evaluation); CNI Day 2 (grounded-generation contract, evaluation discipline) | frozen ~30-question gold set; retrieval Hit@K and MRR; faithfulness via an LLM judge calibrated on human ratings; SASSI questionnaire with 5–8 users; multi-turn scenarios |

Course modules: TA = Text Analytics, NMSM = New Media and Sentiment Mining,
TPML = Text Processing using Machine Learning, CNI = Conversational UIs. The
speech content of CNI Days 3–4 is out of scope: the chatbot is text-only.

---

## 4. Workstreams

Owners are roles, filled offline (no personal names, section 2). One person can hold more than one role.
"AI" means work an AI coding assistant can do with a person reviewing it; the
split is detailed in the checklist.

**Data and NER**
- ~~Load the CNA feed through `ingest/news_filter.py`~~ Done 2026-09-26:
  207 articles from 2023 on (DESIGN decision 20)
- Bank NER: gold set of ~200 sentences (people), the recognition and
  resolution step and its evaluation (AI). The step and the blank 201-row
  sheet are done (1 Oct, [evidence](evidence/bank-ner-2026-10-01.md));
  the labels are not
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
  The larger frozen set (v2, 32 questions), multi-turn scenarios, retrieval
  metrics and the judge are built (1 Oct, [evidence](evidence/chatbot-eval-build-2026-10-01.md));
  calibrating the judge needs people to fill `data/eval/ratings_sheet.csv`
- SASSI user study and transcript reading (people)
- Dashboard: a teammate owns the Streamlit dashboard in `dashboard/`
  (redesigned 1 Oct; DESIGN decision 23, amended). The API serves every view
  too ([api-integration.md](api-integration.md)). Still to do: the consensus
  panel hides UOB (one date for all banks), and every tab needs checking
  after the redesign

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
Also 1 Oct: [Opus 5.5 as an additional labeller](evidence/llm-rater-2026-10-01.md)
(DESIGN 22), which gives the first aspect agreement figure (human–LLM κ 0.80).
1 Oct evening: [the fine-tuned model's errors and a neutral margin](evidence/error-analysis-2026-10-01.md),
[bank entity recognition](evidence/bank-ner-2026-10-01.md) (built; its gold
set is blank, for people), [the chatbot evaluation extended](evidence/chatbot-eval-build-2026-10-01.md)
(gold set v2, conversations, retrieval metrics, a judge; retrieval is the
weakest link), [what the two pending changes would do to the index](evidence/index-preview-2026-10-01.md),
the API extended so a dashboard needs nothing else (DESIGN 23, [api-integration.md](api-integration.md); the Streamlit dashboard stays in this repository),
a [report draft](report/report-draft.md) of the factual sections and an
[examiner's assessment](review/examiner-assessment-2026-10-01.md).
Overnight 1–2 Oct: [the chatbot's live runs](evidence/chatbot-eval-build-2026-10-01.md#live-runs)
(invented citations come from answers that never searched; the judge never
disagrees), [a blind top-up labelling sheet](evidence/labelling-topup-2026-10-01.md),
[cross-validation on two more seeds](evidence/noise-floor-cv-2026-10-02.md)
(the readable label is no better than the key), a second
[examiner's assessment](review/examiner-assessment-2026-10-02.md) and the
[team to-do list with reasons](briefs/team-todo-2026-10-07.html).
2 Oct: [the chatbot fixes, live](evidence/chatbot-eval-build-2026-10-01.md#second-round-2-oct-the-fixes-live)
(conversations 9/9; strip enforcement ends invented citations; the checklist
judge catches them), Opus as an extra rater on the top-up and NER sheets,
[local-context questions](local-context-questions.md), and for the report,
[the approach](report/approach.md) and
[findings, limitations and solutions](report/findings-limitations-solutions.md).

The original ordering: labelling gates the DNN, and aspects gate labelling
(annotators attach sentiment to an aspect), so the aspect classifier comes first.

| week | gate at the end of the week | people | AI |
|---|---|---|---|
| 28 Sep – 4 Oct | Candidates re-drawn and pre-labelled | Rotate API keys; fill roles; check the aspect classifier's 100-sentence validation sample | Aspect-classifier prompt and validation run; full run overnight; re-draw candidates; update the labelling sheet and tools for aspect + sentiment |
| 5 – 11 Oct | κ ≥ 0.6 on the shared sample; blended index decided | Agreement round (two people, 150 rows), then full labelling; NER gold set; CNA load reviewed (loaded 26 Sep) | Discovery re-run and sweep; NER step; frozen chatbot evaluation set; report structure and datasets/methods drafts |
| 12 – 18 Oct | ~1,000 rows labelled; model trained | Finish labelling; decide on passing mentions | Fine-tune (3 seeds); evaluate sentiment, aspect categorisation and NER; re-score the corpus |
| 19 – 25 Oct | Results frozen | Interpret results; transcript reading; SASSI sessions; decide the demo model and the OpenAI backend; rehearse | Chatbot evaluation; results tables and figures; video script; clean-copy install test |
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

*Note, 2 Oct:* DBS Vickers is in fact a DBS subsidiary (DBS Group's list of
subsidiaries, 31 Dec 2024); UOB Kay Hian is separately listed. The broker
rule is therefore under review for DBS Vickers only: see
`docs/evidence/bank-ner-2026-10-01.md` and the DBS Vickers question in
`docs/local-context-questions.md`.

*Decided 4 Oct:* DBS Vickers counts as DBS (section 2, made on 2026-10-04);
UOB Kay Hian stays "not the bank".

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
