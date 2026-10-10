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

Speed and time limits (10 Oct 2026):
  - Before the first request of a question the model is loaded if Ollama has
    unloaded it (chatbot/ollama_load.py), so that a slow load doesn't use up
    the request's time limit.
  - The answer is read as Ollama writes it (`stream`), so the time limit is
    the longest silence allowed, not the longest answer: a long answer on a
    slow machine no longer times out while it is still being written.
  - With ollama_tools_in_system (config/chatbot.yaml), the tool descriptions
    are written at the start of the instructions instead of being passed as
    `tools`. llama3.1's template puts `tools` inside the newest question, so
    the model reads all of them again for every question (967 tokens, 10 to
    20 seconds on the M1); at the start of the instructions they are read
    once and Ollama's prompt cache keeps them. The model then writes each
    call as JSON text, which is read the same way as a call written out by
    mistake. Ollama no longer stops the model after a call, and it was seen
    to carry on into an invented answer (113 and 160 tokens, 25 to 32
    seconds), so reading stops as soon as words follow a complete call.
    Off by default: on the gold set of 10 Oct it was no faster on average
    and no better on the checks
    (docs/evidence/chatbot-timeout-and-speed-2026-10-10.md).
"""

import json
import sys

import requests

from chatbot.backends._openai_compat import to_openai_function_tools as _to_ollama_tools
from chatbot.backends._text_tool_call import text_tool_call, text_tool_calls, writing_past_its_calls
from config.logging_config import get_logger
from chatbot.backends.base import BackendUnavailable, DEFAULT_TEMPERATURE, History, LLMBackend, ToolExecutor

logger = get_logger(__name__)

from chatbot import ollama_load, settings

DEFAULT_BASE_URL = settings.get("ollama_url")
DEFAULT_MODEL = settings.get("models.ollama")
MAX_TOOL_ITERATIONS = settings.get("max_tool_iterations")
_REQUEST_TIMEOUT = settings.get("timeouts_seconds.ollama")  # the longest silence allowed, see _chat
_CONNECT_TIMEOUT = 10

# The words llama3.1's own template puts around `tools` (ollama show llama3.1:8b
# --template), kept so the model is asked for a call in the wording it was
# checked with; only their place changes.
_TOOLS_INTRO = (
    "You are a helpful assistant with tool calling capabilities.\n\n"
    "Given the following functions, please respond with a JSON for a function call with its proper "
    "arguments that best answers the given prompt.\n\n"
    'Respond in the format {"name": function name, "parameters": dictionary of argument name and its value}. '
    "Do not use variables.\n\n"
)
_TOOLS_OUTRO = ("\n\nWhen you receive a tool call response, use the output to format an answer to the "
                "original user question.")


def tools_block(ollama_tools: list[dict]) -> str:
    """The tool descriptions as text for the start of the instructions."""
    listed = "\n".join(json.dumps(t, separators=(",", ":")) for t in ollama_tools)
    return _TOOLS_INTRO + listed + _TOOLS_OUTRO


class OllamaBackend(LLMBackend):
    name = "ollama"

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL,
                 temperature: float = DEFAULT_TEMPERATURE, think: bool | None = None,
                 tools_in_system: bool | None = None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.think = think
        self.tools_in_system = (settings.get("ollama_tools_in_system") if tools_in_system is None
                                else tools_in_system)

    def _slow(self, e: Exception) -> BackendUnavailable:
        return BackendUnavailable(
            f"Ollama is running at {self.base_url} but '{self.model}' went silent for "
            f"{_REQUEST_TIMEOUT} seconds. This usually means the computer is short of memory: "
            f"close other heavy programs, make sure no other model job is running, then ask again. "
            f"Original error: {e}"
        )

    def _chat(self, messages: list[dict], tools: list[dict], written_calls: set[str] | None = None) -> dict:
        """One request, read as it is written. Returns Ollama's last line (its
        timings) with the whole message put together. With `written_calls`
        (the tool names, when calls come as text), reading stops once the
        model writes on past a complete call."""
        payload = {"model": self.model, "messages": messages, "stream": True,
                   "keep_alive": ollama_load.keep_alive(), "options": {"temperature": self.temperature}}
        if tools:
            payload["tools"] = tools
        if self.think is not None:
            payload["think"] = self.think
        content, tool_calls, last = [], [], {}
        try:
            resp = requests.post(f"{self.base_url}/api/chat", json=payload, stream=True,
                                 timeout=(_CONNECT_TIMEOUT, _REQUEST_TIMEOUT))
            if resp.status_code == 404:
                raise BackendUnavailable(
                    f"Ollama returned 404 for model '{self.model}'; pull it first: "
                    f"`ollama pull {self.model}`"
                )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                last = json.loads(line)
                message = last.get("message") or {}
                content.append(message.get("content") or "")
                tool_calls.extend(message.get("tool_calls") or [])
                if written_calls and writing_past_its_calls("".join(content), written_calls):
                    resp.close()                    # Ollama stops writing when the reader leaves
                    break
        except requests.exceptions.Timeout as e:
            raise self._slow(e) from e
        except requests.exceptions.ConnectionError as e:
            if "timed out" in str(e).lower():       # a silence while the answer was being read arrives as this
                raise self._slow(e) from e
            raise BackendUnavailable(
                f"Could not reach Ollama at {self.base_url}. Is it running? "
                f"Start it with `ollama serve` and make sure the model is pulled "
                f"(`ollama pull {self.model}`). Original error: {e}"
            ) from e
        message = {"role": "assistant", "content": "".join(content)}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return {**last, "message": message}

    def ask(self, question: str, system: str, tool_schemas: list[dict],
            tool_executor: ToolExecutor, verbose: bool = True,
            history: History | None = None) -> str:
        ollama_tools = _to_ollama_tools(tool_schemas)
        tool_names = {t["name"] for t in tool_schemas}
        ollama_load.ensure_loaded(self.model, self.base_url)
        in_system = bool(self.tools_in_system and ollama_tools)
        if in_system:
            # Before the instructions, whose last lines change with the
            # conversation: what is cached must come before anything that varies.
            system = tools_block(ollama_tools) + "\n\n" + system
        messages = ([{"role": "system", "content": system}] + list(history or [])
                    + [{"role": "user", "content": question}])

        for _ in range(MAX_TOOL_ITERATIONS):
            data = (self._chat(messages, [], written_calls=tool_names) if in_system
                    else self._chat(messages, ollama_tools))
            message = data.get("message", {})
            messages.append(message)  # store exactly what Ollama returned - keeps shape consistent

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                content = message.get("content", "")
                written = (text_tool_calls(content, tool_names) if in_system
                           else [c for c in [text_tool_call(content, tool_names)] if c])
                if not written:
                    return content
                # Written out instead of made: run it, and keep the history in
                # the shape a real call has.
                if not in_system:
                    logger.warning("%s wrote a %s call as text; running it", self.model, written[0][0])
                tool_calls = [{"function": {"name": name, "arguments": arguments}} for name, arguments in written]
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
