# Grounding, hallucination and citation verification

Subject: Conversational UI (module 4) · Bloom target: Analyze / Evaluate / Create
Prerequisites: [tool-calling-agents](tool-calling-agents.md),
[rag-and-hybrid-search](rag-and-hybrid-search.md)

---

## 1. Why it matters here (Understand)

The chatbot's entire value proposition is that its answers come from the
sentiment store rather than from the model's memory. A retail investor asking
"how does the market feel about DBS's dividend?" is being offered evidence,
not opinion. If the model invents a number or a citation, the tool is worse
than useless: it is a confident-sounding fabrication wearing the costume of
research, aimed at people who by definition lack the expertise to catch it.

This project produced unusually clean evidence about how models fail here, and
it is the most report-worthy material the chatbot work generated.

---

## 2. The concept (Understand / Apply)

**Grounding** means every claim in an answer traces to retrieved data.
**Hallucination** is any claim that does not. In a tool-calling system the
failures divide usefully:

| failure | what it looks like | detectable in code? |
|---|---|---|
| Fabricated citation | Quotes a `sentence_id` or URL that was never retrieved | **Yes** — if `search_evidence` was never called, any citation is fabricated by definition |
| Fabricated number | States a sentiment score no tool returned | Partly — you can check whether a tool was called, not whether the number matches |
| Answering from parametric knowledge | Correct-sounding facts about DBS from pre-training, presented as if from the data | Hard — the text may be accurate yet ungrounded |
| Overstating thin data | Reports a score computed from three observations as fact | **Yes** — enforce a volume floor |

The design principle this project arrived at, the hard way:

> **A grounding rule that matters must be enforced in code, not requested in
> the prompt.**

### The two enforcements

**1. Volume floor.** `get_sentiment` returns `insufficient_data` when fewer
than 5 observations underlie a score, instead of returning a number the model
might report as fact. The model cannot report what it was never given.

**2. Citation verification.** After the answer is generated, if
`search_evidence` was never called in that conversation, then any quoted
evidence, `sentence_id` or URL in the answer is fabricated *by definition*,
and the response is flagged with a verification warning.

The second is a detector, not a preventer. It tells the user the answer is
untrustworthy; it does not stop the model producing it.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| The eight grounding rules given to the model | `chatbot/prompts.py` |
| Citation verification, and the warning it emits | `chatbot/agent.py` |
| Volume floor (`MIN_VOLUME_FOR_SCORE = 5`) | `chatbot/tools.py` |
| Aspect-name validation against the real taxonomy | `chatbot/tools.py` |
| 23-question gold set including 7 advice-seeking questions | `chatbot/eval_gold_set.py` |
| Automated checks and per-model output | `chatbot/run_eval.py` |
| Runs per model, kept apart by tag | `chatbot/run_eval.py --tag` |
| Transcripts and summaries | `data/eval/chatbot_eval_*` |

---

## 4. Analyze

### Prompt instructions were tried first, and failed

`chatbot/prompts.py` contains eight numbered grounding rules. Rule 8 is
explicit: *"NEVER invent a citation, sentence_id, or URL. If you have not
called search_evidence in this conversation, do not write a 'supporting
evidence' section at all."*

A local model violated this twice after the prompt was tightened, in two
different formats: once as plausible-looking invented URLs, and once as
placeholder tokens of the form `Sentence_id: [insert sentence_id]`. The second
is instructive on its own — a check that only looked for URL patterns would
have passed it.

That is the empirical basis for moving the rules into code. It is not a
theoretical preference for defensive programming; it is what happened.

### What the evaluation found across four models

23 questions, five local models via Ollama:

| model | params | errors | tool selection | advice behaviour | citation fabrication |
|---|---|---|---|---|---|
| `llama3.2:3b` (default) | 3B | 0 | 12/16 | 3/7 | 10–11/23 (43–48%) |
| `phi4-mini` | 3.8B | 0 | 0/16 | 1/7 | 19/23 (83%) |
| `gemma3:4b` | 4B | 23 | 0/16 | 0/7 | 0/23 |
| `qwen3:4b` | 4B | 23 | 0/16 | 0/7 | 0/23 |
| `llama3.1:8b` | 8B | 3 | 12/16 | 3/7 | 3/23 (13%) |

Four things follow, and they pull in different directions.

**Scale fixes fabrication and nothing else.** 3B to 8B takes fabrication from
43–48% down to 13%. Tool selection (12/16) and advice-declining (3/7) are
*identical* across the two. So fabrication behaves like a capability limit
that scale relieves, while the behavioural failures look like design problems
a bigger model does not touch. That distinction earns space in the report:
it tells you which problems to solve with a model swap and which need a
redesign.

**A 0% fabrication rate can be an artifact — twice over.** Two models score
0/23 and neither result means anything. `gemma3:4b` has no Ollama
tool-calling support, so all 23 questions failed with HTTP 400. `qwen3:4b`
failed all 23 differently: every call exceeded the 120-second read timeout,
because it emits a long hidden reasoning chain before answering and the agent
loop needs several calls per question. Both produced 23 empty answers, so
there were no citations to fabricate.

