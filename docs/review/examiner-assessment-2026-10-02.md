# An examiner's assessment, 2 October 2026

*Written in the role of an external examiner for the NUS-ISS PLP practice
module. It assesses the repository on `main` the morning after the
1–2 October overnight runs, 30 days before submission. It follows the
[1 October assessment](examiner-assessment-2026-10-01.md), which set
questions for the team to rehearse. This one judges: it breaks the project
down (Analyze), weighs it against the module's requirements with stated
criteria (Evaluate), and proposes what to build next (Create). Bloom levels
are Anderson and Krathwohl (2001). It judges the work, not the people. Every
figure comes from an evidence file named beside it.*

---

## Verdict

| what is assessed | weight | verdict | why, in one line |
|---|---|---|---|
| System, code, datasets, documentation | 20% | **Strong, with one structural risk** | 551 tests, an OpenAPI contract, two clean installs, a figure-to-command evidence trail; but the dashboard a marker will open is outside that regime |
| Report | 20% | **At risk** | Only the factual sections are drafted, and its central results still depend on decisions not yet taken |
| Video | 5% | Not started | — |
| Rubric: a self-built or fine-tuned DNN | required | **Met, modestly** | Fine-tuned FinBERT, three seeds, three baselines; it leads on macro-F1 and trails on accuracy (§2) |
| Rubric: at least two text-mining tasks | required | **Met on paper, thin in the product** | Four designed; sentiment and discovery deployed; aspect classification measured but not applied; NER built, not evaluated |
| Rubric: conversational UI or sentiment mining | required | **Both present; the chatbot's grounding is the weak point** | 11 of 32 answers on the 8B model cite evidence that doesn't exist (§1.2) |

**What changed since 1 October.** Three verdicts moved. The chatbot moved
down: its evaluation now has live numbers, and they show invented evidence
is common and systematic, not occasional. The LLM judge, which the plan
relied on to scale faithfulness checks, does not discriminate at all. The
system verdict gained a risk: the dashboard returned to the repository the
same night it was handed out, and already disagrees with the API on one
view. Two things moved up: a blind top-up labelling sheet exists, and the
evidence base for the demo-model decision is complete for the local models.
One open question is now closed: on three seeds the readable aspect label
is no better than the aspect key, so the DNN's gain over 30 September can't
be credited to it.

---

## 1. Analyze: where the project's weaknesses come from

### 1.1 The gap between what is measured and what is deployed

Four components have a measured better alternative that the running system
does not use. Breaking the index down by component:

| component | in the database today | measured alternative | effect if switched | evidence |
|---|---|---|---|---|
| sentiment | base FinBERT, zero-shot (test macro-F1 0.571, accuracy 0.70) | 3 fine-tuned seeds averaged, dev-chosen neutral margin (0.624, accuracy 0.682) | every bank's headline rises 0.06–0.19; UOB moves ahead of DBS | `finetune-fixes`, `error-analysis`, `index-preview` |
| aspects | seed centroids: about 6.4 aspects a sentence, the human's aspect 41% of the time | `llama3.1:8b`, one aspect: 0.729 (0.835 where `qwen3:4b` agrees) | headline unchanged; several aspects turn negative (DBS asset quality +0.258 → −0.255) | `llm-aspect-classifier`, `index-preview` |
| bank attribution | alias matching | spaCy NER with a resolution table | 763 sentences (1.7%) attributed differently since a 2 Oct fix (714 before), 456 of them DBS Vickers | `bank-ner` |
| evidence retrieval | the user's question as the query: MRR 0.217, equal to random | the aspect's name (`CHATBOT_ASPECT_QUERY=1`): 0.559 | evidence on the asked topic; see evidence-2 in §1.2 | `chatbot-eval-build` |

Two findings follow. First, **the components are not independent in what
they change**: the sentiment model moves the headline, the aspect method
moves the per-aspect rows, and attribution moves which sentences count at
all. The report's headline claims ("UOB trails DBS") and its per-aspect
claims ("asset quality is positive for every bank") are each controlled by a
different pending decision, and both currently rest on the weaker method.
Second, **one root cause sits under two of the four**: FinBERT's mean-pooled
embedding encodes register (earnings prose against a Reddit question) more
than topic. It is why centroid assignment fails and why question-phrased
retrieval ranks at chance. Fixing one doesn't fix the other, but a report
that names the shared cause is stronger than one that reports two
unrelated failures.

### 1.2 Why the chatbot invents evidence

