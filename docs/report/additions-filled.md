# Seven extra analyses on the sentiment index: results and what they mean

Written for a teammate who has not followed this work. Read the first section for the picture;
each section after it stands on its own.

## What this file is

The project turns Reddit posts, news articles, bank earnings reports and broker research notes
into a sentiment index for DBS, OCBC and UOB (45,844 sentences in the database). The index is
a score from -1 (all negative) to +1 (all positive), per bank and per topic ("aspect", such as
dividends or asset quality). A fine-tuned FinBERT model scores each sentence.

This file reports analyses added to check that index from new angles: how certain it is, whether
its ten topics are real, whether the fine-tuned model beats simpler models, and how well three
chatbot features work. Every number comes from a file in `data/eval/` or `docs/evidence/`,
named in each section. Everything ran on the current database and model version
(`finbert-adapted-finetuned-2026-10-11-3seed-m0`); the database was only read.

**Status at a glance**

| Analysis | Result in one line | Needs people? |
|---|---|---|
| How certain is the index | DBS above UOB holds; DBS above OCBC and OCBC above UOB do not | no |
| Do our ten topics match what the text itself groups into | yes, well above chance, but only partly | no |
| Which words set sources and sentiments apart | clear, readable differences | no |
| Fine-tuned model against simpler models and other FinBERT versions | model in use scores 0.709; best simple model 0.606; base FinBERT 0.648 | no |
| Pulling "thing + opinion" pairs from sentences | works roughly (recall 0.76 on a lenient match), precision low | yes: human answer key |
| Short pros-and-cons summaries per bank and topic | 79% supported by their sources (AI rater) | yes: two human raters |
| Chatbot conversation check | fixed replies fine, model-written answers weak | yes: rescore |
| Comparing the index with share prices | not done, dropped | no |

Two sheets (summary ratings and the term answer key) were filled by an AI assistant so the
analyses could run. Those copies are labelled as AI work and kept in `data/labeled/llm_rater/`,
apart from the blank sheets people should fill. They are a first estimate, not human agreement.

## 1. How certain is the index?

**Why it matters.** The index is one number per bank, computed from a sample of sentences. A
different sample would give a slightly different number, so a reader cannot tell if "DBS is above
OCBC" is real or luck without an interval.

**Result.** We redrew the data 2,000 times and recomputed the overall index each time. Intervals
cover the middle 95% of those results. Drawing whole documents (one Reddit thread or one results
report is one unit) gives:

| Bank | Overall index | 95% interval |
|---|---|---|
| DBS | +0.143 | +0.122 to +0.165 |
| OCBC | +0.129 | +0.103 to +0.154 |
| UOB | +0.107 | +0.090 to +0.124 |

| Gap | Size | 95% interval | Supported? |
|---|---|---|---|
| DBS minus OCBC | +0.014 | -0.018 to +0.048 | no, includes zero |
| OCBC minus UOB | +0.022 | -0.010 to +0.053 | no, includes zero |
| DBS minus UOB | +0.036 | +0.007 to +0.062 | yes, but only just |

**How to read it.** The dashboard and chatbot rank DBS, OCBC, UOB in that order. Only the gap
between DBS and UOB survives the check; the other two orderings could be noise. Any report text
that ranks the banks should say so.

**Why document draws, not sentence draws.** Drawing single sentences gives narrower intervals
(DBS +0.134 to +0.152). That treats every sentence as independent, which overstates certainty:
sentences from one thread or report share a topic and a mood. Use the document intervals. The
stored index table matches the recomputed value for all three banks, so nothing needs rebuilding.

Source: `data/eval/uncertainty/uncertainty.md`.

## 2. Do our ten topics match what the text itself groups into?

**Why it matters.** The ten aspects (dividends, asset quality and so on) were chosen by the team.
If they were arbitrary, an unsupervised method that has not seen our definitions should not
recover them. We tested two such methods against 1,277 sentences that people labelled with an
aspect.

- **LDA** groups sentences by which words appear together. We asked for 11 groups (ten aspects
  plus "other"). Every sentence goes into a group.
- **HDBSCAN** groups sentence meanings (FinBERT embeddings reduced to 10 dimensions) and decides
  the number of groups itself. It leaves sentences that fit no group as "noise". It is sensitive
  to one setting, the minimum group size, so we ran three (10, 100, 200) and report all of them.

Agreement is measured with NMI (0 means the groups say nothing about the aspect, 1 means a perfect
match), shown next to the value a random shuffle of the labels would give.

