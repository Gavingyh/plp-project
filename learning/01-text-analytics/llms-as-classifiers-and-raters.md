# LLMs as classifiers and as raters

Subject: Text Analytics (module 1) · Bloom target: Analyze / Evaluate / Create
Prerequisites: [annotation-and-inter-annotator-agreement](annotation-and-inter-annotator-agreement.md),
[aspect-based-sentiment-analysis](../02-sentiment-mining/aspect-based-sentiment-analysis.md).

---

## 1. Why it matters here (Understand)

The project uses large language models in three different roles, and each
needs a different kind of evidence before it can be trusted:

- **suggester**: `llama3.2:3b` proposed a sentiment for annotators to
  correct (September);
- **classifier**: `llama3.1:8b` and `qwen3:4b` choose one aspect per
  sentence, to replace seed-centroid assignment (DESIGN decision 16);
- **rater**: Claude Opus 5.5 labelled the 1,277 sentences as an
  additional, independent annotator (DESIGN decision 22).

Confusing the roles is how a project ends up evaluating a model against
labels that model helped to write.

---

## 2. The concept (Understand / Apply)

**Zero-shot classification with a fixed prompt** (the course's ABSA
pattern, NMSM Day 2): role, task, the label schema with a definition for
each label, constraints, a few examples, then the input. **Structured
output** constrains the model's answer to a JSON schema whose field is an
enum of the allowed labels, so an invalid label becomes nearly impossible.
Temperature 0 makes the answer repeatable for a given model and prompt.

**An LLM rater** is used like a second annotator: the same guideline as the
people, the same rows, *blind* to the human labels, and its agreement is
reported as Cohen's κ. It measures consistency with the guideline, not
correctness.

**Anchoring.** An annotator shown a suggestion tends to keep it. Agreement
between that annotator and the suggester is then inflated, and so is any
evaluation of a model similar to the suggester.

**Agreement as confidence.** A temperature-0 classifier gives no
probability. Two different models agreeing on a sentence is a cheap
substitute: if their errors are not perfectly correlated, agreement picks
out the easier sentences.

---

## 3. Where it lives in this repo (Apply)

| role | where | evidence |
|---|---|---|
| suggester | `train/llm_prelabel.py` (`llm_prelabel` column, never `label`) | `annotation-agreement-2026-09-27.md` |
| classifier | `aspects/llm_classify.py` (`--eval`, `--no-think`) | `llm-aspect-classifier-2026-10-01.md` |
| rater | `data/labeled/llm_rater/`, `train/rater_labels.py` (merge, score, audit) | `llm-rater-2026-10-01.md` |

---

## 4. Analyze

**The classifier against its alternatives** (1,277 sentences, top-1 against
the human aspect): always the commonest aspect 0.374; seed-centroid 0.413;
`qwen3:4b` 0.719; `llama3.1:8b` 0.729; Opus 5.5 0.842. Where the two local
models agree (76% of sentences), they match the human 83.5% of the time;
where they disagree, each is right about 40% of the time. The errors cluster
where the guideline's own boundaries are loose: wealth versus retail
banking, `other`, management guidance.

**The rater, and what its disagreements reveal.** Opus agreed with the human
aspect at κ 0.80 and the human sentiment at κ 0.79. Its 173 sentiment
disagreements are all about where neutral ends (never positive against
negative), and in 118 of them the human label equals the suggestion the
annotators had been shown. Its largest aspect disagreement, 63 rows, is a
category of text the guideline doesn't place: a retail customer's
investment products (brokerage trades, savings plans, gold).

**Making a rater blind, and showing it was.** Each Opus rater was a fresh
subagent given only its instructions and its batch; afterwards every one of
its 108 tool calls was audited for files opened. "Blind" is a claim that
needs a check, not an instruction alone.

**A cost that hides in the defaults.** `qwen3:4b` is a reasoning model: with
its hidden thinking on, three sentences took 92–216 s each; with
`think: false`, about 1.3 s, with the same answers.

---

## 5. Evaluate

The classifier is ready to replace centroid assignment on accuracy (+0.32)
and every aspect's recall rises; what holds it back is the decision about
disagreements and the 24-hour run, not quality. Using two-model agreement
as the acceptance rule would keep 76% of sentences at about 84% accuracy.

The rater earns its place as a *second opinion that finds problems*: it
surfaced a guideline gap and quantified the anchoring that was already
suspected. It does not earn a place as gold. Its agreement figures are
human–LLM; it can share blind spots with the people who wrote the
guideline; and an interactive run on a subscription model can be inspected
but not exactly reproduced.

When the opposite choice would be right: if the human labels were known to
be poor and no budget for people existed, a strong LLM's labels as silver
training data, evaluated only on a human test set, would be defensible. The
evaluation set must stay human either way.

---

## 6. Create

**Exercise (≈ 60 minutes).** Turn two-model agreement into an acceptance
rule and measure it: using `data/aspect_llm/llama3.1_8b.jsonl` and
`qwen3_4b-nothink.jsonl`, label each sentence with the agreed aspect, or
`other` where the models disagree, and score the result against the human
aspect.

*Expected outcome:* coverage of 76% of sentences with their agreed aspect;
top-1 on those 0.835; the rest become `other`, which lowers overall top-1
below 0.729 but makes every non-`other` aspect assignment more precise. Say
which you would publish and why.

---

## 7. Self-check

1. What makes a model's suggestion dangerous for the labels used to test a
   similar model?
2. Opus agrees with the humans at κ 0.80. Name two things that number does
   not show.
3. Why does structured output almost eliminate invalid answers, and what
   can it not prevent?
4. Why is two-model agreement a reasonable confidence signal, and when
   would it fail?
5. Why was the Opus audit necessary if the raters were told not to open
   other files?

<details>
<summary>Answers</summary>

1. Annotators keep suggestions, so the labels drift towards that model, and
   any model making similar errors is scored too kindly.
2. That the labels are correct (only that they're consistent with an LLM
   reading of the guideline), and how much two people would disagree.
3. The decoder may only produce tokens that fit the schema's enum, so an
   off-list label can't be emitted; it can still emit the wrong valid label.
4. Different models make partly independent errors, so agreement filters
   out sentences either finds hard; it fails when both share the same
   misreading (e.g. a guideline gap both interpret the same way).
5. An instruction is not evidence. The audit turns "told to be blind" into
   "shown to be blind" for a reader of the report.

</details>

---

## 8. Sources

**Repository**

- `aspects/llm_classify.py`, `train/llm_prelabel.py`, `train/rater_labels.py`
- `docs/evidence/llm-aspect-classifier-2026-10-01.md`,
  `llm-rater-2026-10-01.md`, `annotation-agreement-2026-09-27.md`
- DESIGN decisions 16 and 22

**Measured in this repository (2026-10-01)**

- Every figure in sections 4 and 5, from the evidence files above.

**Course material**

- NMSM Day 2: the structured zero-shot ABSA prompt; TA Day 1: LLMs as
  annotators with human correction.

**External**

- Ollama, "Structured outputs" (blog post and API docs on the `format`
  JSON schema). **Not fetched during this pass.**

**Not verified**

- The two-model acceptance rule (exercise 6) has not been run.
