"""
Agentic chatbot: a tool-calling loop over the sentiment store.

The loop is plain Python rather than a framework (LangChain and similar). At this scale a framework adds abstraction without adding
capability, and the project report has to be able to explain whatever is
used.

The model backend is pluggable - a local model via Ollama (no API key, no
cost) or a hosted model (Claude, GPT, Gemini). Backend selection is
described in chatbot/backends/__init__.py. The local option exists so the
chatbot can be run and graded without anyone needing to hold an API key.

Citation verification. Small local models invent supporting evidence:
failures seen include fully-invented source URLs and sentence_ids, and placeholder-style
citations ("Sentence_id: [insert sentence_id]") that a URL-matching check
alone would not catch. Prompt instructions alone did not prevent either.

This module therefore enforces the invariant in code: if search_evidence was
never called, any quoted evidence, sentence_id reference or URL in the
answer is fabricated by definition, and the answer is flagged. This is the
same approach used for the volume floor in chatbot/tools.py - grounding
rules that matter are enforced rather than requested.

Flagging still shows the invented evidence. CHATBOT_ENFORCE_EVIDENCE goes
further, for answers that cite evidence without having searched (every
invented citation in the 1 Oct gold-set runs, on both local models):
`strip` removes the evidence the model wrote and says so; `search` removes
it and has the harness run search_evidence for the bank and aspect the
model looked up, showing those real quotes under a heading that says the
system found them. Unset or `off` (the default) leaves answers as written.
A search the harness makes is recorded with `"by": "harness"`, so the
evaluation doesn't count it as the model's tool choice.

The harness around the model (docs/DESIGN.md decision 19).
Each turn runs: input guards (chatbot/guards.py: advice-seeking and
out-of-scope questions get a fixed reply without calling the model) -> the
model's tool-calling loop -> output checks (citations, cited sentence ids,
and every figure against the tools' results). `answer_turn` returns the whole
record; `ask` keeps the old string-returning interface.

Memory. `Conversation` carries the last few turns, trimmed, plus an explicit state
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
from chatbot import intent as intents
from chatbot import settings
from chatbot.guards import is_evidence_text_key, unverified_numbers, unverified_sentence_ids
from chatbot.prompts import SYSTEM_PROMPT, with_state
from chatbot.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, coerce_tool_arguments
from ingest.base import detect_banks

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

logger = get_logger(__name__)

# A link, with or without its scheme ("www.reddit.com/r/...", "straitstimes.com/...").
_URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s)\]}\"'“”]+"
                          r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|sg|net|org|io|co|it|ly)(?:\.[a-z]{2})?/[^\s)\]}\"'“”]*",
                          re.IGNORECASE)
# A purported verbatim quote: opens after whitespace or punctuation and closes
# before it, so the gap between two short quotes ('"buy". ... as "hold"')
# isn't mistaken for one long quote. Straight or curly quotes, wrapped in
# markdown emphasis or not, may run across a single line break.
_QUOTE_PATTERN = re.compile(
    r'(?:^|(?<=[\s(\[:—–*_-]))"[^"\s](?:[^"\n]|\n(?!\n)){8,}?[^"\s]"(?=[\s.,;:!?)\]*_]|$)'
    r'|“[^”]{10,}?”')
# A markdown blockquote line ("> OCBC has the worst app..."): quoted text without quote marks.
# A line opening with a label and a colon ("> **Note:** ...") is the model's own
# aside, not quoted evidence (4 Oct 2026: notes were flagged as invented quotes).
_BLOCKQUOTE = re.compile(r"^[ \t]*>[ \t]*(?![*_]*[A-Z][\w ]{0,20}[*_]*:)(\S.{9,})$", re.MULTILINE)
_SENTENCE_ID_PATTERN = re.compile(r"sentence[_\s]?id", re.IGNORECASE)
_SENTENCE_ID = re.compile(r"\b[0-9a-f]{24}\b")

UNVERIFIED_CITATION_WARNING = (
    "\n\n⚠️ VERIFICATION WARNING: this answer cites evidence (a quote, sentence_id or URL) "
    "that no search_evidence call in this conversation returned. Treat that evidence as "
    "unverified: it may be invented."
)

EMPTY_ANSWER_REPLY = (
    "I couldn't produce an answer to that. Try asking about sentiment on DBS, OCBC or UOB, "
    "for example \"How has sentiment on OCBC's dividends changed?\""
)

UNVERIFIED_NUMBER_WARNING = (
    "\n\n⚠️ NUMBER CHECK: {figures} did not match any value the tools returned for this "
    "question. Treat {them} as unverified."
)

EVIDENCE_REMOVED_NOTE = (
    "\n\n(No evidence search was made for this answer, so the quotes it gave were removed. "
    "Ask for the quotes behind the score to see real ones.)"
)
EVIDENCE_FOUND_HEADING = "\n\nEvidence found by the system for this answer (search_evidence):"
ENFORCE_MODES = ("off", "strip", "search")

HISTORY_TURNS = settings.get("history.turns")                # earlier question/answer pairs passed to the model
HISTORY_ANSWER_CHARS = settings.get("history.answer_chars")  # earlier answers are trimmed so they don't crowd the context


def _norm_text(text: str) -> str:
    """Lower case, straight quotes and apostrophes, single spaces: how quoted text is compared."""
    text = (text or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def _norm_url(url: str) -> str:
    """A link without scheme, "www.", or trailing punctuation, for comparing cited and returned links."""
    url = re.sub(r"^https?://", "", url.strip().rstrip(".,;)]}\"'“”"), flags=re.IGNORECASE)
    return re.sub(r"^www\.", "", url, flags=re.IGNORECASE).rstrip("/").lower()


def _collect_text(obj, out: list[str], key=None) -> None:
    """The text of retrieved evidence, the only thing a quote may come from
    (not the system's own wording or the model's arguments echoed back)."""
    if isinstance(obj, str):
        if is_evidence_text_key(key):
            out.append(_norm_text(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _collect_text(v, out, k)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_text(v, out, key)


class _ToolCallTracker:
    """Records what search_evidence actually returned, so the final answer can
    be checked against what was truly retrieved - not what the model claims.
    Also keeps a general call log (every tool, its arguments, and its result),
    used by chatbot/eval_gold_set.py to check whether the model called the
    tool a question actually calls for."""

    def __init__(self, earlier: list[dict] | None = None):
        self.search_evidence_called = False
        self.verified_urls: set[str] = set()
        self.verified_sentence_ids: set[str] = set()
        self.retrieved_text: list[str] = []      # every string a tool returned, normalised
        self.calls: list[dict] = []
        # Evidence earlier turns of the conversation retrieved: a follow-up may
        # repeat it ("explain that second quote") without searching again.
        self.earlier_text: list[str] = []
        self.earlier_ids: set[str] = set()
        for c in earlier or []:
            if c.get("name") == "search_evidence" and isinstance(c.get("result"), dict):
                for item in c["result"].get("results", []):
                    _collect_text(item, self.earlier_text)
                    if item.get("url"):
                        self.verified_urls.add(_norm_url(item["url"]))
                    if item.get("sentence_id"):
                        self.earlier_ids.add(item["sentence_id"])

    def execute(self, name: str, tool_input: dict, by: str = "model") -> str:
        fn = TOOL_FUNCTIONS.get(name)
        if fn is None:
            return json.dumps({"error": f"unknown tool: {name}"})
        try:
            result = fn(**coerce_tool_arguments(name, tool_input))
        except Exception as e:
            logger.warning("tool %s failed: %s", name, e)   # the model sees the error; so does the log
            result = {"error": str(e)}
        call = {"name": name, "arguments": tool_input, "result": result}
        if by != "model":
            call["by"] = by
        self._record(call)
        return json.dumps(result, default=str)

    def _record(self, call: dict) -> None:
        self.calls.append(call)
        _collect_text(call.get("result"), self.retrieved_text)
        if call["name"] == "search_evidence":
            self.search_evidence_called = True
            if isinstance(call.get("result"), dict):
                for item in call["result"].get("results", []):
                    if item.get("url"):
                        self.verified_urls.add(_norm_url(item["url"]))
                    if item.get("sentence_id"):
                        self.verified_sentence_ids.add(item["sentence_id"])

    def unverified_quotes(self, answer: str, strict: bool = False) -> list[str]:
        """Quotes in the answer (in quote marks, or a markdown blockquote line)
        whose text neither this turn's tools nor an earlier turn's search
        returned. A quote cut with an ellipsis counts if each piece of three or
        more words was returned. A quote with no such piece can't be checked:
        `strict` counts it as unverified."""
        known = self.retrieved_text + self.earlier_text
        spans = [(m.group(0), m.group(0)[1:-1]) for m in _QUOTE_PATTERN.finditer(answer or "")]
        spans += [(m.group(0), m.group(1)) for m in _BLOCKQUOTE.finditer(answer or "")]
        out = []
        for span, inner in spans:
            pieces = [p for p in re.split(r"\.{3}|…", _norm_text(inner)) if len(p.split()) >= 3]
            if not pieces:
                if strict:
                    out.append(span)
            elif not all(any(p in t for t in known) for p in pieces):
                out.append(span)
        return out

    def unverified_urls(self, answer: str) -> list[str]:
        return [u for u in _URL_PATTERN.findall(answer or "")
                if _norm_url(u) not in self.verified_urls]

    def known_ids(self) -> set[str]:
        return self.verified_sentence_ids | self.earlier_ids

    def answer_has_unverified_citation(self, answer: str) -> bool:
        if self.unverified_urls(answer):
            return True
        if unverified_sentence_ids(answer, self.known_ids()):
            return True
        if self.search_evidence_called:
            return bool(self.unverified_quotes(answer))
        # No search this turn: evidence is real only if an earlier turn's search
        # returned it, word for word. Otherwise any quote, and any sentence_id
        # reference without a retrieved id (a placeholder like "[insert
        # sentence_id]"), is fabricated: both were seen in real answers.
        if self.unverified_quotes(answer, strict=True):
            return True
        mentions = len(_SENTENCE_ID_PATTERN.findall(answer or ""))
        return mentions > len([i for i in _SENTENCE_ID.findall(answer or "") if i in self.earlier_ids])

    @classmethod
    def from_calls(cls, calls: list[dict], earlier: list[dict] | None = None) -> "_ToolCallTracker":
        """A tracker holding calls already made, e.g. from a recorded evaluation run."""
        t = cls(earlier)
        for c in calls:
            t._record(dict(c))
        return t


def enforce_evidence_mode() -> str:
    """CHATBOT_ENFORCE_EVIDENCE: off (default), strip or search."""
    mode = (settings.get("enforce_evidence") or "off").strip().lower()
    return mode if mode in ENFORCE_MODES else "off"


_EVIDENCE_HEADING = re.compile(r"^[\W_]*(?:supporting\s+evidence|search\s+evidence|evidence)\b", re.IGNORECASE)
_SECTION_HEADING = re.compile(r"^[\W_]*(?:sample size|time window|caveats?|notes?|limitations?)\b",
                              re.IGNORECASE)


def _remove_inline(text: str, quotes: list[str] | None = None, urls: list[str] | None = None,
                   ids: list[str] | None = None) -> str:
    """Delete quotes, links and sentence-id references from running text, then
    tidy what's left ("as one investor said (https://...)." -> "as one investor said.").
    With lists given, only those; without, every one."""
    for q in (quotes if quotes is not None else _QUOTE_PATTERN.findall(text)):
        text = text.replace(q, "")
    if quotes is None:
        text = _BLOCKQUOTE.sub("", text)
    for u in (urls if urls is not None else _URL_PATTERN.findall(text)):
        text = text.replace(u, "")
    for sid in ids or []:
        text = re.sub(rf"(?:sentence[_\s]?id[:\s]*)?{sid}", "", text, flags=re.IGNORECASE)
    if quotes is None:
        text = re.sub(r"\[?[^\[\]\n]{0,40}sentence[_\s]?id[^\[\]\n]{0,40}\]?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(\s*\)|\[\s*\]|\*\*|\*(?=\W)|(?<=\W)\*", "", text)
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


_CITATION_MARK = re.compile(r"\[E\d+\]|\[[^\[\]\n]*sentence[_\s]?id[^\[\]\n]*\]", re.IGNORECASE)


def _remove_spans(text: str, spans: list[str], ids: list[str]) -> str:
    """Remove these quotes, links and sentence ids, editing only the lines they
    are on: the rest of the answer keeps its markdown (4 Oct 2026: a whole-answer
    tidy-up took bold and bullets from correct lines). A removed quote's own
    citation mark ("[E9]") goes with it; a line left empty goes too."""
    mark = "\x00"
    for span in sorted(set(spans), key=len, reverse=True):      # a quote may wrap a line
        text = text.replace(span, mark)
    for sid in ids:
        text = re.sub(rf"(?:sentence[_\s]?id[:\s]*)?{sid}", mark, text, flags=re.IGNORECASE)
    out = []
    for line in text.split("\n"):
        if mark not in line:
            out.append(line)
            continue
        line = re.sub(rf"{mark}\s*(?:{_CITATION_MARK.pattern})?", "", line, flags=re.IGNORECASE)
        line = re.sub(r"\(\s*\)|\[\s*\]", "", line)
        line = re.sub(r"(?<=\S)[ \t]+([.,;:!?])", r"\1", line).rstrip()
        if line.strip(" \t-*•>:"):
            out.append(line)
    return "\n".join(out)


def strip_unsearched_evidence(answer: str) -> str:
    """The answer without the evidence a model wrote without searching: the
    evidence section (from its heading to the next known section), any later
    line carrying a quote, URL or sentence id, and any quote, URL or id inside
    the first paragraph, which is otherwise kept as written."""
    head, _, rest = answer.partition("\n\n")
    head = _remove_inline(head)
    kept, skipping = [], False
    for line in rest.split("\n"):
        if _EVIDENCE_HEADING.match(line):
            skipping = True
            continue
        if skipping and _SECTION_HEADING.match(line):
            skipping = False
        if skipping or _URL_PATTERN.search(line) or _QUOTE_PATTERN.search(line) \
                or _BLOCKQUOTE.search(line) or _SENTENCE_ID_PATTERN.search(line):
            continue
        kept.append(line)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return head.rstrip() + ("\n\n" + body if body else "")


def _harness_search(tracker: _ToolCallTracker, question: str) -> str:
    """Real quotes for the bank(s) and aspect the model looked up, searched by the harness."""
    banks, aspect = [], None
    for c in tracker.calls:
        args = c.get("arguments") or {}
        if c["name"] == "compare_banks":
            banks = ["DBS", "OCBC", "UOB"]
        elif args.get("bank") and args["bank"] not in banks:
            banks.append(args["bank"])
        aspect = aspect or args.get("aspect")
    k = settings.get("harness_search.k_one_bank") if len(banks) <= 1 else settings.get("harness_search.k_each_bank")
    lines = []
    for bank in (banks or [None])[:3]:
        args = {"query": question, "k": k, **({"bank": bank} if bank else {}),
                **({"aspect": aspect} if aspect else {})}
        found = json.loads(tracker.execute("search_evidence", args, by="harness"))
        for item in (found.get("results") or [])[:k]:
            lines.append(f'- "{(item.get("text") or "").strip()}" {item.get("cite_as")}')
    return EVIDENCE_FOUND_HEADING + "\n" + "\n".join(lines) if lines else ""


EVIDENCE_UNMATCHED_NOTE = (
    "\n\n(Quotes or links in this answer that its searches didn't return were removed.)"
)


def enforce_evidence(answer: str, tracker: _ToolCallTracker, question: str, mode: str) -> tuple[str, bool]:
    """(new answer, whether the model's own text still cites unretrieved evidence).
    With no search made, the answer's evidence goes (and in search mode the
    harness finds real quotes); after a search, only the quotes and links the
    searches didn't return go. Answers citing nothing unretrieved pass unchanged."""
    if mode == "off" or not tracker.answer_has_unverified_citation(answer):
        return answer, tracker.answer_has_unverified_citation(answer)
    if tracker.search_evidence_called:
        # The whole answer at once: a quote can wrap onto the next line, and an
        # invented sentence id must go too (4 Oct 2026: both survived).
        cleaned = _remove_spans(answer, tracker.unverified_quotes(answer) + tracker.unverified_urls(answer),
                                unverified_sentence_ids(answer, tracker.known_ids()))
        return cleaned + EVIDENCE_UNMATCHED_NOTE, tracker.answer_has_unverified_citation(cleaned)
    stripped = strip_unsearched_evidence(answer)
    still_flagged = tracker.answer_has_unverified_citation(stripped)  # checked before any harness search
    found = _harness_search(tracker, question) if mode == "search" else ""
    return stripped + (found or EVIDENCE_REMOVED_NOTE), still_flagged


