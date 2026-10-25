# Status: what the system does and how far to trust it

What is built, what each headline figure rests on, and what is not done. For
the reasoning behind each design choice see [DESIGN.md](DESIGN.md); for how
to run anything, [RUNBOOK.md](RUNBOOK.md); for the documentation map and the
current figures with their sources, [README.md](README.md). The earlier,
longer version of this page, with the project's history, is kept as a
record in [archive/STATUS-2026-10-12.md](archive/STATUS-2026-10-12.md); do
not quote figures from it.

---

## What the system does

| Step | What happens | Where |
|---|---|---|
| Collect | Reddit posts and comments (Arctic Shift, from 2020), the banks' earnings reports (DBS and OCBC from their sites, UOB from the Wayback Machine), news (Google News headlines, Yahoo Finance, NewsAPI, full CNA articles found through the Wayback Machine), 25 broker research reports, and Yahoo Finance analyst consensus. Every news item passes one relevance and duplicate filter, and each rejection is logged. | `ingest/` |
| Prepare | Splits text into sentences (with financial abbreviations handled), cleans each source, attributes each sentence to a bank, removes near-duplicates. | `preprocess/` |
| Aspect | Gives each sentence one aspect, chosen by a local `llama3.1:8b` from 10 aspects plus `other`. The 10 aspects were derived from clustering the corpus's FinBERT embeddings. | `aspects/`, `config/aspects.yaml` |
| Sentiment | Labels each (sentence, aspect) pair positive, neutral or negative with the fine-tuned model in use. Base FinBERT's labels are stored beside them for comparison. | `sentiment/`, `train/`, `config/model_version.py` |
| Index | For each bank, aspect, source and window (7 days, 30 days, all time), averages the labels (+1, 0, -1), weighted by the model's confidence and by source (news 1.5, every other source 1.0), and shrinks the mean by n/(n+5). The 7- and 30-day windows end at the newest stored sentence, 25 Sep 2026, not at today. | `aggregate/index.py`, `config/sources.yaml` |
| API | FastAPI: 20 paths, 21 operations, every number fetchable, a bad `bank`, `window` or `bucket` rejected with HTTP 422. The contract is `docs/api/openapi.json`. | `api/`, [api-integration.md](api-integration.md) |
| Dashboard | Streamlit, maintained by a teammate. It reads only through the API, which returns only the model in use. Its Data Management page runs the pipeline: it starts a run through the API (`/pipeline/runs`) on chosen sources (local PDFs, the CNA cache, Google News, Reddit, NewsAPI), and a worker checks the setup, imports, prepares, assigns aspects, scores and rebuilds the index, showing each stage ([manual-pipeline.md](manual-pipeline.md)). | `dashboard/`, `api/pipeline.py`, `pipeline/` |
| Chatbot | A local `llama3.1:8b` sorts each question into one of 11 intents; every intent except an in-scope question gets a reviewed fixed reply from `config/intents.yaml`. An in-scope question goes to the answer model (OpenAI `gpt-6-luna` by default; `llama3.1:8b` through Ollama, or Claude, when chosen), which calls six tools over the index and the evidence. Before an answer is shown, a draft with a figure, reading or quote no tool returned is rewritten, then trimmed or withheld. | `chatbot/`, `config/chatbot.yaml`, `config/intents.yaml` |
| Setup | Docker (`compose.yaml`) or a native install. The dataset is one file, `data/data.zip`; the fine-tuned models download from the public Hugging Face repo `plp-bank-sentiment/plp-finbert-absa`. | [README](../README.md), [RUNBOOK.md](RUNBOOK.md) |

---

## Before you trust any number

