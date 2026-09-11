# Annotation and inter-annotator agreement

Subject: Text Analytics (module 1) · Bloom target: Analyze / Evaluate / Create
Prerequisites: none. Read with
[evaluation-splits-and-leakage](../03-text-processing-with-ml/evaluation-splits-and-leakage.md).

---

## 1. Why it matters here (Understand)

Labelling is the project's critical blocker. Zero of 998 candidate rows are
human-labelled, and until they are there is no fine-tuned model, and therefore
no deep-learning deliverable.

It is also four people doing subjective judgement independently. Without a
shared guideline and a way to check it is being applied consistently, four
annotators produce four incompatible datasets and the model learns their
disagreement.

---

## 2. The concept (Understand / Apply)

### What makes a guideline work

`docs/annotation-guideline.md` is short and does the three things a guideline
must:

**It states one question precisely.** Not "is this positive?" but *sentiment
toward the bank as an investment, on this specific aspect* — not the writer's
mood, and not sentiment toward something else sharing the sentence. The worked
example makes the distinction vivid:

> "UOB's provisioning jumped but honestly I'm just happy the coffee at the
> branch is free" → **negative** on `asset_quality`, regardless of the
> writer's cheerful tone.

**It decides the edge cases in advance.** Facts with valence are not neutral
("NPL ratio rose to 1.4%" is negative with no opinion word). Sarcasm is
labelled by intent. Quoted analyst opinion is labelled as the analyst's view,
not the annotator's assessment of whether they are right.

**It says what to do when the scheme does not fit.** Incidental bank mentions
should probably not have been assigned that aspect at all, so flag them rather
than forcing a label.

### Cohen's kappa

Raw agreement is misleading on a skewed corpus. Kappa corrects for agreement
expected by chance:

```
κ = (observed agreement − chance agreement) / (1 − chance agreement)
```

Chance agreement is computed from each annotator's own label distribution.
Worked example from this project's tests:

| | value |
|---|---|
| Two annotators, 20 items, both say `neutral` 18 times, swap on the other two | |
| Observed agreement | 0.90 |
| Chance agreement | 0.9×0.9 + 0.05×0.05 + 0.05×0.05 = 0.815 |
| **κ** | (0.90 − 0.815) / (1 − 0.815) = **0.459** |

Ninety percent agreement, and κ of 0.46 — below this project's threshold. The
gap is the whole reason kappa exists.

### Interpreting the number

Landis and Koch's bands, as taught in module 1:

| κ | interpretation |
|---|---|
| < 0.00 | poor |
| 0.00–0.20 | slight |
| 0.21–0.40 | fair |
| 0.41–0.60 | moderate |
| 0.61–0.80 | substantial |
| 0.81–1.00 | almost perfect |

This project sets its own target at **κ ≥ 0.6**. Below that, the guideline is
ambiguous somewhere — find the disagreements, tighten the guideline, re-label
the sample.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| The labelling scheme and decided edge cases | `docs/annotation-guideline.md` |
| Cohen's κ, Landis and Koch bands, disagreement listing | `train/agreement.py` |
| Candidate export and sampling design | `preprocess/export_candidates.py` |
| Blind test sheet | `preprocess/export_blind_test.py` |
| LLM pre-labelling | `train/llm_prelabel.py` |

---

## 4. Analyze

### LLM-assisted annotation, and its two-sided nature

`train/llm_prelabel.py` runs a local model over every candidate row, filling
`llm_prelabel` and `llm_rationale` — **never** `label`, which stays reserved
for human judgement. The intent is to convert labelling from "read and decide"
into "read and correct", which is faster.

Module 1 covers exactly this pattern: structured prompting, validation against
human-verified data, human-in-the-loop correction. The prompt in
`llm_prelabel.py` deliberately mirrors the guideline's core question and
decided edge cases.

**The cost is anchoring.** An annotator who sees a proposed label before
forming a view will agree with it more often than they should. The guideline
addresses this directly: label independently first if you want to measure how
often the model was right, because anchoring on its suggestion before forming
your own view defeats that measurement.

