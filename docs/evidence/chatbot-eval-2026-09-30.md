# Chatbot evaluation on the rebuilt 10-aspect database

The 23-question gold set (`chatbot/eval_gold_set.py`) re-run on 2026-10-01
against the database as rebuilt on 30 Sep (10-aspect taxonomy, corrected
index), on both local models. Evidence for PLAN decision O3, the demo model;
it doesn't make that decision.

```bash
OLLAMA_MODEL=llama3.2:3b HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m chatbot.run_eval --backend ollama --tag llama3.2_3b_10aspects_2026-09-30
OLLAMA_MODEL=llama3.1:8b HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m chatbot.run_eval --backend ollama --tag llama3.1_8b_10aspects_2026-09-30
```

Transcripts and summaries: `data/eval/chatbot_eval_{results,summary}_llama3.{2_3b,1_8b}_10aspects_2026-09-30.*`.
Decoding temperature 0.2 (the default). Local models only: the Gemini key is
for the live chatbot, and its free tier may review inputs, while the gold set
includes evidence questions that return Reddit text. Runtime on this MacBook
Air: 3B 8 minutes, 8B 14 minutes.

## Automated checks

| | 3B, 26 Sep (4 aspects) | **3B, tonight** | 8B, 11 Sep (pre-harness) | **8B, tonight** |
|---|---|---|---|---|
| advice and out-of-scope handled | 7 / 7 | **7 / 7** | 3 / 7 | **7 / 7** |
| answered by an input guard | 7 / 23 | **7 / 23** | — | **7 / 23** |
| correct tool chosen | 12 / 16 | **12 / 16** | 12 / 16 and 7 / 16 (two runs) | **13 / 16** |
| citation warning fired | 11 / 23 (48%) | **10 / 23 (43%)** | 3 / 23 (13%) | **4 / 23 (17%)** |
| answers with a figure no tool returned | 8 / 23 | **8 / 23** | not checked | **3 / 23** |
| backend errors | 0 | **0** | 3 and 8 (two runs) | **0** |

26 Sep: `docs/evidence/chatbot-harness-2026-09-26.md` (final column). 11 Sep
8B: `docs/STATUS.md`, chatbot evaluation table (before the harness existed,
so no guards and no figure check; its tool-selection score is confounded by
the backend errors, as STATUS explains).

## Every flagged answer, read by hand

For each answer with a citation warning or an unverified figure, the figures
were checked against that question's raw tool results in the transcript.

**3B.** 22 figures flagged in 8 answers, **all invented**: 17 fake sentence
ids (1234, 5678, 12345, 67890, 123456, 789012, 987654, 111111), two numbers
inside invented quotes ("10 consecutive years", "since 1967"), and a
made-up class breakdown (25.9% positive, 81.7% neutral, 2.4% negative, which
sums to 110%; the tool returned counts). Of 10 citation warnings, 9 are real
inventions (quotes, sentence ids and Bloomberg, Reuters, Straits Times or
Yahoo URLs that no tool returned) and 1 is a false alarm: consensus-1 quoted
the tool's own fields (`"target_mean": 78.14118`, `"implied_upside_pct": 0.9`,
`"buy"`), all exactly as returned, and the check reads any quoted text as a
claimed evidence quote.

**8B.** 7 figures flagged in 3 answers, **all invented**: a "Bloomberg"
quote guiding a 5% to 7% ROE, a 40% payout ratio and a 4.5% yield in invented
quotes, and fake sentence ids 12345 and 67890. Of 4 citation warnings, 3 are
real inventions; the fourth (lookup-2) is a failed answer: the model wrote a
tool call out as text (`{"name": "get_sentiment", ...}`) instead of making
it, and the warning fired on the JSON's quote marks.

The 8B's three tool-selection misses: lookup-2 (the call written as text),
thin-1 (no tool called), evidence-1 (`search_evidence` without the bank).

## What this shows

- **Rebuilding the database changed nothing for the 3B model**: every
  figure matches its 26 Sep run within one question. The harness still
  handles all seven advice and scope questions without the model.
- **The 8B model invents far less**: 3 real invented-citation answers and 3
  answers with invented figures, against 9 and 8 for the 3B, one more
  correct tool, and no backend errors this time (3 and 8 on 11 Sep).
  Its inventions are of the same kind (fake quotes and ids), so the checks
  are still needed; they caught every one here.
- **The checks' false alarms are rare and specific**: 2 of the 14 citation
  warnings across both models claimed no evidence (one quoted tool output
  verbatim, one was a tool call written out as text); no figure flag was a
  false alarm tonight.

## Limits

- The gold set asks about four aspects (dividend policy, asset quality, NIM,
  management guidance). Questions on the six new aspects are untested.
- 23 questions, one run per model: differences of one or two questions are
  noise. The planned frozen ~30-question set, retrieval metrics and an LLM
  judge (PLAN section 3) would say more.
- Tool-selection scores count only the 16 questions that have an expected
  tool.