| Claim you might make | What the evidence supports |
|---|---|
| "Bank X is more positive than bank Y" | Blended scores follow each bank's mix of sources: earnings text, management describing its own results, scores far higher than Reddit for every bank, and DBS has about six times the earnings text of either other bank (9,093 sentences against 1,600 and 1,561). Compare banks on one source at a time (table below). On all sources, all time, UOB (+0.107) is lower than DBS (+0.143) and OCBC (+0.129) with sampling taken into account; DBS's lead over OCBC is not established (gap 0.015, 95% interval -0.004 to 0.032), and it reversed when the sentiment model changed. Over 30 days DBS is below both others by more than sampling explains; seven-day figures, on 42 to 90 sentences a bank, cannot separate the banks ([evidence](evidence/index-uncertainty-2026-10-14.md)). No interval has been computed for the one-source rows. |
| "Fine-tuning improved sentiment classification" | Modestly, on macro-F1. On the 299 first-round test sentences people labelled, the model in use (three seeds averaged) scores macro-F1 0.670 against base FinBERT's 0.571; each seed alone scores 0.628, 0.657 and 0.662 (mean 0.649, sd 0.018), all above base. The gain is in finding negative (recall 0.21 to 0.59) and positive (0.53 to 0.73) sentences, paid for with neutral recall (0.91 to 0.73); about half of what it calls negative, people did not (precision 0.48; with only 39 negative test sentences, one sentence moves these figures noticeably). Accuracy is 0.716 against 0.699, and the difference is not significant (exact McNemar p = 0.65). On the 100 broker research test sentences: 0.770 against 0.687 ([model card](model-card.md)). |
| "The model was trained and tested cleanly" | With three limits. Its training labels came from an LLM rater, not from people (1,563 sentence-aspect pairs). The first-round test labels were made with a small local model's suggestion in view, which annotators kept on about nine rows in ten, so that test set is not blind; the broker research test sentences were labelled with no suggestion. The model was chosen among candidates by test macro-F1, under a rule written down before the test sentences were scored ([model card](model-card.md)). |
| "The model's labels match people's" | Close overall, coarse as a check. On the 399 test sentences, the share positive minus the share negative is 0.153 by the model and 0.185 by people, a difference of -0.033 (95% interval -0.095 to 0.030). On Reddit test sentences the two match (0.011 each); the largest difference is on broker research (-0.100). A bias the size of that interval would not show here and would matter for gaps of 0.01 to 0.04 between banks, so measurement, not sampling, is the larger uncertainty ([evidence](evidence/index-uncertainty-2026-10-14.md)). |
| "The aspect breakdown shows X" | Each sentence has one aspect, which matches the aspect people chose on 73.9% of the 1,277 sentences they labelled ([evidence](evidence/wealth-definition-trial-2026-10-12.md)). Per-aspect cells are small: their sampling intervals run from about plus or minus 0.014 (DBS retail banking, 9,099 sentences) to plus or minus 0.146 (UOB dividends, 62 sentences) ([evidence](evidence/index-uncertainty-2026-10-14.md)). An aspect error reaches the sentiment, because the model reads the aspect: when 6,914 sentences were re-filed under other aspects, 896 changed label ([model card](model-card.md)). |
| "The chatbot's answers are grounded" | Its quotes and figures are checked, its wording is not. On the 32-question gold set, no answer shown carried a figure no tool returned, on `gpt-6-luna` or on `llama3.1:8b` ([evidence](evidence/chatbot-fixes-2026-10-24.md)). The checks cannot judge whether the model describes a figure correctly: a person rated 32 answers by `llama3.1:8b` from a run before the fixes and found 7 of the 26 the model wrote unfaithful to the tool data (wrong years, periods, ranks and topics), none of them caught by the checks ([evidence](evidence/human-ratings-2026-10-24.md)). Code fixes followed; asked those 7 questions three times each, `gpt-6-luna` was right in 21 of 21 tries and `llama3.1:8b` in 16 of 21, as read by the AI assistant, not rated by a person; the seven are the questions the fixes targeted, so this is not a held-out result. |
| "Reddit text stays on the machine" | Yes. A hosted model (OpenAI or Claude) receives the question, the tools' figures, and sentences from news, CNA, broker research and the banks' reports. Reddit text, and text from any source not listed in `config/sources.yaml`, is withheld before the request is sent (`chatbot/backends/base.py`). |
| "News volume rose sharply in 2026" | An artefact of Google News ranking recent articles higher. Normalise per month before comparing periods ([news-data.md](news-data.md)). |
| "CNA covered the banks more in 2023 to 2024 than in 2025 to 2026" | CNA articles are those the Wayback Machine happened to capture, with a bank in the URL: 0 to 13 a month. Use CNA for its full text, not its volume ([news-data.md](news-data.md)). |

