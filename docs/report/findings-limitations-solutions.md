# Findings, limitations and solutions

*For the report's results and conclusions and for the presentation. Written
2 October 2026 from the evidence files, each linked; numbers are as of the
30 September database snapshot and change when the team re-runs the
pipeline. "Built" means in the repository and tested; "proposed" means
measured or designed but not applied; "decision" means it waits for the
team.*

*Updated 4 October 2026 with the retrained models
([retrain](../evidence/retrain-2026-10-04.md),
[ensemble-margin](../evidence/ensemble-margin-2026-10-04.md)), the intent
classifier ([chatbot-intent](../evidence/chatbot-intent-2026-10-04.md)) and
the 4 Oct read-only audit. Where a 2 Oct figure was superseded, the text
says which models it belongs to.*

---

## Headline findings

1. **The system runs older methods than the ones it has measured to be
   better**, on all four parts that matter: sentiment, aspects, bank
   attribution and evidence search. Switching the aspect method moves the
   per-aspect rows: retail banking turns negative for all three banks where
   centroid assignment made every aspect positive. Switching the sentiment
   model moves the headlines less than first measured. The 0.04–0.07 rise
   in every headline (3 Oct) came from the 1 Oct models, which were trained
   from a relabelled head; the retrained seeds' average (4 Oct, previewed at
   margin 0.12) stays within 0.015 of base FinBERT and agrees with it on
   every aspect's sign. DBS moves just ahead of OCBC either way (by 0.010
   with the retrained seeds; UOB last). Single seeds still differ: retrained
   seed 42 raises every headline.
2. **Assigning aspects by embedding similarity doesn't work; asking an LLM
   does.** Seed centroids pick the human's aspect 41% of the time, barely
   above always guessing the commonest aspect (37%); `llama3.1:8b` picks it
   73% of the time, 84% where a second model agrees.
3. **Fine-tuned FinBERT beats zero-shot FinBERT on macro-F1, modestly.**
   Retrained on 4 Oct after a training bug, every seed beats it (0.592 to
   0.646; mean 0.621 ± 0.027 against 0.571), and the three averaged score
   0.634 with the same accuracy as base (0.702 against 0.699). The neutral
   margin, chosen on dev (0.10), makes no measurable difference on test.
   The input change chosen on 1 October turned out to make no difference
   when tested on more seeds: model selection on one seed was inside the
   noise.
4. **The chatbot's main failure is invented evidence, and its cause is in
   the design, not the model.** On both local models every invented citation
   (25 in 64 answers) came from an answer that never searched for evidence.
   Removing such evidence in code takes citation warnings from 11 to 0 (8B)
   and 16 to 0 (3B) on the same answers, re-measured on 3 Oct with guards
   that also check quoted text, signs and percentages; live runs on 2 Oct
   showed 0 real inventions on both models, with tool choice unchanged.
5. **Evidence search ranks no better than random when the query is a
   question** (MRR 0.217, random 0.217), because FinBERT's vectors encode
   whether text sounds like a Reddit question more than what it is about.
   The same weakness explains finding 2.
6. **An LLM judge passed every answer, including the invented ones; asking
   it differently fixed that, partly.** Told to list every unsupported quote,
   source and figure, the same small model caught all 25 known inventions
   across two runs, but its lists are often wrong, so it can screen answers
   for people, not replace them. Checking the evaluator against known
   failures found both the failure and the limit of the fix.

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
  ([llm-rater](../evidence/llm-rater-2026-10-01.md)).
- Where Opus and the people disagree (202 aspects and 173 sentiments, 80
  of them on the test split), the human labels are kept: a team decision of
  4 Oct 2026, after a spot check found the human labels sound. The
  disagreements are about boundaries, not plain mistakes: every sentiment
  disagreement is about where neutral ends, and 63 of the aspect ones are a
  single guideline question (a retail customer's investment products:
  wealth or retail banking).
- The test labels match the suggestion model shown to annotators on 89% of
  the 299 rows (92% on train/dev): the labels are anchored.
- Five aspects have fewer than 80 labels. A blind top-up sheet of 268 rows
  is ready; checked by Opus, it would bring four of them past 80 but leave
  macro near 49, because about half the macro sentences on it (25 of 52) are
  a bank's economists talking about the economy, which the guideline counts
  as not about the bank ([labelling-topup](../evidence/labelling-topup-2026-10-01.md)).
