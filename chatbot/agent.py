"""
Agentic chatbot — MVP plan Phase 8. A plain tool-calling loop (see plan
Phase 8, "Architecture": at this scale a framework like LangChain adds
abstraction without adding capability, and the report has to explain
whatever gets used), now pluggable between a local model (Ollama, no API
key, no cost — see chatbot/backends/ollama_backend.py) and Claude (frontier,
needs ANTHROPIC_API_KEY). See chatbot/backends/__init__.py for how the
backend is chosen.

WHY PLUGGABLE: this is a school project. A lecturer grading it shouldn't
need to hold an API key just to run the chatbot.

CITATION VERIFICATION — READ THIS: live-tested against llama3.2:3b
(2026-09-07). First attempt: a confident answer citing two fully-fabricated
sources (fake Bloomberg/Reuters URLs, fake sentence_ids) despite never
calling search_evidence. After tightening the system prompt (added an
explicit "never invent a citation" rule) the model STILL fabricated a
"supporting evidence" quote on the next run — this time with placeholder
tokens ("Sentence_id: [insert sentence_id]") instead of a fake URL, which
would have slipped straight past a naive URL-regex check. Two different
fabrication styles from one prompt change is exactly why this is a code
check, not a prompt-tuning problem: the invariant that actually holds is
"if search_evidence was never called, ANY quoted evidence or sentence_id
reference in the final answer is fabricated by definition" — this module
enforces that directly rather than trying to enumerate every way a model
might dress up a fake citation. Mirrors how MIN_VOLUME_FOR_SCORE etc. are
enforced in code in chatbot/tools.py rather than left to the prompt.

USAGE:
  python -m chatbot.agent "How does the market feel about DBS's dividend policy?"
  CHATBOT_BACKEND=ollama python -m chatbot.agent "..."   # force local
  CHATBOT_BACKEND=claude python -m chatbot.agent "..."   # force frontier
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
    be checked against what was truly retrieved — not what the model claims."""

    def __init__(self):
        self.search_evidence_called = False
        self.verified_urls: set[str] = set()

    def execute(self, name: str, tool_input: dict) -> str:
        fn = TOOL_FUNCTIONS.get(name)
        if fn is None:
            return json.dumps({"error": f"unknown tool: {name}"})
        try:
            result = fn(**coerce_tool_arguments(name, tool_input))
        except Exception as e:
            result = {"error": str(e)}
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


def ask(question: str, verbose: bool = True, backend_name: str | None = None) -> str:
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
    return answer


if __name__ == "__main__":
    setup_logging()
    question = " ".join(sys.argv[1:]) or "How does the market feel about DBS's dividend policy?"
    print(f"Q: {question}\n")
    print(ask(question))