### The index by source (all time, model in use)

| Source | DBS | OCBC | UOB |
|---|---|---|---|
| All sources | +0.143 (24,978 sentences) | +0.129 (7,774) | +0.107 (13,092) |
| Reddit | +0.058 (12,226) | -0.009 (3,936) | +0.058 (9,371) |
| Earnings reports | +0.276 (9,093) | +0.343 (1,561) | +0.332 (1,600) |
| Google News headlines | +0.177 (2,510) | +0.217 (1,446) | +0.174 (1,491) |
| CNA | -0.161 (915) | -0.020 (435) | -0.120 (249) |
| Broker research | +0.552 (151) | +0.184 (251) | -0.021 (239) |

From the `sentiment_index` table, `window = 'all_time'`, `aspect = 'ALL'`,
the model in use. Each bank has a different mix of sources, so its blended
score moves with that mix; a cell on a few hundred sentences, such as broker
research, is far less certain than the Reddit or earnings rows.

---

## Current corpus

| | count |
|---|---|
| documents | 28,852 |
| sentences | 45,844 |
| period | 6 Jan 2020 to 25 Sep 2026; nothing published later was collected (25 broker research reports added on 4 Oct and 825 older Reddit posts on 11 Oct were all published earlier) |
| scored sentence-aspect pairs | 45,844 for the model in use and 45,844 for base FinBERT (one aspect a sentence) |

By source:

| source | documents | sentences |
|---|---|---|
| Reddit (`arctic_shift`) | 22,630 | 25,533 |
| Earnings reports (DBS, OCBC, UOB) | 178 | 12,254 |
| Google News (headlines) | 5,685 | 5,447 |
| CNA (full articles) | 207 | 1,599 |
| Broker research (`sgx_research`) | 25 | 641 |
| Yahoo Finance news | 114 | 344 |
| NewsAPI | 13 | 26 |

By bank: DBS 24,978 · UOB 13,092 · OCBC 7,774 sentences. Earnings sentences
by bank: DBS 9,093 · UOB 1,600 · OCBC 1,561.

Labels given by the model in use: 13,976 positive, 24,211 neutral, 7,657
negative. Base FinBERT, on the same sentences: 9,344, 31,983 and 4,517.

Sentences by aspect (`aspect_sentiment`, model in use):

| aspect | label | sentences |
|---|---|---|
| `retail_banking_sentiment` | Retail Banking Products & Customer Experience | 20,877 |
| `other` | Other / Not an investment aspect | 6,786 |
| `investor_stock_sentiment` | Investor / Retail Stock Sentiment | 4,565 |
| `income_profit_results` | Income & Profit Results | 3,834 |
| `management_guidance` | Management Guidance | 2,184 |
| `asset_quality` | Asset Quality / Provisioning | 1,699 |
| `net_interest_margin` | Net Interest Margin | 1,425 |
| `wealth_business` | Wealth Management / Private Banking | 1,423 |
| `capital_liquidity` | Capital & Liquidity | 1,262 |
| `macro_market_environment` | Macro & Market Environment | 1,175 |
| `dividend_policy` | Dividend Policy | 614 |

Every figure in this section was read from `data/plp.db`. The database is
not in git; it is shared inside `data/data.zip`, and the README lists the
snapshot it holds with its checksum. News collection and its rules are in
[news-data.md](news-data.md).

Codebase: 51,195 lines of Python in git, 29,536 outside `tests/`; 2957
tests in `tests/` (3004 with the diagram and notebook checks).

---

## Done