- Singlish is rare (121 sentences, 0.3%; about a dozen labelled), but Singapore product
  vocabulary is everywhere: "UOB One" in 2,908 sentences, "OCBC 360" in 670
  ([local-context-questions](../local-context-questions.md)).

**Limitations**
- Aspect agreement between two people has never been measured; there is
  only one human aspect column.
- Anchored test labels inflate agreement with any model that resembles the
  suggestion model. The fine-tuned models learned from these labels and base
  FinBERT never saw them, so the anchoring may favour the fine-tuned models
  in the comparison itself; that hasn't been measured (scoring both against
  the Opus labels would).
- 39 negative sentences in the test split: one sentence moves negative F1 by
  about 0.02.
- Opus agreement is human–LLM, not human–human.
- The kept labels keep their anchoring: in 118 of the 173 sentiment
  disagreements the human label is the suggestion the annotators were
  shown. A spot check can't show which side of the neutral boundary is
  right, so the reported scores rest on the human side of 80 contested test
  labels.
- Some stored text is damaged by the extraction, found on 3 Oct and fixed
  in the code for future data only (re-cleaning stored text would change
  sentence ids and orphan their labels and scores): earnings PDFs lost
  short wrapped lines, splicing sentences ("Markets trading income rose to
  Expenses increased 10%, ..."); Reddit text was never HTML-unescaped, so
  54 sentences keep `&gt;`, `&amp;` or `&#x200B;`, and in 6 documents a
  quoted parent comment survived as the commenter's own words.
- Three Reddit months lost most of their comments to failing pages (Sep
  2021: 10 against 107 and 82 either side; May 2024: 167 against 513 and
  385; Mar 2025: 89 against 497 and 377). Refilling them needs approval.
- Duplicate sentences are dropped across the whole corpus, not within one
  outlet's copy of a story: a sentence repeated in a later quarter's report,
  or in another bank's, is kept once. "Asset quality remained resilient."
  is in 17 earnings documents (DBS and OCBC, 10 dates) and stored once, for
  DBS. That removes syndicated copies as intended, but also thins the
  repeated statements a time series should count. Changing it means
  re-segmenting the corpus, so it is recorded, not fixed.
- Six UOB earnings documents (114 sentences of 2023–2024 results) are dated
  by their extraction day, 10 Sep 2026, so they count as recent; in the
  index recomputed on the evening of 3 Oct they were 114 of the 211 sentences
  in UOB's 30-day window. The parser
  is fixed; repairing the rows needs approval.

**Solutions**
- Built: a blind top-up sheet and its merge (`preprocess.export_topup`,
  `train.labels --topup`); Opus as an extra rater on it.
- Decided (4 Oct): keep the human labels where Opus disagrees; Opus stays
  a second rater, reported beside them.
- Decided (4 Oct): no full relabel. Only the rows on the bank-economist
  and wealth-or-retail boundaries are fixed, once the team decides those two
  rules (`data/labeled/boundary-review-2026-10-04.csv`).
- Decision: relabel the 299 test rows blind; settle the wealth/retail and
  bank-economist questions in the guideline before labelling.
- Proposed: two people label the same 40 top-up rows first, giving the first
  human–human aspect κ.

**Terms of use and ethics**
- The Reddit posts and comments were collected through a third-party archive
  (Arctic Shift), not through Reddit's own API. As the team reads it,
  Reddit's developer policy
  ([Developer Platform: Accessing Reddit Data](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data))
  restricts academic use of Reddit data through third-party tools, and the
  use of Reddit content to train models without consent. *The page refused
  automated requests on 4 Oct (HTTP 403), so its wording is not quoted here:
  copy the exact sentences from a browser before the report relies on them.*
- The fine-tuned model is trained partly on labelled Reddit sentences: 433
  of the 978 training and development rows (44%) come from Reddit, and 184
  of the 299 test rows (`data/labeled/candidates.csv`).
- Mitigations: the data isn't redistributed outside the team. The GitHub
  repository, which holds the labelled sentences and evaluation results that
  quote Reddit text, and the Hugging Face model repository are both private
  (checked 4 Oct); the database and the corpus are not in git. Reddit text
  is withheld from every hosted model (decided 4 Oct: Gemini already, the
  Claude and OpenAI backends on their own branch). These reduce the exposure
  but don't settle whether the collection itself is allowed; the report
  should state it as a limitation.

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
- The full corpus takes about a day on the MacBook, and any change to the
  aspects, their definitions or the examples means a full redo.

**Solutions**
- Built: the classifier and its corpus cache (resumable, no database writes).
  The cache file is named by a hash of the prompt, so a changed wording
  starts a new file instead of reusing answers to the old question.
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
| fine-tuned FinBERT, 1 Oct seeds | 0.604 ± 0.035 | 0.61–0.68 |
| the 1 Oct seeds averaged, margin 0.13 chosen on dev | 0.624 | 0.682 |
| fine-tuned FinBERT, retrained 4 Oct | 0.621 ± 0.027 | 0.66–0.71 |
| the retrained seeds averaged, argmax | **0.634** | 0.702 |
| the retrained seeds averaged, margin 0.10 chosen on dev | 0.612 | 0.702 |

The 1 Oct seeds were trained from a relabelled pretrained head (each output
answered for the wrong class at the start); the fix and the retrain are in
the [retrain](../evidence/retrain-2026-10-04.md) evidence. The retrained
models' margin is a single-model stand-in: each seed held out different dev
rows, so no clean dev set exists for the three-seed average, and the
difference from argmax on test is not measurable (paired bootstrap 95%
interval −0.058 to +0.009; [ensemble-margin](../evidence/ensemble-margin-2026-10-04.md)).

- Most errors are neutral sentences called positive or negative, typically
  Reddit descriptions of retail products ([error-analysis](../evidence/error-analysis-2026-10-01.md)).
- Cross-validation on three seeds: the readable aspect label chosen on
  1 October is no better than the aspect key (+0.005 over 15 paired folds,
  8 better); the noise between configurations is about 0.026 per fold
  ([noise-floor-cv](../evidence/noise-floor-cv-2026-10-02.md)).
- The class weights the documents described were never applied before
  1 October; found by reading the code before training.

**Limitations**
- The lead over zero-shot FinBERT is about one seed standard deviation for
  the 1 Oct seeds and 1.4 to 1.9 for the retrained ones, still on anchored
  labels.
- Training on the Apple GPU isn't bit-for-bit reproducible.

**Solutions**
- Built: three seeds, three baselines, the neutral margin, 3-seed CV as the
  standard for choosing configurations.
- Decision: whether the fine-tuned models score the corpus, and which:
  `scripts/rescore.py` still defaults to the 1 Oct seeds.

## 5. The sentiment index

**Findings** (all 44,345 sentences, 3 Oct, [index-preview](../evidence/index-preview-2026-10-01.md);
a first preview on 1,000 overstated both effects)
- Switching the aspect method leaves the headline unchanged (one vote per
  sentence) but moves the per-aspect rows: DBS asset quality falls from
  +0.27 to +0.07, and retail banking turns slightly negative for all three
  banks.
- With the 1 Oct models, switching the sentiment model raised every
  headline: by 0.12–0.18 with centroid aspects, by 0.04–0.07 with LLM
  aspects and the margin. With the retrained seeds (4 Oct, LLM aspects,
  margin 0.12) the average stays within 0.015 of base FinBERT (DBS +0.132,
  OCBC +0.122, UOB +0.084) and agrees with it on every aspect's sign. Today
  OCBC is just ahead of DBS; with both changes DBS is just ahead of OCBC
  (both gaps under 0.02); UOB is last either way. The
  1,000-sentence preview's UOB-ahead-of-DBS result was sampling noise.
- All of that is the three-seed average of the 1 Oct models. Scored by each seed alone, the
  headlines spread by 0.04 (UOB) to 0.12 (DBS); with seed 1, OCBC stays
  ahead and both DBS and OCBC fall below base FinBERT. Retail banking stays
  negative for DBS and OCBC under every seed; NIM and macro change sign.
- Under centroid assignment every named aspect of every bank scores
  positive: each aspect inherits the bank's overall tone.
- On a memory-starved Mac the GPU returned all-zero probabilities without
  an error; a check now refuses them.

**Limitations**
- With LLM aspects a named bank-aspect cell holds a median of 699 sentences
  (smallest 59). The figures above for the 1 Oct seeds came from a
  relabelled head; the retrained seeds moved them, as above. Their seeds
  spread less on the DBS and OCBC headlines (0.068 and 0.062), but 5 of the
  30 named cells still change sign between seeds.
- The 7-day and 30-day windows count back from the moment the index is
  rebuilt (`aggregate/index.py:228`), not from the newest sentence. The
  newest sentence is from 25 September and collection is stopped, so a
  rebuild during the 12–18 October re-score would leave the 7-day window
  empty and the 30-day one nearly so: every recent score and trend would
  read "not enough data".
- The seeds disagree: each seed alone gives DBS +0.113 to +0.235, OCBC
  +0.116 to +0.210, UOB +0.105 to +0.149, and 8 of the 30 named cells
  (NIM and macro for every bank among them) change sign between seeds.
  Retail banking for DBS and OCBC, dividends and wealth hold under every
  seed.

**Solutions**
- Built: the full-corpus preview, with the fine-tuned scores saved to a
  file, so applying the chosen setting takes minutes.
- Decision: which aspect method and sentiment model score the corpus; then
  one combined re-score.
- Decision: anchor the windows to the newest sentence, labelled "as of" that
  date, or collect up to the re-score.

## 6. The chatbot

**Findings**
- Gold set v2, 32 questions, 1 October ([chatbot-eval-build](../evidence/chatbot-eval-build-2026-10-01.md)):

| | `llama3.2:3b` | `llama3.1:8b` |
|---|---|---|
| right tool | 18 / 24 | 20 / 24 |
| advice and no-data questions handled | 8 / 8 | 8 / 8 |
| answers citing evidence no tool returned | 15 | 11 |

- 4 October, with the intent classifier that replaced the word-list input
  guards ([chatbot-intent](../evidence/chatbot-intent-2026-10-04.md)): a
  local model (`llama3.1:8b`) sorts 100 of 103 labelled questions correctly
  and blocks no real question (possibly optimistic: its definitions quote
  some evaluation phrasings). Live on the gold set, re-scored with today's
  checks: advice and no-data questions 8 of 8, right tool 21 and 22 of 24,
  and with strip enforcement no invented citation and one invented figure.
  Questions about HSBC and Standard Chartered now reach the chatbot model,
  which declined both. Five gold-set questions took a median of 22.2
  seconds each on the 8B and 20.7 on the 3B (the classifier on the 8B); the
  3B called the wrong tool for the trend question.
- Every invented citation came from an answer that never searched; the
  prompt forbids exactly that and the models ignore it. The opening figures
  of each answer always came from a tool.
- Conversations: the 8B got 7 of 9 turns right at first; the scope guard
  (since replaced by the intent classifier) refused a follow-up with no bank
  named, and the model once wrote a tool call as text. After both fixes: 9
  of 9 on both models, and 9 of 9 again with the classifier (4 Oct).
- Evidence search: MRR 0.217 for question-phrased queries (random 0.217),
  0.559 when ranked by the aspect's name. A live answer presented card-fee
  and fraud complaints as "complaints about UOB's asset quality", and every
  automated check passed it.
- The LLM judge (`qwen3:4b`) scored all 32 answers "fully supported",
  including the 11 with invented evidence. Asked instead to list every quote,
  source and figure the tool data doesn't contain, the same model caught all
  11, plus one real error no rule catches (a score of +0.03 described as
  "slightly negative"), with about three false alarms where it overlooked a
  quote that is in the data or treated a rounded figure as invented. On a
  second set (the 3B's answers) it caught all 14 known inventions too, but
  also scored 7 of 9 other answers 1, often for reasons that are wrong (quotes
  it calls missing are in the data): a screening tool for choosing which
  answers people read, not a measurement. `gemma3:4b` was too lenient with one
  prompt and flagged almost everything with the other; with thinking on,
  `qwen3:4b` took over 5 minutes an answer.

**Limitations**
- One run per configuration at temperature 0.2: rates are indicative.
- No human faithfulness ratings or user study yet.
- Removing invented evidence leaves answers without evidence; having the
  system search instead finds mostly off-topic quotes, because retrieval is
  weak.

**Solutions**
- Built: an intent classifier (4 October) replaced the word-list guards,
  the scope guard among them: a local model sorts each question, reading
  the conversation, and every intent but in-scope gets a reviewed fixed
  reply; a tool call written as text is run; `CHATBOT_ENFORCE_EVIDENCE=strip` removes evidence written
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
- 1126 tests in `tests/` (1173 with the diagram and notebook checks), an
  OpenAPI contract kept current by a test, two clean-copy
  installs (the first found that the README never named its Python
  version), and every figure in the evidence traceable to a command.
- Two read paths: the dashboard queries the database directly while other
  clients use the API, and they already disagree on one view (the
  dashboard hides UOB's analyst consensus).
- Earnings-PDF sentences store a local file path as their URL, which
  carries the developer's macOS username into the database (178 documents
  and 12,254 sentences, and every snapshot) and 29 committed files (4
  October), among them evaluation results that record tool output.

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
