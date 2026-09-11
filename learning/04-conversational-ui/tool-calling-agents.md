# Tool-calling agents

Subject: Conversational UI (module 4) · Bloom target: Analyze / Evaluate / Create
Prerequisites: none

---

## 1. Why it matters here (Understand)

The chatbot satisfies the course's conversational-UI requirement, and the
proposal asked for something *agentic* — able to call retrieval functions
rather than being a static prompt-and-response wrapper. That distinction is
the whole design.

A model asked "what is DBS's dividend sentiment?" without tools will answer
from what it learned in pre-training, which is a plausible-sounding number
about a real bank with no connection to this project's data. With tools it
must go and get the number. The agent loop is the mechanism that forces the
trip.

---

## 2. The concept (Understand / Apply)

### The loop

1. Send the user's question, the system prompt, and a list of **tool schemas**
   describing the available functions.
2. The model replies either with a final answer, or with one or more tool
   calls: a function name and arguments.
3. Execute the requested functions locally, append the results to the
   conversation.
4. Send the conversation back to the model.
5. Repeat from 2 until the model returns text instead of a tool call.

That is the entire pattern. In this codebase it is roughly fifty lines.

### Tool schemas

A tool schema tells the model what a function is called, what it does, and
what arguments it takes. This project has six:

| tool | arguments | returns |
|---|---|---|
| `get_sentiment` | `bank*`, `aspect` | Score with `n`, or `insufficient_data` |
| `compare_banks` | `aspect` | All three banks side by side |
| `get_trend` | `bank*`, `aspect` | Direction, delta, up to 12 monthly points |
| `get_coverage` | `bank`, `aspect` | `has_data` — no data versus neutral |
| `search_evidence` | `query*`, `bank`, `aspect`, `sentiment`, `k` | Sentences with `sentence_id` and `url` |
| `get_analyst_consensus` | `bank*` | Yahoo aggregates |

The descriptions are prompt engineering. A tool the model does not understand
is a tool it will not call, and the evaluation shows two of five models never
called one.

### Arguments are validated, not trusted

`aspect` values are checked against the real taxonomy in `config/aspects.yaml`.
If a model invents `interest_rates`, the call fails loudly instead of quietly
returning nothing. That distinction matters: an empty result reads to the
model like "no sentiment exists", which is a wrong answer it will happily
relay, whereas an error prompts a retry.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| The loop, and citation verification around it | `chatbot/agent.py` |
| Tool functions, schemas, argument coercion and validation | `chatbot/tools.py` |
| Backend abstraction and why each owns its own loop | `chatbot/backends/base.py` |
| Backends | `chatbot/backends/{ollama,claude,openai,gemini}_backend.py` |
| System prompt | `chatbot/prompts.py` |
| Evaluation | `chatbot/eval_gold_set.py`, `chatbot/run_eval.py` |

---

## 4. Analyze

### Why no framework

LangChain and similar would supply this loop. The project wrote it instead.

| consideration | framework | fifty lines |
|---|---|---|
| Time to first working version | Faster | Slower |
| Dependencies | Large, fast-moving | None beyond each provider's SDK |
| Explaining it in a report | Must explain the framework's abstractions too | Read the function |
| Debugging a wrong tool call | Through the framework's layers | Print statement |
| Swapping providers | Framework's abstraction, if it covers yours | Write a backend |

The decisive criterion for a graded project is the third: **the report has to
explain whatever is used.** A framework adds abstractions to describe without
adding capability at this scale. That reasoning would flip for a system with
twenty tools, multiple agents and streaming, where the framework's structure
starts paying for itself.

### Why each backend owns its whole loop

This looks like duplication and is not. The providers represent conversation
history differently:

| provider | assistant turn with tool calls | tool results |
|---|---|---|
| Claude | Content-block list mixing text and `tool_use` blocks | `tool_result` blocks in a user turn |
| Ollama / OpenAI | Message with a flat `tool_calls` array | One `role="tool"` message per result |

Forcing both through one shared loop would require an abstraction layer whose
only job is papering over that difference. For two shapes, the layer costs
more than it saves. Tool *schemas* stay in one place, in Anthropic's native
shape, and each backend converts them.

The judgement to notice: the thing worth centralising is the part that is
genuinely identical (the schemas), and the thing worth duplicating is the part
that only looks identical (the loop).

### What the evaluation revealed about tool calling

