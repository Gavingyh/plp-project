"""
Pluggable LLM backend for the chatbot's tool-calling loop.

Several backends exist so the chatbot runs without an API key (a local model)
as well as with one. Each backend owns its whole tool-calling loop rather
than sharing a generic one, because providers represent conversation history
differently (Claude: content-block lists on assistant and user turns;
Ollama and OpenAI: a flat tool_calls array plus one role="tool" message per
result), and a shared loop would need its own layer to hide that. Tool *schemas* stay in one
place (chatbot/tools.py's TOOL_SCHEMAS, Anthropic's native shape) and each
backend converts them to whatever it needs internally.
"""

from abc import ABC, abstractmethod
from typing import Callable

ToolExecutor = Callable[[str, dict], str]  # (tool_name, tool_input) -> JSON string result
History = list[dict]  # earlier turns: [{"role": "user" | "assistant", "content": str}, ...]

# Factual, grounded answers want near-greedy decoding (TPML Day 3 decoding guide:
# temperature 0.1-0.3 for factual QA). Ollama's own default is tuned for chat.
from chatbot import settings

DEFAULT_TEMPERATURE = settings.get("temperature")


class BackendUnavailable(RuntimeError):
    """The model service can't answer: not running, unreachable, a missing or
    rejected key, or an error status after retries. The API reports it as 503;
    anything else raised while answering is a bug, reported as 500."""


class LLMBackend(ABC):
    """One implementation per model provider. `ask()` runs the complete
    question -> [tool calls -> tool results]* -> final text answer loop."""

    name: str  # short identifier, e.g. "claude", "ollama" - used in logs/errors

    temperature: float = DEFAULT_TEMPERATURE

    @abstractmethod
    def ask(self, question: str, system: str, tool_schemas: list[dict],
             tool_executor: ToolExecutor, verbose: bool = True,
             history: History | None = None) -> str:
        """`history` holds earlier turns as plain text, oldest first. Tool calls
        from earlier turns are not replayed: the model re-fetches what it needs."""
        ...