The 1–2 October runs give a complete decomposition on 32 questions
(`chatbot-eval-build-2026-10-01.md`, Live runs):

| failure | 8B | 3B | where it arises |
|---|---|---|---|
| a citation no tool returned | 11 / 32 | 15 / 32 (14 real, 1 a tool call written as text) | generation |
| wrong or missing tool | 4 / 24 | 6 / 24 | planning |
| off-topic evidence presented as on-topic | seen in evidence-2 | not counted | retrieval and centroid aspects |
| follow-up refused as out of scope | 1 of 9 turns | not run | the input guard |
| tool call written out as text | 1 of 9 turns | 1 / 32 | the model's tool-calling format |

The decisive observation: **every one of the 25 confirmed invented citations
(11 on the 8B, 14 on the 3B) comes from an answer that never called
`search_evidence`.** The
model looks up a score and then writes a "Supporting evidence" section
anyway. The prompt contains both the cause and the attempted cure: rule 6
asks for "supporting evidence with citations" in every answer, and rule 8
forbids an evidence section without a search. Small models resolve that
conflict in favour of the format. This is a design fault, not a model
fault: a constraint the system can check (was a search made?) is delegated
to the model, which can't be relied on to obey it, while the harness that
can check it only appends a warning afterwards.

The second observation is subtler. **The judge's blind spot is the same as
the model's.** `qwen3:4b` scored all 32 answers 3 ("every claim supported"),
including the 11 inventions, and its reasons show why: it checks the figures
an answer opens with (which always come from a tool) and ignores the
evidence section, which is exactly where every invented figure sits. The
harness's rule-based checks found what the judge missed. An evaluation
design that had calibrated this judge against human ratings first would have
spent people's time calibrating a constant.

### 1.3 The dashboard: two read paths, already drifting

The dashboard was removed on 1 October (DESIGN 23), with the API extended
to serve every view, and restored the same night when the teammate building
it pushed a redesign to the repository. The result is two ways to read the
same data: the dashboard queries SQLite directly; any other client uses the
API. They have already diverged. The API's `/analyst-consensus/latest`
takes each bank's newest row, a fix made on 1 October because a single
"latest date" for all banks hid UOB's consensus. The dashboard still
uses the single date, so it still hides UOB. The API has a test that fails
if its contract drifts; the dashboard has a styling test. A marker will
judge the system by what the dashboard shows, which is the less tested path.

### 1.4 Which conclusions survive the threats to validity

| conclusion | threat | survives? |
|---|---|---|
| the fine-tuned model beats base FinBERT on macro-F1 | test labels anchored on a model suggestion (89% agreement); 39 negative test rows | as a comparison, mostly: both models face the same labels. The size of the gap (about one seed sd) does not survive as a precise number |
| the readable aspect label is the best input | CV differences smaller than the noise between two runs of one configuration (sd 0.024, one pair) | **No.** Repeated on seeds 1 and 7 its lead disappears: +0.005 over 15 paired folds, 8 of 15 better (`noise-floor-cv`). The final models stand; the claim that the input helped doesn't |
| the LLM aspect classifier beats centroids | one human rater for aspects; no human–human κ | yes: +0.32 is far beyond any plausible rater noise |
| retrieval is no better than random for questions | 28 queries; relevance = the human aspect | yes: an exact baseline and a mechanism |
| the 8B invents less than the 3B | one run each at temperature 0.2 | the direction, yes (4 vs 10 on 30 Sep, 11 vs 15 now); the size, no |

---

## 2. Evaluate: against the module's requirements

**The DNN.** The criterion a marker will apply is whether the network was
trained and evaluated properly, not whether it wins. On that criterion the
work is good: a frozen random test split, selection on cross-validation with
rules fixed before the runs, three seeds, three baselines (base FinBERT,
VADER, TF-IDF with logistic regression), and an error analysis that found the
model's bias (neutral sentences called polar) and a dev-chosen correction.
Its weaknesses are honestly reported: a lead of about one standard
deviation on macro-F1, a deficit on accuracy, and a documented bug (class
weights computed but never applied before 1 October). Its selection story is
weaker than its test result: the input change chosen on 1 October showed no
effect when cross-validated on two more seeds, so the report should credit no
single change for the gain over 30 September. The requirement is met.
What would raise it: applying the model to the corpus, so the DNN changes
what the product shows (§3.1).

