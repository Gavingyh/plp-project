# Evaluation, splits, leakage and macro-F1

Subject: Text Processing using Machine Learning (module 3) · Bloom target: Analyze / Evaluate / Create
Prerequisites: [transfer-learning-and-finbert](transfer-learning-and-finbert.md)

---

## 1. Why it matters here (Understand)

The report will make one central claim: *fine-tuning FinBERT on our labelled
data beats base FinBERT applied zero-shot.* Everything in this topic exists to
make that claim mean something.

It is easy to produce a number that supports it and does not survive scrutiny.
This project has already come within one step of doing exactly that, which
makes it a better teaching example than any textbook case.

---

## 2. The concept (Understand / Apply)

### The splits

| split | size here | how sampled | what it is for |
|---|---|---|---|
| `train_dev` | 798 | Model-assisted stratified, oversampling non-neutral | Training, and choosing when to stop |
| `test` | 200 | **Purely at random, before any model screening** | Every headline metric, computed once |

The asymmetry is deliberate and is the most important idea here.

**Why oversample for training.** Base FinBERT calls 87.4% of this corpus
neutral. A training set drawn uniformly would be overwhelmingly neutral and
would starve the positive and negative classes, so the model would learn to
say "neutral" and score well by doing so.

**Why not for test.** Because the test set must represent the real
distribution. If it were drawn from model-screened candidates, it would be
enriched for cases the screening model finds interesting, and the fine-tuned
model's F1 would be inflated relative to the baseline it is compared against.
The comparison, not just the absolute number, would be corrupted.

**This cannot be retrofitted.** You cannot decide after training that a subset
of your model-screened pool is now the test set. The randomness has to come
first.

### Why macro-F1

| metric | what it rewards | on a 87% neutral corpus |
|---|---|---|
| Accuracy | Getting the majority class right | Predict "neutral" always: ~87%. Useless |
| Micro-F1 | Same, weights by class frequency | Dominated by neutral |
| **Macro-F1** | Equal weight to each class | Predicting only neutral scores badly, because positive and negative F1 are 0 |

Macro-F1 averages the per-class F1 scores with equal weight, so a model that
ignores a minority class is punished in proportion to how many classes it
ignores. On a skewed corpus it is the only one of the three that measures what
you care about.

Per class you still report precision (of what I called positive, how much
was), recall (of what really was positive, how much did I find) and their
harmonic mean, F1.

### Baselines are not optional

"Fine-tuning helped" is unsupported without something to compare against.
`train/evaluate.py` runs three, on the same frozen test set:

1. **Base FinBERT zero-shot** — the honest incumbent, since it is what the
   system uses today
2. **A lexicon method** (VADER) — the pre-neural approach
3. **A classical ML method** (TF-IDF + logistic regression) — the pre-transformer approach

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| The sampling design and its rationale | `preprocess/export_candidates.py` |
| Blind test export | `preprocess/export_blind_test.py` |
| Fine-tuning configuration | `train/finetune.py` |
| Baselines and metrics on the frozen test set | `train/evaluate.py` |
| Inter-annotator agreement | `train/agreement.py` |
| Labelling rules | `docs/annotation-guideline.md` |

---

## 4. Analyze

### The leak that actually happened

`train/llm_prelabel.py` ran a local model over `candidates.csv` to propose a
label for each row. It processed **199 of the 200 test rows**.

Every row also carries `base_finbert_label`, base FinBERT's own zero-shot
guess, included as reference context for annotators.

So an annotator opening `candidates.csv` to label the test set would see, next
to each sentence, two model opinions — one of them from **the very model the
test set exists to compare against**. Two distinct failures follow:

| column | what it corrupts | severity |
|---|---|---|
| `llm_prelabel` | Measures agreement with `llama3.2:3b` rather than establishing ground truth | Serious |
| `base_finbert_label` | Anchors the annotator on the *baseline's* answer, biasing the comparison in the baseline's favour | **Worse** |

