# Chatbot evaluation across Ollama, Groq and Gemini (2026-10-06)

## What was compared

The same questions, asked through the same chatbot code (tools, prompt, evidence checks), with only the answering model changed. The questions are the project's gold sets in `chatbot/eval_gold_set.py`. The intent classifier that decides whether a question is in scope is the local Ollama model in every arm.

| arm | model | free-tier budget used (requests per minute / per 24 hours) | requests sent | time spent answering |
|---|---|---|---|---|
| ollama | `OllamaBackend / llama3.1:8b` | local, no limit | n/a (local) | 7.9 minutes |
| groq | `OpenAIBackend / openai/gpt-oss-120b` | 20 / 700 | 128 | 68.6 minutes |
| gemini | `not run` | 8 / 200 | 0 | 0.0 minutes |

## Summary

- **ollama**: answered 61 of 61 single questions and 18 of 18 conversation turns. Right tool 25/27; declines and no-data replies 7/9; right input guard 28/29; 0 citations flagged; 2 answers with a figure no tool returned; 0 errors.
- **groq**: answered 61 of 61 single questions and 18 of 18 conversation turns. Right tool 27/27; declines and no-data replies 6/9; right input guard 28/29; 0 citations flagged; 5 answers with a figure no tool returned; 0 errors.
- **gemini**: not run (the provider rejected the key (HTTP 401); create a new one (aistudio.google.com/apikey) and update .env).

## Gold set (32 questions)

| arm | answered | errors | tool selection | behaviour (declines and no-data) | right input guard | citation flagged | answers with a figure no tool returned | answered by an input guard | no intent found | mean seconds |
|---|---|---|---|---|---|---|---|---|---|---|
| ollama | 32/32 | 0 | 23/24 | 7/8 | n/a | 0 | 2 | 6 | 0 | 7.7 |
| groq | 32/32 | 0 | 24/24 | 6/8 | n/a | 0 | 4 | 6 | 0 | 69.9 |
| gemini | 0/32 | 0 | n/a | n/a | n/a | 0 | 0 | 0 | 0 | n/a |

## Scope set (29 questions)

| arm | answered | errors | tool selection | behaviour (declines and no-data) | right input guard | citation flagged | answers with a figure no tool returned | answered by an input guard | no intent found | mean seconds |
|---|---|---|---|---|---|---|---|---|---|---|
| ollama | 29/29 | 0 | 2/3 | 0/1 | 28/29 | 0 | 0 | 22 | 0 | 3.9 |
| groq | 29/29 | 0 | 3/3 | 0/1 | 28/29 | 0 | 1 | 22 | 0 | 35.2 |
| gemini | 0/29 | 0 | n/a | n/a | n/a | 0 | 0 | 0 | 0 | n/a |

## Multi-turn conversations

| arm | set | turns correct | conversations with every turn correct | errors |
|---|---|---|---|---|
| ollama | Multi-turn conversations | 9/9 (of 9) | 4/4 (of 4) | 0 |
| ollama | Multi-turn scope conversations | 9/9 (of 9) | 3/3 (of 3) | 0 |
| groq | Multi-turn conversations | 9/9 (of 9) | 4/4 (of 4) | 0 |
| groq | Multi-turn scope conversations | 9/9 (of 9) | 3/3 (of 3) | 0 |
| gemini | Multi-turn conversations | 0/0 (of 9) | 0/0 (of 4) | 0 |
| gemini | Multi-turn scope conversations | 0/0 (of 9) | 0/0 (of 3) | 0 |

## Questions where the arms differ

A question is listed when the arms did not all pass or all fail it (over the checks that apply to it).

| set | question | category | ollama | groq | gemini |
|---|---|---|---|---|---|
| v2 | oos-2: How does the market feel about HSBC right now? | out_of_scope | pass | FAIL | not run |
| v2 | thin-1: What is UOB's sentiment on net interest margin in the last 7 days? | thin_data | FAIL | pass | not run |
| scope | ctrl-4: What can you tell me about UOB's dividends? | control | FAIL | pass | not run |

## How to read this