**A rate is only interpretable alongside its denominator and its error
count**, which is why the table carries both. Reporting either as the
best-grounded model would be a straightforward misreading of a real number,
and the fact that two models reach 0% for two unrelated non-reasons makes the
point better than one did.

**`phi4-mini` is the strongest argument in the project for code-level
enforcement.** It called a tool in **0 of 16** questions yet fabricated
citations in **83%** of answers. It answered entirely from parametric
knowledge while producing text that looked sourced. No prompt rule prevented
this; the code-level check caught every instance, because the check does not
ask the model anything — it observes whether the retrieval call happened.

**The default model's rate is a range, not a point.** Two runs of the same
model on the same gold set gave 11/23 and 10/23. One question on a 23-question
set is 4.3 percentage points. This is a sampling-noise problem, and the honest
fix in the report is to state the spread rather than pick the flattering
number.

**A second column has the same confound, and it is worse there.** Re-running
`llama3.1:8b` moved its reported tool selection from 12/16 to 7/16 — same
model, same questions. All 8 rerun errors were 120-second timeouts, and a
question that times out never calls a tool, so it scores as a tool-selection
failure. Excluding errored questions the figures are 12/13 and 7/9, and
genuine wrong-tool choices were 1 and 2 rather than 4 and 9.

The general rule this establishes: **any metric defined over "did the model do
X" is depressed by errors, because a model that produced nothing did not do
X.** Fabrication rate and tool selection are both such metrics. Compare them
only across rows with comparable error counts, or adjust first.

Note which figures did *not* move: fabrication was exactly 3/23 in both runs,
and advice-declining exactly 3/7. The conclusions the project draws from this
table are the stable ones.

### Comparing three approaches to grounding

| approach | cost | catches | misses |
|---|---|---|---|
| Prompt instructions alone | Free | Nothing reliably | Everything, when the model is small enough. Demonstrated twice here |
| Post-hoc verification (this project) | ~20 lines | Any citation when retrieval never ran | Fabricated citations *after* a real retrieval call; wrong numbers |
| Constrained generation: build the citation block from tool results, never from model text | More plumbing, less fluent output | Fabricated citations entirely, by construction | Nothing in this category, because the model never writes the citation |

The third is strictly stronger and was not implemented. It is the honest
recommendation for future work: if the citation block is assembled from
`search_evidence`'s return value rather than from the model's prose, a
fabricated citation stops being possible rather than merely being detected.

---

### Checking that evidence exists is not checking what it says (3 Oct 2026)

A review of the guards found that they verified the *presence* of a search,
not the *content* of the answer. Once the model had called `search_evidence`,
even a search that returned nothing, any quote it wrote passed: the check
asked "was there a search?", never "did the search return this text?". The
number check had the same shape of weakness. It compared absolute values, so
a trend delta of −0.05 written as "+0.05" passed. It accepted a fraction 0.12
written as "0.12%". And it let a figure match any ratio of any two numbers in
the tool output, which on one recorded trend answer accepted 85 to 95 of the
whole percentages from 1% to 99%. A check that accepts almost everything is
not a check.

The fixes compare content: a quote must appear in text a tool returned, a
signed figure must have the right sign, a percentage must come from a
fraction × 100 or a percentage field, and ratios pair only the counts inside
one result. Strip mode also stopped keeping the opening paragraph untouched,
which had left one-paragraph answers with their invented quote under a note
saying it was removed.

**The lesson for evaluation:** measure a detector's *acceptance rate* on
invented inputs, not only its catch rate on recorded failures. The 2 Oct
result (citation warnings 11 → 0 with strip) survived the stronger checks
(8B 11 → 0, 3B 16 → 0), but only because those inventions all came from
answers that never searched; the old checks would not have caught an
invention after a search. Re-measured figures: `docs/evidence/chatbot-eval-build-2026-10-01.md`,
"Third round".

## 5. Evaluate

**Code-level enforcement was the right call, and the evidence is unusually
direct.** `phi4-mini` fabricated in 83% of answers while calling zero
tools, under a prompt that explicitly forbade exactly that. No amount of
prompt tightening addresses a model that ignores the prompt.

**What the evaluation does not show.** Three limits, stated plainly:

1. **Numerical fidelity is unmeasured.** Whether a number the model states
   matches what the tool returned is not automated. That was a deliberate
   choice — verifying a number by extracting it with another model is less
   trustworthy than the check itself — but it means "does the chatbot report
   correct numbers?" is currently unanswered.
2. **Citation *relevance* is unmeasured.** A real `sentence_id` cited in
   support of an unrelated claim passes every check here.
3. **Single runs.** Only the default model was run twice. The rest are one
   sample each.

**The weakest area is not fabrication.** Advice-declining sits at 3 of 7 at
best, on every model tested, and `advice-1` and `advice-2` fail universally.
For a tool that carries a not-financial-advice disclaimer, being unable to
decline "should I buy DBS?" more than half the time is the most serious
finding in the evaluation, and it is a prompt and design problem rather than a
model-choice one. It is also the one that would matter most if this were
deployed rather than graded.

