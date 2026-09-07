"""
Ollama backend — runs entirely locally, no API key, no cost. Built for this
being a school project: a lecturer grading it should be able to run the
chatbot with nothing but `ollama serve` and a pulled model.

Tool-calling shape verified live against a running Ollama instance
(2026-09-07) before writing this, not assumed from docs:
  - request:  POST /api/chat with a `tools` array in OpenAI function-calling
    shape ({"type": "function", "function": {name, description, parameters}})
  - response: message.tool_calls[].function.{name, arguments} — arguments
    already parsed as a dict, not a JSON string (unlike OpenAI's own API)
  - a role="tool" message with the JSON result string sent back continues
    the conversation correctly

Models confirmed working (any Ollama model tagged for tool use should also
work): llama3.2:3b (~4s per tool call — recommended default) and qwen3:4b
(tool-calling works identically, but ~7x slower per call because it emits a
hidden `thinking` chain-of-thought field first — fine for accuracy-over-
speed use, not a snappy default).
"""

import sys

import requests

from chatbot.backends._openai_compat import to_openai_function_tools as _to_ollama_tools
from chatbot.backends.base import LLMBackend, ToolExecutor

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"
MAX_TOOL_ITERATIONS = 8
_REQUEST_TIMEOUT = 120  # local generation, esp. "thinking" models, can be slow on CPU


class OllamaBackend(LLMBackend):
    name = "ollama"

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _chat(self, messages: list[dict], tools: list[dict]) -> dict:
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "tools": tools, "stream": False},
                timeout=_REQUEST_TIMEOUT,
            )
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"Could not reach Ollama at {self.base_url}. Is it running? "
                f"Start it with `ollama serve` and make sure the model is pulled "
                f"(`ollama pull {self.model}`). Original error: {e}"
            ) from e
        if resp.status_code == 404:
            raise RuntimeError(
                f"Ollama returned 404 for model '{self.model}' — pull it first: "
                f"`ollama pull {self.model}`"
            )
        resp.raise_for_status()
        return resp.json()

    def ask(self, question: str, system: str, tool_schemas: list[dict],
            tool_executor: ToolExecutor, verbose: bool = True) -> str:
        ollama_tools = _to_ollama_tools(tool_schemas)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]

        for _ in range(MAX_TOOL_ITERATIONS):
            data = self._chat(messages, ollama_tools)
            message = data.get("message", {})
            messages.append(message)  # store exactly what Ollama returned — keeps shape consistent

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return message.get("content", "")

            for call in tool_calls:
                fn = call.get("function", {})
                name, arguments = fn.get("name"), fn.get("arguments", {})
                if verbose:
                    print(f"  [ollama tool call] {name}({arguments})", file=sys.stderr)
                result_json = tool_executor(name, arguments)
                messages.append({
                    "role": "tool",
                    "content": result_json,
                    **({"tool_call_id": call["id"]} if "id" in call else {}),
                })

        return ("I wasn't able to reach a final answer within the tool-call budget — "
                "this usually means the question needs to be narrowed down, or that this "
                "local model is struggling with multi-step tool use (try a larger model).")