**How much the pre-label adds.** Running `train/agreement.py`
over the two model opinions already in `candidates.csv`:

| | value |
|---|---|
| Rows compared | 997 |
| Observed agreement | 0.462 |
| Cohen's κ | 0.215 (fair) |

The local model and base FinBERT disagree on more than half the rows. The
pattern is one-directional: the local model called **208** sentences positive
and **135** negative that FinBERT called neutral.

That is explicable rather than random. The local model was prompted with the
guideline's rule that a factual statement with clear valence is not neutral;
FinBERT was not. So the disagreement is substantially by design, and two
things follow: the pre-labels are not a copy of the baseline, so correcting
them is real work rather than rubber-stamping — and neither column is ground
truth, which is what the annotators are creating.

### A model-choice finding

`llm_prelabel.py` documents testing two models on the same case, a rising NPL
ratio, which the guideline's own worked example labels negative:

| model | time per call | answer |
|---|---|---|
| `llama3.2:3b` | 3–5 s | **negative** (correct) |
| `qwen3:4b` | 65–97 s | **positive**, while its own rationale described "worsening risk exposure" and "a negative signal" |

The larger, slower reasoning model was both slower *and* wrong, and
internally inconsistent: its chain of thought contradicted its final answer.
"Bigger model, better labels" is not a safe assumption, and this is a concrete
counterexample from the project's own data.

### Comparing four ways to get labels

| approach | cost | quality | risk |
|---|---|---|---|
| Human from scratch | Highest | Best available | Slow; four people may drift apart |
| **LLM pre-label, human corrects** (used) | Moderate | Depends on correction discipline | Anchoring |
| LLM labels alone | Lowest | Unknown, and unmeasurable without human labels | The DNN would learn another model's opinions, not ground truth |
| Weak supervision from a finance lexicon | Low | Poor on financial phrasing | General lexicons mislabel "beat lowered guidance" |

Row 3 deserves emphasis because it is tempting under deadline. Fine-tuning on
LLM labels would produce a model that imitates `llama3.2:3b` — the same model
that fabricates citations in 43–48% of chatbot answers. The result would be
presented as a fine-tuned financial sentiment classifier and would be a
distillation of a 3B model's guesses.

The original proposal's step 1 was row 4, weak labels from the
Loughran-McDonald dictionary. That was superseded by the LLM approach, which
is a reasonable substitution and should be stated as such in the report rather
than left as an unexplained divergence from the plan.

---

## 5. Evaluate

**The guideline is good on the criterion that matters:** it decides the
hard cases in advance rather than leaving them to each annotator. The
factual-valence rule alone will prevent a large fraction of potential
disagreement, because it is the case that arises most in earnings text.

**The κ ≥ 0.6 target sits at the lower end** of "substantial" and is
defensible for a subjective three-class task. Module 1 notes 0.8 is commonly
cited as a good threshold, so 0.6 is a pragmatic floor rather than an
ambitious one. The report should state it as the project's chosen threshold,
not as a standard.

**The unmeasurable risk.** With pre-labels visible, a rushed annotator
approves rather than judges. Nothing in the workflow detects this: a
high-agreement dataset produced by rubber-stamping looks exactly like a
high-agreement dataset produced by careful independent judgement. The
guideline's advice to label independently first is the only defence, and it is
advice rather than a control — the same weakness as prompt-based grounding in
the chatbot, and the same fix would apply, which is to withhold the column
during a first pass.

**What has not been done.** Everything. Zero rows labelled, no κ computed
between humans, no annotator training pass. The tooling is complete and the
work has not started, and with the deadline of 1 November 2026 this is the
project's critical path.

---

## 6. Create

**Exercise (about two hours, and it is real project work).** Run the
inter-annotator agreement check the guideline asks for.

1. Take the first 150 rows of `data/labeled/test_blind.csv` — the blind sheet,
   which withholds both model opinions.
