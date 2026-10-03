"""
What a chatbot question is asking for, decided by a model rather than by word
lists (4 Oct 2026; replaces the regex input guards of 26 Sep).

A local model reads the question, with the conversation's bank, aspect and
previous question, and returns one intent from config/intents.yaml through
Ollama's structured output, as aspects/llm_classify.py does for aspects.
`in_scope` goes on to the chatbot model; every other intent gets the reviewed
reply from the same file, without the model. Definitions, examples and
replies live in the YAML, not here.

If the classifier can't answer (Ollama not running, a timeout, an answer
outside the list twice), the question goes on to the chatbot model, whose
system prompt still says to decline advice and unrelated questions, and the
turn records that no intent was found. Failing open keeps the chatbot usable;
the evaluation (chatbot/eval_intent.py) measures how often it would matter.

Settings: CHATBOT_INTENT_MODEL (default llama3.1:8b), CHATBOT_INTENT_THINK
("false" turns a reasoning model's thinking off), OLLAMA_BASE_URL.
"""

import functools
import json
import os

import requests
import yaml

from config.logging_config import get_logger
from ingest.base import detect_banks

logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "intents.yaml")
IN_SCOPE = "in_scope"
TIMEOUT_SECONDS = 60


@functools.cache
def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def intent_names() -> list[str]:
    return list(load_config()["intents"])


def default_model() -> str:
    return os.environ.get("CHATBOT_INTENT_MODEL") or "llama3.1:8b"


def _think_setting() -> bool | None:
    value = (os.environ.get("CHATBOT_INTENT_THINK") or "").strip().lower()
    return {"false": False, "true": True}.get(value)


def describe_context(state: dict | None, previous_question: str | None) -> str:
    """The conversation so far, as the classifier sees it: "" at the start."""
    parts = []
    banks = (state or {}).get("banks") or []
    if banks:
        parts.append("bank: " + ", ".join(banks))
    if (state or {}).get("aspect"):
        parts.append("aspect: " + state["aspect"].replace("_", " "))
    if previous_question:
        parts.append(f"previous question: {previous_question}")
    return "; ".join(parts)


def build_messages(question: str, context: str = "") -> list[dict]:
    """System instructions with every intent's definition, then the examples
    as user/assistant pairs, then the question."""
    cfg = load_config()
    lines = [cfg["instructions"].strip(), "", "Intents:"]
    lines += [f"- {name}: {spec['definition'].strip()}" for name, spec in cfg["intents"].items()]
    lines += ["", 'Answer with JSON: {"intent": "<one intent name>"}.']
    messages = [{"role": "system", "content": "\n".join(lines)}]

    def user(q: str, ctx: str) -> str:
        return (f"Conversation so far: {ctx}\n" if ctx else "") + f"Question: {q}"

    for ex in cfg["examples"]:
        messages.append({"role": "user", "content": user(ex["question"], ex.get("context", ""))})
        messages.append({"role": "assistant", "content": json.dumps({"intent": ex["intent"]})})
    messages.append({"role": "user", "content": user(question, context)})
    return messages


def ollama_chat(model: str, messages: list[dict], names: list[str]) -> str:
    """One deterministic call, its answer constrained to the intent names."""
    payload = {"model": model, "messages": messages, "stream": False,
               "format": {"type": "object", "properties": {"intent": {"type": "string", "enum": names}},
                          "required": ["intent"]},
               "options": {"temperature": 0}}
    think = _think_setting()
    if think is not None:
        payload["think"] = think
    url = os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
    resp = requests.post(f"{url}/api/chat", timeout=TIMEOUT_SECONDS, json=payload)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def classify_intent(question: str, state: dict | None = None, previous_question: str | None = None,
                    model: str | None = None, chat=None) -> str | None:
    """The question's intent, or None if the classifier couldn't give one
    (the caller then lets the question through: see the module docstring)."""
    chat = chat or ollama_chat          # looked up now, so tests can replace it
    names = intent_names()
    messages = build_messages(question, describe_context(state, previous_question))
    for _attempt in (1, 2):
        try:
            answer = json.loads(chat(model or default_model(), messages, names))["intent"]
        except (requests.RequestException, ValueError, KeyError, TypeError) as e:
            logger.warning("intent classifier unavailable (%s); the question goes to the model", e)
            return None
        if answer in names:
            return answer
    logger.warning("intent classifier answered outside the list twice; the question goes to the model")
    return None


def reply_for(intent: str | None, question: str, state: dict | None = None) -> str | None:
    """The reviewed reply for an intent the model shouldn't answer; None for
    in_scope, no intent, or an intent with no reply."""
    if not intent or intent == IN_SCOPE:
        return None
    cfg = load_config()
    template = cfg["replies"].get(intent)
    if template is None:
        return None
    banks = detect_banks(question) or list((state or {}).get("banks") or [])
    subject = " / ".join(banks) if banks else ("your bank" if intent == "service" else "these banks")
    context = ""
    if (state or {}).get("banks"):
        topic = " / ".join(state["banks"]) + (f" {state['aspect'].replace('_', ' ')}" if state.get("aspect") else "")
        context = cfg["replies"]["context"].format(topic=topic)
    examples = "For example:\n" + "\n".join(f'- "{q}"' for q in cfg["example_questions"])
    return template.format(subject=subject, covered=" / ".join(banks) if banks else "DBS, OCBC or UOB",
                           context=context, examples=examples, what_i_do=cfg["replies"]["what_i_do"].strip())
