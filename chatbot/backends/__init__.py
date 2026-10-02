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
  OPENAI_MODEL      default "gpt-4o-mini" (never run against the live API;
                    see openai_backend.py)
  OPENAI_BASE_URL   default "https://api.openai.com/v1"; any OpenAI-compatible
                    provider, e.g. "https://api.groq.com/openai/v1"
  GEMINI_MODEL      default "gemini-3.8-flash"; GEMINI_CHAT_MODEL also read
                    (verified against the live API on 2026-09-30; see
                    gemini_backend.py)
  OLLAMA_MODEL      default "llama3.2:3b" (verified tool-calling support -
                    see ollama_backend.py docstring for other tested options)
  OLLAMA_BASE_URL   default "http://localhost:11434"
  OLLAMA_THINK      "false" turns a reasoning model's thinking off (qwen3);
                    unset leaves the model's default
"""

import os

from chatbot.backends.base import DEFAULT_TEMPERATURE, LLMBackend
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


def _temperature() -> float:
    """CHATBOT_TEMPERATURE, or the low default for grounded answers."""
    try:
        return float(os.environ.get("CHATBOT_TEMPERATURE", DEFAULT_TEMPERATURE))
    except ValueError:
        return DEFAULT_TEMPERATURE


def _think() -> bool | None:
    """OLLAMA_THINK as a bool, or None (unset or unrecognised) for the model's default."""
    value = (os.environ.get("OLLAMA_THINK") or "").strip().lower()
    return {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}.get(value)


def get_backend(name: str | None = None) -> LLMBackend:
    """Build the requested backend, or auto-detect one if name is None."""
    name = (name or os.environ.get("CHATBOT_BACKEND") or _auto_detect()).lower()
    temperature = _temperature()

    if name == "claude":
        return ClaudeBackend(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-5"),
            temperature=temperature,
        )
    if name == "openai":
        return OpenAIBackend(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            model=os.environ.get("OPENAI_MODEL", OPENAI_DEFAULT_MODEL),
            temperature=temperature,
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
        )
    if name == "gemini":
        return GeminiBackend(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            # GEMINI_CHAT_MODEL is accepted too: the key is for the chatbot only,
            # and that is the name the team's .env uses.
            model=(os.environ.get("GEMINI_MODEL") or os.environ.get("GEMINI_CHAT_MODEL")
                   or GEMINI_DEFAULT_MODEL),
            temperature=temperature,
        )
    if name == "ollama":
        return OllamaBackend(
            model=os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL),
            temperature=temperature,
            think=_think(),
        )
    raise ValueError(
        f"Unknown CHATBOT_BACKEND {name!r}: expected 'claude', 'openai', 'gemini', or 'ollama'"
    )