**Collection and preparation.** Every source in the table above, through
idempotent adapters: re-running one inserts nothing new. One command runs
every news pull (`run_news_pull.py`); the dashboard's Data Management page
runs a manual update from local PDFs, the CNA cache, Google News, Reddit or
NewsAPI ([manual-pipeline.md](manual-pipeline.md)). A daily launchd job
exists but is not installed.

**Aspects.** Taxonomy discovery by clustering FinBERT embeddings
([evidence](evidence/aspect-taxonomy-2026-09-25.md)); the LLM classifier
(`aspects/llm_classify.py`), evaluated against people's aspect labels and
applied to the whole corpus by `aspects/assign.py`
(`assignment_method: llm`). The embedding-similarity method it replaced
matched people's aspect on 41% of labelled sentences and gave a sentence
6.4 aspects on average ([evidence](evidence/llm-aspect-classifier-2026-10-01.md);
6.4 from [rescore-rehearsal-2026-10-12.md](evidence/rescore-rehearsal-2026-10-12.md)).

**Labels.** Two people labelled 1,300 first-round sentences, 1,277 after
removing duplicates and train/test leakage: they corrected each sentence's
suggested aspect together, so agreement between people on aspect was not
measured, and labelled sentiment separately, with kappa 0.93, an upper bound because
both saw the same suggested label and kept it on most rows
([evidence](evidence/annotation-agreement-2026-09-27.md)). An LLM rater,
blind to every other label, labelled the same sentences and agrees with the
people at kappa 0.80 on aspect and 0.79 on sentiment; it is kept as an
additional rater in `data/labeled/llm_rater/`, and its labels train the
model in use ([model card](model-card.md)). People also labelled 100 broker
research test sentences with no model suggestion.

**Sentiment model.** FinBERT further pretrained on 42,822 of the corpus's
sentences (every labelled sentence and anything resembling one left out),
then fine-tuned on (sentence, aspect) pairs, three seeds averaged, with
checksums and a model card ([model card](model-card.md),
[evidence](evidence/model-rerun-2026-10-11.md)). The weights are on
Hugging Face.

**Index.** Per bank, aspect, source and window, with confidence and source
weighting and small-sample shrinkage; a time series by week, month or
quarter (`GET /sentiment/series`) computed by the same code as the stored
index, so a chart cannot disagree with the headline. Bootstrap intervals
and a test of the index's constants: no all-time headline moves by more
than 0.011 under any variant tried, and the order DBS, OCBC, UOB holds
([evidence](evidence/index-uncertainty-2026-10-14.md)).

**Chatbot.** Conversation memory; the intent classifier
([evidence](evidence/chatbot-intent-2026-10-04.md)); six tools; evidence
search that ranks a topic's sentences by the question's words, then the
newest, and uses `all-MiniLM-L6-v2` vectors when no topic is named, because
FinBERT's own vectors ranked no better than a random draw
([evidence](evidence/search-models-2026-10-24.md)); figures, readings,
ranks, the data's end date and a bank's strongest and weakest topics
handed to the model as sentences to copy; checks on every figure and quote,
with a failing draft rewritten, then trimmed, before it is shown
([evidence](evidence/chatbot-fixes-2026-10-24.md)); a gold-set evaluation
with a recheck mode that re-scores saved answers without calling a model
(`chatbot/run_eval.py`).

**Engineering.** 2957 tests, external APIs mocked with captured payloads;
central logging; start, stop and status scripts; a Docker setup that
restores `data.zip`, downloads and checks the models, and starts Ollama, the
API and the dashboard (validation in [RUNBOOK.md](RUNBOOK.md)); a clean
native install from the README on Python 3.14
([evidence](evidence/install-test-2026-10-12.md)).

---

## Chatbot evaluation

On the 32-question gold set (`chatbot/eval_gold_set.py`, `GOLD_SET_V2`),
with the database described above:

| Check | `gpt-6-luna` (default), run on the final code | `llama3.1:8b` (local), run after the description fixes |
|---|---|---|
| Right tool chosen | 24 / 24 (23 / 24 in two earlier runs) | 24 / 24 |
| Advice declined, missing data admitted | 8 / 8 | 8 / 8 |
| Citation fabrication flagged | 0 / 32 | 0 / 32 |
| Answered by a fixed reply, not the model | 6 / 32 | 6 / 32 |
| A figure no tool returned, in the model's first draft | 3 / 32 | 1 / 32 |
| The same, in the answer shown | 0 / 32 | 0 / 32 |
| Conversation turns correct | 9 / 9 | 9 / 9 |
| Median seconds per model-written answer | 5.9 | 78, on a processor shared with other jobs (43 in the run before the fixes) |

Sources: `data/eval/chatbot_eval_summary_luna_shown_v2.md` and
`chatbot_eval_summary_fixes_v2.md`, with the times and conversation results
in [evidence/chatbot-fixes-2026-10-24.md](evidence/chatbot-fixes-2026-10-24.md).

What these checks do not cover, and what does:

- **Whether the model describes a figure correctly.** A person rated the 32
  answers by `llama3.1:8b`, from a run before the fixes, on faithfulness,
  relevance and correctness; 7 of the 26 model-written answers stated something the tool data
  contradicts, and an AI judge agreed with the person only weakly
  (weighted kappa 0.22) ([evidence](evidence/human-ratings-2026-10-24.md)).
  The fixes for those faults were measured by the AI assistant reading the
  answers to the same 7 questions asked three times (not a person's rating,
  and not held out, since the fixes target these questions): 21 of 21 right on `gpt-6-luna`, 16 of
  21 on `llama3.1:8b`, whose remaining fault is reporting a different score
  when a topic has too little recent data. A person's rating of the default
  model's answers is not yet done (below).
- **Whether cited evidence is relevant.** Only a person reading the
  transcripts can judge it; the results files in `data/eval/` hold every
  tool call, its raw result and the answer.

Earlier findings, on the first 23-question gold set and older code, that
shaped the design:

- **Prompt rules did not keep local models grounded.** `phi4-mini` called a
  tool in 0 of 16 questions yet was flagged for citation fabrication in 19
  of 23 answers (`data/eval/chatbot_eval_summary_phi4-mini_latest.md`);
  `llama3.2:3b` was flagged in 10 to 11 of 23 answers over two runs and
  `llama3.1:8b` in 3 of 23. The grounding checks moved into code as a
  result ([evidence](evidence/chatbot-eval-rerun-2026-09-11.md)).
- **Declining advice was a design problem, not a model one.** No model
  tested handled more than 3 of the 7 advice and out-of-scope questions
  correctly ([evidence](evidence/chatbot-eval-rerun-2026-09-11.md));
  answering them with a fixed reply in code raised that to 7 of 7, though
  the off-topic rule was written after seeing these questions
  ([evidence](evidence/chatbot-harness-2026-09-26.md)).
- **A rate means little without its error count.** A model that times out
  produces no citations to fabricate and calls no tools, so its 0% and its
  tool score measure nothing; compare models only on runs with similar
  error counts ([evidence](evidence/chatbot-eval-rerun-2026-09-11.md)).

Reproduce with `chatbot.run_eval` (RUNBOOK, "Evaluating the chatbot").

---

## Not done

Open items are tracked on the team to-do page,
[briefs/team-todo.html](briefs/team-todo.html), which is the register of
known issues. The project is due on 1 Nov 2026. At the time of writing they
were:

- **Two human ratings of the chatbot's answers.** One person rates the
  default model's 26 model-written answers for faithfulness; a second
  person re-rates the original 32 answers blind, so agreement between
  people can be measured (weighted kappa).
- **The report.** Paste the pending text in
  [report/word-report-updates.md](report/word-report-updates.md) into the
  master report; add the limitations table and the conclusions; record the
  video.
- **A licence on the public Hugging Face model card**, a team decision: the
  models are built on base FinBERT, licensed CC BY-NC-SA 4.0, and the model
  card declares none.