2. Two people label them **independently**. Do not discuss while labelling.
3. Save as `alice.csv` and `bob.csv`, keeping `sentence_id` and `aspect`.

```bash
.venv-plp/bin/python3 -m train.agreement --a alice.csv --b bob.csv
.venv-plp/bin/python3 -m train.agreement --a alice.csv --b bob.csv --show-disagreements 25
```

**Expected outcome.** Probably κ between 0.4 and 0.7 on a first pass. Under
0.6, the tool prints what to do: read the 25 disagreements together, decide
which rule was ambiguous, add it to the guideline as a decided edge case, and
re-label the same 150.

Watch the gap between raw agreement and κ. If raw is high and κ is low, you
are both defaulting to `neutral` and the guideline's factual-valence rule is
not being applied.

**For the report:** κ before and after the guideline revision, the specific
rule you added, and the final agreed threshold. A methods section that shows
agreement being measured, found wanting, and improved is substantially
stronger than one reporting a single number.

---

## 7. Self-check

1. Why is raw agreement misleading here, with a worked number?
2. Why does `llm_prelabel.py` never write to the `label` column?
3. The local model and base FinBERT agree on only 46% of rows. Why is that
   more reassuring than alarming?
4. Why is fine-tuning directly on LLM labels a bad idea?
5. What does κ below 0.6 mean, per this project's guideline?

<details>
<summary>Answers</summary>

1. Because the corpus is heavily neutral, so two annotators who both default
   to `neutral` agree often without sharing judgement. Worked: both say
   neutral 18 of 20 times and swap the other two — raw agreement 0.90, chance
   agreement 0.815, κ 0.459, below the 0.6 target.
2. Because `label` is reserved for human judgement. Keeping the model's
   proposal in a separate column preserves the distinction between what a
   model guessed and what a person decided, and makes it possible to measure
   how often the model was right.
3. Because it shows the pre-labels are not merely reproducing the baseline. If
   they agreed almost perfectly, pre-labelling would add nothing over
   `base_finbert_label` and correcting them would be rubber-stamping. The
   disagreement is also explicable: the local model was given the
   factual-valence rule and FinBERT was not.
4. Because the resulting model would imitate the labelling model rather than
   learn ground truth, and the labelling model here is a 3B local model that
   fabricates citations in 43–48% of chatbot answers. It would be presented as
   a fine-tuned financial classifier while being a distillation of another
   model's guesses.
5. That the guideline is ambiguous somewhere, not that an annotator was
   careless. The prescribed response is to find the disagreements, tighten the
   guideline, and re-label that sample before dividing up the rest.

</details>

---

## 8. Sources

**Repository**

- `docs/annotation-guideline.md` — the scheme, edge cases, κ target
- `train/agreement.py` — κ, Landis and Koch bands, the raw-vs-κ gap warning
- `train/llm_prelabel.py` — the prompt, and the llama-vs-qwen model comparison
- `tests/test_agreement.py` — the worked 0.90/0.459 case
- `preprocess/export_blind_test.py` — why the test sheet withholds model columns

**Measured in this repository (2026-09-11)**

- κ = 0.215 and 46.2% agreement between `llm_prelabel` and
  `base_finbert_label` over 997 rows, via `train/agreement.py`.
- The 208 positive / 135 negative directional split, from its confusion matrix.

**External**

- Landis, J.R. and Koch, G.G. (1977), "The Measurement of Observer Agreement
  for Categorical Data", *Biometrics* 33(1):159–174 — the source of the
  interpretation bands, cited in module 1's material. **Not fetched during
  this pass**; cite the paper directly.
- Cohen, J. (1960), "A Coefficient of Agreement for Nominal Scales". **Not
  fetched.**

**Course material**

- `.project-context/course-content/TA-context.txt` — corpus annotation
  methodology, IAA measures, LLMs as annotators

**Not verified**

- No human labels exist, so no human-to-human κ has ever been computed. Every
  agreement figure here is model-to-model.
- The llama-vs-qwen comparison is a single test case documented in
  `train/llm_prelabel.py`, not a systematic evaluation.