| model | called the expected tool | fabricated citations |
|---|---|---|
| `llama3.2:3b` | 12/16 | 43–48% |
| `llama3.1:8b` | 12/16 | 13% |
| `phi4-mini` | **0/16** | 83% |
| `gemma3:4b` | 0/16 (all errored, HTTP 400) | 0/23 — artifact |
| `qwen3:4b` | 0/16 (all errored, timeout) | 0/23 — artifact |

Three distinct failure modes, and separating them is the useful analysis:

1. **Cannot call tools at all.** `gemma3:4b` has no Ollama tool-calling
   support and returns HTTP 400. An infrastructure fact, not a model
   judgement.
2. **Too slow to complete the loop.** `qwen3:4b` emits a long hidden reasoning
   chain before answering; every call exceeded the 120-second timeout. The
   loop's multi-turn structure multiplies per-call latency, so a model that is
   merely slow in single-turn use becomes unusable here.
3. **Can call tools and does not.** `phi4-mini` supports tool calling and
   chose to answer from parametric knowledge in all 16 cases, while producing
   text that looked sourced. This is the dangerous one, because it fails
   silently and fluently.

**Scale did not help tool selection.** 3B and 8B both score 12/16, identical.
Whatever causes the four misses is not model capacity.

**But read that column carefully.** Re-running `llama3.1:8b` gave 7/16 rather
than 12/16, on the same questions with the same weights, because 8 questions
timed out and a question that times out never calls a tool. Excluding errored
questions the two runs give 12/13 and 7/9. **Tool selection is confounded with
the error rate**, so it is only comparable across models with similar error
counts. `phi4-mini`'s 0/16 with zero errors is the one figure in that column
that needs no adjustment at all, which is what makes it so damning.

### Which four, and what they say

Running the diagnosis in section 6 over `llama3.2:3b`'s transcript:

| question | expected | actually called |
|---|---|---|
| `lookup-2` "How is OCBC's asset quality being discussed?" | `get_sentiment` | nothing |
| `lookup-5` "How does the market feel about DBS's management guidance?" | `get_sentiment` | nothing |
| `trend-1` | `get_trend` | `get_sentiment` |
| `thin-1` | `get_sentiment` | `get_trend` |

Two clean groups, and neither looks like a capacity problem.

**Two questions produced no tool call at all**, and both are phrased
indirectly — "how is X being discussed", "how does the market feel about X" —
rather than as a request for a number. The directly-phrased lookups in the
same category succeeded. That points at question phrasing interacting with
tool descriptions, not at the model failing to understand the tools.

**Two questions swapped `get_sentiment` and `get_trend`, in opposite
directions.** That is the signature of an ambiguous boundary rather than a
mistake: if the model confused them one way only, you would suspect a bias in
one description; confusing them both ways says the descriptions do not draw a
clear line between "the current level" and "the change over time". Notably
`thin-1` is a thin-data question, where calling `get_trend` instead of
`get_sentiment` is arguably defensible.

That is a prompt-side problem with a cheap fix, which is consistent with both
model sizes failing identically.

---

## 5. Evaluate

**The plain loop was right on the report-explainability criterion**, and
the code is genuinely readable. The cost is real but small: four backends were
written by hand, and each is a place a provider change could break something.

**Per-backend loops were right for two shapes.** It is starting to strain
at four, since `openai` and `gemini` were written to documented contracts and
have never received a real response. If a fifth arrived, the balance would
shift toward a shared loop with adapters.

**What the evidence does not show.** The four failures are now identified
(section 4) and their *cause* is still inferred rather than demonstrated. The
pattern is consistent with unclear tool descriptions, and nobody has tested
that by rewriting the descriptions and re-running. Until someone does, "the
tool descriptions are the problem" is a hypothesis with supporting evidence,
not a finding.

**The uncomfortable finding.** Two of five local models cannot participate at
all, and a third participates without calling anything. The pluggable-backend
design is a genuine strength of the codebase and the pool of models that
actually work with it is much smaller than the pool that nominally supports
tool calling.

---

## 6. Create

**Exercise (about ninety minutes).** Diagnose the 4-of-16 tool selection
failures, which nobody has done.