- **CNA and broker research sentences in tracked files.** They are in the
  labelled data and evaluation results, which is acceptable while the
  repository is private; before any public release they are to be removed
  with their history.
- **A fourth success claim for aspect accuracy** has not been written,
  although the aspect method is decided.

---

## Limitations that still hold

- **Blending sources.** Whether management's own reports and retail chatter
  belong in one index is a fair methodological question. The design keeps
  the proposal's blend, makes its composition visible (every per-source row
  is in the API), and weights the banks' reports at 1.0, no more than a
  Reddit sentence. Their volume still moves each bank's blend, DBS's most
  (the by-source table above).
- **Uneven earnings coverage.** DBS publishes full analyst-call transcripts,
  so it has about six times the earnings sentences of either other bank.
- **Incidental mentions.** A sentence that names a bank in passing ("paid
  via DBS PayNow") still enters the corpus and counts towards that bank.
- **Sentences are not independent.** The bootstrap treats them as if they
  were; sentences from one Reddit thread or one report are not, so the
  intervals are, if anything, too narrow.
- **Training and test labels follow different rules for retail products.**
  The training labels treat a product's fee or perk as sentiment towards
  the bank; the first-round test labels were made earlier, when such
  sentences were neutral ([model card](model-card.md)).
- **Local language.** Singapore product names are common ("UOB One", "OCBC
  360"), and only about a dozen labelled sentences contain any Singlish,
  slang or emoji, so performance on them is barely measured.
- **The corpus is frozen.** Every window ends on 25 Sep 2026; "the last 7
  days" means the 7 days to that date.
- **Data sources that add nothing.** Alpha Vantage does not cover SGX
  tickers and stays in the code unused; NewsAPI's free tier gives about one
  month of lookback, headline and description only.

---

## Where the original plan was wrong

Cases where building the system contradicted the proposal, for the report's
methodology discussion.

**SGX was the wrong target for analyst reports.** The plan assumed analyst
reports could come from SGX. SGX hosts company announcements, not
third-party analyst reports, which are brokerage property behind
entitlements. The banks' own sites turned out to be open and to carry the
same earnings material, including DBS's analyst-call transcripts. Broker
research did come in later by another route: 25 notes, 12 from SGX's
research listing and 13 printed from sginvestors.io pages
([evidence](evidence/sgx-research-round-2026-10-04.md),
[evaluation](evidence/sgx-research-evaluation-2026-10-06.md)).

**The aspects did not emerge as predicted.** The plan assumed clustering
would surface the proposal's four aspects. On the Reddit-only corpus it
surfaced only a split between consumer banking and investment discussion;
with earnings text added, clusters such as the leverage ratio, Basel III
reforms and fee income by line appeared, none of which existed before
([evidence](evidence/aspect-discovery-2026-09-11.md)). The ten aspects in
use were derived from a later discovery run
([evidence](evidence/aspect-taxonomy-2026-09-25.md)), and assigning them by
embedding similarity failed: on Reddit, the sentences most similar to "net
interest margin" were all about retail products such as fees, cards and
fixed deposits. An LLM choosing one aspect a sentence replaced it.

**Adding a data source made a metric worse.** Earnings text closed a real
vocabulary gap and at first broke the cross-bank comparison, because it
arrived for two banks out of three: UOB had 4 earnings sentences until its
reports were fetched from the Wayback Machine, which gave it 1,600. More
data is not automatically better if it arrives unevenly.

**Prompt instructions were not enough for grounding.** The plan assumed
instructions in the prompt would keep the chatbot honest. Local models
fabricated citations after the prompt was tightened, so the checks moved
into code, and then to before the answer is shown.

**The sentiment model's own vectors were a poor search model.** The first
design reused FinBERT's embeddings for the chatbot's evidence search. FinBERT was
trained to classify sentiment, not to match sentences by topic, and its
ranking was no better than a random draw; the search now uses the question's
words within a topic and a model built for search otherwise
([evidence](evidence/search-models-2026-10-24.md)).
