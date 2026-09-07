"""
Backend selection for the chatbot.

Env vars (all optional):
  CHATBOT_BACKEND   "claude", "openai", "gemini", or "ollama". If unset:
                    auto-detects by checking for API keys in that order
                    (ANTHROPIC_API_KEY, then OPENAI_API_KEY, then
                    GEMINI_API_KEY), falling back to Ollama (local, no key
                    needed) if none are set. This exists specifically so a
                    lecturer with no API key still gets a working chatbot by
                    default, while anyone with a key gets a frontier model
                    without having to configure anything.
  CLAUDE_MODEL      default "claude-sonnet-5"
  OPENAI_MODEL      default "gpt-4o-mini" (NOT live-tested — see
                    openai_backend.py docstring)
  GEMINI_MODEL      default "gemini-2.0-flash" (NOT live-tested, and carries
                    more real risk than the OpenAI backend — see
                    gemini_backend.py docstring)
  OLLAMA_MODEL      default "llama3.2:3b" (verified tool-calling support —
                    see ollama_backend.py docstring for other tested options)
  OLLAMA_BASE_URL   default "http://localhost:11434"
"""

import os

from chatbot.backends.base import LLMBackend
from chatbot.backends.claude_backend import ClaudeBackend
from chatbot.backends.gemini_backend import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL
from chatbot.backends.gemini_backend import GeminiBackend
from chatbot.backends.ollama_backend import DEFAULT_BASE_URL, DEFAULT_MODEL, OllamaBackend
from chatbot.backends.openai_backend import DEFAULT_MODEL as OPENAI_DEFAULT_MODEL
from chatbot.backends.openai_backend import OpenAIBackend

_KEY_ENV_VAR_BY_BACKEND = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def _auto_detect() -> str:
    for backend_name, env_var in _KEY_ENV_VAR_BY_BACKEND.items():
        if os.environ.get(env_var):
            return backend_name
    return "ollama"


def get_backend(name: str | None = None) -> LLMBackend:
    """Build the requested backend, or auto-detect one if name is None."""
    name = (name or os.environ.get("CHATBOT_BACKEND") or _auto_detect()).lower()

    if name == "claude":
        return ClaudeBackend(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5"),
        )
    if name == "openai":
        return OpenAIBackend(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            model=os.environ.get("OPENAI_MODEL", OPENAI_DEFAULT_MODEL),
        )
    if name == "gemini":
        return GeminiBackend(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            model=os.environ.get("GEMINI_MODEL", GEMINI_DEFAULT_MODEL),
        )
    if name == "ollama":
        return OllamaBackend(
            model=os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL),
        )
    raise ValueError(
        f"Unknown CHATBOT_BACKEND {name!r} — expected 'claude', 'openai', 'gemini', or 'ollama'"
    )