**The text-mining tasks.** Two are required and four are designed. Judged
by "built, evaluated and in the product": sentiment classification (all
three) and aspect discovery (built and used to derive the taxonomy; its
evaluation is qualitative) meet it. Aspect categorisation is built and
evaluated but not in the product; NER is built but not evaluated, because
its gold set is blank. The requirement is met by two; the project's own
claim of four is not yet earned for the other two.

**The conversational UI.** Strong on architecture: tool calling over a
typed API, conversation memory, input guards, a citation check and a number
check, four interchangeable backends, a 32-question gold set with multi-turn
scenarios and an exact retrieval baseline. Weak on outcome: on the better
local model a third of answers carry invented evidence. The
detect-and-warn design was defensible while invention looked occasional; the
new data shows it is systematic and has a known trigger, which makes
prevention cheap (§3.2). At the 8B's rate on 1 October (11 of the 24 answers
that reached the model), a marker who asks three questions about scores in
the demo is more likely than not to see a warning.

**Sentiment mining.** The index's design is careful (confidence and source
weighting, shrinkage at low volume, one vote per sentence in the headline,
a continuous series computed with the same weights), and the source-mix
effect on the headline (DBS carries six times the earnings text) is
documented rather than hidden. Its weakness is §1.1: the numbers it shows
come from the weaker method on three of four components.

**Evaluation practice as a whole.** This is the project's distinguishing
strength and should be the report's spine: every number traces to a
command; negative results (retrieval at chance, centroid assignment at 41%,
a judge that never disagrees) are reported with their mechanism; tonight's
judge result was found because the team checked the judge against known
failures before spending human effort on calibrating it. Few student
projects test their evaluator.

**Process.** Decisions are logged with dates and reasons (23 DESIGN
decisions), and corrections are made in the open. The risk is the inverse
of that care: four measured improvements await team decisions, and the
1 October assessment already ranked applying them first. Every week they
wait shortens the time to re-score (planned for 12–18 Oct), re-evaluate and
write up before results freeze (19–25 Oct).

---

## 3. Create: what to build in the remaining 30 days

### 3.1 Close the deployed gap by 18 October, in dependency order