@dataclass
class TurnResult:
    """Everything one turn produced, for the UI, the evaluation and the trace."""
    question: str
    answer: str
    calls: list = field(default_factory=list)
    guard: str | None = None                 # the intent whose fixed reply answered (config/intents.yaml), if any
    intent: str | None = None                # the classifier's intent; None if it couldn't run
    model_answer: str | None = None          # the answer before the harness's warnings were appended
    citation_unverified: bool = False
    unverified_numbers: list = field(default_factory=list)
    evidence_enforced: str | None = None     # "strip" or "search" if CHATBOT_ENFORCE_EVIDENCE changed the answer


def answer_turn(question: str, backend_name: str | None = None, history: list | None = None,
                state: dict | None = None, verbose: bool = True, backend=None,
                earlier_calls: list | None = None) -> TurnResult:
    previous = next((h["content"] for h in reversed(history or []) if h.get("role") == "user"), None)
    intent = intents.classify_intent(question, state, previous)
    reply = intents.reply_for(intent, question, state)
    if reply:
        if verbose:
            logger.info("intent %s: answered with its fixed reply", intent)
        return TurnResult(question=question, answer=reply, guard=intent, intent=intent)

    backend = backend or get_backend(backend_name)
    if verbose:
        logger.info("backend: %s (%s)", backend.name, getattr(backend, "model", "?"))

    tracker = _ToolCallTracker(earlier_calls)
    answer = backend.ask(question, with_state(SYSTEM_PROMPT, state), TOOL_SCHEMAS,
                         tracker.execute, verbose=verbose, history=history)
    if not (answer or "").strip(" \n{}[]\"'"):
        # An empty answer, or a bare "{}" from a model that tried to emit a tool call
        # as text. The replacement is the harness's own text, so it skips the checks.
        return TurnResult(question=question, answer=EMPTY_ANSWER_REPLY, calls=tracker.calls)
    result = TurnResult(question=question, answer=answer, calls=tracker.calls, intent=intent)

    mode = enforce_evidence_mode()
    enforced, flagged = enforce_evidence(answer, tracker, question, mode)
    if enforced != answer:
        if verbose:
            logger.warning("evidence written without a search was removed (%s)", mode)
        answer, result.answer, result.evidence_enforced = enforced, enforced, mode

    result.model_answer = answer
    if flagged:
        if verbose:
            logger.warning("citation check failed: answer contains evidence not "
                           "actually retrieved via search_evidence")
        result.citation_unverified = True
        result.answer += UNVERIFIED_CITATION_WARNING

    # Only the model's own text and calls: a harness search run afterwards must
    # not vouch for figures the model wrote before it, and the real quotes the
    # harness added are not the model's figures.
    figures = unverified_numbers(answer.split(EVIDENCE_FOUND_HEADING)[0],
                                 [c.get("result") for c in tracker.calls if c.get("by") != "harness"], question)
    if figures:
        if verbose:
            logger.warning("number check failed: %s not returned by any tool", figures)
        result.unverified_numbers = figures
        result.answer += UNVERIFIED_NUMBER_WARNING.format(
            figures=", ".join(figures), them="it" if len(figures) == 1 else "them")
    return result