The second is worse because of its direction. Anchoring on the baseline makes
the human labels more like the baseline's predictions, which inflates the
baseline's apparent accuracy and *understates* the fine-tuned model's
improvement. It is a bias against the project's own hypothesis, which makes it
subtle — a result that looked disappointing would not have prompted anyone to
go looking for a leak.

`preprocess/export_blind_test.py` is the repair: `test_blind.csv` carries the
sentence, its aspect and its provenance, and nothing else.

**Be precise about what the repair does and does not do.** It prevents the
leak for anyone labelling from the blind sheet, and since zero rows are
labelled so far, nothing is yet contaminated. It does not undo the model's
exposure to those rows, and it cannot help if someone opens `candidates.csv`
and labels the test rows there anyway.

### The class-balance problem nobody can fix by relabelling

The proposal asks for 200–300 examples per sentiment class. Candidate rows by
aspect:

| aspect | rows |
|---|---|
| other | 524 |
| dividend_policy | 200 |
| net_interest_margin | 119 |
| management_guidance | 97 |
| asset_quality | 58 |

`asset_quality` cannot yield 200 per class no matter how the labels fall,
because it has 58 rows total. Neither can `management_guidance`. And `other`,
the fallback bucket rather than a real aspect, is over half the sheet.

This is a sampling problem discovered after export, and it constrains what the
evaluation can claim: per-aspect metrics on `asset_quality` will rest on a few
dozen examples and should be reported with that caveat or not at all.

### Comparing three evaluation designs

| design | cost | what it gives | risk |
|---|---|---|---|
| **Frozen random hold-out** (used) | 200 rows spent on evaluation | One honest estimate | High variance on 200 rows, especially per class |
| k-fold cross-validation | Every row used for both | Lower-variance estimate, plus a spread | Needs care to keep model-assisted selection out of every fold. Harder to keep genuinely blind |
| Temporal split (train on 2020–24, test on 2025–26) | Same as hold-out | Tests generalisation to *future* text, which is the real deployment condition | Confounds time with topic; a rate-hike cycle changes what is discussed |

The proposal allowed either hold-out or k-fold given the small seed set. The
hold-out was chosen and the honest reason to prefer it here is not statistical
— it is that "frozen, random, never touched" is a property you can *state and
defend*, while a k-fold over a partly model-screened pool needs a much more
careful argument about what leaked into which fold.

The temporal split is the interesting road not taken, since the dashboard's
actual job is scoring text that has not been written yet.

---

## 5. Evaluate

**The sampling design is the strongest piece of methodological thinking in the
project.** It was documented in
`preprocess/export_candidates.py` before the data was exported, with the trap
spelled out explicitly.

**And it was undermined anyway.** The design was right; the operational
discipline slipped, because the pre-labelling script had no notion that the
test split was special. *A methodological safeguard that lives only in a
docstring will eventually be walked past by a script that never read it.* The blind export enforces in code what the docstring asked
for, which is the same move the chatbot made with citation verification.

**What 200 test rows can support.** Not much per class. If the labels split
anything like the model's proposals (positive 464, negative 310, neutral 223
over 998 rows), the test set holds roughly 40–90 examples per class. A
macro-F1 difference of a few points between models will not be significant at
that size. The report should give the number of test examples per class next
to every metric, and should resist reading small differences as real.

**When leakage would not matter.** If the fine-tuned model were being compared
against a *human* baseline rather than against base FinBERT, the
`base_finbert_label` column would be far less dangerous. It is the fact that
the baseline's opinion is visible while labelling the set used to judge that
baseline that makes it corrosive.

---

## 6. Create

**Exercise (about ninety minutes).** Quantify what the test set can and cannot
support, before anyone spends days labelling it.

