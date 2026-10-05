# How the chatbot was evaluated and improved

The loop that found the chatbot's failures and fixed them: run a frozen question set, read every automated flag by hand, find the cause, fix it in code, check the fix on the recorded answers, then run live again. The judge branch shows why an evaluator needs checking too. For the report's evaluation section. Evidence: `chatbot-eval-build-2026-10-01` (Live runs).

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
flowchart TB
  accTitle: Chatbot evaluation and improvement loop
  accDescr: A frozen gold set, multi-turn conversations and retrieval metrics are run on each local model, recording every tool call and result. The harness flags invented citations and unverified figures; each flag is read by hand against the tool data. The cause found was that every invented citation came from an answer that never searched. Fixes went into code, were replayed on the recorded answers, then run live. The LLM judge was checked against the known inventions and failed; asked to list unsupported quotes, sources and figures instead, the same model caught all of them.

  gold["Gold set v2 (32 questions) · 4 conversations<br/>retrieval Hit@K and MRR against human aspects<br/>chatbot.run_eval · chatbot.retrieval_eval"]
  run["Run each local model; record every<br/>tool call and its result"]
  flags["Harness flags: citations no search returned,<br/>figures no tool returned"]
  read["Every flag read against the tool data:<br/>25 of 26 real inventions"]
  cause["Cause: every invention came from an answer<br/>that never searched; the prompt rule was ignored"]
  fix["Fixed in code: strip evidence written without a search<br/>(a setting) · the scope check reads the conversation<br/>(an intent classifier since 4 Oct) · run a tool call written as text"]
  replay["Replay the fix on the recorded answers:<br/>citation warnings 11 to 0 (8B), 15 to 0 (3B)<br/>chatbot.replay"]
  live["Run live again: 0 of 32 on the 8B;<br/>conversations 9 of 9 on both models"]
  retr["Retrieval: a question as the query ranks at chance<br/>(MRR 0.217); the aspect's name 0.559 (a setting)"]
  judge["LLM judge scores faithfulness 1-3<br/>chatbot.judge"]
  jcheck["Checked against the known inventions:<br/>scored all 32 answers 3, so not usable"]
  jnext["Asked to list every unsupported quote,<br/>source and figure (checklist prompt):<br/>catches all 25 known inventions, but its<br/>reasons are unreliable: it screens, not scores"]

  gold --> run --> flags --> read --> cause --> fix --> replay --> live
  gold --> retr
  run --> judge --> jcheck --> jnext
  live -. repeat .-> gold
```

Rendered for the report: [SVG](img/23-chatbot-improvement-loop.svg) · [PNG](img/23-chatbot-improvement-loop.png)

## What this shows and doesn't show

The order of work, and the principle that every automated check, including the judge, was checked by hand before it was trusted. Not shown: the human ratings and the user questionnaire, which are still to do (PLAN section 3).

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| gold set v2 | `chatbot/eval_gold_set.py:121` | `GOLD_SET_V2 = ` |
| conversations | `chatbot/run_eval.py:267` | `def run_multi_turn(` |
| random baseline for retrieval | `chatbot/retrieval_eval.py:53` | `def random_baseline(` |
| citation flag | `chatbot/agent.py:669` | `def answer_has_unverified_citation(self, answer: str) -> bool:` |
| strip evidence written without a search | `chatbot/agent.py:837` | `def strip_unsearched_evidence(answer: str) -> str:` |
| scope check reads the conversation | `chatbot/intent.py:59` | `def describe_context(state` |
| tool call written as text | `chatbot/backends/_text_tool_call.py:19` | `def text_tool_call(content: str, tool_names: set[str])` |
| replay on recorded answers | `chatbot/replay.py:28` | `def replay(results: list[dict], mode: str) -> list[dict]:` |
| judge checked against the flags | `chatbot/judge.py:203` | `def against_checks(results: list[dict], judged: pd.DataFrame) -> pd.DataFrame:` |
| checklist judge | `chatbot/judge.py:134` | `def checklist_score(parsed: dict) -> tuple[int, str]:` |
