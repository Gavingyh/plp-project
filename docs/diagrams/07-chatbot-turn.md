# Chatbot: one turn

Every path a question can take through the chatbot, including the points where code, not the model, decides the answer. For the report's conversational-UI section and for anyone changing the chatbot.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
flowchart TB
  accTitle: One chatbot turn
  accDescr: A local model sorts the question first; every intent except in-scope gets a fixed reply without the chatbot model, and a question the classifier can't sort goes on to the model. Otherwise the model calls tools in a loop of at most eight calls; its answer then passes an empty-answer check, a citation check (a quote mark the checks can't place counts as unretrieved evidence) and a figure check, and the citations it retrieved are numbered with their sources listed, before it is shown.

  q(["Question"])
  cls{"Intent classifier (local model):<br/>what is the question asking for?"}
  fixR["Fixed reply for that intent<br/>(config/intents.yaml)"]
  ctx["System prompt + conversation state<br/>+ last three turns"]
  llm["Model: final text<br/>or tool calls"]
  tc{"Tool calls?"}
  tools["Run the tools,<br/>record calls and results"]
  cap{"Eight model calls used?"}
  budget["Answer: couldn't finish<br/>within the budget"]
  emp{"Empty, or just braces?"}
  empR["Fixed reply: couldn't answer,<br/>with an example question"]
  cite{"Cites evidence it didn't retrieve?<br/>URL, quote or sentence id, or a quote<br/>mark the checks can't place"}
  w1["Append VERIFICATION WARNING"]
  num{"States a figure<br/>no tool returned?"}
  w2["Append NUMBER CHECK"]
  refs["Number the citations it retrieved,<br/>list their sources under the answer"]
  out(["Answer and turn record"])

  q --> cls
  cls -- "advice, another bank, small talk, help,<br/>service, injection, feedback, off-topic" --> fixR --> out
  cls -- "in scope, or no answer" --> ctx --> llm --> tc
  tc -- yes --> tools --> cap
  cap -- no --> llm
  cap -- yes --> budget --> emp
  tc -- no --> emp
  emp -- yes --> empR --> out
  emp -- no --> cite
  cite -- yes --> w1 --> num
  cite -- no --> num
  num -- yes --> w2 --> refs
  num -- no --> refs --> out
```

Rendered for the report: [SVG](img/07-chatbot-turn.svg) · [PNG](img/07-chatbot-turn.png)

## What this shows and doesn't show

The intent classifier is its own local model with fixed replies, and the three checks are
code, so they behave the same whichever chatbot model runs (`chatbot/intent.py`,
`chatbot/guards.py`, DESIGN decisions 19 and 24). If the classifier can't answer, the
question goes on to the model, whose prompt still says to decline advice and unrelated
questions. Everything between "System prompt" and
"Tool calls?" is the model's own behaviour. Warnings are appended, not substituted: a
flagged answer is still shown, with the warning under it. A double quote mark the checks can't
place (one that is no mark of a quote found, nor of a word in quote marks, an inch mark or a
stray mark) may belong to a quote they missed, so it counts as unretrieved evidence. With
`CHATBOT_ENFORCE_EVIDENCE` at strip, the default, each line holding such a mark is removed with
its citation, then the unretrieved quotes and links, before the citation check's warning is
decided, and stray numbered markers the model wrote are dropped after the checks
(`chatbot/agent.py`, `enforce_evidence`); the diagram shows the checks, not the removal. The eight-call cap is per
backend; Ollama's is shown and the others use the same value. Evaluation results for this
design are in `docs/evidence/chatbot-harness-2026-09-26.md`; the numbered sources and
the answers' wording, in `docs/evidence/chatbot-answers-2026-10-04.md`.

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| intent classifier runs first | `chatbot/agent.py:1065` | `intent = intents.classify_intent(question, state, previous)` |
| classifier | `chatbot/intent.py:106` | `def classify_intent(question: str` |
| fixed reply for the intent | `chatbot/intent.py:125` | `def reply_for(intent` |
| state and turns passed to the model | `chatbot/agent.py:1077` | `answer = backend.ask(question, with_state(SYSTEM_PROMPT, state)` |
| state added to the system prompt | `chatbot/prompts.py:84` | `def with_state(system: str` |
| last three turns | `config/chatbot.yaml:36` | `turns:        {value: 3}` |
| tool-call loop, eight calls | `config/chatbot.yaml:22` | `max_tool_iterations: {value: 8}` |
| loop | `chatbot/backends/ollama_backend.py:84` | `for _ in range(MAX_TOOL_ITERATIONS):` |
| tool calls? | `chatbot/backends/ollama_backend.py:89` | `tool_calls = message.get("tool_calls") or []` |
| run the tools | `chatbot/backends/ollama_backend.py:106` | `result_json = tool_executor(name, arguments)` |
| record calls and results | `chatbot/agent.py:670` | `def execute(self, name: str, tool_input: dict, by: str = "model")` |
| budget message | `chatbot/backends/ollama_backend.py:113` | `within the tool-call budget` |
| empty answer check | `chatbot/agent.py:1079` | `if not (answer or "").strip(` |
| empty answer replaced, checks skipped | `chatbot/agent.py:1082` | `return TurnResult(question=question, answer=EMPTY_ANSWER_REPLY` |
| citation check | `chatbot/agent.py:1086` | `enforced, flagged = enforce_evidence(answer, tracker, question, mode)` |
| sentence ids checked | `chatbot/agent.py:757` | `if unverified_sentence_ids(answer, self.known_ids()):` |
| a quote mark the checks can't place | `chatbot/agent.py:755` | `if _QUOTE_PATTERN.loose(answer):` |
| its line removed in strip mode | `chatbot/agent.py:891` | `cleaned = _without_loose_lines(text)` |
| figure check | `chatbot/agent.py:1112` | `figures = unverified_numbers(` |
| number warning appended | `chatbot/agent.py:1118` | `result.answer += UNVERIFIED_NUMBER_WARNING.format(` |
| citations numbered, sources listed | `chatbot/agent.py:1120` | `result.answer = number_citations(result.answer, tracker)` |
