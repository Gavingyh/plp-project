# Findings, limitations and solutions

*For the report's results and conclusions and for the presentation. Written
2 October 2026 from the evidence files, each linked; numbers are as of the
30 September database snapshot and change when the team re-runs the
pipeline. "Built" means in the repository and tested; "proposed" means
measured or designed but not applied; "decision" means it waits for the
team.*

---

## Headline findings

1. **The system runs older methods than the ones it has measured to be
   better**, on all four parts that matter: sentiment, aspects, bank
   attribution and evidence search. Switching changes the results: every
   bank's headline score rises by 0.06–0.19, UOB moves ahead of DBS, and
   several aspects turn from positive to negative.
2. **Assigning aspects by embedding similarity doesn't work; asking an LLM
   does.** Seed centroids pick the human's aspect 41% of the time, barely
   above always guessing the commonest aspect (37%); `llama3.1:8b` picks it
   73% of the time, 84% where a second model agrees.
3. **The fine-tuned FinBERT beats zero-shot FinBERT on macro-F1 (0.624
   against 0.571) but not on accuracy (0.682 against 0.70),** and the input
   change chosen to get there turned out to make no difference when tested
   on more seeds. Model selection on one seed was inside the noise.
4. **The chatbot's main failure is invented evidence, and its cause is in
   the design, not the model.** On both local models every invented citation
   (25 in 64 answers) came from an answer that never searched for evidence.
   Removing such evidence in code takes citation warnings from 11 to 0 (8B)
   and 15 to 0 (3B) on the same answers, and to 0 real inventions in live
   runs on both models, with tool choice unchanged.
5. **Evidence search ranks no better than random when the query is a
   question** (MRR 0.217, random 0.217), because FinBERT's vectors encode
   whether text sounds like a Reddit question more than what it is about.
   The same weakness explains finding 2.
6. **An LLM judge passed every answer, including the invented ones; asking
   it differently fixed that.** A judge told to list every unsupported quote,
   source and figure caught all 11 known inventions with the same small
   model. Checking the evaluator against known failures before calibrating it
   found both the failure and the fix.

---

## 1. Data and labels

**Findings**
- 44,345 sentences: Reddit 55.6%, earnings reports 27.6%, Google News
  12.3%, CNA 3.6%, other news 0.9%. DBS has 24,431, UOB 12,502, OCBC 7,412.
  DBS carries about six times the earnings text of the others, and earnings
  text is far more positive than Reddit, so the source mix drives the
  blended headline ([STATUS](../STATUS.md)).
- 1,277 labelled sentences; two people agree on sentiment at κ 0.93
  ([annotation-agreement](../evidence/annotation-agreement-2026-09-27.md)).
  Opus 5.5, labelling blind, agrees with them at κ 0.80 on aspect and 0.79
  on sentiment, every sentiment disagreement on the neutral boundary
  ([opus-labeller](../evidence/opus-labeller-2026-10-01.md)).
- The test labels match the suggestion model shown to annotators on 89% of
  the 299 rows (92% on train/dev): the labels are anchored.
- Five aspects have fewer than 80 labels. A blind top-up sheet of 268 rows
  is ready; checked by Opus, it would bring four of them past 80 but leave
  macro near 49, because about half the macro sentences on it (25 of 52) are
  a bank's economists talking about the economy, which the guideline counts
  as not about the bank ([labelling-topup](../evidence/labelling-topup-2026-10-01.md)).
- Singlish is rare (121 sentences, 0.3%; 12 labelled), but Singapore product
  vocabulary is everywhere: "UOB One" in 2,908 sentences, "OCBC 360" in 670
  ([local-context-questions](../local-context-questions.md)).

**Limitations**
- Aspect agreement between two people has never been measured; there is
  only one human aspect column.
- Anchored test labels inflate agreement with any model that resembles the
  suggestion model; comparisons between models survive better than absolute
  scores.
- 39 negative sentences in the test split: one sentence moves negative F1 by
  about 0.02.
- Opus agreement is human–LLM, not human–human.

**Solutions**
- Built: a blind top-up sheet and its merge (`preprocess.export_topup`,
  `train.labels --topup`); Opus as an extra rater on it.
- Decision: relabel the 299 test rows blind; settle the wealth/retail and
  bank-economist questions in the guideline before labelling.
- Proposed: two people label the same 40 top-up rows first, giving the first
  human–human aspect κ.

