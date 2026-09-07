"""
OpenAI (GPT) backend — a second frontier-model option alongside Claude.

NOT LIVE-TESTED: no OPENAI_API_KEY is available in this dev environment
(same situation ClaudeBackend was originally built under — see its
docstring history). This is written from OpenAI's documented, long-stable
Chat Completions tool-calling contract rather than assumption-from-nothing,
but "documented" is not the same guarantee as "verified live" — the way
ollama_backend.py's contract was confirmed against a real running instance
before being trusted. If you add a key, run `python -m chatbot.agent
"..."` with CHATBOT_BACKEND=openai and treat the first real response as the
actual verification this module hasn't had yet.

Key contract detail that's easy to get wrong and IS specific to OpenAI
(Ollama's version of this API pre-parses it for you — see ollama_backend.py):
tool_calls[].function.arguments comes back as a **JSON-encoded string**,
not a dict. It must be json.loads()'d before use.

Default model (OPENAI_MODEL env var to override): gpt-4o-mini — cheap and
tool-calling capable as of when this was written; check for a newer/cheaper
option before relying on the default long-term, model naming moves fast.
"""

import json
import sys

import requests

from chatbot.backends._openai_compat import to_openai_function_tools
from config.logging_config import get_logger
from chatbot.backends.base import LLMBackend, ToolExecutor

logger = get_logger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"
MAX_TOOL_ITERATIONS = 8
_REQUEST_TIMEOUT = 60
_API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIBackend(LLMBackend):
    name = "openai"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Set it in .env to use GPT, or use CHATBOT_BACKEND=ollama "
                "for a free local model instead."
            )
        self._api_key = api_key
        self.model = model

    def _chat(self, messages: list[dict], tools: list[dict]) -> dict:
        try:
            resp = requests.post(
                _API_URL,
                headers={"Authorization": f"Bearer {self._api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages, "tools": tools},
                timeout=_REQUEST_TIMEOUT,
            )
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"Could not reach the OpenAI API: {e}") from e
        if resp.status_code == 401:
            raise RuntimeError("OpenAI API rejected the key (401) — check OPENAI_API_KEY.")
        resp.raise_for_status()
        return resp.json()

    def ask(self, question: str, system: str, tool_schemas: list[dict],
            tool_executor: ToolExecutor, verbose: bool = True) -> str:
        openai_tools = to_openai_function_tools(tool_schemas)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]

        for _ in range(MAX_TOOL_ITERATIONS):
            data = self._chat(messages, openai_tools)
            message = data["choices"][0]["message"]
            messages.append(message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return message.get("content") or ""

            for call in tool_calls:
                fn = call["function"]
                name = fn["name"]
                # Unlike Ollama, OpenAI sends arguments as a JSON STRING, not a dict.
                try:
                    arguments = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                if verbose:
                    logger.info("tool call: %s(%s)", name, arguments)
                result_json = tool_executor(name, arguments)
                messages.append({
                    "role": "tool", "tool_call_id": call["id"], "content": result_json,
                })

        return ("I wasn't able to reach a final answer within the tool-call budget — "
                "this usually means the question needs to be narrowed down.")
