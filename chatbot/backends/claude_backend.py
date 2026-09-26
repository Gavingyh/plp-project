"""
Claude backend — the frontier-model option. Requires ANTHROPIC_API_KEY.

This is the original chatbot/agent.py loop, moved here unchanged when the
backend abstraction was introduced so a local model (see ollama_backend.py)
could be swapped in for school-project use without needing an API key.
"""

import sys

from config.logging_config import get_logger
from chatbot.backends.base import DEFAULT_TEMPERATURE, History, LLMBackend, ToolExecutor

logger = get_logger(__name__)

MAX_TOOL_ITERATIONS = 8  # safety cap so a confused loop can't run forever


class ClaudeBackend(LLMBackend):
    name = "claude"

    def __init__(self, api_key: str, model: str = "claude-sonnet-5",
                 temperature: float = DEFAULT_TEMPERATURE):
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Either set it in .env to use Claude, or use the "
                "local Ollama backend instead (see chatbot/backends/ollama_backend.py / README)."
            )
        self.model = model
        self._api_key = api_key
        self.temperature = temperature

    def ask(self, question: str, system: str, tool_schemas: list[dict],
            tool_executor: ToolExecutor, verbose: bool = True,
            history: History | None = None) -> str:
        import anthropic  # imported here so importing this module doesn't require the package at load time

        client = anthropic.Anthropic(api_key=self._api_key)
        messages = list(history or []) + [{"role": "user", "content": question}]

        for _ in range(MAX_TOOL_ITERATIONS):
            response = client.messages.create(
                model=self.model, max_tokens=1024, system=system, temperature=self.temperature,
                tools=tool_schemas, messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            tool_calls = [b for b in response.content if b.type == "tool_use"]
            if not tool_calls:
                return "".join(b.text for b in response.content if b.type == "text")

            tool_results = []
            for call in tool_calls:
                if verbose:
                    logger.info("tool call: %s(%s)", call.name, call.input)
                result_json = tool_executor(call.name, call.input)
                tool_results.append({
                    "type": "tool_result", "tool_use_id": call.id, "content": result_json,
                })
            messages.append({"role": "user", "content": tool_results})

        return ("I wasn't able to reach a final answer within the tool-call budget — "
                "this usually means the question needs to be narrowed down.")