**When detection beats prevention.** Constrained generation costs fluency: the
answer reads more like a form. For a system whose users are non-experts being
handed financial information, make that trade. For an internal
tool used by people who can sanity-check the output, detection may be enough.

---

## 6. Create

**Exercise (about ninety minutes).** Measure what the automated checks
deliberately skip: numerical fidelity.

```python
# .venv-plp/bin/python3
import json, re

PATH = "data/eval/chatbot_eval_results_llama3.2_3b.jsonl"
rows = [json.loads(l) for l in open(PATH)]

def numbers(text):
    # sentiment scores look like -0.0107; counts look like 29701
    return set(re.findall(r"-?\d+\.\d{2,4}", text or ""))

for r in rows:
    stated = numbers(r.get("answer"))
    # every number any tool actually returned in this conversation
    returned = set()
    for call in r.get("tool_calls", []):
        returned |= numbers(json.dumps(call.get("result")))
    invented = stated - returned
    if invented:
        print(f"[{r['id']}] states numbers no tool returned: {sorted(invented)}")
```

**Note on the data.** Until 2026-09-11 the transcript recorded each tool call's
`name` and `arguments` but dropped its `result`, even though the docs claimed
otherwise — which made exactly this exercise impossible. That is fixed, but
transcripts generated *before* the fix have no `result` key, so re-run the
evaluation first:

```bash
CHATBOT_BACKEND=ollama OLLAMA_MODEL=llama3.2:3b HF_HUB_OFFLINE=1 \
    .venv-plp/bin/python3 -m chatbot.run_eval --tag llama3.2_3b
```

**Expected outcome.** You will get false positives: percentages the model
computed from returned values, rounded figures, years. That is the point of
the exercise. Triage twenty of them by hand and classify each as *arithmetic
on real data*, *rounding*, or *genuinely invented*. Then answer the question
the automated suite could not: **on how many of the 23 questions does the
default model state a number that no tool produced and that cannot be derived
from one?**

Write the number and your triage method into the report. It is a
human-verified result, which beats another automated proxy, and
it fills the one gap `docs/STATUS.md` explicitly flags as outstanding human
work.

---

## 7. Self-check

1. Why is a fabricated citation detectable in code when a fabricated *number*
   largely is not?
2. `gemma3:4b` scored 0% fabrication. Why is that not a good result?
3. What did `phi4-mini` demonstrate that the other three models did not?
4. Fabrication drops from ~45% to 13% between 3B and 8B, while
   advice-declining stays at 3/7. What does that difference tell you about
   where to spend effort?
5. How would constrained generation make fabricated citations impossible
   rather than merely detectable?

<details>
<summary>Answers</summary>

1. Because whether `search_evidence` was called is an observable fact about
   the conversation, independent of the answer's content. If it was never
   called, any citation is fabricated by definition. A number, by contrast,
   requires comparing the answer's text against tool output, which means
   parsing free text — and doing that with another model is less reliable than
   the check itself.
2. It made zero tool calls because it has no Ollama tool-calling support; all
   23 questions errored and every answer was empty. There were no citations to
   fabricate, so the 0% measures absence of output, not grounding. A rate
   needs its error count beside it to be interpretable.
3. That a model can fabricate citations at a very high rate (83%) while
   calling no tools at all — answering purely from pre-training while
   producing text that looks sourced. It separates "retrieved and misquoted"
   from "never retrieved and invented wholesale", and shows prompt rules alone
   do not bind.
4. Fabrication is a capability limit that scale relieves, so it can be
   addressed by choosing a bigger model. Advice-declining is unchanged by
   scale, so it is a prompt and design problem and no model swap will fix it.
   Spend model budget on the first and design effort on the second.
5. By assembling the citation block programmatically from what
   `search_evidence` returned, rather than letting the model write citations
   in prose. If the model never emits a `sentence_id`, it cannot emit a false
   one.

</details>

---

## 8. Sources

**Repository**

- `chatbot/prompts.py` — the eight grounding rules, including rule 8
- `chatbot/agent.py` — citation verification and the two observed failure
  formats, documented in its module docstring
- `chatbot/tools.py` — `MIN_VOLUME_FOR_SCORE = 5`
- `chatbot/eval_gold_set.py`, `chatbot/run_eval.py`
- `docs/STATUS.md` — the evaluation table and its four readings
- `data/eval/chatbot_eval_results_*.jsonl` — transcripts
- `data/eval/model_comparison.log` — the run producing 0.435 for the default
  model, against 11/23 in the earlier untagged run

**Measured in this repository**

- All figures in section 4, from the evaluation runs of 2026-09-07 and
  2026-09-10. The 43–48% range is two runs of the same model, reconciled in
  `docs/verification-ledger.md`.

**Not verified**

- No external source is cited for the general claim that smaller models
  hallucinate more. The pattern here is measured on four models, one corpus,
  and 23 questions, which is a demonstration rather than a result that
  generalises.
- Whether the two fabrication runs differ for a systematic reason (model
  update, temperature, ordering) rather than sampling noise. Not investigated.
