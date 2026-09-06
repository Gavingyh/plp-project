"""
Pluggable LLM backend for the chatbot's tool-calling loop.

WHY THIS EXISTS: this is a school project, and grading it shouldn't require
a lecturer to hold an ANTHROPIC_API_KEY. Each backend owns its FULL
tool-calling loop rather than sharing one generic loop, because Claude and
Ollama represent conversation history differently enough (Claude:
content-block lists on assistant/user turns; Ollama/OpenAI-style: a flat
tool_calls array plus one role="tool" message per result) that forcing them
through a single shared loop would need its own abstraction layer just to
paper over that — not worth it for two backends. Tool *schemas* stay in one
place (chatbot/tools.py's TOOL_SCHEMAS, Anthropic's native shape) and each
backend converts them to whatever it needs internally.
"""

from abc import ABC, abstractmethod
from typing import Callable

ToolExecutor = Callable[[str, dict], str]  # (tool_name, tool_input) -> JSON string result


class LLMBackend(ABC):
    """One implementation per model provider. `ask()` runs the complete
    question -> [tool calls -> tool results]* -> final text answer loop."""

    name: str  # short identifier, e.g. "claude", "ollama" — used in logs/errors

    @abstractmethod
    def ask(self, question: str, system: str, tool_schemas: list[dict],
             tool_executor: ToolExecutor, verbose: bool = True) -> str:
        ...