## 2. Bank attribution (entity recognition)

**Findings**
- Alias matching counts "UOB Kay Hian" as UOB and "DBS Vickers" as DBS.
  spaCy NER with an entity ruler, a resolution table and a gazetteer
  fallback attributes 763 sentences (1.7%) differently
  ([bank-ner](../evidence/bank-ner-2026-10-01.md)).
- Against Opus as a provisional reference on the 201-sentence gold sheet,
  NER names exactly the right banks for 200 sentences, alias matching for
  126. Opus caught a NER bug ("OCBC360" written as one word), fixed the same
  day.

**Limitations**
- The gold sheet isn't labelled by people, so NER has no human accuracy
  figure yet. Opus was given the rules NER encodes, so its agreement tests
  the code, not the rules.
- Whether DBS Vickers is DBS (456 sentences) is a policy choice.

**Solutions**
- Built: NER, the gold sheet, its evaluation.
- Decision: the DBS Vickers rule; whether to apply NER to the database.

## 3. Aspects

**Findings**
- Seed-centroid assignment: top-1 0.413 against the human aspect (always the
  commonest: 0.374), 6.4 aspects per sentence; no similarity threshold fixes
  it ([aspect-assignment-calibration](../evidence/aspect-assignment-calibration-2026-09-30.md)).
- LLM classification: `llama3.1:8b` 0.729 (macro-F1 0.679), `qwen3:4b`
  0.719; where they agree (76% of sentences) 0.835; Opus 0.842
  ([llm-aspect-classifier](../evidence/llm-aspect-classifier-2026-10-01.md)).
- The LLM's errors are on boundaries the guideline draws loosely (wealth
  against retail banking) and on local products: it reads customer rates as
  net interest margin, and the gaming word "nerf" (a savings account made
  worse) as sentiment about the stock.

**Limitations**
- Wealth, `other` and management guidance stay near 0.5 F1.
- The full corpus takes about 24 hours on the MacBook; the cache was 25%
  full on 2 Oct.

**Solutions**
- Built: the classifier and its corpus cache (resumable, no database writes).
- Decision: apply it, with a rule for where the two models disagree.
- Proposed: distil Opus's labels into a FinBERT aspect classifier, after
  checking Anthropic's terms on training with model outputs.

## 4. Sentiment classification (the DNN)

**Findings** (299-row test split)

| model | macro-F1 | accuracy |
|---|---|---|
| VADER lexicon | 0.427 | 0.49 |
| TF-IDF + logistic regression | 0.515 | 0.57 |
| FinBERT, zero-shot | 0.571 | 0.70 |
| fine-tuned FinBERT, three seeds | 0.604 ± 0.035 | 0.61–0.68 |
| the three averaged, with a neutral margin chosen on dev | **0.624** | 0.682 |

- Most errors are neutral sentences called positive or negative, typically
  Reddit descriptions of retail products ([error-analysis](../evidence/error-analysis-2026-10-01.md)).
- Cross-validation on three seeds: the readable aspect label chosen on
  1 October is no better than the aspect key (+0.005 over 15 paired folds,
  8 better); the noise between configurations is about 0.026 per fold
  ([noise-floor-cv](../evidence/noise-floor-cv-2026-10-02.md)).
- The class weights the documents described were never applied before
  1 October; found by reading the code before training.

**Limitations**
- The lead over zero-shot FinBERT is about one seed standard deviation, on
  anchored labels.
- Training on the Apple GPU isn't bit-for-bit reproducible.

**Solutions**
- Built: three seeds, three baselines, the neutral margin, 3-seed CV as the
  standard for choosing configurations.
- Decision: whether the fine-tuned models score the corpus.

## 5. The sentiment index

**Findings** (1,000 sampled sentences, [index-preview](../evidence/index-preview-2026-10-01.md))
- Switching the aspect method leaves the headline unchanged (one vote per
  sentence) but moves the per-aspect rows: DBS asset quality goes from
  +0.26 to −0.26, NIM turns negative for UOB and OCBC.
- Switching the sentiment model raises every headline by 0.06–0.19 and puts
  UOB ahead of DBS.
- Under centroid assignment every named aspect of every bank scores
  positive: each aspect inherits the bank's overall tone.
- On a memory-starved Mac the GPU returned all-zero probabilities without
  an error; a check now refuses them.

**Limitations**
- One sample of 1,000; per-aspect cells hold a median of 17 sentences.

