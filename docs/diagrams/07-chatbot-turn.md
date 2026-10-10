# Chatbot: one turn

Every path a question can take through the chatbot, including the points where code, not the model, decides the answer. For the report's conversational-UI section and for anyone changing the chatbot.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
flowchart TB
  accTitle: One chatbot turn
  accDescr: A local model sorts the question first; every intent except in-scope gets a fixed reply without the chatbot model, and a question the classifier can't sort goes on to the model. Otherwise the model calls tools in a loop of at most eight calls; its answer then passes an empty-answer check, a citation check (quote marks around words no search returned count as unretrieved evidence) and a figure check, and the citations it retrieved are numbered with their sources listed, before it is shown.

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
  cite{"Cites evidence it didn't retrieve?<br/>URL, quote or sentence id, or quote<br/>marks around words no search returned"}
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
flagged answer is still shown, with the warning under it. Quote marks around words no search
returned count as unretrieved evidence, whatever shape they take, but for an inch mark, an
apostrophe and a word or two in quote marks that no citation vouches for; so does a citation,
or a link, that vouches for such words: a citation vouches for its own sentence, and for a word
or two in quote marks before it, or after it where it introduces the words after it. With
`CHATBOT_ENFORCE_EVIDENCE` at strip, the default, the quotes, links and sentence ids no search
returned are removed first, with their citations, and stray numbered markers the model wrote
are dropped; then the quote marks come off everything else no search returned, the words
staying, and each citation that would vouch for such words is cut (DESIGN decision 26), so the
citation check has nothing left to warn about (`chatbot/agent.py`, `enforce_evidence`). In
`off` mode the check flags exactly what strip mode would change. The diagram shows the
checks, not the removal. The eight-call cap is per
backend; Ollama's is shown and the others use the same value. Evaluation results for this
design are in `docs/evidence/chatbot-harness-2026-09-26.md`; the numbered sources and
the answers' wording, in `docs/evidence/chatbot-answers-2026-10-04.md`.

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| intent classifier runs first | `chatbot/agent.py:2161` | `intent = intents.classify_intent(question, state, previous)` |
| classifier | `chatbot/intent.py:108` | `def classify_intent(question: str` |
| fixed reply for the intent | `chatbot/intent.py:127` | `def reply_for(intent` |
| state and turns passed to the model | `chatbot/agent.py:2179` | `answer = backend.ask(question, with_state(SYSTEM_PROMPT, state)` |
| state added to the system prompt | `chatbot/prompts.py:84` | `def with_state(system: str` |
| last three turns | `config/chatbot.yaml:58` | `turns:        {value: 3}` |
| tool-call loop, eight calls | `config/chatbot.yaml:24` | `max_tool_iterations: {value: 8}` |
| loop | `chatbot/backends/ollama_backend.py:168` | `for _ in range(MAX_TOOL_ITERATIONS):` |
| tool calls? | `chatbot/backends/ollama_backend.py:174` | `tool_calls = message.get("tool_calls") or []` |
| run the tools | `chatbot/backends/ollama_backend.py:193` | `result_json = tool_executor(name, arguments)` |
| record calls and results | `chatbot/agent.py:788` | `def execute(self, name: str, tool_input: dict, by: str = "model")` |
| budget message | `chatbot/backends/ollama_backend.py:200` | `within the tool-call budget` |
| empty answer check | `chatbot/agent.py:2182` | `if not (answer or "").strip(` |
| empty answer replaced, checks skipped | `chatbot/agent.py:2186` | `return TurnResult(question=question, answer=EMPTY_ANSWER_REPLY` |
| citation check | `chatbot/agent.py:2190` | `enforced, flagged = enforce_evidence(answer, tracker, question, mode)` |
| sentence ids checked | `chatbot/agent.py:898` | `unverified_sentence_ids(answer, self.known_ids())` |
| quote marks around words no search returned | `chatbot/agent.py:937` | `return _demark(stripped, self, original=text) != _drop_bare_marks(text)` |
| marks taken off in strip mode | `chatbot/agent.py:2061` | `cleaned = _demark(text, tracker, original=answer)` |
| figure check | `chatbot/agent.py:2218` | `figures = unverified_numbers(` |
| number warning appended | `chatbot/agent.py:2224` | `result.answer += UNVERIFIED_NUMBER_WARNING.format(` |
| citations numbered, sources listed | `chatbot/agent.py:2226` | `result.answer = number_citations(result.answer, tracker)` |
