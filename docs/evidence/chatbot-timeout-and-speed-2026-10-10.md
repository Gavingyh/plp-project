# The chatbot's time-out, and where its time goes (2026-10-10)

On 10 Oct 2026 the dashboard's Ask page answered a question with "The chatbot
backend could not be reached: HTTPConnectionPool(host='localhost',
port=11434): Read timed out. (read timeout=120)". This note records the
cause, the fix, and what was measured about speed the same evening. Machine:
the MacBook Air (M1, 16 GB), Ollama 0.32.1, `llama3.1:8b`. Nothing was
written to the database.

## The time-out

`data/logs/plp.log` has the first half of it: at 22:06:44 the intent
classifier gave up after its 60 seconds ("Read timed out. (read
timeout=60)") and passed the question on; the chatbot model then gave up
after its 120 seconds. Ollama was running throughout, and at 22:51 it held
no model: it unloads a model five minutes after its last request, and the
dashboard had been open since 6 Oct.

So both requests were waiting for the model to load. Two things made that
fatal:

- **A request that gives up cancels the load.** Checked directly: with the
  model unloaded, a request cut off after 1 second left Ollama with no model
  loaded 2, 8 and 20 seconds later. The intent classifier's time-out
  therefore threw away 60 seconds of loading, and the chatbot's request
  started again from nothing.
- **The Mac was short of memory.** At the first check 5,984 MB of 7,168 MB
  of swap was in use. With memory free the same load took 4.8 seconds.

### What changed

| change | where |
|---|---|
| Before the first request of a question, ask Ollama which models are loaded; if ours isn't, load it with a request of its own that may take 300 seconds | `chatbot/ollama_load.py`, called from `chatbot/intent.py` and the Ollama backend |
| Every request asks Ollama to keep the model for 30 minutes (`OLLAMA_KEEP_ALIVE`), so a pause between questions doesn't unload it | `config/chatbot.yaml` |
| The answer is read as Ollama writes it, so 120 seconds is now the longest silence allowed, not the longest answer | `chatbot/backends/ollama_backend.py` |
| A time-out says the model is slow and the computer is probably short of memory, instead of suggesting Ollama isn't running | the same file |

The second and third matter because the model's speed is not steady (next
section): one request took 68.9 seconds that evening, and an answer twice as
long would have passed 120 seconds while still being written.

Tests: `tests/test_ollama_load.py` (29 tests, none reaching Ollama). The
dashboard has to be restarted to pick the change up. Its own wording around
the error ("check that `ollama serve` is running") is the dashboard owner's
to change.

## Where the time goes

Five questions, each in a fresh conversation, timed request by request
(`data/run/speed/chat_timing.py`, results in
`data/run/speed/timing-2026-10-10.json`, on this Mac only), 23:00 to 23:03:

| question | seconds | reading the prompt | writing |
|---|---|---|---|
| What is the overall sentiment on DBS? | 55.2 | 9.9 + 20.6 + 3.4 | 8, 23 and 148 tokens in 15.5 s |
| How do people feel about OCBC's wealth management business? | 25.0 | 0.4 + 10.5 + 2.4 | 8, 26 and 86 tokens in 10.9 s |
| Compare the banks on dividends. | 42.0 | 0.3 + 12.9 + 5.9 | 8, 20 and 150 tokens in 21.3 s |
| Is sentiment on UOB's retail banking improving? | 61.5 | 0.6 + 19.4 + 12.5 | 8, 30 and 102 tokens in 27.5 s |
| What do people say about DBS's app? | 104.6 | 0.9 + 24.4 + 21.0 | 8, 26 and 249 tokens in 53.4 s |

Each question is three requests: the intent classifier, the model choosing a
tool, and the model writing the answer. The first question also loaded the
model (5.1 s) and read both prompts for the first time.

Two things stand out.

**The model slowed down by half during the run.** Its first answer was
written at 11.4 tokens a second (148 in 13.0 s) and its last at 5.2 (249 in
47.6 s); reading the same tool-choosing prompt of about 2,120 tokens went
from 10.5 to 24.4 seconds. Swap in use rose from 7,170 MB before the run to
8,052 MB after it, and `pmset -g therm` recorded no thermal warning, so this
is memory pressure from the other programs open on the Mac, not the chatbot's
code. A later single request wrote at 2.7 tokens a second (152 in 56.6 s).
The 7 Oct note that a question takes 25 to 85 seconds is the same effect.

**The tool descriptions are read again for every question.** The
instructions and a question are 1,156 tokens; with the six tools passed to
Ollama they are 2,123, so the tools are 967 tokens. `llama3.1`'s template
(`ollama show llama3.1:8b --template`) writes the tools inside the newest
question, after everything that changes between questions, so Ollama's
prompt cache never covers them: 10 seconds a question when the Mac is quiet,
20 when it is not.

## Tool descriptions at the start of the instructions: tried, left off

`ollama_tools_in_system` (`OLLAMA_TOOLS_IN_SYSTEM=true`) writes the tool
descriptions at the start of the instructions, where they are read once and
cached, and reads the model's tool calls from its text. Without Ollama's own
handling the model carried on after a call into an invented answer (113 and
160 tokens, 25 and 32 seconds, in two of three questions tried), so reading
now stops as soon as words follow a complete call.

Gold set v2 (32 questions) both ways, one after the other, 23:14 to 23:51:

| | tools in the instructions | tools passed to Ollama (as now) |
|---|---|---|
| right tool | 22 of 24 | 23 of 24 |
| declines and no-data replies | 8 of 8 | 8 of 8 |
| citations flagged | 0 | 0 |
| answers with a figure no tool returned | 1 | 0 |
| answers with unsearched evidence removed | 5 | 4 |
| seconds, the 26 questions the model answered: median | 36.8 | 41.3 |
| the same: mean | 42.9 | 42.3 |
| all 32 questions, minutes | 18.8 | 18.5 |

It was faster on 16 of the 26 questions and no faster on average. The
comparison is rough: the first run shared the Mac with the test suite for
about three minutes, and the model's speed drifts as shown above. On the
checks it was no better: one more wrong tool choice, and for the Standard
Chartered question (out of scope) it called no tool and wrote four figures
no tool had returned, which the number check flagged. One run each, so
neither difference is established.

The setting therefore stays off. It is worth one more run on a Mac with
nothing else open before turning it on; the expected gain is the 967 tokens,
about 10 seconds a question.

Results: `data/eval/chatbot_eval_results_tools-in-system-2026-10-10.jsonl`,
`chatbot_eval_results_tools-native-2026-10-10.jsonl` and their summaries.
The 6 Oct provider evaluation's 7.7 seconds a question for the same model
(`chatbot_eval_results_ollama-v2.jsonl`) was not measured under these
conditions; the machine was not recorded.

## What would make it faster

1. **Free memory before a demo.** Close Teams, Chrome tabs and other heavy
   programs; this alone was worth a factor of two that evening.
2. The cached tool descriptions, once checked on a quiet machine.
3. A smaller model, which the team decided against on 4 Oct for its answers.

Not available without redesign: showing the answer as it is written. The
evidence check has to see the whole answer before any of it is shown.