```python
# .venv-plp/bin/python3
import pandas as pd
df = pd.read_csv("data/labeled/candidates.csv", keep_default_na=False)
test = df[df["split"] == "test"]

print("test rows:", len(test))
print("\nby aspect:\n", test["aspect"].value_counts())
print("\nby bank:\n", test["bank"].value_counts())
print("\nby source:\n", test["source"].value_counts())
print("\nmodel-proposed label distribution (a proxy, NOT ground truth):\n",
      test["llm_prelabel"].value_counts())
print("\nrows carrying a model opinion:",
      (test["llm_prelabel"].astype(str).str.strip() != "").sum(), "of", len(test))
```

Then estimate: if the true label distribution resembles the proposals, how
many test examples fall in the smallest class? Use that to work out the
narrowest macro-F1 difference the test set could distinguish. A rough guide is
that a proportion estimated from `m` examples carries a standard error of
about `sqrt(0.25/m)`.

**Expected outcome.** You should conclude that per-class counts in the low tens
mean differences of several percentage points are within noise, and that
per-aspect breakdowns on `asset_quality` are not supportable at all.

**Write for the report:** the test-set composition table, the smallest class
count, and one sentence stating the minimum difference you would treat as
real. Deciding that *before* seeing the results is what stops the analysis
becoming a search for a flattering comparison.

---

## 7. Self-check

1. Why is the training set deliberately oversampled for non-neutral examples
   while the test set is not?
2. Why is `base_finbert_label` more dangerous on the test sheet than
   `llm_prelabel`?
3. In which direction did the leak bias the comparison, and why does that make
   it hard to notice?
4. Why is accuracy a poor headline metric here?
5. Why can't the test split be chosen after the model-assisted screening?

<details>
<summary>Answers</summary>

1. Training needs enough positive and negative examples to learn those classes;
   a uniform sample from an 87%-neutral corpus would starve them. The test set
   must represent the real distribution, because its job is to estimate
   performance in the wild rather than to teach anything.
2. Because base FinBERT is one of the two models the test set exists to
   compare. Anchoring an annotator on the baseline's answer biases the
   comparison directly in the baseline's favour. `llm_prelabel` is a third
   party and merely measures agreement with it.
3. Toward the baseline: human labels drift toward base FinBERT's predictions,
   inflating the baseline's apparent accuracy and understating the fine-tuned
   model's improvement. It is hard to notice because it makes your own result
   look worse, and nobody investigates a disappointing number for signs that it
   was unfairly disadvantaged.
4. Because 87.4% of the corpus is neutral, so a model that always predicts
   neutral scores about 87% while being useless. Macro-F1 gives each class
   equal weight and punishes ignoring the minority classes.
5. Because model screening enriches the pool for cases the screening model
   finds interesting. A test set drawn from that pool is not a random sample
   of the real distribution, so metrics computed on it are inflated relative
   to the baseline being compared against. The randomness must precede the
   screening.

</details>

---

## 8. Sources

**Repository**

- `preprocess/export_candidates.py` — the sampling design and the trap it names
- `preprocess/export_blind_test.py` — the leak, in its own words, and the repair
- `train/evaluate.py` — the three required baselines and the frozen test set
- `train/finetune.py` — training configuration and the multi-seed instruction
- `docs/annotation-guideline.md` — the frozen-test-split rule
- `docs/STATUS.md` — labelling status and class-balance risk
- `docs/verification-ledger.md` — candidate counts

**Measured in this repository (2026-09-11)**

- 998 candidates (798 train_dev, 200 test), 0 human labels, 997 rows carrying
  `llm_prelabel`, 199 of 200 test rows affected, aspect distribution, and the
  87.4% neutral rate across `aspect_sentiment`.

**Course material**

- `.project-context/course-content/TPML-context.txt` day 1 — hold-out versus
  k-fold, over/underfitting, regularisation

**Not verified**

- The standard-error rule of thumb in section 6 is the usual normal
  approximation for a proportion and is offered as a rough guide, not a
  rigorous power calculation. Do a proper one if the report claims
  significance.
- Whether the eventual human label distribution will resemble the model's
  proposals. It may not; the estimate in the exercise is explicitly a proxy.