def ask(question: str, verbose: bool = True, backend_name: str | None = None,
        return_trace: bool = False):
    """Returns the answer string. With return_trace=True, returns
    (answer, calls) instead, where calls is the list of tools invoked while
    answering - used by chatbot/eval_gold_set.py, not needed for normal use.
    Single-turn; use Conversation for follow-ups."""
    r = answer_turn(question, backend_name=backend_name, verbose=verbose)
    return (r.answer, r.calls) if return_trace else r.answer


def _strip_warnings(answer: str) -> str:
    """For turns rebuilt from plain messages (the API's history), which carry no
    model_answer: the text before the first warning the harness appends."""
    return answer.split("\n\n⚠️")[0]


class Conversation:
    """A multi-turn chat: recent turns plus explicit state (banks, aspect, window)."""

    def __init__(self, backend_name: str | None = None, trace_path: str | None = None):
        self.backend_name = backend_name
        self.turns: list[TurnResult] = []
        self.state: dict = {"banks": [], "aspect": None, "window": None}
        self.trace_path = trace_path or settings.get("trace_file") or None

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
                        "content": (t.model_answer if t.model_answer is not None
                                    else _strip_warnings(t.answer))[:HISTORY_ANSWER_CHARS]})
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
        earlier = [c for t in self.turns[-HISTORY_TURNS:] for c in t.calls if c.get("name") == "search_evidence"]
        r = answer_turn(question, backend_name=self.backend_name, history=self.history(),
                        state=self.state, verbose=verbose, earlier_calls=earlier)
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