| Method | Groups | Sentences left as noise | NMI (random level) | Purity (random level) |
|---|---|---|---|---|
| LDA | 11 | 0% | 0.264 (0.019) | 0.507 (0.373) |
| HDBSCAN, min size 10 | 345 | 63% | 0.274 (0.173) | 0.543 (0.443) |
| HDBSCAN, min size 100 | 27 | 59% | 0.253 (0.050) | 0.522 (0.378) |
| HDBSCAN, min size 200 | 5 | 11% | 0.103 (0.014) | 0.413 (0.374) |

Purity is the share of sentences that sit with their group's most common human aspect.

**What it shows.**
- Both methods agree with the human aspects far above chance, so the ten aspects are not
  arbitrary. LDA is 14 times its random level; HDBSCAN at size 100 is about 5 times.
- The agreement is partial. Both find the retail banking groups (cards and cashback, foreign
  currency accounts; 90% or more of labelled sentences in the matching HDBSCAN groups are retail
  banking) and the results language (income, rose, billion). Management, regional and rates
  sentences mix several aspects.
- HDBSCAN leaves most sentences out and is unstable: 345 groups at size 10, 27 at 100, 5 at 200.
  On the 41% it does group at size 100, agreement is higher (NMI 0.409, random 0.086), but that
  covers the easy cases, not the corpus.

**A caution that applies to this whole comparison.** The ten aspects were themselves derived
from HDBSCAN on these same embeddings, and the pipeline assigns aspects using sentences from those
groups. The human labels are people's judgements, but they use a scheme HDBSCAN helped create, so
this test favours HDBSCAN. LDA never saw the scheme, which makes its agreement the cleaner
evidence that the aspects are real. HDBSCAN did not beat LDA even with that advantage. So read the
table as "how well each method recovers our scheme", not "which finds better topics"; the latter
needs labels made without the clustering, which we do not have.

**Why HDBSCAN is still the method to describe for discovery.** It finds the number of groups from
the data instead of assuming it, uses meaning instead of shared words, and flags sentences that
fit nowhere. Its instability is why the scheme was derived once and then frozen, not re-derived
each run. LDA serves as the independent check.

HDBSCAN used the 43,331 of 45,844 sentences that have an embedding stored, including all 1,277
labelled ones. Sources: `data/eval/topic_model/hdbscan_vs_lda.md`, `topic_model.md`.

## 3. Which words set sources and sentiments apart?

**Why it matters.** It shows in plain words what each source talks about and what makes a
sentence negative, as a sanity check on the scores.

We scored every word by how much more it appears in one group of sentences than another
(weighted log-odds with an informative prior; words seen under 5 times are left out).

- **Reddit against earnings reports.** Reddit leans to everyday banking: card, account, just, use,
  like, usd, transfer. Earnings reports lean to results language: income, net, total, growth,
  million, quarter, wealth.
- **Negative against positive Reddit sentences.** Negative: fee, charge, charges, charged, tried,
  transaction, app, issue. Positive: cashback, spend, good, mpd (miles per dollar), better, gives,
  miles, free.

So the negative Reddit sentiment is mostly about fees, charges and app or transaction problems,
while positive sentiment is about rewards. The same file has the comparison for each bank and each
aspect, with charts.

Source: `data/eval/term_analysis/term_analysis.md`.

## 4. Is the fine-tuned model better than simpler models?

**Why it matters.** Fine-tuning FinBERT takes effort and time. The claim "it helped" is only
supported if it beats cheap alternatives trained on the same data, and if the final choice among
the FinBERT versions we tried is justified.

**The test.** Every model below is scored on the same 399 sentences that **people** labelled and
no model trained on: 299 drawn at random from Reddit, earnings reports and news, and 100 from
broker research. The score is macro-F1, which averages the three classes (positive, neutral,
negative) equally, so the rare negative class counts as much as the common neutral one. 1 is
perfect.

### What each model does

**Simple models.** They were trained here on 1,563 labelled sentence-aspect pairs (275 of them
broker research), the same pairs the fine-tuned FinBERT used. The labels came from an AI model,
not people. The four classical models read a sentence as a list of words and word pairs, weighted
by how distinctive they are, with the aspect added as one extra word. They learn nothing about
language beyond those 1,563 sentences.
- **Naive Bayes:** counts how often each word appears in positive, neutral and negative training
  sentences, then picks the class whose word pattern best fits a new sentence, treating words as
  independent.
- **Complement Naive Bayes:** the same idea, but it learns each class from the sentences that are
  *not* in it, which copes better when classes are uneven (here neutral is common and negative is
  rare).
- **Linear SVM:** draws the straight boundary between the classes, in word-weight space, that
  leaves the widest gap to the nearest training sentences.