```python
# .venv-plp/bin/python3
import json
from chatbot.eval_gold_set import GOLD_SET

expected_by_id = {g["id"]: g.get("expected_tool") for g in GOLD_SET}

for tag in ("llama3.2_3b", "llama3.1_8b"):
    path = f"data/eval/chatbot_eval_results_{tag}.jsonl"
    print(f"\n===== {tag}")
    for line in open(path):
        r = json.loads(line)
        chk = r.get("tool_selection_check") or {}
        if chk.get("applicable") and not chk.get("correct"):
            called = [c["name"] for c in r.get("tool_calls", [])]
            print(f"  [{r['id']}] {r['question']}")
            print(f"      expected: {expected_by_id.get(r['id'])}   "
                  f"called: {called or 'nothing'}")
```

Note that `tool_selection_check` records only `applicable` and `correct`, so
the expected tool has to come from the gold set itself — which is why the
script imports it rather than reading it from the transcript.

**Expected outcome.** For `llama3.2:3b` you should reproduce the four failures
in section 4. The first thing to check is whether `llama3.1:8b` fails on the
*same* four — both score 12/16, but that does not guarantee the same
questions, and if the sets differ the "ambiguous descriptions" explanation
weakens considerably.

Then classify each failure: (a) the question is genuinely ambiguous about
which tool applies, (b) the tool's schema description does not make its
purpose clear, or (c) the model called a reasonable alternative and the gold
set is too strict. `thin-1` is a good test of your own judgement here.

**Then act on it.** If most failures are (b), rewrite `get_sentiment`'s and
`get_trend`'s descriptions in `chatbot/tools.py` to draw a sharper line
between "the current level" and "the change over time", and re-run:

```bash
CHATBOT_BACKEND=ollama OLLAMA_MODEL=llama3.2:3b HF_HUB_OFFLINE=1 \
    .venv-plp/bin/python3 -m chatbot.run_eval --tag llama3.2_3b_newdesc
```

A measurable improvement from a prompt-side change, with before and after
numbers, is exactly the kind of result the report needs. Remember the
run-to-run noise from the fabrication figures: a move from 12/16 to 13/16 is
one question and is not evidence of anything. Run it twice.

---

## 7. Self-check

1. What makes an agent "agentic" rather than a prompt wrapper?
2. Why does each backend implement its own loop while the tool schemas are
   shared?
3. Why does an invalid `aspect` argument raise an error instead of returning
   an empty result?
4. Three models scored 0/16 on tool selection for three different reasons.
   Name them.
5. Both 3B and 8B score 12/16. What does that suggest about the cause of the
   four misses?

<details>
<summary>Answers</summary>

1. It can call tools and act on their results within a multi-turn loop, so its
   answer depends on data fetched at question time rather than only on the
   prompt and its parameters.
2. Because providers represent conversation history genuinely differently —
   Claude uses content-block lists, Ollama and OpenAI use a flat `tool_calls`
   array plus `role="tool"` messages — so a shared loop would need an
   abstraction layer purely to hide that. The schemas are genuinely identical,
   so they are shared.
3. Because an empty result reads to the model as "no sentiment exists for
   this", which it will report as an answer. An error is a signal that
   something went wrong and prompts a retry.
4. `gemma3:4b` has no Ollama tool-calling support and errors with HTTP 400.
   `qwen3:4b` supports it but is too slow, exceeding the 120-second timeout on
   every call. `phi4-mini` supports it and simply did not call anything,
   answering from parametric knowledge instead.
5. That the cause is not model capacity. Since a model more than twice the
   size fails on the same questions, the likely explanations are ambiguous
   questions, unclear tool descriptions, or an over-strict gold set — all
   cheaper to fix than a model swap.

</details>

---

## 8. Sources

**Repository**

- `chatbot/agent.py` — the loop and the tracker
- `chatbot/tools.py` — schemas, argument coercion, aspect validation
- `chatbot/backends/base.py` — the docstring explaining the per-backend loop
- `chatbot/prompts.py` — the eight grounding rules
- `docs/DESIGN.md` decisions 8 and 9
- `docs/STATUS.md` — the evaluation table

**Measured in this repository**

- Tool-selection and fabrication figures from the evaluation runs of
  2026-09-07, 2026-09-10 and 2026-09-11, recorded in `data/eval/`.

**Not verified**

- Why the four tool-selection failures occur. Counted, never diagnosed; the
  exercise in section 6 exists to close that gap.
- The Claude and OpenAI/Ollama message-shape descriptions come from this
  codebase's backend implementations rather than from provider documentation
  fetched during this pass. Check each provider's current docs before
  describing their APIs in the report.
- The OpenAI and Gemini backends have never received a real API response, so
  their message handling is written to documented contracts and is unverified
  in practice.
