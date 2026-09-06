"""
Backend selection for the chatbot.

Env vars (all optional):
  CHATBOT_BACKEND   "claude" or "ollama". If unset: auto-detects — uses
                    Claude if ANTHROPIC_API_KEY is set, otherwise falls back
                    to Ollama (local, no key needed). This exists specifically
                    so a lecturer with no API key still gets a working
                    chatbot by default, while anyone with a key gets the
                    frontier model without having to configure anything.
  CLAUDE_MODEL      default "claude-sonnet-5"
  OLLAMA_MODEL      default "llama3.2:3b" (verified tool-calling support —
                    see ollama_backend.py docstring for other tested options)
  OLLAMA_BASE_URL   default "http://localhost:11434"
"""

import os

from chatbot.backends.base import LLMBackend
from chatbot.backends.claude_backend import ClaudeBackend
from chatbot.backends.ollama_backend import DEFAULT_BASE_URL, DEFAULT_MODEL, OllamaBackend


def get_backend(name: str | None = None) -> LLMBackend:
    """Build the requested backend, or auto-detect one if name is None."""
    name = name or os.environ.get("CHATBOT_BACKEND")
    if name is None:
        name = "claude" if os.environ.get("ANTHROPIC_API_KEY") else "ollama"
    name = name.lower()

    if name == "claude":
        return ClaudeBackend(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5"),
        )
    if name == "ollama":
        return OllamaBackend(
            model=os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL),
        )
    raise ValueError(f"Unknown CHATBOT_BACKEND {name!r} — expected 'claude' or 'ollama'")
