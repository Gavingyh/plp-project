"""
OpenAI (GPT) backend - a second frontier-model option alongside Claude, and
the way in for any OpenAI-compatible provider: set OPENAI_BASE_URL (default
https://api.openai.com/v1) to, say, https://api.groq.com/openai/v1, with that
provider's key in OPENAI_API_KEY and its model name in OPENAI_MODEL.

Not yet run against the live API: no OPENAI_API_KEY was available when
this was written. It implements OpenAI's documented Chat Completions
tool-calling contract, which is long-stable and widely used, but that is a
weaker guarantee than the Ollama backend has (whose contract was confirmed
against a running instance). With a key available, run
`CHATBOT_BACKEND=openai python -m chatbot.agent "..."` and treat the first
successful response as this module's verification.

Key contract detail that's easy to get wrong and IS specific to OpenAI
(Ollama's version of this API pre-parses it for you - see ollama_backend.py):
tool_calls[].function.arguments comes back as a **JSON-encoded string**,
not a dict. It must be json.loads()'d before use.

Default model (OPENAI_MODEL env var to override): gpt-4o-mini - cheap and
tool-calling capable as of when this was written; check for a newer/cheaper
option before relying on the default long-term, model naming moves fast.

Free tiers of compatible providers rate-limit hard (Groq's: 8,000 tokens a
minute when this was written), so a 429 or 503 is retried, after the provider's
Retry-After when it sends one. Only the standard fields of each assistant
message are sent back: reasoning models can return extra ones (a `reasoning`
field) that a provider need not accept as input.
"""

import json
import sys
import time

import requests

from chatbot.backends._openai_compat import to_openai_function_tools
from config.logging_config import get_logger
from chatbot.backends.base import (BackendUnavailable, DEFAULT_TEMPERATURE, History, LLMBackend, ToolExecutor,
                                   history_for_hosted, withheld_tool_result)

logger = get_logger(__name__)

from chatbot import ratelimit, settings

DEFAULT_MODEL = settings.get("models.openai")
MAX_TOOL_ITERATIONS = settings.get("max_tool_iterations")
_REQUEST_TIMEOUT = settings.get("timeouts_seconds.hosted")
DEFAULT_BASE_URL = settings.get("openai_base_url")
_RETRY_WAITS = tuple(settings.get("retry_waits_seconds.openai"))  # before each retry on 429 / 503, unless Retry-After says
_MAX_RETRY_AFTER = settings.get("max_retry_after_seconds")


class OpenAIBackend(LLMBackend):
    name = "openai"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL,
                 temperature: float = DEFAULT_TEMPERATURE, base_url: str | None = None):
        if not api_key:
            raise BackendUnavailable(
                "OPENAI_API_KEY not set. Set it in .env to use GPT, or use CHATBOT_BACKEND=ollama "
                "for a free local model instead."
            )
        self._api_key = api_key
        self.model = model
        self.temperature = temperature
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")

    def _chat(self, messages: list[dict], tools: list[dict]) -> dict:
        payload = {"model": self.model, "messages": messages, "tools": tools, "temperature": self.temperature}
        # Free tiers limit requests and tokens: every attempt, retries included, goes through the pacer.
        pacer = ratelimit.get_pacer(ratelimit.provider_for("openai", self.base_url))
        for attempt in range(len(_RETRY_WAITS) + 1):
            if pacer:
                pacer.before_request(ratelimit.estimate_tokens(payload))
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}",
                             "Content-Type": "application/json"},
                    json=payload,
                    timeout=_REQUEST_TIMEOUT,
                )
            except requests.exceptions.ConnectionError as e:
                raise BackendUnavailable(f"Could not reach {self.base_url}: {e}") from e
            final = resp.status_code not in (429, 503) or attempt == len(_RETRY_WAITS)
            if pacer:
                pacer.after_response(resp.status_code, getattr(resp, "headers", None), final=final)
            if final:
                break
            wait = _retry_wait(resp, _RETRY_WAITS[attempt])
            logger.warning("%s returned %s; retrying in %ss", self.model, resp.status_code, wait)
            time.sleep(wait)
        if resp.status_code == 401:
            raise BackendUnavailable(f"{self.base_url} rejected the key (401); check OPENAI_API_KEY.")
        if resp.status_code == 400:
            raise BackendUnavailable(f"{self.base_url} returned 400 (bad request): {resp.text[:500]}")
        resp.raise_for_status()
        return resp.json()

    def ask(self, question: str, system: str, tool_schemas: list[dict],
            tool_executor: ToolExecutor, verbose: bool = True,
            history: History | None = None) -> str:
        openai_tools = to_openai_function_tools(tool_schemas, nullable_optional=True)
        messages = ([{"role": "system", "content": system}] + history_for_hosted(history)
                    + [{"role": "user", "content": question}])

        for _ in range(MAX_TOOL_ITERATIONS):
            data = self._chat(messages, openai_tools)
            message = data["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            sent_back = {"role": "assistant", "content": message.get("content") or ""}
            if tool_calls:
                sent_back["tool_calls"] = tool_calls
            messages.append(sent_back)

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
                    "role": "tool", "tool_call_id": call["id"], "content": withheld_tool_result(name, result_json),
                })

        return ("I wasn't able to reach a final answer within the tool-call budget: "
                "this usually means the question needs to be narrowed down.")


def _retry_wait(resp, default: float) -> float:
    """The provider's Retry-After in seconds when it sends one, capped; else the default."""
    try:
        after = float((getattr(resp, "headers", None) or {}).get("retry-after"))
    except (TypeError, ValueError):
        return default
    return min(max(after, 1.0), _MAX_RETRY_AFTER)
