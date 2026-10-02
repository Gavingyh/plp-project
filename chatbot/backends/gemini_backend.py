"""
Gemini backend - a third frontier-model option alongside Claude and GPT.

Verified against the live API on 2026-09-30 with gemini-3.6-flash
(docs/evidence/gemini-backend-2026-09-30.md): tool calling and the
functionResponse continuation both work. It was written before any key was
available, and these were the risky parts:

  - Gemini's function-declaration `type` field is a proto enum serialized
    as an UPPERCASE string ("OBJECT", "STRING", "INTEGER"...), not
    JSON Schema's lowercase ("object", "string"). chatbot/tools.py's
    TOOL_SCHEMAS use lowercase throughout, so _to_gemini_tools() below
    recursively uppercases every "type" value. This is the single most
    likely thing to be wrong if this backend 400s on first real use.
  - The conversation-continuation shape for function results
    (a "functionResponse" part wrapped in a role="user" turn) is written
    from Google's documented pattern, but the exact required shape of the
    inner `response` object has shifted across API versions historically.

If you add a key: run with CHATBOT_BACKEND=gemini and treat the first real
response as the actual verification this module hasn't had. If it 400s,
the error body will usually say exactly which field is wrong - start there
before assuming the whole approach is broken.

Default model (GEMINI_MODEL, or GEMINI_CHAT_MODEL, to override):
gemini-3.8-flash, stable since 2026-09-02 with no shutdown date announced.
The previous default, gemini-2.0-flash, was shut down on 2026-06-01 (Google's
deprecations page), so check that page when this starts failing with 404.
"""

import json
import sys
import time

import requests

from config.logging_config import get_logger
from chatbot.backends.base import DEFAULT_TEMPERATURE, History, LLMBackend, ToolExecutor

logger = get_logger(__name__)

DEFAULT_MODEL = "gemini-3.8-flash"
MAX_TOOL_ITERATIONS = 8
_REQUEST_TIMEOUT = 60
_RETRY_WAITS = (2, 5, 15)   # seconds before each retry on 429 / 503
_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _uppercase_schema_types(node):
    """Recursively uppercases every JSON-Schema "type" value, to match
    Gemini's proto-enum convention (STRING/OBJECT/INTEGER/...). See module
    docstring - this is the single riskiest, most-likely-wrong conversion
    in this file."""
    if isinstance(node, dict):
        return {
            k: (v.upper() if k == "type" and isinstance(v, str) else _uppercase_schema_types(v))
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_uppercase_schema_types(item) for item in node]
    return node


def _to_gemini_tools(claude_tool_schemas: list[dict]) -> list[dict]:
    return [{
        "function_declarations": [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": _uppercase_schema_types(t["input_schema"]),
            }
            for t in claude_tool_schemas
        ]
    }]


class GeminiBackend(LLMBackend):
    name = "gemini"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL,
                 temperature: float = DEFAULT_TEMPERATURE):
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Set it in .env to use Gemini, or use "
                "CHATBOT_BACKEND=ollama for a free local model instead."
            )
        self._api_key = api_key
        self.model = model
        self.temperature = temperature

    def _generate(self, contents: list[dict], system: str, tools: list[dict]) -> dict:
        url = f"{_API_BASE}/{self.model}:generateContent"
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": tools,
            "generationConfig": {"temperature": self.temperature},
        }
        # 503 ("high demand") and 429 (rate limit) are routine on the free tier
        # and usually clear within seconds; a single one shouldn't lose the answer.
        for attempt in range(len(_RETRY_WAITS) + 1):
            try:
                # The key goes in a header, not the URL: requests puts the URL in
                # its error messages, and errors are logged to data/logs/plp.log.
                resp = requests.post(url, headers={"x-goog-api-key": self._api_key},
                                     json=payload, timeout=_REQUEST_TIMEOUT)
            except requests.exceptions.ConnectionError as e:
                raise RuntimeError(f"Could not reach the Gemini API: {e}") from e
            if resp.status_code not in (429, 503) or attempt == len(_RETRY_WAITS):
                break
            logger.warning("Gemini %s returned %s; retrying in %ss", self.model,
                           resp.status_code, _RETRY_WAITS[attempt])
            time.sleep(_RETRY_WAITS[attempt])
        if resp.status_code == 400:
            raise RuntimeError(
                f"Gemini API returned 400 (bad request); the error body usually names the "
                f"exact bad field, check it before assuming the whole approach is broken: "
                f"{resp.text[:500]}"
            )
        if resp.status_code == 401 or resp.status_code == 403:
            raise RuntimeError(f"Gemini API rejected the key ({resp.status_code}): "
                                f"check GEMINI_API_KEY.")
        resp.raise_for_status()
        return resp.json()

    def ask(self, question: str, system: str, tool_schemas: list[dict],
            tool_executor: ToolExecutor, verbose: bool = True,
            history: History | None = None) -> str:
        gemini_tools = _to_gemini_tools(tool_schemas)
        # Gemini names the assistant role "model".
        contents = [{"role": "model" if h["role"] == "assistant" else "user",
                     "parts": [{"text": h["content"]}]} for h in (history or [])]
        contents.append({"role": "user", "parts": [{"text": question}]})

        for _ in range(MAX_TOOL_ITERATIONS):
            data = self._generate(contents, system, gemini_tools)
            candidates = data.get("candidates") or []
            if not candidates:
                return "(Gemini returned no candidates, possibly blocked by a safety filter.)"

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            contents.append({"role": "model", "parts": parts})

            function_calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not function_calls:
                return "".join(p.get("text", "") for p in parts)

            response_parts = []
            for call in function_calls:
                name, arguments = call["name"], call.get("args", {})
                if verbose:
                    logger.info("tool call: %s(%s)", name, arguments)
                result_json = tool_executor(name, arguments)
                response_parts.append({
                    "functionResponse": {"name": name,
                                          "response": {"name": name,
                                                       "content": json.loads(result_json)}},
                })
            contents.append({"role": "user", "parts": response_parts})

        return ("I wasn't able to reach a final answer within the tool-call budget: "
                "this usually means the question needs to be narrowed down.")