- **Logistic regression:** learns a weight for each word and class, adds them up and turns the
  totals into class probabilities.
- **BiLSTM:** a small neural network that reads the sentence word by word, forwards and backwards,
  keeping a running memory of it. It starts with no language knowledge.
- **CNN:** a small neural network that slides over the sentence looking for short word patterns
  (such as "not good") and combines what it finds.

The score for each network is a vote of three training runs.

**The FinBERT versions.** FinBERT is a BERT language model already trained on a large amount of
financial text and on a public financial-news sentiment set, so it starts with real knowledge of
how finance is written. The versions differ in what was added on top:
- **Base FinBERT, no fine-tuning:** used as it comes. It reads the sentence alone and ignores the
  aspect.
- **Fine-tuned on people's labels (1 Oct and 4 Oct versions):** base FinBERT trained further on
  the project's sentences that people labelled, taking the sentence and the aspect together. The
  4 Oct version is a retrain after a training bug was fixed. The 7 Oct version also adds broker
  research rows.
- **Fine-tuned on an AI model's labels, no extra pretraining (11 Oct):** the same fine-tuning, on
  the 1,563 pairs labelled by an AI model, which are the pairs the simple models use.
- **Adapted, then fine-tuned on an AI model's labels (11 Oct), the model in use:** first the
  encoder's masked-word training continues for three rounds on the project's own 42,822 unlabelled
  sentences (so it meets forum language and local product names), then it is fine-tuned as above.

Each FinBERT version was trained three times with different random seeds. "Mean of 3 runs" is the
average of the three models' scores. "3 averaged" means their probabilities were averaged first
and the combined model scored once, which is how the model in use works.

### Results on all 399 test rows

The measures, for each of the three classes (negative, neutral, positive):
- **Accuracy:** the share of all 399 sentences given the right class. The classes are uneven
  (201 neutral, 136 positive, 62 negative), so a model that favours neutral can score well on
  accuracy.
- **Precision (P):** of the sentences the model calls this class, the share that really are. High
  precision means few false alarms.
- **Recall (R):** of the sentences that really are this class, the share the model finds. High
  recall means few missed.
- **Macro-F1:** combines precision and recall for each class, then averages the three classes
  equally, so the rare negative class counts as much as neutral.

Rows are ordered by macro-F1. The first column of each pair is precision, the second recall.

| Model | Accuracy | Macro-F1 | Negative P / R | Neutral P / R | Positive P / R |
|---|---|---|---|---|---|
| Adapted, AI labels (in use), 3 averaged | **0.729** | **0.709** | 0.56 / 0.71 | 0.80 / 0.73 | 0.73 / 0.74 |
| Adapted, AI labels (in use), mean of 3 runs | 0.702 | 0.685 | 0.56 / 0.71 | 0.76 / 0.70 | 0.71 / 0.70 |
| Fine-tuned, AI labels, no pretraining, 3 averaged | 0.699 | 0.677 | 0.58 / 0.61 | 0.77 / 0.70 | 0.67 / 0.74 |
| Fine-tuned, AI labels, no pretraining, mean of 3 runs | 0.689 | 0.669 | 0.57 / 0.63 | 0.76 / 0.68 | 0.66 / 0.73 |
| Base FinBERT, no fine-tuning | 0.697 | 0.648 | 0.64 / 0.44 | 0.68 / 0.84 | 0.75 / 0.61 |
| Fine-tuned, people's labels, 4 Oct retrain, mean of 3 runs | 0.688 | 0.647 | 0.60 / 0.48 | 0.71 / 0.76 | 0.69 / 0.67 |
| Complement Naive Bayes | 0.632 | 0.606 | 0.43 / 0.61 | 0.69 / 0.67 | 0.69 / 0.58 |
| Naive Bayes | 0.652 | 0.583 | 0.61 / 0.31 | 0.68 / 0.78 | 0.61 / 0.62 |
| Linear SVM | 0.579 | 0.556 | 0.39 / 0.56 | 0.66 / 0.59 | 0.59 / 0.57 |
| Logistic regression | 0.574 | 0.550 | 0.38 / 0.58 | 0.66 / 0.60 | 0.59 / 0.54 |
| BiLSTM, vote of 3 runs | 0.544 | 0.524 | 0.33 / 0.56 | 0.71 / 0.48 | 0.54 / 0.62 |
| CNN, vote of 3 runs | 0.484 | 0.464 | 0.23 / 0.50 | 0.63 / 0.48 | 0.61 / 0.49 |

The 1 Oct and 7 Oct versions fine-tuned on people's labels were not scored on all 399 rows, so
they are left out.

### What it shows

