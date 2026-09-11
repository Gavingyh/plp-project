# Chatbot evaluation: re-running the same model twice

Run 2026-09-11 (SGT). `llama3.1:8b` was evaluated a second time on the same
23-question gold set, to check whether its 3 errors in the first run were
transient.

```bash
CHATBOT_BACKEND=ollama OLLAMA_MODEL=llama3.1:8b HF_HUB_OFFLINE=1 \
    .venv-plp/bin/python3 -m chatbot.run_eval --tag llama3.1_8b_rerun
```

They were not transient, and answering the question turned up something more
useful than the answer.

---

## The two runs

| | run 1 (2026-09-10) | rerun (2026-09-11) |
|---|---|---|
| Errors | 3 | **8** |
| Tool selection | 12/16 | **7/16** |
| Advice-declining behaviour | 3/7 | 3/7 |
| Citation fabrication | 3/23 (13%) | 3/23 (13%) |

Two metrics identical, two apparently collapsed. Taken at face value this
would read as a model that got substantially worse at choosing tools, which
fixed weights cannot do.

## Every rerun error is a timeout

All 8 are `HTTPConnectionPool(host='localhost', port=11434): Read timed out.
(read timeout=120)`.

| run | errored question IDs |
|---|---|
| run 1 | `evidence-2`, `thin-1`, `trend-1` |
| rerun | `advice-3`, `compare-1`, `compare-3`, `evidence-2`, `lookup-1`, `lookup-3`, `trend-1`, `trend-2` |

**The rerun shared the machine with a full pytest run and other work.** That
is the most likely cause and it is this session's doing, not a property of the
model. The finding below survives regardless of cause.

## Tool selection is confounded with the error rate

A question that times out never calls a tool, so it is counted as a
tool-selection failure. Separating the two:

| | run 1 | rerun |
|---|---|---|
| Applicable questions | 16 | 16 |
| Reported correct | 12/16 | 7/16 |
| Of those, errored before any tool could be called | 3 | **7** |
| **Correct, excluding errored questions** | **12/13** | **7/9** |

The headline drop from 12/16 to 7/16 is almost entirely timeouts. On questions
the model actually got to answer, it scored 92% and 78% — still different, on
9 and 13 observations, which is well inside what two small samples do.

Genuine tool-selection failures, meaning the model answered and chose wrongly:

| run | genuine failures |
|---|---|
| run 1 | `lookup-2` |
| rerun | `evidence-1`, `thin-1` |

One and two. Not four and nine.

---

## What this means for the evaluation table

`docs/STATUS.md` already warns that citation-fabrication rates are only
meaningful alongside their error counts, because `gemma3:4b` and `qwen3:4b`
both score 0% by producing no output at all.

**The same confound applies to tool selection, and that was not previously
stated.** Any row with a non-zero error count has a tool-selection score
depressed by exactly those errors. Concretely:

- `llama3.2:3b` (0 errors) — 12/16 is a clean measurement.
- `phi4-mini` (0 errors) — 0/16 is a clean and damning measurement.
  It answered every question and called nothing.
- `gemma3:4b`, `qwen3:4b` (23 errors each) — 0/16 measures nothing at all.
- `llama3.1:8b` (3 or 8 errors) — **the reported figure is not comparable to
  the zero-error rows without adjustment.**

The table should carry error-adjusted tool selection, or readers should be
told to compute it. Reporting "llama3.1:8b selects tools worse than
llama3.2:3b" from 7/16 against 12/16 would be a straightforward error, and it
is the kind a report gets marked down for.

## What is stable across both runs

The useful half:

- **Citation fabrication: 3/23 in both runs.** Identical. Against
  `llama3.2:3b`'s 10–11/23 across its two runs, the gap between the two models
  is real and reproducible.
- **Advice-declining: 3/7 in both runs.** Also identical, and identical again
  to `llama3.2:3b`. Four measurements of the same number across two models
  strongly supports the standing conclusion that this is a prompt and design
  problem rather than a model-capacity one.

So the two conclusions the project actually draws from this table — scale cuts
fabrication, and advice-declining is a design failure — both survive. The
tool-selection column is the one that needs care.

## Recommendation

1. Re-run the full comparison on an otherwise idle machine before the report
   is written. Timings and error counts here are contaminated by concurrent
   work.
2. Report tool selection as *correct / applicable-and-answered*, not
   *correct / applicable*.
3. Raise the Ollama read timeout above 120 seconds for 8B models, or record
   the timeout alongside each run so the number is interpretable.
4. Keep reporting error counts beside every rate. Two models already produce
   meaningless 0% fabrication rates for unrelated reasons, and this run shows
   the same trap in a second column.
