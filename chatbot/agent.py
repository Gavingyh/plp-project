"""
Agentic chatbot: a tool-calling loop over the sentiment store.

The loop is deliberately plain rather than framework-based (LangChain and
similar). At this scale a framework adds abstraction without adding
capability, and the project report has to be able to explain whatever is
used.

The model backend is pluggable — a local model via Ollama (no API key, no
cost) or a hosted model (Claude, GPT, Gemini). Backend selection is
described in chatbot/backends/__init__.py. The local option exists so the
chatbot can be run and graded without anyone needing to hold an API key.

CITATION VERIFICATION
Small local models fabricate supporting evidence. Observed failure modes
include fully-invented source URLs and sentence_ids, and placeholder-style
citations ("Sentence_id: [insert sentence_id]") that a URL-matching check
alone would not catch. Prompt instructions alone did not prevent either.

This module therefore enforces the invariant in code: if search_evidence was
never called, any quoted evidence, sentence_id reference or URL in the
answer is fabricated by definition, and the answer is flagged. This is the
same approach used for the volume floor in chatbot/tools.py — grounding
rules that matter are enforced rather than requested.

USAGE:
  python -m chatbot.agent "How does the market feel about DBS's dividend policy?"
  CHATBOT_BACKEND=ollama python -m chatbot.agent "..."   # force local
  CHATBOT_BACKEND=claude python -m chatbot.agent "..."   # force hosted
"""

import json
import os
import re
import sys

from dotenv import load_dotenv

from chatbot.backends import get_backend
from config.logging_config import get_logger, setup_logging
from chatbot.prompts import SYSTEM_PROMPT
from chatbot.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, coerce_tool_arguments

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

logger = get_logger(__name__)

_URL_PATTERN = re.compile(r"https?://[^\s)\]}\"']+")
_QUOTE_PATTERN = re.compile(r'"[^"]{10,}"')          # a purported verbatim quote
_SENTENCE_ID_PATTERN = re.compile(r"sentence[_\s]?id", re.IGNORECASE)

UNVERIFIED_CITATION_WARNING = (
    "\n\n⚠️ VERIFICATION WARNING: this response appears to cite evidence "
    "(a quote, sentence_id, or URL) that was not returned by any search_evidence call in "
    "this conversation. Treat any quoted evidence above as UNVERIFIED — it may be fabricated. "
    "(Seen from smaller local models; see chatbot/agent.py docstring.)"
)


class _ToolCallTracker:
    """Records what search_evidence actually returned, so the final answer can
    be checked against what was truly retrieved — not what the model claims.
    Also keeps a general call log (every tool, its arguments, and its result),
    used by chatbot/eval_gold_set.py to check whether the model called the
    tool a question actually calls for."""

    def __init__(self):
        self.search_evidence_called = False
        self.verified_urls: set[str] = set()
        self.calls: list[dict] = []

    def execute(self, name: str, tool_input: dict) -> str:
        fn = TOOL_FUNCTIONS.get(name)
        if fn is None:
            return json.dumps({"error": f"unknown tool: {name}"})
        try:
            result = fn(**coerce_tool_arguments(name, tool_input))
        except Exception as e:
            result = {"error": str(e)}
        self.calls.append({"name": name, "arguments": tool_input, "result": result})
        if name == "search_evidence":
            self.search_evidence_called = True
            if isinstance(result, dict):
                for item in result.get("results", []):
                    url = item.get("url")
                    if url:
                        self.verified_urls.add(url)
        return json.dumps(result, default=str)

    def answer_has_unverified_citation(self, answer: str) -> bool:
        cited_urls = [u.rstrip(".,;)]}\"'") for u in _URL_PATTERN.findall(answer)]
        if any(url not in self.verified_urls for url in cited_urls):
            return True
        if not self.search_evidence_called:
            # No real evidence was retrieved at all this turn — any quoted
            # "evidence" or explicit sentence_id reference must be fabricated,
            # regardless of whether it's dressed up as a real URL or a
            # placeholder like "[insert sentence_id]" (both observed live).
            if _QUOTE_PATTERN.search(answer) or _SENTENCE_ID_PATTERN.search(answer):
                return True
        return False


def ask(question: str, verbose: bool = True, backend_name: str | None = None,
        return_trace: bool = False):
    """Returns the answer string. With return_trace=True, returns
    (answer, calls) instead, where calls is the list of tools invoked while
    answering — used by chatbot/eval_gold_set.py, not needed for normal use."""
    backend = get_backend(backend_name)
    if verbose:
        logger.info("backend: %s (%s)", backend.name, getattr(backend, "model", "?"))

    tracker = _ToolCallTracker()
    answer = backend.ask(question, SYSTEM_PROMPT, TOOL_SCHEMAS, tracker.execute, verbose=verbose)

    if tracker.answer_has_unverified_citation(answer):
        if verbose:
            logger.warning("citation check FAILED — answer contains evidence not "
                           "actually retrieved via search_evidence")
        answer += UNVERIFIED_CITATION_WARNING
    return (answer, tracker.calls) if return_trace else answer


if __name__ == "__main__":
    setup_logging()
    question = " ".join(sys.argv[1:]) or "How does the market feel about DBS's dividend policy?"
    print(f"Q: {question}\n")
    print(ask(question))
