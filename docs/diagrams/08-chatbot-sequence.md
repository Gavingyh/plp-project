# Chatbot: one turn from a chat client

Which component calls which, in order, when someone asks a question in the terminal chat (`chatbot/chat.py`); `POST /chat` runs the same turn ([13](13-api-chat.md)). For the report's system-design section and for debugging a turn.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
sequenceDiagram
  accTitle: Chatbot sequence from a chat client
  accDescr: The chat client hands the question to the conversation, which asks a local intent classifier first, then runs the model's tool loop against the database, then the output checks, and updates its state.

  actor user as Investor
  participant ui as Chat client (terminal chat)
  participant conv as Conversation
  participant turn as answer_turn
  participant ic as Intent classifier (local model)
  participant g as chatbot.guards (output checks)
  participant be as Backend (Ollama)
  participant llm as Language model
  participant tools as Tools
  participant db as plp.db and embeddings

  user->>ui: types a question
  ui->>conv: ask(question)
  conv->>turn: question, last three turns, state
  turn->>ic: question, state, previous question
  ic-->>turn: one intent (none if unavailable)
  alt any intent but in scope
    turn->>turn: fixed reply from config/intents.yaml
  else in scope, or no intent
    turn->>be: question, system prompt with state, tools, history
    loop until a final answer, at most eight model calls
      be->>llm: messages, tool schemas, temperature 0.2
      llm-->>be: tool calls, or final text
      opt tool calls
        be->>tools: execute(name, arguments)
        tools->>db: SELECT index rows, sentences, embeddings
        db-->>tools: rows
        tools-->>be: JSON result, recorded for the checks
      end
    end
    be-->>turn: answer text
    turn->>g: cited ids and figures against recorded results
    g-->>turn: anything unverified
  end
  turn-->>conv: TurnResult, with any warnings
  conv->>conv: update state from the tool calls, keep the turn
  conv-->>ui: answer
  ui-->>user: shows the answer
```

Rendered for the report: [SVG](img/08-chatbot-sequence.svg) · [PNG](img/08-chatbot-sequence.png)

## What this shows and doesn't show

The REST API follows the same path from `Conversation` onwards, rebuilding the
conversation from the `history` the client sends ([13](13-api-chat.md)). With a
hosted-model key, the backend calls that service instead of Ollama; the loop is the same.
The intent classifier is a separate Ollama call (`chatbot/intent.py`), made whichever
backend answers. The citation check that runs alongside the figure check lives in the
tool-call tracker in `chatbot/agent.py`. The model's own reasoning between calls is not shown.

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| chat client hands over the question | `chatbot/chat.py:77` | `last = conv.ask(q)` |
| Conversation.ask | `chatbot/agent.py:2323` | `def ask(self, question: str, verbose: bool = False, on_step=None)` |
| last three turns and state | `chatbot/agent.py:2325` | `r = answer_turn(question, backend_name=self.backend_name, history=self.history(),` |
| intent classifier first | `chatbot/agent.py:2161` | `intent = intents.classify_intent(question, state, previous)` |
| fixed reply | `chatbot/agent.py:2162` | `reply = intents.reply_for(intent, question, state)` |
| backend chosen | `chatbot/agent.py:2172` | `backend = backend or get_backend(backend_name)` |
| model call | `chatbot/backends/ollama_backend.py:170` | `self._chat(messages, ollama_tools)` |
| temperature sent | `chatbot/backends/ollama_backend.py:114` | `"options": {"temperature": self.temperature}` |
| tool executed and recorded | `chatbot/agent.py:793` | `result = fn(**coerce_tool_arguments(name, tool_input))` |
| tools read the database | `chatbot/tools.py:76` | `def get_sentiment(bank: str` |
| evidence search uses embeddings | `chatbot/retrieval.py:149` | `query_vec = embed_sentences([rank_text])[0]` |
| figures checked against results | `chatbot/agent.py:2218` | `figures = unverified_numbers(` |
| state updated | `chatbot/agent.py:2327` | `self._update_state(r)` |
| turn kept | `chatbot/agent.py:2328` | `self.turns.append(r)` |
