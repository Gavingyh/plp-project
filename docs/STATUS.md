# Status: what's done, what isn't, what to improve

Written to be usable directly as source material for the project report —
the sections map onto methodology, results, limitations and future work.

For reasoning behind design choices, see [DESIGN.md](DESIGN.md). For how to
run anything mentioned here, see [RUNBOOK.md](RUNBOOK.md). For what happens
next, see [PLAN.md](PLAN.md).

**Last updated 2026-10-04**, after the LLM's corpus aspect run, the
full-corpus index preview, the re-score step (`scripts/rescore.py`, tested on
a copy) and two rounds of bug fixes (HANDOFF, 3 and 4 Oct); before that,
2026-10-01, after the fine-tuning fixes, the LLM aspect classifier's
evaluation and the Opus 5.5 labeller; and 2026-09-26,
after the news backfill, a full pipeline run on the news, and the decisions
recorded in PLAN.md section 2. Sections that still describe an earlier state
carry a dated note saying so.

---

## Before you trust any number

| claim you might make | why you can't, yet |
|---|---|
| "DBS/OCBC show more positive sentiment than UOB" | No longer an artifact of missing UOB data — all three banks now have earnings coverage (DBS 9,093 sentences, UOB 1,600, OCBC 1,561). DBS still carries ~6x the earnings volume of the other two, so check the per-source breakdown before making a blended claim. |
| "Fine-tuning improved sentiment classification" | On macro-F1, modestly, and only since 2026-10-01: with the aspect's readable label as input, test macro-F1 0.604 ± 0.035 over three seeds, 0.615 for the three averaged, against base FinBERT zero-shot's 0.571 on the 299-row test split; the gap is about one seed standard deviation ([evidence](evidence/finetune-fixes-2026-10-01.md)). Don't credit the readable label for it: on two more seeds' cross-validation it is no better than the aspect key (+0.005 over 15 paired folds; [evidence](evidence/noise-floor-cv-2026-10-02.md)). Base FinBERT still has the higher accuracy (0.70 against 0.66): the fine-tuned model calls neutral sentences positive or negative more often. The test labels weren't independent of the LLM's suggestions, and all stored scores are still base FinBERT. Retrained on 2026-10-04 after a training bug (the pretrained head's outputs were renamed): every seed beats base (0.621 ± 0.027; 0.634 for the three averaged, accuracy 0.702), but these models are not adopted, a team decision ([evidence](evidence/retrain-2026-10-04.md)). On 2026-10-07, fine-tuning from FinBERT further pretrained on the corpus's own unlabelled sentences raised 5-fold cross-validation dev macro-F1 from 0.663 to 0.701, better in 13 of 15 paired folds; on the test split, scored once, 0.628 ± 0.022 over the seeds and 0.662 for the three averaged (accuracy 0.72); also not adopted, and to be pretrained again: a 7 Oct validation found 151 of its 43,036 pretraining sentences related to test sentences, a filter gap fixed that day ([evidence](evidence/dapt-2026-10-06.md)). On 2026-10-06 the models were also retrained with 280 human-labelled broker research rows added (1,258 train/dev), and scored on the original 299, on 100 broker research test rows and on both: 0.631, 0.735 and 0.674 for the three averaged ([evidence](evidence/sgx-research-evaluation-2026-10-06.md)); the Fine-tuning lead claim stays defined on the original 299. Fine-tuned on those 1,258 rows on the Mac on 2026-10-07, the adapted models led FinBERT on all three scopes (3 averaged 0.652, 0.751, 0.690 against 0.597, 0.698, 0.649; gains about one seed sd; [evidence](evidence/dapt-2026-10-06.md)). |
| "The aspect breakdown shows NIM sentiment is Y" | **Not meaningful yet, for any source.** Under the 10-aspect taxonomy (DESIGN decision 21) embedding-similarity assignment gives a sentence 6.4 aspects on average, and annotators changed the matched aspect on 86% of labelled rows ([evidence](evidence/annotation-agreement-2026-09-27.md)); under the earlier four, factual sentences took three or four aspects and evaluative ones fell to `other` ([evidence](evidence/aspect-sentiment-concentration-2026-09-24.md)). The assignment is being replaced (DESIGN decision 16): an LLM classifier (`llama3.1:8b`) matches the human aspect on 0.729 of the 1,277 labelled sentences against 0.413 for the embedding match; it classified the whole corpus on 3 Oct but isn't applied to the database yet ([evidence](evidence/llm-aspect-classifier-2026-10-01.md), [index preview](evidence/index-preview-2026-10-01.md)). Earlier finding, still true: **measured and failing for Reddit.** The 20 highest-similarity Reddit sentences assigned to `net_interest_margin` are all retail banking products (fees, cards, fixed deposits) and none are about margins. Earnings-only rows for that aspect are defensible; Reddit-only and blended ones are not. |
| "The chatbot cites its sources" | Local models invent citations: on gold set v2 (1 Oct), 15 of 32 answers on the default `llama3.2:3b`, 11 of 32 on `llama3.1:8b`, every one from an answer that never searched for evidence ([evidence](evidence/chatbot-eval-build-2026-10-01.md#live-runs)). A code check flags this; since 2 Oct `CHATBOT_ENFORCE_EVIDENCE=strip` (the default since 4 Oct) removes such evidence: replayed under the stricter checks of 3 Oct, citation warnings fell to 0 on both models (8B 11 → 0, 3B 16 → 0) and answers with a figure no tool returned to 0 on the 8B and 2 on the 3B, both real inventions ([evidence](evidence/chatbot-eval-build-2026-10-01.md)). |
| "GPT / Gemini backends work" | Gemini works: verified live on 2026-09-30 on numbers-only questions ([evidence](evidence/gemini-backend-2026-09-30.md)). Since 4 Oct every hosted backend (Gemini, Claude, OpenAI or Groq) withholds Reddit, CNA and unlisted-source evidence text and earlier answers, so they never reach a hosted model. The OpenAI backend has never been run: no key exists. Since 1 Oct it also reaches OpenAI-compatible providers such as Groq (`OPENAI_BASE_URL`), equally unverified. |
| "The chatbot's answers are grounded" | The harness flags invented figures and citations and answers advice and off-topic questions itself, but the local models still invent: on gold set v2 (32 questions, 1 Oct), 15 answers on the 3B and 11 on the 8B carried a citation warning ([evidence](evidence/chatbot-eval-build-2026-10-01.md#live-runs)). Without `strip`, a flagged answer is flagged, not corrected. |
| "News volume rose sharply in 2026" | An artefact of Google News ranking recent articles higher. Normalise per month before comparing periods ([news-data.md](news-data.md)). |
| "CNA covered the banks more in 2023–24 than in 2025–26" | CNA articles are those the Wayback Machine happened to capture, with a bank in the URL: 0 to 13 a month. Use CNA for its full text, not its volume ([news-data.md](news-data.md)). |

**The Reddit-only rows remain the cleanest cross-bank comparison** (DBS
-0.003, OCBC -0.029, UOB -0.022, all-time, 2026-09-30 — no meaningful
difference). Read blended rows alongside the per-source breakdown: earnings
text scores far higher than retail chatter for every bank (DBS +0.286, OCBC
+0.375, UOB +0.406), and Google News headlines sit in between (DBS +0.172,
OCBC +0.218, UOB +0.201), so blended scores (DBS +0.122, OCBC +0.136, UOB
+0.074) track each bank's source mix as much as its sentiment.

**Figures before 2026-09-30 counted a sentence once per aspect it matched.**
The cross-aspect rows (the headline, and each source's all-aspect row) now
count each sentence once. The old method weighted sentences that match many
aspects, which are mostly positive earnings prose, more heavily, and at the
new taxonomy's 6.4 aspects per sentence it would have lifted DBS's headline
to +0.23. The earlier published headlines were DBS +0.060, OCBC +0.071, UOB
+0.036; dated figures elsewhere in the docs used the old method.

---

## Current corpus

| | count |
|---|---|
| documents | 28,852 |
| sentences | 45,844 |
| (sentence, aspect) pairs scored | 291,508 (6.4 aspects per sentence under the ten-aspect taxonomy) |

Since 2026-10-11 these include the broker research source (25 reports, 641
sentences), copied in from the Windows PC's database, and the Reddit comments
refilled for September 2021, May 2024 and March 2025 (825 documents, 858
sentences). Six UOB earnings documents were re-dated the same day. Every
evaluation dated up to 10 Oct ran on the corpus before these changes: 28,002
documents, 44,345 sentences, 281,744 pairs. The local LLM has not classified
the 1,499 new sentences.
| date range | 6 Jan 2020 – 25 Sep 2026 |

By source:

| source | documents | sentences |
|---|---|---|
| Reddit (`r/singaporefi`) | 21,805 | 24,675 |
| Earnings PDFs (DBS, OCBC, UOB) | 178 | 12,254 |
| Google News (headlines) | 5,685 | 5,447 |
| CNA (full articles) | 207 | 1,599 |
| Yahoo Finance news | 114 | 344 |
| NewsAPI | 13 | 26 |

By bank: DBS 24,431 · UOB 12,502 · OCBC 7,412 sentences.

Earnings sentences by bank: DBS 9,093 · UOB 1,600 · OCBC 1,561.

Codebase on 2026-10-07: 34,270 lines of Python in git (18,768 excluding
tests), 2491 tests in `tests/` (2538 with the diagram and notebook checks).

These figures were taken from `data/plp.db` on 2026-09-26, after CNA was
loaded (DESIGN decision 20), the one planned addition; the corpus is frozen
from that date (the daily job is stopped).
The database is not in git: the snapshot matching it, and its checksum, are
listed in the README. [verification-ledger.md](verification-ledger.md)
records the 2026-09-11 figures with their queries; news figures and method
are in [news-data.md](news-data.md).

---

## Done

**Ingestion.** Reddit (Arctic Shift, 2020–present), earnings PDFs auto-fetched
from DBS and OCBC IR sites and, for WAF-blocked UOB, from the Wayback
Machine; news from Google News RSS (backfilled month by month from January
2023), Yahoo Finance and NewsAPI, and CNA full-text articles from 2023 found
through the Wayback Machine, all through one relevance and dedup filter
(`ingest/news_filter.py`, every rejection logged); Yahoo Finance analyst
consensus. All idempotent — re-running any adapter inserts nothing new. One
command runs every news pull (`run_news_pull.py`); a daily launchd job exists
but is not running.

**Preprocessing.** Sentence segmentation with financial-abbreviation handling,
per-source cleaning, per-sentence bank attribution, near-duplicate removal.

**Aspects.** FinBERT embeddings, offline clustering for taxonomy discovery,
frozen-centroid assignment per batch, and a tool for comparing candidate
taxonomies quantitatively. An LLM aspect classifier on local Ollama models
(`aspects/llm_classify.py`), evaluated against the human aspect labels; it
classified the whole corpus on 3 Oct, but its answers aren't applied to the
database yet (`scripts/rescore.py` does that once the team decides).

**Sentiment & aggregation.** Base FinBERT scoring, per-bank/aspect index with
volume shrinkage, 7d/30d/all-time windows, per-source breakdown.

**Labels and the fine-tuned model.** One labelling round of 1,277 sentences
(aspect and sentiment), cleaned of train/test leakage and duplicates. FinBERT
fine-tuned on (sentence, readable aspect label) pairs, three seeds saved with
checksums, evaluated against all three baselines; not used for scoring. Opus
5.5 labelled the same sentences as an additional rater (DESIGN decision 22),
giving the first aspect agreement figure.

**Interfaces.** A FastAPI REST API that serves every number, its evidence,
analyst consensus and the chatbot (sixteen endpoints, open CORS, an OpenAPI
contract in `docs/api/openapi.json`), and a terminal chat for testing the
chatbot, which has four pluggable model backends and RAG evidence retrieval.
Suggested starter questions are generated from the index rather than
hardcoded, so a chat UI never offers a question the data cannot answer. The
Streamlit dashboard (`dashboard/`) is maintained by a teammate and reads the
database directly; it was removed on 2026-10-01 and restored the same night
with the teammate's redesign (DESIGN decision 23, amended).

**Chatbot answers for a retail investor (4 Oct, branch `fix/chatbot-answers`).**
The prompt asks for a plain opening sentence, a score once with its scale
and its reading in words, the shares of positive and negative sentences, how
the bank ranks among the three and which topics lift or drag it; citations
the model copies show as numbered sources. The model doesn't always follow
it: in the kept version's run of the 32-question gold set, 13 of the 19
answers giving a score gave its scale, and none had labelled sections (23 of
26 before). The readings, shares, rankings and trend sentence are computed
in code and handed to the model (DESIGN decision 25); the API is unchanged.
Strip mode, the default, shows only quotes a search returned: it removes
the quotes no search returned and takes the quote marks off any other words
a search doesn't vouch for (DESIGN decision 26, after nine validations of
the branch). Answers take about a minute on the M1, against about 36 seconds
before (the before run's log, on the evidence page).
[Evidence](evidence/chatbot-answers-2026-10-04.md).

**Engineering.** 2491 tests (external APIs mocked with captured payloads),
central logging with debug configuration, resumable overnight backfill script,
start/stop/status scripts for the API and Ollama. A clean copy installs
and runs from the README on Python 3.14
([evidence](evidence/install-test-2026-10-01.md)).

---

## Chatbot evaluation

> **Updated 2026-10-04.** The regex input guards are replaced by an intent
> classifier (DESIGN decision 24): a local model sorts each question into one
> of eleven intents, and every intent but in-scope gets a reviewed fixed
> reply. `llama3.1:8b` sorts 100 of 103 labelled questions correctly and
> blocks no real question (possibly optimistic: the intent definitions quote
> some evaluation phrasings). Live on the 32-question gold set with the same
> chatbot model, behaviour stays 8/8 and the right tool is called 21–22 of 24
> times (20 on 1–2 Oct; the prompt and checks changed too); with strip
> enforcement, no invented citation and one invented figure. Two other-bank questions now reach the model, which
> declined both. Method and tables:
> [evidence/chatbot-intent-2026-10-04.md](evidence/chatbot-intent-2026-10-04.md).

> **Updated 2026-09-26.** Memory, input guards and output checks were added
> (DESIGN decision 19). With them, advice and out-of-scope questions are
> handled correctly 7 of 7 times (was 2–3 of 7), by code rather than the
> model; invented citations are unchanged at 43–48% on `llama3.2:3b`; the new
> number check flagged 19 figures in the final run, 18 of them invented.
> Method and tables: [evidence/chatbot-harness-2026-09-26.md](evidence/chatbot-harness-2026-09-26.md).
> The analysis below is of the 11 Sep runs and still describes the model's
> own behaviour.

A 23-question gold set (`chatbot/eval_gold_set.py`) run against five local
models via `chatbot/run_eval.py`. Tool selection, advice-declining behaviour
and citation fabrication are checked automatically; whether a stated number
is correct is not (see the note at the end of this section).

Two models were run twice; those rows show both runs.

| model | params | errors | tool selection | behaviour | citation fabrication |
|---|---|---|---|---|---|
| `llama3.2:3b` (default) | 3B | 0 | 12/16 | 3/7 | **10–11/23 (43–48%)** |
| `phi4-mini` | 3.8B | 0 | 0/16 | 1/7 | 19/23 (83%) |
| `gemma3:4b` | 4B | 23 | 0/16 | 0/7 | 0/23 — *artifact, see below* |
| `qwen3:4b` | 4B | 23 | 0/16 | 0/7 | 0/23 — *artifact, see below* |
| `llama3.1:8b` | 8B | 3 / 8 | 12/16 / 7/16 — *see the confound below* | 3/7 | **3/23 (13%), both runs** |

Seven findings for the report:

**The default model's fabrication rate is a range because it was run twice.**
11/23 on 2026-09-07 and 10/23 on 2026-09-10, same model, same gold set. That
is a one-question difference, and on 23 questions one question is 4.3
percentage points. Every other rate in this table rests on a single run and
carries the same uncertainty without showing it. Treat these as approximate
to within roughly one question, and do not report a change of a few points
between two models as a real difference unless it survives a re-run. The
gap that does survive is `llama3.2:3b` against `llama3.1:8b`, which is
roughly eight questions wide.

**Scale cuts fabrication sharply, and fixes nothing else.** Going from 3B to
8B drops citation fabrication from 43–48% to 13%, a gap far wider than the
run-to-run noise above. Tool selection (12/16) and advice-declining behaviour
(3/7) are *identical* across the two. So fabrication is a capability limit
that scale relieves, while the behavioural failures are design problems that a
bigger model does not touch.

**Two models score 0% fabrication and neither result means anything.**
`gemma3:4b` has no Ollama tool-calling support, so all 23 questions failed
with HTTP 400. `qwen3:4b` (added 2026-09-11) failed all 23 differently: every
call exceeded the 120-second read timeout, because it emits a long hidden
reasoning chain before answering and the agent loop needs several calls per
question. Both produced 23 empty answers, so there were no citations to
fabricate. **A fabrication rate is only meaningful alongside its error
count**, which is why the table carries both — read either 0% as "produced no
output", not "stayed grounded".

The qwen result is consistent with what `train/llm_prelabel.py` already
records: on a far simpler single-turn labelling task the same model took
65–97 seconds per call, against 3–5 seconds for `llama3.2:3b`. It is not
viable for an agent loop at any reasonable timeout. One caveat on this
particular run: it shared the machine with other work, which will have made
the timeouts worse, so treat "unusably slow here" rather than a specific
latency as the finding.

**phi4-mini is the worst case and the most instructive one.** It called a
tool in 0 of 16 questions yet fabricated citations in 83% of answers — it
answered entirely from parametric knowledge while producing text that looks
sourced. This is the strongest single argument in the project for enforcing
grounding in code rather than in the prompt.

**Advice-declining is the weakest area regardless of model.** 3/7 at best,
and `advice-1`/`advice-2` fail on every model tested. For a tool carrying a
not-financial-advice disclaimer this is the most report-relevant gap, and it
is a prompt/design fix rather than a model choice. It came out at exactly 3/7
in four separate runs across two models, which is unusually strong support
for that reading.

**Tool selection is confounded with the error count, the same way fabrication
is.** A question that errors never calls a tool, so it counts as a
tool-selection failure. Re-running `llama3.1:8b` on 2026-09-11 made this
unmistakable:

| | run 1 | rerun |
|---|---|---|
| Errors | 3 | 8 (all timeouts) |
| Tool selection, as reported | 12/16 | 7/16 |
| Excluding questions that errored | **12/13** | **7/9** |

Same model, same gold set. The apparent collapse from 12/16 to 7/16 is almost
entirely timeouts — the rerun shared the machine with a full test run, which
is this project's doing rather than the model's. Genuine wrong-tool choices
were 1 and 2, not 4 and 9.

**So do not compare the tool-selection column across rows with different error
counts.** `llama3.2:3b`'s 12/16 and `phi4-mini`'s 0/16 are clean, because both
had zero errors — and phi4-mini's is the damning one, since it answered every
question and called nothing. The two 0/16 rows with 23 errors measure nothing.
`llama3.1:8b`'s figure needs the adjustment above before it can sit beside
them. Detail in
[evidence/chatbot-eval-rerun-2026-09-11.md](evidence/chatbot-eval-rerun-2026-09-11.md).

Per-model transcripts are in `data/eval/chatbot_eval_results_*.jsonl`,
summaries in `data/eval/chatbot_eval_summary_*.md`. Reproduce with
`chatbot.run_eval --tag <model>` once per model (RUNBOOK, "Evaluating the
chatbot").

**Not automated:** whether the numbers a model states are actually correct,
and whether cited evidence is relevant. That needs a human reading the
transcripts — verifying a number by extracting it with another model is less
trustworthy than the check itself.

---

## Not done

### 1. Labelling — the critical blocker

> **Updated 2026-10-01.** Opus 5.5 labelled all 1,277 rows blind as an
> additional rater (DESIGN decision 22). Against the human labels: aspect κ
> 0.80, sentiment κ 0.79, every sentiment disagreement on the neutral
> boundary. That is a human–LLM figure; human–human aspect agreement is still
> unmeasured. The disagreements (202 aspect, 173 sentiment) wait in
> `data/labeled/llm_rater/review_*.csv` for people to settle, and the largest
> group, 63 rows, is a guideline gap: whether a retail customer's investment
> products are wealth or retail banking
> ([evidence](evidence/llm-rater-2026-10-01.md)).
>
> **Updated 2026-09-30.** The first round is done: 1,300 rows labelled by two
> people on 2026-09-27 under the 10-aspect taxonomy, 1,277 after removing
> duplicates and train/test leakage, sentiment κ 0.93 (test sheet 0.96).
> Aspect agreement wasn't measured, the test labels weren't independent of
> the model's suggestion, and five aspects have fewer than 80 rows
> ([evidence](evidence/annotation-agreement-2026-09-27.md)). Everything
> below describes the superseded version-1 sheet.
>
> **Updated 2026-09-26.** The labelling design changes (DESIGN decision 17):
> annotators will choose the aspect and the sentiment for each sentence, on
> a re-drawn candidate set that includes news. **Don't start labelling the
> current sheet.** The candidate set now holds 997 rows, one having been
> removed with the off-topic news on 2026-09-24. The description below is of
> the current sheet and remains accurate for it.

Zero examples human-labelled. This blocks the fine-tuned classifier, which
blocks the deep-learning deliverable the proposal commits to.

The candidate set is exported (`data/labeled/candidates.csv`, 998 rows: 798
`train_dev` and 200 `test`). `train/llm_prelabel.py` has run a local model
over it to propose a label and rationale for each row, so labelling becomes
correction rather than starting from scratch: 997 rows carry an
`llm_prelabel` from `llama3.2:3b` (999 succeeded, 1 failed).
`train/finetune.py` / `train/evaluate.py` are written and smoke-tested. Only
the human correction step is missing.

**The test split was pre-labelled before anyone noticed it shouldn't be.**
199 of the 200 `test` rows received an `llm_prelabel`, and every row also
carries `base_finbert_label` — base FinBERT being one of the two models the
test set exists to compare. An annotator working from that sheet would have
been measuring agreement with a model rather than establishing ground truth,
and anchoring on the baseline's answer would have biased the comparison in
the baseline's favour.

`preprocess/export_blind_test.py` is the repair: it writes
`data/labeled/test_blind.csv` carrying the sentence, its aspect and its
provenance and nothing else, and merges the filled sheet back afterwards.
Be precise about what this does and does not fix. It does prevent
the leak for anyone who labels from the blind sheet, which is nobody so far
since zero rows are labelled. It does not undo the model's exposure to those
rows, and it cannot help if someone opens `candidates.csv` and labels the
test rows there instead. **Label the test split from `test_blind.csv` only.**

**Class balance is a live risk for two aspects.** The proposal asks for
200–300 examples per sentiment class. The candidate pool is not distributed
to make that reachable per aspect:

| aspect | candidate rows |
|---|---|
| other | 524 |
| dividend_policy | 200 |
| net_interest_margin | 119 |
| management_guidance | 97 |
| asset_quality | 58 |

`asset_quality` and `management_guidance` cannot yield 200 per class no
matter how the labels fall, and `other` — the fallback bucket, not a real
aspect — is the majority of the sheet. The model's own proposed labels split
positive 464 / negative 310 / neutral 223, which is far less neutral-heavy
than the base-FinBERT distribution over the whole corpus (87% neutral) and is
a consequence of the deliberate non-neutral oversampling in the `train_dev`
sampler. Human labels may not follow it.

Running pre-labelling for real surfaced something to know before
correcting: some candidates are off-topic for the aspect they were assigned
(a product description assigned to `management_guidance`, for instance) —
exactly the "incidental mentions" case `docs/annotation-guideline.md`
already anticipated. Expect to flag/discard some rows rather than correct
their label.

The sampling design matters and shouldn't be shortcut: the test split is
drawn at random *before* any model-assisted selection. If the test set were
drawn from model-screened candidates, the fine-tuned model's reported F1
would be inflated relative to the baseline it's compared against.

### 2. UOB earnings coverage — resolved

Was the project's biggest validity problem: DBS 9,093 earnings sentences,
OCBC 1,561, **UOB 4**. UOB's IR site sits behind an F5 WAF that answers
scripted requests with a challenge stub, so the direct fetch used for DBS and
OCBC could not reach it.

Resolved by fetching the same PDFs from the Wayback Machine, which is not
behind that WAF (`ingest/earnings_fetch_uob.py`): 66 quarterly documents,
2020–2025, giving UOB 1,600 earnings sentences. UOB's blended all-time score
moved from -0.011 to +0.020 as a direct result — a clean illustration of how
much a coverage gap had been distorting the comparison.

Residual caveat: DBS still carries ~6x the earnings volume of either other
bank, because it publishes full analyst-call transcripts and they are long.
The per-source breakdown remains the honest way to read blended figures.

### 3. Aspect taxonomy not validated

> **Updated 2026-10-03.** The corpus run finished: `llama3.1:8b` gave all
> 44,345 sentences one aspect each, none invalid. Applying them waits for the
> team; on a copy, `scripts/rescore.py` applied them in seconds
> ([evidence](evidence/index-preview-2026-10-01.md)).
>
> **Updated 2026-10-01.** The LLM classifier is built and evaluated:
> `llama3.1:8b` top-1 0.729 and `qwen3:4b` 0.719 against the human aspect,
> against 0.413 for embedding assignment; where the two models agree (76% of
> sentences) they match the human 83.5% of the time. A corpus run would take
> about 24 hours on the MacBook and rewrites `sentence_aspects`, so it waits
> for the team ([evidence](evidence/llm-aspect-classifier-2026-10-01.md)).
>
> **Updated 2026-09-30.** The taxonomy is now ten aspects derived from the
> 338-cluster discovery run (DESIGN decision 21,
> [evidence](evidence/aspect-taxonomy-2026-09-25.md)), and the corpus was
> re-assigned under it. Assignment is still by embedding similarity at an
> un-re-tuned floor, so the validation this section asks for is still owed;
> the LLM classifier (decision 16) now has 1,277 human aspect labels to be
> evaluated against. The rest of this section is the history.
>
> **Decided 2026-09-26.** Keep the proposal's four aspects plus `other`, and
> assign them with a local LLM, one per sentence (DESIGN decision 16). The
> analysis below is the evidence behind that decision.

The taxonomy is still the proposal's four a-priori aspects. The earlier
finding — that clustering found only a coarse consumer-banking versus
investment-discussion split — was drawn from a Reddit-only corpus of 2,888
sentences and **no longer holds**.

**Discovery re-run, 2026-09-11, on all 36,884 sentences.** This could not be
run before today: `aspects.discover` bound one SQL parameter per embedding
and SQLite caps that at 32,766, so it had been failing outright since the
corpus passed that size. Fixed on this branch.

With earnings text in the corpus, clusters of exactly the kind the proposal
anticipated appear unprompted: leverage ratio against the regulatory minimum,
final Basel III reforms and their CET-1 effect, fee income by line, return on
equity and return on tangible equity. None of these existed in the
Reddit-only run. **This is the clearest evidence the project has that
ingesting earnings material closed a real vocabulary gap, and did not simply
add volume.**

It does not settle the taxonomy. The run produced 281 clusters with a median
size of 23 and 67% of the corpus left as noise, which is a topic list rather
than an aspect set, and the fundamental clusters are finer than
`asset_quality` or `management_guidance` and cut across them. Noise rose from
52%, so a bigger corpus did not buy cleaner structure at the default
`min_cluster_size`. Full write-up:
[evidence/aspect-discovery-2026-09-11.md](evidence/aspect-discovery-2026-09-11.md).

**A side finding worth acting on:** several clusters are extraction artifacts
rather than topics — character-spaced PDF text, chart axis labels, earnings
boilerplate, Reddit markdown table fragments. Measured across the corpus these
are 2.6% of sentences (2.7% of earnings, 2.5% of Reddit), so they are not
distorting the index, but they will undermine any cluster listing reproduced
in the report. Crude filters in `preprocess/clean.py` would remove most of
them.

The evidence that assignment is not yet trustworthy: Reddit sentences are
assigned to `net_interest_margin` by centroid similarity, but the Reddit
corpus contains **zero** occurrences of "net interest margin" and 4 of the
abbreviation `NIM`. The earnings corpus contains 375 and 300. Adding earnings
data closed the vocabulary gap; it did not fix assignment.

**Now measured, not just suspected (2026-09-11).** The twenty Reddit sentences
with the *highest* similarity to the `net_interest_margin` centroid are, in
order: "No fees for ocbc", "DBS Fixed deposit interest.", "DBS My Account: no
minimum balance and fees.", "UOB one savings terms and conditions", "UOB
Absolute Amex, 1.7% unlimited cashback", and so on. **Not one is about net
interest margin.** All twenty are retail banking products — fees, cards,
fixed deposits, transfers. These are the best matches, so the rest are worse.

Worse, the polarity inverts on the ones that do mention interest. "UOB One
(5.2% interest)" is a *deposit rate paid to a customer*, which is a funding
cost to the bank and compresses its margin. A depositor's enthusiasm is scored
as positive sentiment on a metric it actually damages.

**Practical consequence: do not report Reddit-sourced `net_interest_margin`
rows.** They measure retail enthusiasm for deposit products. The earnings-only
rows for that aspect are defensible; the blended and Reddit-only ones are not.
Whether the other three aspects fail the same way has not been checked, and
`dividend_policy` may well be fine given Reddit discusses dividends in 561
sentences. Reproduce with the query in
`learning/02-sentiment-mining/aspect-based-sentiment-analysis.md`.

**Re-run on the full corpus, 2026-09-11.** `aspects/compare_taxonomies.py`
was itself measuring at the wrong threshold: it hardcoded the pre-calibration
floor of 0.35 while `config/aspects.yaml` had moved to 0.65 five days
earlier and `aspects/assign.py` reads the config. The tool now reads the live
floor and can sweep a range. Results at the production floor, over all 36,884
sentences:

| candidate | aspects | avg matched/sentence | % other | centroid separation |
|---|---|---|---|---|
| A — the proposal's four | 4 | 1.80 | 37.3% | 0.1125 |
| B — data-derived coarse | 2 | 1.69 | 7.7% | 0.1695 |
| C — data-derived fine | 3 | 2.38 | 8.5% | 0.2222 |

Centroid separation is the column that matters most, because it is computed
from the seed embeddings alone and therefore cannot be changed by tuning the
floor. The proposal's four aspects are the least distinct of the three
candidates. Sweeping the floor from 0.35 to 0.80 shows candidate A has no
usable operating point: at 0.60 it still matches 2.55 of 4 aspects per
sentence, at 0.65 it discards 37.3% of the corpus to `other`, and at 0.70 it
discards 57.9%. The data-derived candidates hold their shape across the whole
range.

Full table, caveats and the argument against over-reading it are in
[evidence/taxonomy-comparison-2026-09-11.md](evidence/taxonomy-comparison-2026-09-11.md).
The short version of the caveat: coarser taxonomies separate more easily
partly as arithmetic, and none of this measures whether assignments are
*correct*. This remains a judgement call for the team, not something to
settle in code.

### 4. Model backends never verified

GPT and Gemini backends are written to documented API contracts but have
never received a real response. Gemini carries more risk — its schema `type`
field expects uppercase proto-enum values, unlike the JSON-Schema lowercase
used everywhere else in this codebase. **Gemini was verified live on
2026-09-30** ([evidence](evidence/gemini-backend-2026-09-30.md)): tool calls and answers were correct on
`gemini-3.6-flash`; `gemini-3.8-flash`, the default, was overloaded that day.
GPT remains unverified.

### 5. Smaller gaps

- `get_trend`'s headline direction is still a two-window comparison (7d vs
  30d); it now also returns up to 12 monthly points alongside it, so the
  shape behind the direction is visible. The two-window figure remains what
  the `direction` field is computed from.
- The news-derived analyst proxy (`ingest/analyst_tag.py`) matches zero
  documents; largely superseded by Yahoo consensus but retained since the
  zero result is itself a finding.
- Alpha Vantage contributes nothing (no SGX coverage) but remains in the
  codebase.
- NewsAPI's free tier gives ~1 month of lookback and title+description only.

---

## Where the original plan was wrong

Useful for the report's methodology discussion — these are cases where
implementation contradicted the plan.

**SGX was the wrong target.** The plan assumed analyst reports could come
from SGX. They cannot: SGX hosts company announcements, not third-party
analyst reports, which are brokerage IP behind entitlements. The banks' own
IR sites turned out to be open and to carry the same earnings material —
including DBS's quarterly analyst call transcripts, which are closer to the
original goal than anything SGX would have provided. *Update, 5 to 6 Oct
2026:* broker research did come in by another route, as a fourth labelled
source (`sgx_research`): 25 notes, 12 downloaded from SGX's research listing
and 13 printed from sginvestors.io pages, extracted on the team's Windows PC
([evidence](evidence/sgx-research-round-2026-10-04.md),
[evaluation](evidence/sgx-research-evaluation-2026-10-06.md)). Their full text
stays in git while the repository is private to the team (decided 7 Oct).

**The aspect taxonomy did not emerge as predicted.** The plan assumed
clustering would surface the four proposed aspects. It surfaced a
consumer-banking vs. investment-discussion split instead, because the
dominant corpus (`r/singaporefi`) discusses banking products rather than
equity fundamentals.

**Adding a data source made a metric worse.** Earnings ingestion closed a
real vocabulary gap and simultaneously broke cross-bank comparability, since
it arrived for two banks out of three. Worth reporting: more data is not
automatically better if it arrives unevenly.

**Prompt instructions were insufficient for grounding.** The plan assumed
system-prompt rules would keep the chatbot honest. A local model fabricated
citations twice, in two different formats, after the prompt was tightened.
The rules had to move into code.

---

## How to improve it

> **Superseded 2026-09-26 by [PLAN.md](PLAN.md)**, which sequences this list
> against the submission date and adds what came out of the final course
> module. Kept as the record of how the priorities looked on 2026-09-11.

Roughly in order of value.

1. **Label the data.** Unblocks the fine-tuned classifier and the DNN
   deliverable. LLM-assisted pre-labelling followed by human correction is
   viable and can run free on the local Ollama model.
2. ~~**Add UOB earnings.**~~ Done — 66 quarterly PDFs (2020–2025) fetched
   from the Wayback Machine, which is not behind the WAF that blocks UOB's
   IR site. See `ingest/earnings_fetch_uob.py`.
3. **Settle the aspect taxonomy.** Re-run discovery on the enriched corpus,
   review it as a team, freeze the decision.
4. **Fix advice-declining, and switch the default local model.** The
   evaluation above has been run; two actions fall out of it. Advice-seeking
   questions are declined only 3/7 of the time on every model tested, which
   is a prompt/design fix, not a model-choice one. And `llama3.1:8b`
   fabricates citations at 13% against `llama3.2:3b`'s 43–48%, so it is the
   better default for anyone whose machine can run it — at the cost of being
   noticeably slower. Reading the transcripts for numerical fidelity is still
   outstanding and still human work.
5. **Verify the GPT backend** with one real call (Gemini was verified on 2026-09-30).
6. ~~**Continuous time series** for `get_trend`.~~ Done — `compute_time_series`
   in `aggregate/index.py` buckets by week, month or quarter through the same
   `_summarize` the stored index uses, so a chart cannot disagree with the
   headline number. Exposed at `GET /sentiment/series`, on the dashboard's
   Time Series tab, and as `monthly_series` inside `get_trend`. Thin buckets
   are returned with `sufficient=false` rather than dropped, so a gap in a
   line means missing data rather than neutral sentiment.
7. **Improve relevance filtering.** Sentences mentioning a bank incidentally
   ("paid via DBS PayNow") still enter the corpus.
8. **Reconsider blending.** Whether management commentary and retail chatter
   belong in a single index at all is a legitimate methodological question,
   currently resolved in favour of the proposal's design with the
   composition made visible.
