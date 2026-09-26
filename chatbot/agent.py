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

THE HARNESS AROUND THE MODEL (docs/DESIGN.md decision 19)
Each turn runs: input guards (chatbot/guards.py: advice-seeking and
out-of-scope questions get a fixed reply without calling the model) -> the
model's tool-calling loop -> output checks (citations, cited sentence ids,
and every figure against the tools' results). `answer_turn` returns the whole
record; `ask` keeps the old string-returning interface.

MEMORY
`Conversation` carries the last few turns, trimmed, plus an explicit state
(banks, aspect, window) taken from the tools actually called, so a follow-up
like "and OCBC?" resolves. Earlier tool calls are not replayed: the model is
told to re-fetch rather than repeat an old number, and the number check only
accepts figures from the current turn's tools.

USAGE:
  python -m chatbot.agent "How does the market feel about DBS's dividend policy?"
  CHATBOT_BACKEND=ollama python -m chatbot.agent "..."   # force local
  CHATBOT_BACKEND=claude python -m chatbot.agent "..."   # force hosted
"""

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field

from dotenv import load_dotenv

from chatbot.backends import get_backend
from config.logging_config import get_logger, setup_logging
from chatbot.guards import advice_reply, scope_reply, unverified_numbers, unverified_sentence_ids
from chatbot.prompts import SYSTEM_PROMPT, with_state
from chatbot.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, coerce_tool_arguments
from ingest.base import detect_banks

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

logger = get_logger(__name__)

_URL_PATTERN = re.compile(r"https?://[^\s)\]}\"']+")
# A purported verbatim quote: opens after whitespace or punctuation and closes
# before it, so the gap between two short quotes ('"buy". ... as "hold"')
# isn't mistaken for one long quote.
_QUOTE_PATTERN = re.compile(r'(?:^|(?<=[\s(\[:—–-]))"[^"\s][^"\n]{8,}[^"\s]"(?=[\s.,;:!?)\]]|$)')
_SENTENCE_ID_PATTERN = re.compile(r"sentence[_\s]?id", re.IGNORECASE)

UNVERIFIED_CITATION_WARNING = (
    "\n\n⚠️ VERIFICATION WARNING: this response appears to cite evidence "
    "(a quote, sentence_id, or URL) that was not returned by any search_evidence call in "
    "this conversation. Treat any quoted evidence above as UNVERIFIED — it may be fabricated. "
    "(Seen from smaller local models; see chatbot/agent.py docstring.)"
)

EMPTY_ANSWER_REPLY = (
    "I couldn't produce an answer to that. Try asking about sentiment on DBS, OCBC or UOB, "
    "for example \"How has sentiment on OCBC's dividends changed?\""
)

UNVERIFIED_NUMBER_WARNING = (
    "\n\n⚠️ NUMBER CHECK: {figures} did not match any value the tools returned for this "
    "question. Treat {them} as unverified."
)

HISTORY_TURNS = 3            # earlier question/answer pairs passed to the model
HISTORY_ANSWER_CHARS = 1200  # earlier answers are trimmed so they don't crowd the context


class _ToolCallTracker:
    """Records what search_evidence actually returned, so the final answer can
    be checked against what was truly retrieved — not what the model claims.
    Also keeps a general call log (every tool, its arguments, and its result),
    used by chatbot/eval_gold_set.py to check whether the model called the
    tool a question actually calls for."""

    def __init__(self):
        self.search_evidence_called = False
        self.verified_urls: set[str] = set()
        self.verified_sentence_ids: set[str] = set()
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
                    if item.get("sentence_id"):
                        self.verified_sentence_ids.add(item["sentence_id"])
        return json.dumps(result, default=str)

    def answer_has_unverified_citation(self, answer: str) -> bool:
        cited_urls = [u.rstrip(".,;)]}\"'") for u in _URL_PATTERN.findall(answer)]
        if any(url not in self.verified_urls for url in cited_urls):
            return True
        if unverified_sentence_ids(answer, self.verified_sentence_ids):
            return True
        if not self.search_evidence_called:
            # No real evidence was retrieved at all this turn — any quoted
            # "evidence" or explicit sentence_id reference must be fabricated,
            # regardless of whether it's dressed up as a real URL or a
            # placeholder like "[insert sentence_id]" (both observed live).
            if _QUOTE_PATTERN.search(answer) or _SENTENCE_ID_PATTERN.search(answer):
                return True
        return False


@dataclass
class TurnResult:
    """Everything one turn produced, for the UI, the evaluation and the trace."""
    question: str
    answer: str
    calls: list = field(default_factory=list)
    guard: str | None = None                 # "advice" or "scope" if an input guard answered
    citation_unverified: bool = False
    unverified_numbers: list = field(default_factory=list)


def answer_turn(question: str, backend_name: str | None = None, history: list | None = None,
                state: dict | None = None, verbose: bool = True, backend=None) -> TurnResult:
    context_banks = (state or {}).get("banks")
    for guard, reply in (("advice", advice_reply(question, context_banks)),
                         ("scope", scope_reply(question))):
        if reply:
            if verbose:
                logger.info("input guard: %s question answered with the fixed reply", guard)
            return TurnResult(question=question, answer=reply, guard=guard)

    backend = backend or get_backend(backend_name)
    if verbose:
        logger.info("backend: %s (%s)", backend.name, getattr(backend, "model", "?"))

    tracker = _ToolCallTracker()
    answer = backend.ask(question, with_state(SYSTEM_PROMPT, state), TOOL_SCHEMAS,
                         tracker.execute, verbose=verbose, history=history)
    if not (answer or "").strip(" \n{}[]\"'"):
        # An empty answer, or a bare "{}" from a model that tried to emit a tool call
        # as text. The replacement is the harness's own text, so it skips the checks.
        return TurnResult(question=question, answer=EMPTY_ANSWER_REPLY, calls=tracker.calls)
    result = TurnResult(question=question, answer=answer, calls=tracker.calls)

    if tracker.answer_has_unverified_citation(answer):
        if verbose:
            logger.warning("citation check FAILED — answer contains evidence not "
                           "actually retrieved via search_evidence")
        result.citation_unverified = True
        result.answer += UNVERIFIED_CITATION_WARNING

    figures = unverified_numbers(answer, [c.get("result") for c in tracker.calls], question)
    if figures:
        if verbose:
            logger.warning("number check FAILED — %s not returned by any tool", figures)
        result.unverified_numbers = figures
        result.answer += UNVERIFIED_NUMBER_WARNING.format(
            figures=", ".join(figures), them="it" if len(figures) == 1 else "them")
    return result


def ask(question: str, verbose: bool = True, backend_name: str | None = None,
        return_trace: bool = False):
    """Returns the answer string. With return_trace=True, returns
    (answer, calls) instead, where calls is the list of tools invoked while
    answering — used by chatbot/eval_gold_set.py, not needed for normal use.
    Single-turn; use Conversation for follow-ups."""
    r = answer_turn(question, backend_name=backend_name, verbose=verbose)
    return (r.answer, r.calls) if return_trace else r.answer


def _strip_warnings(answer: str) -> str:
    return answer.split("\n\n⚠️")[0]


class Conversation:
    """A multi-turn chat: recent turns plus explicit state (banks, aspect, window)."""

    def __init__(self, backend_name: str | None = None, trace_path: str | None = None):
        self.backend_name = backend_name
        self.turns: list[TurnResult] = []
        self.state: dict = {"banks": [], "aspect": None, "window": None}
        self.trace_path = trace_path or os.environ.get("CHATBOT_TRACE_FILE") or None

    @classmethod
    def from_messages(cls, messages: list[dict], backend_name: str | None = None) -> "Conversation":
        """Rebuild from plain role/content messages, e.g. a stateless API request.
        Tool calls aren't known, so the state comes from the banks the user named."""
        conv = cls(backend_name=backend_name)
        pending = None
        for m in messages:
            if m.get("role") == "user":
                pending = m.get("content", "")
                banks = detect_banks(pending)
                if banks:
                    conv.state["banks"] = banks
            elif m.get("role") == "assistant" and pending is not None:
                conv.turns.append(TurnResult(question=pending, answer=m.get("content", "")))
                pending = None
        return conv

    def history(self) -> list[dict]:
        out = []
        for t in self.turns[-HISTORY_TURNS:]:
            out.append({"role": "user", "content": t.question})
            out.append({"role": "assistant",
                        "content": _strip_warnings(t.answer)[:HISTORY_ANSWER_CHARS]})
        return out

    def _update_state(self, r: TurnResult) -> None:
        for c in r.calls:
            args = c.get("arguments") or {}
            if c["name"] == "compare_banks":
                self.state["banks"] = ["DBS", "OCBC", "UOB"]
            elif args.get("bank"):
                self.state["banks"] = [args["bank"]]
            if c["name"] in ("get_sentiment", "compare_banks", "get_trend", "get_coverage"):
                self.state["aspect"] = args.get("aspect")  # None means overall
                if args.get("window"):
                    self.state["window"] = args["window"]
        if not r.calls:
            banks = detect_banks(r.question)
            if banks:
                self.state["banks"] = banks

    def ask(self, question: str, verbose: bool = False) -> TurnResult:
        r = answer_turn(question, backend_name=self.backend_name, history=self.history(),
                        state=self.state, verbose=verbose)
        self._update_state(r)
        self.turns.append(r)
        if self.trace_path:
            with open(self.trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({**asdict(r), "state_after": dict(self.state)}, default=str) + "\n")
        return r


if __name__ == "__main__":
    setup_logging()
    question = " ".join(sys.argv[1:]) or "How does the market feel about DBS's dividend policy?"
    print(f"Q: {question}\n")
    print(ask(question))
