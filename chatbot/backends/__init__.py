"""
Backend selection for the chatbot.

Settings, defaults and the environment variables that override them:
config/chatbot.yaml (backend, models, Ollama and OpenAI addresses,
temperature, thinking). The default answer backend is OpenAI and requires
OPENAI_API_KEY. A missing key never changes the selected provider.
CHATBOT_BACKEND explicitly chooses another (claude, ollama),
or `auto` selects ANTHROPIC_API_KEY, then OPENAI_API_KEY, else Ollama.
"""

import os

from chatbot import settings
from chatbot.backends.base import DEFAULT_TEMPERATURE, LLMBackend
from chatbot.backends.claude_backend import ClaudeBackend
from chatbot.backends.ollama_backend import OllamaBackend
from chatbot.backends.openai_backend import OpenAIBackend

_KEY_ENV_VAR_BY_BACKEND = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _auto_detect() -> str:
    for backend_name, env_var in _KEY_ENV_VAR_BY_BACKEND.items():
        if os.environ.get(env_var, "").strip():
            return backend_name
    return "ollama"


def _temperature() -> float:
    """CHATBOT_TEMPERATURE, or the low default for grounded answers."""
    try:
        return float(settings.get("temperature"))
    except (TypeError, ValueError):
        return DEFAULT_TEMPERATURE


def _think() -> bool | None:
    """OLLAMA_THINK as a bool, or None (unset or unrecognised) for the model's default."""
    value = settings.get("ollama_think")
    return value if isinstance(value, bool) else None


def get_backend(name: str | None = None) -> LLMBackend:
    """Build the requested backend; with no name, the configured one (OpenAI
    unless CHATBOT_BACKEND says otherwise; `auto` picks by the keys set)."""
    name = (name or settings.get("backend") or "openai").strip().lower() or "openai"
    if name == "auto":
        name = _auto_detect()
    temperature = _temperature()

    if name == "claude":
        return ClaudeBackend(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            model=settings.get("models.claude"),
            temperature=temperature,
        )
    if name == "openai":
        return OpenAIBackend(
            api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            model=settings.get("models.openai"),
            temperature=temperature,
            base_url=settings.get("openai_base_url"),
        )
    if name == "ollama":
        return OllamaBackend(
            model=settings.get("models.ollama"),
            base_url=settings.get("ollama_url"),
            temperature=temperature,
            think=_think(),
        )
    raise ValueError(
        f"Unknown CHATBOT_BACKEND {name!r}: expected 'claude', 'openai', or 'ollama'"
    )