**Solutions**
- Proposed: the same preview on the full corpus once the aspect cache is
  complete; then one combined re-score.

## 6. The chatbot

**Findings**
- Gold set v2, 32 questions, 1 October ([chatbot-eval-build](../evidence/chatbot-eval-build-2026-10-01.md)):

| | `llama3.2:3b` | `llama3.1:8b` |
|---|---|---|
| right tool | 18 / 24 | 20 / 24 |
| advice and no-data questions handled | 8 / 8 | 8 / 8 |
| answers citing evidence no tool returned | 15 | 11 |

- Every invented citation came from an answer that never searched; the
  prompt forbids exactly that and the models ignore it. The opening figures
  of each answer always came from a tool.
- Conversations: the 8B got 7 of 9 turns right at first; the scope guard refused a
  follow-up with no bank named, and the model once wrote a tool call as
  text. After both fixes: 9 of 9 on both models.
- Evidence search: MRR 0.217 for question-phrased queries (random 0.217),
  0.559 when ranked by the aspect's name. A live answer presented card-fee
  and fraud complaints as "complaints about UOB's asset quality", and every
  automated check passed it.
- The LLM judge (`qwen3:4b`) scored all 32 answers "fully supported",
  including the 11 with invented evidence. Asked instead to list every quote,
  source and figure the tool data doesn't contain, the same model caught all
  11, plus one real error no rule catches (a score of +0.03 described as
  "slightly negative"), with about three false alarms, two because it sees
  the tool data cut at 4,000 characters. `gemma3:4b` was too lenient with one
  prompt and flagged almost everything with the other; with thinking on,
  `qwen3:4b` took over 5 minutes an answer.

**Limitations**
- One run per configuration at temperature 0.2: rates are indicative.
- No human faithfulness ratings or user study yet.
- Removing invented evidence leaves answers without evidence; having the
  system search instead finds mostly off-topic quotes, because retrieval is
  weak.

**Solutions**
- Built: the scope guard reads the conversation; a tool call written as
  text is run; `CHATBOT_ENFORCE_EVIDENCE=strip` removes evidence written
  without a search (off by default), which took live citation warnings to 0
  on the 8B and to 2 false alarms on the 3B, with tool choice unchanged; `CHATBOT_ASPECT_QUERY` ranks
  evidence by the aspect's name (off by default), more on topic in live
  answers but often report boilerplate; a checklist
  judge; larger hosted models through `OPENAI_BASE_URL` (needs a Groq key).
  `qwen3:4b` was tried as the chatbot model and isn't viable on this Mac (22
  of 32 questions timed out).
- Decision: which settings to switch on, and the demo model.
- Proposed: a sentence-similarity embedding model for retrieval, which
  would fix question-phrased search at the root.

## 7. Engineering and process

**Findings**
- 590 tests, an OpenAPI contract kept current by a test, two clean-copy
  installs (the first found that the README never named its Python
  version), and every figure in the evidence traceable to a command.
- Two read paths: the dashboard queries the database directly while other
  clients use the API, and they already disagree on one view (the
  dashboard hides UOB's analyst consensus).
- Earnings-PDF sentences store a local file path as their URL, which
  carries the developer's macOS username into the database and 25 committed
  files.

**Solutions**
- Proposed: a one-line fix for the consensus panel; the dashboard on the API
  or with tests; relative paths for PDF URLs (a database write).

## 8. Lessons for the report's conclusions

1. **Measure the noise before choosing.** One seed's cross-validation can't
   separate configurations closer than about 0.02 macro-F1.
2. **Evaluate the evaluator.** A judge, a retrieval metric or a rule-based
   flag needs its own check against known cases: the judge failed it, the
   citation flags passed it (25 of 26 confirmed by hand), retrieval needed an
   exact random baseline to show it was at chance.
3. **Enforce in code what the system can check.** The prompt asked the model
   not to cite without searching; only code made it so.
4. **Replay to isolate a change.** Applying a post-processing fix to recorded
   answers compares like with like; a fresh run changes the model's answers
   too.
5. **LLM labels are a reference, not gold.** Opus at κ 0.80 is consistency
   with the guideline, and it shares the guideline's blind spots.
6. **Local context is where general models fail quietly.** Not Singlish,
   which is rare, but products: savings-account rate cuts read as bank
   margins, "Dividend+" accounts read as dividends.
