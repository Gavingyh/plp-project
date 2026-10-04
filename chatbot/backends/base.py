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

import json
from abc import ABC, abstractmethod
from typing import Callable

from config import sources

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


# What a hosted model may see (decided 4 Oct 2026 for every hosted backend:
# Gemini, Claude, OpenAI or Groq). Reddit evidence text (other people's posts),
# CNA text (which stays within the team) and text from a source the config
# doesn't list never leave this machine; free tiers may have their inputs read
# by people, and Reddit's developer policy restricts third-party use of its
# content. Enforced in each hosted backend, not left to the caller. The model
# still sees that the sentence exists, its bank, date, sentiment and id, and
# can't quote it: a quote it writes is then invented, and the citation check
# flags it. The local Ollama backend sends nothing off the machine.
WITHHELD = "[text by a member of the public (Reddit), withheld from the hosted model]"
WITHHELD_TEAM_ONLY = "[CNA text, kept within the team, withheld from the hosted model]"
WITHHELD_UNKNOWN = "[text from a source not cleared for the hosted model, withheld]"


def withhold_reddit(name: str, content):
    """A tool result as a hosted model may see it: evidence written by members
    of the public or kept within the team (config/sources.yaml, personal_text
    and team_only) without its text, link or citation. Evidence from a source
    the config doesn't list, or with no source, is withheld too."""
    if name != "search_evidence" or not isinstance(content, dict):
        return content
    personal, team_only, known = (sources.personal_text_sources(), sources.team_only_sources(),
                                  sources.weights().keys())
    items = []
    for item in content.get("results") or []:
        source = item.get("source")
        if source in personal or "reddit.com" in str(item.get("url") or ""):
            marker = WITHHELD
        elif source in team_only:
            marker = WITHHELD_TEAM_ONLY
        elif source not in known:
            marker = WITHHELD_UNKNOWN
        else:
            items.append(item)
            continue
        items.append({**item, "text": marker, "url": None, "cite_as": None})
    return {**content, "results": items}


def withheld_tool_result(name: str, result_json: str) -> str:
    """The JSON a hosted model receives for one tool call: `withhold_reddit`
    applied to the result the tools returned (the tracker keeps the original,
    so the citation check still sees everything)."""
    try:
        content = json.loads(result_json)
    except (TypeError, ValueError):
        return result_json                  # not JSON: an error message, no evidence in it
    return json.dumps(withhold_reddit(name, content), ensure_ascii=False)


EARLIER_ANSWER = "[an earlier answer, not shown: it may quote Reddit posts or CNA articles]"


def history_for_hosted(history: list | None) -> list:
    """Earlier turns with each earlier answer replaced by a placeholder: an
    answer may quote or paraphrase Reddit posts that another model, or the
    harness, retrieved, and picking quotes out of it missed cut, wrapped and
    nested ones (4 Oct 2026). The user's own questions stay, and the bank and
    aspect travel in the conversation state, so follow-ups still resolve."""
    return [{**h, "content": EARLIER_ANSWER} if h.get("role") == "assistant" else h for h in history or []]


history_for_gemini = history_for_hosted     # its name before the rule covered every hosted backend