- **The checks are automatic and narrow.** They test that the right tool was called, that advice was declined, that no-data cases said so, and that no figure or quote appeared that no tool returned. They do not test that a stated number is right or that evidence is relevant; a person must read the answers in `data/eval/chatbot_eval_results_<arm>-<set>.jsonl` for that.
- **The arms do not see the same evidence.** The hosted models (Groq, Gemini) never receive text written by members of the public (Reddit), CNA articles or broker research; those quotes are replaced by a placeholder (`chatbot/backends/base.py`, decided 4 Oct 2026). The local Ollama model sees them. A hosted model can therefore look worse on questions that need those quotes, and its tool calls and figures are the fair comparison.
- **Free-tier limits shaped the run.** Requests were paced below the providers' published free limits (`rate_limits` in `config/chatbot.yaml`, `chatbot/ratelimit.py`) and a run that reached its budget stopped and can be resumed, not retried in a loop. 'Answered' above shows how far each arm got.
- **Seconds are not speed for the hosted arms.** Requests to Groq and Gemini are deliberately spread out to stay under their limits, so their seconds per question are mostly waiting. Only the local arm's time reflects how fast a model answers.
- **Sample sizes are small.** With 32 and 29 questions, a difference of one or two is inside what a different run of the same model can produce. Only repeated differences across sets mean much.

> **This report is incomplete.** At least one arm did not answer every question (see the 'answered' columns). Rerun `python -m chatbot.provider_eval --resume` when the provider's budget is back, then regenerate this report.

## Reproduce

```bash
python -m chatbot.provider_eval --dry-run      # what is ready, and the request budget, with no calls
python -m chatbot.provider_eval                # run every ready arm, resuming where one stopped
python -m chatbot.provider_report              # regenerate this file from the saved results
```

## Reading the answers (written 7 Oct 2026 from the transcripts)

These notes come from reading the saved answers in `data/eval/chatbot_eval_results_<arm>-<set>.jsonl`. They
are one person's reading of one run per model, so treat them as leads, not findings.

**Run status.** Ollama and Groq answered every question. Gemini was not run: the key in `.env` is rejected by
Google (HTTP 401), and it is 53 characters long without the `AIza` start that an AI Studio key has. Create a key at
aistudio.google.com/apikey, put it in `.env` as `GEMINI_API_KEY`, then run `python -m chatbot.provider_eval --arms gemini`.
Nothing about Gemini can be concluded from this report. No request hit a rate limit: Groq received 128 requests
for the evaluation (131 counting a 3-request check beforehand) against a budget of 700 in 24 hours, and no 429 was returned.

**The three questions where the arms differ**

- *oos-2 (HSBC), and oos-1 (Standard Chartered), mixed-1 (weather):* all three of Groq's missed decline checks are
  correct declines that the detector in `chatbot/eval_gold_set.py` did not recognise. oos-2: "I only have sentiment data for
  Singapore's three listed banks... I don't have market-feel information for HSBC". oos-1 is worded the same way. mixed-1:
  "I can't help with the weather", then the DBS answer. The detector looks for fixed phrases such as "don't have data" and
  "only cover", and Groq writes the apostrophe as a typographic one (don't). Normalising the apostrophe on the saved answers makes
  mixed-1 pass; oos-1 and oos-2 still miss because their wording is not in the phrase list. I have not changed the detector, because
  that would change a frozen check after seeing results; it is a decision for the team. Ollama passed oos-2 with "I have no data
  on HSBC." Ollama's two misses: oos-1 ("There isn't enough data to answer reliably.", a terse no-data reply the detector also
  missed) and mixed-1, where it answered the DBS part and said nothing about the weather, a real miss.
- *thin-1 and ctrl-4:* the local model (`llama3.1:8b`) did not call the tool. On thin-1 it gave a 7-day score for UOB with no
  tool call behind it; on ctrl-4 it wrote "I will call the get_sentiment tool" instead of calling it. Groq called the tool both times
  and answered with the returned figures. These are real differences in following the tool-use instructions, on two questions.

**Figures flagged as not returned by a tool.** Groq 5 answers, Ollama 2. The check is strict and a flagged figure still needs a
person to read it. In the Groq answers, several flagged values are small whole numbers or a thousands-separated number inside
a sentence the model composed (`24`, `11`, `10`, `49,700`), which may be counts or dates it restated rather than invented, and I did not
check each against its tool result. One Groq answer (trend-3) contains a stray tool tag, `functions.get_trend`, in the visible text,
which a user would notice.

**What this does and does not show.** On these 61 questions and 18 conversation turns, `gpt-oss-120b` on Groq used the right tool
on 27 of 27 checked questions against 25 of 27 for the local model, and both got 9 of 9 and 9 of 9 conversation turns right. The
decline-and-no-data check reads 7 of 9 for the local model and 6 of 9 for Groq, but on my reading of the answers all of
Groq's three misses are correct declines the detector did not recognise, so that figure understates Groq and the
detector, not the model, is the weak part. The hosted model never sees Reddit, CNA or broker-research text, so these tests (which mostly ask for scores and
trends) do not exercise the thing it cannot see. With this few questions and one run each, a gap of one or two is not a ranking.
