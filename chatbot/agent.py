"""
Agentic chatbot — MVP plan Phase 8. A plain tool-calling loop against the
Claude API (see plan Phase 8, "Architecture" for why this is a ~50-line loop
rather than a framework like LangChain: at this scale a framework adds
abstraction without adding capability, and the report has to explain
whatever gets used).

REQUIRES: ANTHROPIC_API_KEY in .env — not set in this dev environment, so
this module has been built and its tool functions unit-tested (see
chatbot/tools.py, chatbot/retrieval.py) but the live agent loop itself has
not been run end-to-end. Set the key and run this file directly to try it.

USAGE:
  python -m chatbot.agent "How does the market feel about DBS's dividend policy?"
"""

import json
import os
import sys

from dotenv import load_dotenv

from chatbot.prompts import SYSTEM_PROMPT
from chatbot.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

MODEL = "claude-sonnet-5"
MAX_TOOL_ITERATIONS = 8  # safety cap so a confused loop can't run forever


def _execute_tool(name: str, tool_input: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        result = fn(**tool_input)
    except Exception as e:
        result = {"error": str(e)}
    return json.dumps(result, default=str)


def ask(question: str, verbose: bool = True) -> str:
    import anthropic  # imported here so importing this module doesn't require the package at load time

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set in .env. This chatbot calls the Claude API directly — "
            "see chatbot/agent.py module docstring."
        )
    client = anthropic.Anthropic(api_key=api_key)

    messages = [{"role": "user", "content": question}]

    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if not tool_calls:
            # No more tools requested — the text blocks are the final answer.
            return "".join(b.text for b in response.content if b.type == "text")

        tool_results = []
        for call in tool_calls:
            if verbose:
                print(f"  [tool call] {call.name}({call.input})", file=sys.stderr)
            result_json = _execute_tool(call.name, call.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": result_json,
            })
        messages.append({"role": "user", "content": tool_results})

    return ("I wasn't able to reach a final answer within the tool-call budget — "
            "this usually means the question needs to be narrowed down.")


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "How does the market feel about DBS's dividend policy?"
    print(f"Q: {question}\n")
    print(ask(question))