- **Fine-tuned FinBERT beats every simple model, and the neural networks are far behind.** The
  model in use scores 0.709 against 0.606 for the best simple model (complement Naive Bayes) and
  0.464 to 0.524 for the networks. A network trained from nothing on 1,563 sentences cannot match a
  model that already knows finance. A paired comparison on the same rows (resampling the test rows
  2,000 times) puts the gap beyond what the choice of test rows would explain for every simple
  model.
- **Accuracy and macro-F1 rank the models differently, and the reason is the negative class.**
  Base FinBERT is as accurate as the model in use when single runs are compared (0.697 against
  0.702) but has lower macro-F1 (0.648 against 0.685), because it finds only 44% of negative
  sentences against 71%. Naive Bayes is more accurate than complement Naive Bayes (0.652 against
  0.632) but lower on macro-F1, because it finds only 31% of negative sentences. Only the three
  averaged models of the model in use lead clearly on both measures (accuracy 0.729). For an index
  that must pick up criticism, negative recall matters more than accuracy.
- **Fine-tuning's gain over untouched FinBERT is real but moderate.** Base FinBERT (0.648) already
  beats every simple model, and the model in use gains about 0.04 to 0.06 over it. The gain comes
  from the negative class: base FinBERT finds 44% of negative sentences and the model in use 71%,
  paid for with neutral recall (0.84 down to 0.73). Base FinBERT reads many complaints as neutral,
  which fits its training on formal financial news.
- **The labels used for fine-tuning matter.** Fine-tuning on people's labels (4 Oct) did not beat
  base FinBERT (0.647 against 0.648), while the AI-label versions do (0.669 and 0.685). The
  people-labelled version had no broker research text to learn from, which may be part of the
  reason; this was not tested.
- **The choice between the AI-label versions is close.** The model in use leads fine-tuning
  without pretraining by 0.016 (0.685 against 0.669 as means of three runs), about the size of the
  variation between runs (0.010 to 0.013). It was chosen by a rule written down before any test row
  was scored, and because every measure points the same way, including cross-validation on the
  training rows (ahead by 0.014 in 11 of 15 paired folds, p = 0.016). Averaging three runs adds
  more (0.685 to 0.709) than the pretraining step does.
- **Reddit is the weak source:** the model in use gets 0.68 accuracy on Reddit, against 0.81 on
  earnings text.

### Limits

- Three training runs per version, so differences between FinBERT versions are about the size of
  run-to-run variation. Only the gap to the simple models and to base FinBERT is clear.
- Training labels came from an AI model that agrees with people at kappa about 0.8. The test
  labels are people's.
- The paired comparison used the labels stored in the database, which differ slightly from the
  scores in the table (0.697 against 0.709 on the 399 rows) because the stored label used the
  pipeline's aspect, which differs from the human aspect on 114 of the 399 rows.
- The project's headline fine-tuning claim stays defined on the 299 random rows only (0.604 ± 0.035 for the earlier fine-tuned version).

Sources: FinBERT versions, `docs/evidence/model-rerun-2026-10-11.md` and `docs/model-card.md`;
simple models, `data/eval/baselines_extended/results.md` and `data/eval/baselines/`.

## 5. Pulling "thing + opinion" pairs out of sentences

**Why it matters.** An aspect label says a sentence is about dividends. A pair says more: "payout
ratio" is the thing and "looks thin" is the opinion. Counting the commonest opinions per aspect
could explain why a score moved.

**What was done.** A local language model (llama3.1:8b) read 3,000 sentences spread over the ten
aspects and listed pairs. Any pair whose words are not in the sentence was dropped: 409 of 5,222
(7.8%), leaving 4,813. The commonest opinion terms per bank and aspect are in
`data/eval/terms/opinion_terms.md`.

**How accurate.** We compared its pairs with an answer key of 300 sentences (153 pairs in 133
sentences). **That key was written by an AI assistant, not by people**, so this is a first
estimate only.

| Match rule | Precision | Recall | F1 |
|---|---|---|---|
| Exact words | 0.128 | 0.392 | 0.193 |
| Lenient (overlapping words) | 0.247 | 0.758 | 0.373 |

Recall is the more trustworthy figure: the model finds about three quarters of the answer-key
pairs on the lenient rule. Precision is low partly because the key is sparse. The model offered
469 pairs on those sentences against 153 in the key, and many extras may be sensible but count as
wrong.

**Still needed.** Two people should fill `data/eval/terms/gold_sheet.csv`, then run the
evaluation again, to get a human accuracy figure and an agreement figure.

Source: `data/eval/terms/evaluation.json`, `run3000.log`.

## 6. Short pros-and-cons summaries

