"""
Ollama backend - runs entirely locally, no API key, no cost. Built for this
being a school project: a lecturer grading it should be able to run the
chatbot with nothing but `ollama serve` and a pulled model.

Tool-calling contract, confirmed against a running Ollama instance rather
than taken from documentation:
  - request:  POST /api/chat with a `tools` array in OpenAI function-calling
    shape ({"type": "function", "function": {name, description, parameters}})
  - response: message.tool_calls[].function.{name, arguments} - arguments
    already parsed as a dict, not a JSON string (unlike OpenAI's own API)
  - a role="tool" message with the JSON result string sent back continues
    the conversation correctly

Models confirmed working (any Ollama model tagged for tool use should also
work): llama3.2:3b (~4s per tool call - recommended default) and qwen3:4b
(tool-calling works identically, but ~7x slower per call because it emits a
hidden `thinking` chain-of-thought field first - fine for accuracy-over-
speed use, not a snappy default). Set OLLAMA_THINK=false to turn the
thinking off; it is sent as Ollama's `think` field only when set.

A tool call the model writes out as text instead of making it is recognised
and run (chatbot/backends/_text_tool_call.py).
"""

import sys

import requests

from chatbot.backends._openai_compat import to_openai_function_tools as _to_ollama_tools
from chatbot.backends._text_tool_call import text_tool_call
from config.logging_config import get_logger
from chatbot.backends.base import BackendUnavailable, DEFAULT_TEMPERATURE, History, LLMBackend, ToolExecutor

logger = get_logger(__name__)

from chatbot import settings

DEFAULT_BASE_URL = settings.get("ollama_url")
DEFAULT_MODEL = settings.get("models.ollama")
MAX_TOOL_ITERATIONS = settings.get("max_tool_iterations")
_REQUEST_TIMEOUT = settings.get("timeouts_seconds.ollama")  # local generation can be slow on a CPU


class OllamaBackend(LLMBackend):
    name = "ollama"

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL,
                 temperature: float = DEFAULT_TEMPERATURE, think: bool | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.think = think

    def _chat(self, messages: list[dict], tools: list[dict]) -> dict:
        payload = {"model": self.model, "messages": messages, "tools": tools, "stream": False,
                   "options": {"temperature": self.temperature}}
        if self.think is not None:
            payload["think"] = self.think
        try:
            resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=_REQUEST_TIMEOUT)
        except requests.exceptions.ConnectionError as e:
            raise BackendUnavailable(
                f"Could not reach Ollama at {self.base_url}. Is it running? "
                f"Start it with `ollama serve` and make sure the model is pulled "
                f"(`ollama pull {self.model}`). Original error: {e}"
            ) from e
        if resp.status_code == 404:
            raise BackendUnavailable(
                f"Ollama returned 404 for model '{self.model}'; pull it first: "
                f"`ollama pull {self.model}`"
            )
        resp.raise_for_status()
        return resp.json()

    def ask(self, question: str, system: str, tool_schemas: list[dict],
            tool_executor: ToolExecutor, verbose: bool = True,
            history: History | None = None) -> str:
        ollama_tools = _to_ollama_tools(tool_schemas)
        tool_names = {t["name"] for t in tool_schemas}
        messages = ([{"role": "system", "content": system}] + list(history or [])
                    + [{"role": "user", "content": question}])

        for _ in range(MAX_TOOL_ITERATIONS):
            data = self._chat(messages, ollama_tools)
            message = data.get("message", {})
            messages.append(message)  # store exactly what Ollama returned - keeps shape consistent

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                written = text_tool_call(message.get("content", ""), tool_names)
                if written is None:
                    return message.get("content", "")
                # Written out instead of made: run it, and keep the history in
                # the shape a real call has.
                name, arguments = written
                logger.warning("%s wrote a %s call as text; running it", self.model, name)
                tool_calls = [{"function": {"name": name, "arguments": arguments}}]
                messages[-1] = {"role": "assistant", "content": "", "tool_calls": tool_calls}

            for call in tool_calls:
                fn = call.get("function", {})
                name, arguments = fn.get("name"), fn.get("arguments", {})
                if verbose:
                    logger.info("tool call: %s(%s)", name, arguments)
                result_json = tool_executor(name, arguments)
                messages.append({
                    "role": "tool",
                    "content": result_json,
                    **({"tool_call_id": call["id"]} if "id" in call else {}),
                })

        return ("I wasn't able to reach a final answer within the tool-call budget: "
                "this usually means the question needs to be narrowed down, or that this "
                "local model is struggling with multi-step tool use (try a larger model).")
