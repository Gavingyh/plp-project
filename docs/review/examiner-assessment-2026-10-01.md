# An examiner's assessment, 1 October 2026

*Written in the role of an external examiner for the NUS-ISS PLP practice
module, assessing the repository as it stands on 1 October (`main`), a
month before submission. Every question is at Bloom level 4 or above
(Analyze, Evaluate, Create; Anderson and Krathwohl, 2001), and each comes
with what a strong answer would draw on, so the team can rehearse. It
judges the work, not the people, and it is deliberately hard: the point is
to find what a marker will find before the marker does.*

---

## Verdict in brief

| deliverable | weight | where it stands | main risk |
|---|---|---|---|
| System, code, datasets, docs | 20% | Strong. A working pipeline, an API with an OpenAPI contract, 500+ tests, evidence for every number, a clean-copy install that works | The dashboard is now another project: the marker must be able to run both together |
| Report | 20% | Not written; a factual draft exists | The results most likely to be challenged (the fine-tuned model's margin, the aspect assignment) need careful framing |
| Video | 5% | Not started | — |
| Rubric: two text-mining tasks | required | Four designed; discovery and sentiment done, aspect classification evaluated but not applied, NER built but not evaluated | "Evaluated" is not "in the system": two of the four are not yet part of what the dashboard shows |
| Rubric: a DNN | required | Met: fine-tuned FinBERT, three seeds, three baselines | Its lead over the zero-shot baseline is one standard deviation and it is less accurate |
| Rubric: sentiment mining or conversational UI | required | Both | The chatbot's evidence retrieval ranks no better than random for question-phrased queries |

The engineering and the honesty of the evidence are the project's
strongest suit. The weakest point is a gap between what has been measured
and what the deployed system does: the stored scores still come from base
FinBERT, the aspects from centroid assignment that picks the human's
aspect 41% of the time, and bank attribution from alias matching. A marker
who opens the dashboard sees the old pipeline.

---

## 1. Data and labels

**Q1 (Analyze).** Your test labels match the local model's suggestion on
89% of rows, and the annotation-agreement evidence says the "blind" sheet
appears to have been filled from the sheet that showed it. Break down
exactly which of your reported results this affects, and which it doesn't.

*A strong answer:* it affects every sentiment figure measured against the
test labels (the fine-tuned model, base FinBERT, the baselines) in the
same way, so comparisons between models survive better than absolute
scores; it biases towards whatever the `llama3.2:3b` suggestion favoured
(the Opus labeller found the human side of 118 of 173 disagreements equals
the suggestion); it does not affect the aspect results, which were not
suggested by that model. Evidence: `annotation-agreement-2026-09-27.md`,
`opus-labeller-2026-10-01.md`.

**Q2 (Evaluate).** Opus 5.5 agrees with your aspect labels at κ 0.80.
Is that evidence that your aspect labels are good? Argue both sides, then
decide.

*A strong answer:* for — an independent rater with the same guideline,
blind, audited, agrees well above the 0.6 bar, and the largest
disagreement is traced to a genuine guideline gap (63 rows of retail
investment products), not noise. Against — it is human–LLM, not
human–human agreement; LLMs and humans can share biases from the same
wording; one human rater means no estimate of human disagreement exists.
Decision: it is evidence of consistency with the guideline, not of
correctness, and the report should say "human–LLM κ".

**Q3 (Create).** Design the aspect agreement round you didn't run, within
two person-hours, so that its result would change a decision.

*A strong answer:* 40–60 rows drawn to over-represent the known boundaries
(wealth vs retail banking, management guidance vs other), two people
labelling blind with `--field aspect`; a pre-stated rule (κ below 0.6 on
the boundary rows means the guideline changes before the top-up round);
the Opus disagreement queue as the source of hard rows. Tools exist:
`train.agreement --field aspect`, `python -m preprocess.export_topup`.

## 2. The sentiment model (the DNN)

**Q4 (Evaluate).** Your fine-tuned model scores macro-F1 0.604 ± 0.035
against base FinBERT's 0.571, but is less accurate (0.66 against 0.70).
Which model should score the corpus? Justify the criterion before the
answer.

*A strong answer:* the criterion follows from the product: an index of
investor sentiment is damaged most by missing negative and positive
signals in a 70%-neutral corpus, which favours macro-F1 over accuracy; but
the margin is about one seed standard deviation on 299 test rows with
anchored labels, so the honest claim is "at least as good, finds more
negatives"; the three-model average with a dev-chosen neutral margin
(0.624, accuracy 0.682) narrows the accuracy gap. A defensible decision
either way, if the criterion is stated first.
Evidence: `finetune-fixes-2026-10-01.md`, `error-analysis-2026-10-01.md`.

**Q5 (Analyze).** Three changes (balanced class weights, source weights,
readable aspect names) each beat the baseline in four of five
cross-validation folds, yet the evidence calls none of them a measured
improvement. Explain the reasoning, and what experiment would settle it.

*A strong answer:* re-running the identical baseline with only padding
changed moved single folds by up to 0.037 (sd 0.024), larger than every
gain; four of five folds is a lean, not significance. Settling it needs
repeated CV over several seeds and a paired test on the fold differences,
or a larger labelled set.

**Q6 (Analyze).** Until 1 October your docs said the loss was
class-weighted; it never was. What does that tell an examiner about the
other claims, and how did the project find out?

*A strong answer:* claims written from intention rather than from the
code drift; it was found by reading the code before a training run, and
fixed in the docs rather than hidden, with an option that reproduces the
old behaviour; the verification protocol (every number to a command) is
what makes the remaining claims checkable. Evidence: the class-weights
section of `finetune-fixes-2026-10-01.md`, HANDOFF run log.

## 3. Aspects

**Q7 (Analyze).** Seed-centroid assignment picks the human's aspect 41% of
the time and gives a sentence 6.4 aspects. Explain *why* it fails, using
evidence from at least two different experiments.

*A strong answer:* FinBERT's mean-pooled embedding wasn't trained for
similarity, so it encodes register (earnings prose vs Reddit question)
more than topic: the centroids sit close together (mean pairwise distance
0.206; the closest pairs 0.94 cosine), no floor fixes accuracy (0.41–0.42
up to 0.70), and the same embeddings make evidence retrieval no better
than random for question-phrased queries while the aspect's name alone
works (MRR 0.559 vs 0.217). Evidence: `aspect-assignment-calibration-
2026-09-30.md`, `chatbot-eval-build-2026-10-01.md`.

**Q8 (Evaluate).** The LLM classifier reaches 0.729, Opus 0.842. Is 0.729
good enough to replace centroid assignment in the published index?

*A strong answer:* relative to the alternative it is a large gain (+0.32
top-1, every aspect's recall higher); where `llama3.1:8b` and `qwen3:4b`
agree (76% of sentences) accuracy is 0.835, a usable confidence signal;
the cost is ~24 hours of local compute and a re-score. Against: weak
aspects (wealth, `other`, management guidance) remain near 0.5 F1, and
the human ceiling is unknown. A strong answer proposes the disagreement
rule (e.g. two-model agreement, else `other`) and re-measures on the test
split.

## 4. Entity recognition

**Q9 (Create).** Your NER resolves DBS Vickers to "not the bank". Construct
the argument for the opposite rule, then design the evidence that would
decide it.

*A strong answer:* DBS Vickers is the bank's own brokerage; for
sentiment towards "DBS as an investment", complaints about its platform
are about DBS's service; the Opus labeller and annotators treated those
rows as wealth or retail banking. Evidence to decide: label the 30
Vickers rows in the gold set under both readings and check which one the
team's sentiment labels assume; and measure how much the DBS index moves
when the 456 sentences are included or excluded.

## 5. The chatbot

**Q10 (Analyze).** Retrieval ranks no better than random when the query is
a question and far better when it names the aspect. Trace, step by step,
how that weakness would reach a user's answer.

*A strong answer:* the model passes its question-like query to
`search_evidence`; the top-k evidence is Reddit-register text off the
topic; the model either cites off-topic quotes (caught only if invented,
not if irrelevant) or summarises them; the citation check verifies that a
quote was retrieved, not that it is relevant, so off-topic evidence
passes every automated check. Fix and test: rank by the aspect name when
given, and re-measure with `chatbot.retrieval_eval`.

**Q11 (Evaluate).** Your harness flags invented citations and figures but
doesn't prevent them, and the 3B model still invents citations in 43–48%
of answers. Is "detect, don't prevent" an acceptable design for a
retail-investor tool?

*A strong answer:* weigh the cost of a wrong figure shown to an investor
against refusing to answer; detection plus a visible warning is honest
but places the burden on the reader; with the 8B model at 13–17% the
residual risk is lower; a stronger design blocks flagged answers or
regenerates them; the report should present the rates, not the
mechanism, as the result.

## 6. The system as a whole

**Q12 (Evaluate).** The dashboard has moved to a separate project. Does
that strengthen or weaken the submission against the rubric?

*A strong answer:* strengthens the architecture (a tested, documented
contract; any front end), weakens the demonstrability unless the marker
can run both; the "System" deliverable must include run instructions for
the dashboard against this API, and the demo video should show them
together.

**Q13 (Create).** You have four weeks. Rank the five changes that would
most improve what a marker *sees in the running system*, and justify the
order with your own evidence.

*A strong answer, one defensible ranking:* (1) run the LLM aspect
classifier on the corpus, since aspect scores are the product and are
currently near-meaningless; (2) fix evidence retrieval's query, cheap and
measured; (3) decide and apply the scoring model; (4) evaluate and apply
NER, after the gold set; (5) settle the neutral boundary in the guideline,
which limits labels, Opus agreement and the model at once. Each with the
evidence file that supports it.

---

## Threats to validity a marker will raise

1. **Anchored labels** (Q1): the test split isn't an independent standard.
2. **One seed for model selection, three for testing**: CV conclusions
   rest on seed 42 alone.
3. **Small test classes**: 39 negative rows; one sentence moves negative F1
   by about 0.02.
4. **Measured but not deployed**: the aspect classifier, the fine-tuned
   model and NER are evaluated offline; the index still reflects the old
   pipeline.
5. **Source mix drives the headline**: DBS carries six times the earnings
   text, which is far more positive than Reddit.
6. **LLM involvement in labels**: the suggestion model anchored the human
   labels; Opus agreement is human–LLM; both belong in the GenAI
   declaration.

## Strengths a marker will credit

- Every number traces to a command; errors were found and corrected in
  the open (class weights, error counts, a wrong explanation).
- Selection on cross-validation with rules fixed in advance; the test
  split was never used to choose.
- Baselines for every model, including a random baseline for retrieval.
- An honest negative result (retrieval, centroid assignment) explained
  rather than buried.
- Reproducibility: a checksummed snapshot, a clean-copy install test, an
  OpenAPI contract kept current by a test.

## Sources

Every claim above links to, or names, an evidence file in
`docs/evidence/` or a document in `docs/`. Bloom levels as in
[learning/README.md](../../learning/README.md) (Anderson and Krathwohl,
2001).
