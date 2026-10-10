"""
Loading the local model before it is asked anything.

Ollama unloads a model a few minutes after its last request. The next
request then waits for the model to load before it answers, and on a Mac
short of memory that wait can pass the request's own time limit: on
10 Oct 2026 the intent classifier gave up after 60 s and the chatbot model
after 120 s, both while the model was still loading. Giving up closes the
connection, which makes Ollama abandon the load, so the next request starts
it again.

ensure_loaded asks Ollama which models are loaded and, if ours isn't, loads
it with a request of its own that has a longer limit. Every request then
names how long the model should stay loaded (keep_alive), so a pause between
questions doesn't unload it.

Settings in config/chatbot.yaml: ollama_keep_alive (OLLAMA_KEEP_ALIVE),
timeouts_seconds.ollama_load, ollama_url.
"""

import requests

from chatbot import settings
from config.logging_config import get_logger

logger = get_logger(__name__)

_PS_TIMEOUT = 5   # seconds; /api/ps answers at once or Ollama isn't there


def keep_alive() -> str:
    """How long Ollama keeps the model loaded after a request, as Ollama reads it ("30m")."""
    return str(settings.get("ollama_keep_alive"))


def is_loaded(model: str, base_url: str) -> bool:
    resp = requests.get(f"{base_url}/api/ps", timeout=_PS_TIMEOUT)
    resp.raise_for_status()
    return any(model in (m.get("name"), m.get("model")) for m in resp.json().get("models", []))


def ensure_loaded(model: str, base_url: str | None = None) -> bool:
    """Load `model` if Ollama doesn't hold it. True if it had to be loaded.

    Never raises: if Ollama can't be reached or the load fails, the request
    that follows reports it in its own words."""
    base_url = (base_url or settings.get("ollama_url")).rstrip("/")
    try:
        if is_loaded(model, base_url):
            return False
        logger.info("loading %s into Ollama (it was unloaded)", model)
        resp = requests.post(f"{base_url}/api/generate", json={"model": model, "keep_alive": keep_alive()},
                             timeout=settings.get("timeouts_seconds.ollama_load"))
        resp.raise_for_status()
        return True
    except (requests.RequestException, ValueError) as e:
        logger.warning("could not load %s into Ollama ahead of the request (%s)", model, e)
        return False
