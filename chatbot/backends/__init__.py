"""
Backend selection for the chatbot.

Settings, defaults and the environment variables that override them:
config/chatbot.yaml (backend, models, Ollama and OpenAI addresses,
temperature, thinking). The default backend is Ollama, the local demo
model: a key in .env no longer switches the chatbot to
a hosted model by itself. CHATBOT_BACKEND chooses another (claude, openai,
gemini), or `auto` restores the old behaviour: the first of
ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY that is set, else Ollama.
"""

import os

from chatbot import settings
from chatbot.backends.base import DEFAULT_TEMPERATURE, LLMBackend
from chatbot.backends.claude_backend import ClaudeBackend
from chatbot.backends.gemini_backend import GeminiBackend
from chatbot.backends.ollama_backend import OllamaBackend
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
        return float(settings.get("temperature"))
    except (TypeError, ValueError):
        return DEFAULT_TEMPERATURE


def _think() -> bool | None:
    """OLLAMA_THINK as a bool, or None (unset or unrecognised) for the model's default."""
    value = settings.get("ollama_think")
    return value if isinstance(value, bool) else None


def get_backend(name: str | None = None) -> LLMBackend:
    """Build the requested backend; with no name, the configured one (Ollama
    unless CHATBOT_BACKEND says otherwise; `auto` picks by the keys set)."""
    name = (name or settings.get("backend") or "ollama").lower()
    if name == "auto":
        name = _auto_detect()
    temperature = _temperature()

    if name == "claude":
        return ClaudeBackend(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=settings.get("models.claude"),
            temperature=temperature,
        )
    if name == "openai":
        return OpenAIBackend(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            model=settings.get("models.openai"),
            temperature=temperature,
            base_url=settings.get("openai_base_url"),
        )
    if name == "gemini":
        return GeminiBackend(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            # GEMINI_CHAT_MODEL is accepted too (config/chatbot.yaml): the key is
            # for the chatbot only, and that is the name the team's .env uses.
            model=settings.get("models.gemini"),
            temperature=temperature,
        )
    if name == "ollama":
        return OllamaBackend(
            model=settings.get("models.ollama"),
            base_url=settings.get("ollama_url"),
            temperature=temperature,
            think=_think(),
        )
    raise ValueError(
        f"Unknown CHATBOT_BACKEND {name!r}: expected 'claude', 'openai', 'gemini', or 'ollama'"
    )