1. **By 5 Oct: decide the aspect method and the disagreement rule**
   (llama's answer, or `other` where the two models disagree). The corpus
   run takes about 24 hours of machine time and is resumable; the cache
   started filling on the night of 1 October.
2. **By 9 Oct: decide the scoring model** (the three-seed average with the
   neutral margin is the measured best on macro-F1). Re-scoring needs no
   new labels.
3. **By 12 Oct: decide bank attribution**, after the NER gold set is
   labelled; the DBS Vickers rule (456 sentences) is the one choice that
   matters.
4. **12–18 Oct: re-score once, re-aggregate once, re-run every evaluation
   once**, and snapshot. One combined re-run is cheaper and easier to
   explain than three.
5. **Fallback.** If a decision isn't made by its date, ship the old method
   for that component and report the alternative as a measured result. The
   index-preview evidence already shows the size of each switch.

### 3.2 Make grounding a property of the code, then prove it

Design: when an answer has no `search_evidence` call, the harness removes
its evidence section (or runs the search itself with the bank and aspect it
already has, and appends real quotes it formats from the tool result). The
model never writes a sentence id or URL. Add context to the scope guard so
a follow-up isn't refused, and parse a tool call the model writes as text
and execute it.

Proof: re-run gold set v2 and the conversations on both local models with
the same commands. Success criteria, stated before the run: zero citation
warnings on answers without a search; tool selection no worse than 20/24
(8B); conversations 9/9 turns. Then switch `CHATBOT_ASPECT_QUERY` on and
re-run once more, reading every evidence answer for relevance by hand.

### 3.3 Replace the judge before asking people to calibrate it

Validate any judge against the harness's known failures first
(`chatbot.judge checks`): it must score most confirmed inventions 1 before
human ratings are worth collecting. Candidates in order of cost: `qwen3:4b`
with thinking on; a narrow judge asked one question at a time ("is every
quoted sentence in the tool data?"); a larger hosted model (the Groq option
is built, awaiting a key). People's ratings of the 32 answers remain the
faithfulness measure either way.

### 3.4 Make the dashboard read the API, or test it like the API

Either the dashboard's owner moves its views onto the API, which already
serves all of them and is tested, or the dashboard gets tests that pin
what it shows to what the API returns, starting with the consensus panel.
Whichever, the consensus fix (`ingest.yahoo_analyst.latest_per_bank`) is
one line and should go in now.

### 3.5 The report's argument

The evidence supports a clear thesis: *in a small-data, multi-source
setting, how an aspect-based sentiment system is evaluated matters as much
as which model it uses.* Each section can carry one measured instance:
labels anchored by a model suggestion; cross-validation differences inside
the noise; a classifier that beats centroid assignment by 0.32; retrieval
at chance for one query style; a judge that never disagrees. That framing
turns the project's honest negatives into its contribution.

---

## Questions for the viva

**V1 (Analyze).** All 25 confirmed invented citations came from answers that
never searched. What does that tell you about where the fault lies, and why
didn't prompt rule 8 work?

**V2 (Evaluate).** Your LLM judge scored every answer 3. Was building it
wasted effort? Defend a position.

*A strong answer:* not wasted, because validating it against known failures
was cheap and stopped human time being spent calibrating a constant; but the
plan should have validated before building the calibration step. The general
lesson: an evaluator needs its own evaluation.

**V3 (Analyze).** Your dashboard and your API show different analyst
consensus for UOB. Trace why, and what architectural choice made it
possible.

**V4 (Evaluate).** Switching to the fine-tuned model puts UOB ahead of DBS.
Which ranking would you publish, and on what criterion?

*A strong answer:* states the criterion first (macro-F1, since the index
exists to surface non-neutral sentiment), notes the fine-tuned model's known
bias towards polar labels and that the margin version reduces it, and
publishes the margin version's ranking with the base model's as a
sensitivity check, because a ranking that flips with the model is itself a
finding.

**V5 (Evaluate).** On two more seeds, the readable label's cross-validation
lead vanished. Was choosing it on seed 42 a mistake?

*A strong answer:* separates the decision from the procedure. The decision
did no harm: the label is no worse (+0.005 over 15 paired folds), so the
final models and their test results stand. The procedure was underpowered,
not wrong: the rule was fixed in advance and the 1 October evidence already
called the lead "within noise". The fault is in what one seed's five folds
can resolve (about 0.02), which the team then measured. What changes: the
report credits no input change for the gain over 30 September, and future
choices use at least three seeds.

**V6 (Evaluate).** The top-up sheet's NIM rows are 45% Reddit, mostly about
customer rates. Was spreading candidates across sources the right design?

*A strong answer:* right for diversity in aspects that appear in every
source (dividends, macro), wrong for an aspect that lives in earnings text;
the selection should weight sources by where the aspect actually occurs,
which the centroid pool can estimate; the margin of 20 rows absorbs it this
time.

---

## Strengths a marker will credit

- An evidence trail in which every figure maps to a command, with
  corrections made in the open (class weights, error counts, a wrong
  explanation, tonight's relevance figure).
- Evaluation that tests its own instruments: an exact random baseline for
  retrieval, the judge checked against known failures, and every harness
  flag read by hand (2 false alarms in 14 citation warnings on 30 Sep; none
  in the 8B's 11 on 1 Oct, and one failed answer among the 3B's 15).
- Selection rules fixed before the runs; the test split never used to
  choose.
- Engineering that a marker can verify: 551 tests, an OpenAPI contract kept
  current by a test, two clean-copy installs, checksummed snapshots.
- Honest negative results, each with a mechanism.

## Threats to validity, updated

1. Anchored test labels (89% match the suggestion model): still open; the
   decision whether to relabel the 299 test rows blind has been pending
   since 30 Sep.
2. Model selection on one seed: confirmed on 2 Oct. The selected input's
   lead vanished on seeds 1 and 7, and every 1 October CV comparison was
   within noise (`noise-floor-cv`). The test result stands; the selection
   story doesn't.
3. Small test classes: 39 negative rows.
4. Measured but not deployed: §1.1.
5. Source mix drives the headline.
6. LLM involvement in labels and in evaluation: suggestions anchored the
   labels, Opus agreement is human–LLM, and the judge is an LLM that
   doesn't discriminate.
7. One run per chatbot configuration at temperature 0.2: rates are
   indicative, not precise.

## Sources

`docs/evidence/`: `finetune-fixes-2026-10-01.md`, `error-analysis-2026-10-01.md`,
`index-preview-2026-10-01.md`, `llm-aspect-classifier-2026-10-01.md`,
`bank-ner-2026-10-01.md`, `chatbot-eval-build-2026-10-01.md` (Live runs),
`labelling-topup-2026-10-01.md`, `opus-labeller-2026-10-01.md`,
`noise-floor-cv-2026-10-02.md`; `docs/DESIGN.md` decision 23 and its
amendment; `docs/api-integration.md`; `chatbot/prompts.py` rules 6 and 8.
