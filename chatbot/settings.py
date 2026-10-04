"""
The chatbot's settings, from config/chatbot.yaml: each setting's default, or
the environment variable the file names for it, which wins when set. One
place for what used to be literals spread across the backends, the agent,
the tools, the intent classifier and the judge.

  settings.get("models.ollama")           # "llama3.2:3b", or $OLLAMA_MODEL
  settings.get("timeouts_seconds.hosted") # 60
"""

import functools
import os

import yaml

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "chatbot.yaml")
_TRUE, _FALSE = {"1", "true", "yes", "on"}, {"0", "false", "no", "off"}


@functools.cache
def _load() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _spec(path: str) -> dict:
    node = _load()
    for part in path.split("."):
        node = node[part]
    if not isinstance(node, dict) or "value" not in node:
        raise KeyError(f"{path} is not a setting in {CONFIG_PATH}")
    return node


def _coerce(raw: str, default):
    """An environment string as the type of the default."""
    text = raw.strip()
    if isinstance(default, bool) or (default is None and text.lower() in _TRUE | _FALSE):
        if text.lower() in _TRUE:
            return True
        if text.lower() in _FALSE:
            return False
        return default
    if isinstance(default, int):
        return int(text)
    if isinstance(default, float):
        return float(text)
    if isinstance(default, list):
        return [type(default[0])(x) for x in text.replace(",", " ").split()] if default else text.split()
    return text


def get(path: str):
    """The setting at `path` (dots between levels): its environment variable
    if one is named and set, else its default. A malformed value in the
    environment falls back to the default."""
    spec = _spec(path)
    names = spec.get("env") or []
    for name in [names] if isinstance(names, str) else names:
        raw = os.environ.get(name)
        if raw not in (None, ""):
            try:
                return _coerce(raw, spec["value"])
            except ValueError:
                return spec["value"]
    return spec["value"]