**Why it matters.** The chatbot can summarise what people praise and criticise per bank and aspect.
A summary is only useful if each point is backed by the sentences it cites.

**What was done.** For each bank and aspect the system writes up to three praised and three
criticised points, each citing its sentences: 188 points. Automatic checks dropped 2 (the cited
sentences did not contain the claim), leaving 186.

**How good.** An AI assistant rated all 186 points on two questions: do the cited sentences
support the claim (yes or no), and is the point useful to a reader (1 to 5)?

| | Supported | Useful (average of 5) |
|---|---|---|
| All 186 points | 79% | 2.5 |
| Praised points | 89% | 2.7 |
| Criticised points | 69% | 2.3 |

Criticised points are weaker. Typical faults: a claim that goes past its sentence ("high fees"
from a sentence giving one fee), a cited passage cut off mid-sentence, and a sentence from a
different product (a savings account called "dividend plus" cited for dividend policy). A point
can also be supported yet unrepresentative, since the system cites the highest-ranked sentences,
not a random sample.

**Still needed.** The rater was one AI assistant, so there is no agreement figure. Two people
should fill `data/eval/summaries/rating_sheet.csv`.

Sources: `data/eval/summaries/summaries.md`; ratings in `data/labeled/llm_rater/summaries/`.

## 7. Does the chatbot hold a sensible conversation?

**Why it matters.** The chatbot answers from the index and quotes evidence. A conversation can
go wrong in ways a single question does not show: losing the bank named earlier, giving a figure
the tools never returned, or refusing a fair question.

**What was done.** 13 scripted conversations (16 turns) were run through the live bot on the local
model, covering plain questions, follow-ups, quote requests, an advice request, thin data, a
mixed question, an injection attempt, an unknown bank and a question with no bank. An AI assistant
scored four yes/no items from the transcripts.

| Item | Result |
|---|---|
| Follow-up keeps the bank and topic | 2 of 3 conversations |
| Every figure matches the tools and the answer is consistent | 3 of 7 |
| Refuses where it should, with a redirect | 4 of 5 |
| Shows an invented quote | none, but the bot showed no quotes at all, so this is not a strength |

**What it shows.** Replies written in advance (advice, injection, unknown bank) were correct every
time because the model never writes them. The weak part is answers the model writes: four said
"not enough data" without a count or reason although the index has data, one called the sentiment
negative and clearly positive in the same paragraph, and two misstated how many pieces of evidence
a figure rested on. The bot's own check caught three unmatched figures in one answer but not the
contradiction. "What about the bank?" was refused as an injection when it should ask which bank.
Part of the cause looks like the tool the model picked (for example a search filtered to
negative sentences for a neutral question), though we did not confirm that.

**Limits.** One run on a small local model, scored by one rater; a rerun will differ. The sample
dialogues in `docs/report/conversation-design.md` show intended behaviour, not a transcript, and
should be labelled that way. The team should rescore before quoting these counts.

Sources: `docs/evidence/scripted-dialogues-2026-10-18.md`, transcripts in `data/eval/dialogues/`.

## 8. Not done: comparing the index with share prices

The plan included checking the index against share-price returns and results-release reactions.
The team decided it is not needed, so it was not run. The report should not claim that the index
predicts or tracks prices.

## What people still need to do

1. Two people fill the summary rating sheet (`data/eval/summaries/rating_sheet.csv`).
2. Annotate the term answer key (`data/eval/terms/gold_sheet.csv`), then rerun its evaluation.
3. Rescore the chatbot conversations, and decide whether the sample dialogues in
   `conversation-design.md` stay as labelled intended behaviour.
4. Run `/sync-docs`, since tests and scripts were added.
5. Review before committing: new scripts `aspects/hdbscan_compare.py`,
   `train/baselines_extended_test.py` and `scripts/scripted_dialogues.py`; fixes to
   `train/bilstm_baseline.py` (the vote score was always 0) and `aspects/extract_terms.py`
   (a pandas change dropped a column); all of `data/eval/` output.

## Where everything is

| Topic | Files |
|---|---|
| Index certainty | `data/eval/uncertainty/` |
| Topic methods | `data/eval/topic_model/` |
| Word analysis | `data/eval/term_analysis/` |
| Model comparison | `data/eval/baselines_extended/`, `data/eval/baselines/` |
| Term pairs | `data/eval/terms/` |
| Summaries | `data/eval/summaries/` |
| Chatbot conversations | `docs/evidence/scripted-dialogues-2026-10-18.md`, `data/eval/dialogues/` |
| AI-filled sheets (not human) | `data/labeled/llm_rater/summaries/`, `data/labeled/llm_rater/terms/` |
