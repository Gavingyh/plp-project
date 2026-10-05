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
system found them. `off` leaves answers as written; the default is `strip`
(config/chatbot.yaml).
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
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime

from dotenv import load_dotenv

from chatbot.backends import get_backend
from config import aspect_taxonomy
from config.sources import label as source_label
from config.logging_config import get_logger, setup_logging
from chatbot import intent as intents
from chatbot import settings
from chatbot.guards import is_evidence_text_key, unverified_numbers, unverified_sentence_ids
from chatbot.prompts import SYSTEM_PROMPT, with_state
from chatbot.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, coerce_tool_arguments
from ingest.base import BANK_NAMES, detect_banks

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

logger = get_logger(__name__)

# A link, with or without its scheme ("www.reddit.com/r/...", "straitstimes.com/...").
_URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s)\]}\"'“”]+"
                          r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}/[^\s)\]}\"'“”]*",
                          re.IGNORECASE)
# A purported verbatim quote (as in commit f4b9145, changed in validations on 4
# and 5 Oct 2026). A curly or angle quote (“...”, «...») is known by its own
# marks. A mark that can also stand elsewhere, a straight one or a closing mark
# used to open (»...«, ”...”), is known by what stands around it too: it opens
# only where no letter or digit stands before it, and closes only where none
# follows, so an inch mark ('a 6" phone') opens nothing and the gap between two
# short quotes ('"buy". ... as "hold"') isn't read as one long quote, while
# brackets, table bars and other punctuation ('"..."(Reddit)', '|”...”|') don't
# hide a quote. A quote holds no other double quote mark (_DOUBLE_MARKS), so it
# never runs past a closing mark of another style ('"...”(Reddit) ... a 6"
# phone' ran on to the inch mark), with two exceptions. It may hold an inch mark
# (_INCH). And a straight quote may hold whole curly quotes and a curly quote
# whole straight ones ('“I asked them "..." and they said ...”'), the outer
# quote then being checked whole (validation, 5 Oct 2026: the words after the
# inner quote went unchecked); only those two, as on made-up answers a quote
# with mixed marks that could hold one read the closing mark of one quote and
# the opening mark of another as one quote around a third. Quotes, wrapped in
# markdown emphasis or not, may run across a single line break. Mixed marks
# count, and so does a straight quote never closed by the end of its line (an
# answer cut short at the length limit ends in an open quote); that one opens
# only after a space, bracket, colon, dash or emphasis mark, so the closing mark
# of a short quote ('"Bad!"(Reddit) ...') doesn't open one to the line's end.
# A low-9 mark („...“, „...”, German and Polish style) is found by the pairing
# of marks in _QuoteSpans, not by this pattern (validation, 5 Oct 2026: such a
# quote went unread). A mark neither places is one _QuoteSpans.loose reports.
_DOUBLE_MARKS = '"\u201c\u201d\u00ab\u00bb\u201e\u201f'          # " “ ” « » „ ‟
_NOT_AFTER_WORD = r"(?<![^\W_])"                            # no letter or digit before the mark
_NOT_BEFORE_WORD = r"(?![^\W_])"                            # nor after it
# A quote inside a quote opens and closes like a quote: no letter or digit
# outside its marks, no space inside them. So the closing mark of one quote and
# the opening mark of the next ('“...it" and "fees...”') are never a pair.
_INNER = rf'(?![\s{_DOUBLE_MARKS}])[^{_DOUBLE_MARKS}\n]*(?<!\s)'
_CURLY_INSIDE = rf'{_NOT_AFTER_WORD}“{_INNER}”{_NOT_BEFORE_WORD}'
_STRAIGHT_INSIDE = rf'{_NOT_AFTER_WORD}"{_INNER}"{_NOT_BEFORE_WORD}'
# An inch mark ('my 6" phone'): a straight mark after a digit, before no letter
# or digit. A quote that closes with a curly or angle mark may hold one, and so
# may one the pairing finds opened with any but a straight mark: on `main` a
# curly quote held any straight mark, and from 6e1560f none, so '“my 6" phone
# ...”' went unchecked. In a quote that closes with a straight mark it is read as the close
# wherever the quote is long enough to end there, and a straight quote left open
# to the end of its line holds none.
_INCH = r'(?<=\d)"(?![^\W_])'
_INCH_MARK = re.compile(_INCH)
_HOLDS_INCH = rf'(?:[^{_DOUBLE_MARKS}\n]|{_INCH}|\n(?!\n))'                    # no double mark but an inch mark, no blank line
_HOLDS_CURLY = rf'(?:[^{_DOUBLE_MARKS}\n]|{_CURLY_INSIDE}|{_INCH}|\n(?!\n))'     # ... or a whole curly quote
_HOLDS_STRAIGHT = rf'(?:[^{_DOUBLE_MARKS}\n]|{_STRAIGHT_INSIDE}|{_INCH}|\n(?!\n))'  # ... or a whole straight quote
_QUOTE_REGEX = re.compile(
    rf'{_NOT_AFTER_WORD}"(?![\s"]){_HOLDS_CURLY}{{10,}}?(?<!\s)"{_NOT_BEFORE_WORD}'
    rf'|“{_HOLDS_STRAIGHT}{{10,}}?”'
    rf'|«{_HOLDS_INCH}{{10,}}?»'
    rf'|“{_HOLDS_INCH}{{10,}}?(?<!\s)"{_NOT_BEFORE_WORD}'
    rf'|{_NOT_AFTER_WORD}"(?![\s"]){_HOLDS_INCH}{{10,}}?”'
    rf'|(?:^|(?<=[\s(\[\]:—–*_-]))"[^"\s][^{_DOUBLE_MARKS}\n]{{9,}}(?=\n|\Z)'
    rf'|{_NOT_AFTER_WORD}»[^{_DOUBLE_MARKS}\s]{_HOLDS_INCH}{{8,}}?[^{_DOUBLE_MARKS}\s]«{_NOT_BEFORE_WORD}'
    rf'|{_NOT_AFTER_WORD}”[^{_DOUBLE_MARKS}\s]{_HOLDS_INCH}{{8,}}?[^{_DOUBLE_MARKS}\s]”{_NOT_BEFORE_WORD}')
# A passage in single quotes. A single mark is also an apostrophe, and a short
# passage in single marks is mostly a term or a scare quote ('strong buy', 'customer
# first digital approach'), not a quote (validation, 5 Oct 2026: three words
# stripped a scare quote as invented). So one counts from six words
# (_QuoteSpans._SINGLE_WORDS), or from three where it reads as a quote: right after
# a verb of saying ("One user wrote '...'") or a speaker and a colon ("One user:
# '...'"), or right before a citation or a source tag (validation, 5 Oct 2026: a
# five-word invented quote after "wrote" passed). An apostrophe inside a word
# ("OCBC's", "don't") neither opens nor closes one, and a quote must open on a
# letter, so "the '08 crisis ... banks' margins" is not one. It opens after a space, bracket, colon, dash, emphasis mark
# or table bar, with any of the three marks (’ too: '’...’', as typed in Sweden or
# Finland, or by a smart-quote slip), and closes with any of them.
_SINGLE_QUOTE = re.compile(
    r"(?:^|(?<=[\s(\[\]:—–*_|-]))['‘’](?=[^\W\d_])(?:[^'‘’\n]|(?<=\w)['’](?=\w)|\n(?!\n)){10,}?"
    r"(?<=[^\s'‘’])['’‘](?!\w)")


class _QuoteSpans:
    """Quoted passages in an answer, from two detectors that each catch what the
    other misses (validations, 4 and 5 Oct 2026; each round found a new shape).

    First, _QUOTE_REGEX: a curly or angle quote by its own marks, a straight
    one or one opened with a closing mark also by the letters and digits
    around its marks, so one stray or missing mark ('a 6" phone', an unclosed
    quote) never shifts the quotes after it. Then, in the text between its
    quotes, each paragraph's marks are paired in order, first with second and
    third with fourth, as a reader pairs them, whatever stands around them: a
    space inside the marks, a letter against one. With nothing open, an inch
    mark ('a 6" phone') opens nothing, and a mark opens only where it reads as
    an opening one (_opens): a low-9 mark („ or ‟) opens like “, a closing
    mark (” or ») only before a letter or digit. A pair around fewer than
    ten characters ('"buy"') is a word in quote marks, not a quote, but still
    takes its two marks, so the gap between two short quotes is never read as
    one. A mark left without a partner opens a quote that runs to the end of
    its line, or to the next quote the regex found, stopping before a citation;
    a mark closing a word ('bad" ') opens no such quote. Then the words right
    after a closing mark that reads as an opening one (_after_closes). Last,
    single-quoted passages (_SINGLE_QUOTE) where none of these found a quote:
    from six words, or from three after a quoting cue or before a citation
    (_cued).

    Offers a compiled pattern's finditer, search and findall, the spans in text
    order and never overlapping, so its callers read like any regex's (a span
    from _after_closes has no marks of its own); and loose, the double quote
    marks none of them could place, which the checks treat as evidence they
    can't verify (validation, 5 Oct 2026: a quote holding an inch mark ran on
    to the next quote's opening mark, and left that quote outside every span)."""

    _DOUBLE = _DOUBLE_MARKS
    _MARK = re.compile(f"[{_DOUBLE}]")
    _PARAGRAPH = re.compile(r"(?:[^\n]|\n(?![ \t]*\n))+")
    _CITATION = re.compile(r"[ \t]*\[[A-Z]+, \d{4}-\d{2}-\d{2}, sentence_id")
    _SHORTEST = 10
    _WORD_NEXT = re.compile(r"[*_`]*[^\W_]")            # a letter or digit next, in any script, emphasis marks aside
    _LATIN_NEXT = re.compile(r"[*_`]*[A-Za-z0-9]")       # ... from A to Z or 0 to 9
    _SINGLE_WORDS = 6
    _SINGLE_CUED_WORDS = 3
    # A single-quoted passage of three to five words is a quote right after a verb
    # of saying in the past tense or the present, never in a form that is also a
    # noun (validation, 5 Oct 2026: "post", "report" and "note" made terms into
    # quotes, "Users report 'long queue times'"), or "put it" or "call it", among
    # the three words before its opening mark; or right after a speaker and a
    # colon ("One user: '...'", "Another: '...'"), a colon after anything else
    # being a label ("Note: 'fees are high' is the theme"); or right before a
    # citation, cite_as, a numbered marker or a source tag ("(Reddit)", "(CNA)",
    # "(news)").
    _CUE_WORDS = frozenset("""
        said say says  wrote write writes  complained complain complains  posted  commented
        tweeted  replied  added  asked  claimed  stated  quoted""".split())
    _CUE_PAIRS = frozenset({("put", "it"), ("call", "it"), ("calls", "it"), ("called", "it")})
    _CUE_COLON = re.compile(r"(?:\b(?:one|a|another)[ \t]+(?:[^\W\d_]+[ \t]+)?(?:user|post|comment|reply|tweet"
                            r"|poster|commenter|redditor|reader|investor|customer|reviewer|analyst)s?|\banother)"
                            r"[*_]*[ \t]*:[\s*_]*\Z", re.IGNORECASE)                # a speaker, then a colon
    _CITED_NEXT = re.compile(r"[ \t.,;:!?*_]{0,3}(?:\[[A-Z]+, \d{4}-\d{2}-\d{2}, sentence_id|\(?\[?cite_as\b"
                             r"|\[E?\d{1,3}(?:[ \t]*[,\u2013-][ \t]*E?\d{1,3})*\]"
                             r"|\((?:source:?[ \t]*)?(?:reddit|cna|news|bank results report)\b)", re.IGNORECASE)

    class _Span:
        def __init__(self, text: str, start: int, end: int, after: tuple[int, int] | None = None):
            self._text, self._start, self._end = text, start, end
            self.after = after      # words after a closing mark (_after_closes): the quote before them

        def group(self, index: int = 0) -> str:
            return self._text[self._start:self._end]

        def start(self) -> int:
            return self._start

        def end(self) -> int:
            return self._end

    @staticmethod
    def _closes_a_word(text: str, i: int) -> bool:
        """A straight mark right after a letter or digit, with neither after it:
        where a quote closes, or an inch mark ('a 6" phone')."""
        after = text[i + 1] if i + 1 < len(text) else " "
        return text[i] == '"' and i > 0 and text[i - 1].isalnum() and not after.isalnum()

    @staticmethod
    def _opens_a_word(text: str, i: int) -> bool:
        """“, «, „ or ‟, or a straight mark before a letter or digit and not after one."""
        after = text[i + 1] if i + 1 < len(text) else " "
        if text[i] in "\u201c\u00ab\u201e\u201f":
            return True
        return text[i] == '"' and after.isalnum() and not (i > 0 and text[i - 1].isalnum())

    def _opens(self, text: str, i: int, following) -> bool:
        """Whether the mark at i opens a quote when none is open. Not a closing
        mark (” or »), unless it reads as an opening one: no letter or digit
        before it, one right after it, emphasis marks aside ('»...»', '”..."').
        Nor an inch mark ('a 6" phone'), nor an opening mark that reads as a
        closing one, after a letter, a digit or punctuation and before no
        letter or digit ('for sure“ a 6" phone'). A straight mark closing a
        word ('bad" ') closes a quote whose opening was lost, unless the next
        mark can't open one either: then it closes a quote inside a quote
        ('"What do you think of "DBS Robot" with the fees?"') and opens the rest."""
        if text[i] in "\u201d\u00bb":
            return not (i > 0 and text[i - 1].isalnum()) and bool(self._WORD_NEXT.match(text, i + 1))
        if text[i] != '"' and i > 0 and (text[i - 1].isalnum() or text[i - 1] in ".,;!?") \
                and not self._WORD_NEXT.match(text, i + 1):
            return False      # 'for sure“ a 6" phone': an opening mark typed to close a quote whose opening was lost
        if self._closes_a_word(text, i):
            return not text[i - 1].isdigit() and not (following is not None and self._opens_a_word(text, following))
        return True

    def _only_opens(self, text: str, opened: int, i: int) -> bool:
        """A mark that only opens a quote (“, «, „, ‟) where it reads as an
        opening mark, a letter or digit right after it, emphasis marks aside;
        but for “ closing „ or ‟ („...“). Before a space or punctuation
        it reads as a closing mark typed wrong ('"...night“ ok') and closes."""
        return text[i] in "\u201c\u00ab\u201e\u201f" and not (text[i] == "\u201c" and text[opened] in "\u201e\u201f") \
            and bool(self._WORD_NEXT.match(text, i + 1))

    @staticmethod
    def _word_in_marks(text: str, opened: int, closed: int) -> bool:
        """Whether two marks around fewer than ten characters read as a word in
        quote marks ('"buy"', '"Tier 1"'): no space after the first or before
        the second. Two other marks, such as the closing mark of a quote whose
        opening was taken by another and a mark after it ('...sure" and a 6"
        phone'), are not a pair to a reader."""
        return not text[opened + 1].isspace() and not text[closed - 1].isspace()

    def _glued_end(self, text: str, i: int) -> int | None:
        """Where the words glued to the closing mark at i may end as a quote: a
        citation on their line before any other mark, or the next double quote
        mark in their paragraph if it reads as a closing one, with no letter or
        digit right after it, emphasis marks aside (an inch mark too); else
        None, and they read as the model's own words."""
        m = self._MARK.search(text, i + 1)
        line_end = text.find("\n", i + 1)
        line_end = len(text) if line_end == -1 else line_end
        cite = self._CITATION.search(text, i + 1, min(line_end, m.start() if m else len(text)))
        if cite:
            return cite.start()
        if m is None or re.search(r"\n[ \t]*\n", text[i:m.start()]) or self._WORD_NEXT.match(text, m.start() + 1):
            return None
        return m.start()

    def _opens_glued(self, text: str, i: int) -> bool:
        """Whether the second mark of a pair around fewer than ten characters,
        at i, with a letter or digit right after it, opens a quote all the same:
        the words after it, ten or more characters, end where a quote may end
        (_glued_end): '"x"OCBC will cut its dividend next year for sure"', or
        before a citation, or with an inch mark, '... by 5"', which is never a
        mark the checks can't place. With none of these after it ('"DBS"and
        "OCBC"', '"buy-now"s offer') it only closes a word in quote marks."""
        j = self._glued_end(text, i) if self._WORD_NEXT.match(text, i + 1) else None
        return j is not None and len(text[i + 1:j].strip()) >= self._SHORTEST

    def _paired(self, text: str, start: int, end: int, taken: set):
        """(start, end) of the quotes found by pairing marks within text[start:end];
        the marks of a pair too short to be a quote go into `taken` if they read
        as a word in quote marks (_word_in_marks), whatever follows the second
        ('"buy"', '"DBS"and', '"buy-now"s', in Chinese '“应用”的'): validation, 5
        Oct 2026, where a letter right after the second left both unplaced and
        took a correct line in strip mode. Unless that second mark, with a letter
        or digit right after it, is followed by a citation or a mark that reads
        as a closing one ten or more characters on (_opens_glued): then it opens
        a quote, and the first is left unplaced, as before. A mark that only
        opens, where it reads as an opening one (_only_opens), closes nothing:
        the quote open before it ends there, unclosed, and it opens the next ('a
        stray " here, he wrote „...'). Nor is a pair too short to be a quote, and
        not a word in quote marks, one whose second mark opens a quote, a letter
        or digit right after it ('a stray " here "...'): the first mark is left
        unplaced, and the second opens a quote. A straight
        mark after a space, left open at the end of a paragraph before fewer
        than ten characters ('and a stray " here'), is a stray mark, taken;
        after anything else ('...for sure!" ok') it reads as a closing mark,
        and is left unplaced."""
        for para in self._PARAGRAPH.finditer(text, start, end):
            opened = None
            marks = [m.start() for m in self._MARK.finditer(text, para.start(), para.end())]
            for k, i in enumerate(marks):
                following = marks[k + 1] if k + 1 < len(marks) else None
                if opened is None:
                    if self._opens(text, i, following):
                        opened = i
                    continue
                if text[opened] != '"' and _INCH_MARK.match(text, i):
                    continue      # '“my 6" phone ...': an inch mark in a quote not opened with a straight mark
                long_enough = len(text[opened + 1:i].strip()) >= self._SHORTEST
                if self._only_opens(text, opened, i):
                    if long_enough:
                        yield opened, len(text[:i].rstrip())
                    opened = i
                elif long_enough:
                    yield opened, i + 1
                    opened = None
                elif self._word_in_marks(text, opened, i) and not self._opens_glued(text, i):
                    taken.update((opened, i))      # '"buy"', '"DBS"and', '"buy-now"s', in Chinese '“应用”的'
                    opened = None
                elif self._WORD_NEXT.match(text, i + 1) and (self._opens(text, i, following)
                                                             or self._opens_glued(text, i)):
                    opened = i        # 'a stray " here "...', '“x”OCBC ... for sure”': it opens the next quote
                else:
                    opened = None     # two marks no reader pairs ('...sure" and a 6" phone')
            if opened is not None and not self._closes_a_word(text, opened):
                line_end = text.find("\n", opened, para.end())
                line_end = para.end() if line_end == -1 else line_end
                cite = self._CITATION.search(text, opened, line_end)
                stop = cite.start() if cite else line_end
                while stop > opened and text[stop - 1] in " \t":
                    stop -= 1
                if len(text[opened + 1:stop].strip()) >= self._SHORTEST:
                    yield opened, stop
                elif text[opened] == '"' and (opened == 0 or text[opened - 1].isspace()) \
                        and re.search(r"[^\W_]", text[opened + 1:stop]):
                    taken.add(opened)     # a stray straight mark before a few words ('a stray " here'): no quote

    def _regex_spans(self, text: str):
        for m in _QUOTE_REGEX.finditer(text):
            start, end = m.span()
            if text[end - 1] not in self._DOUBLE:     # left open: like a pairing's, it stops before a citation
                cite = self._CITATION.search(text, start, end)
                end = cite.start() if cite else end
                while end > start and text[end - 1] in " \t":
                    end -= 1
                if len(text[start + 1:end].strip()) < self._SHORTEST:
                    continue
            yield start, end

    def _cued(self, text: str, m: re.Match) -> bool:
        """Whether a single-quoted passage reads as a quote: a verb of saying,
        "put it" or "call it" among the three words before it ("One user wrote
        '...'", "As one user put it, '...'"), a speaker and a colon right before
        it ("One user: '...'"), or a citation or a source tag right after it."""
        before = text[max(0, m.start() - 80):m.start()].split("\n\n")[-1]
        if self._CUE_COLON.search(before):
            return True
        words = [w.lower() for w in re.findall(r"[^\W\d_]+", before)[-3:]]
        if any(w in self._CUE_WORDS for w in words) or any(p in self._CUE_PAIRS for p in zip(words, words[1:])):
            return True
        return bool(self._CITED_NEXT.match(text, m.end()))

    def _after_closes(self, text: str, spans: list[tuple[int, int]]):
        """(start, end, the quote before) of the words right after a quote's
        closing mark that has a letter from A to Z or a digit right after it,
        emphasis marks aside ('... Another wrote ”OCBC will ...'; in Chinese,
        where no space follows a closing mark, a character does): such a mark may
        be the next quote's opening mark, taken as this one's close (validation,
        5 Oct 2026: '“my rate went up to 5" in one post. Another wrote ”...' hid
        the second quote). They run to the next double quote mark but an inch
        mark, or to the end of the line, stopping before a citation, and count
        from ten characters, as any quote does, so a word in quote marks inside a
        quote ('"What do you think of "DBS Robot" with the fees?"') makes none.
        The checks read them as a quote only after a quote that is itself
        unverified, or where they end where a quote may end
        (_ToolCallTracker.quotes_to_check)."""
        for s, e in spans:
            if text[e - 1] not in self._DOUBLE or not self._LATIN_NEXT.match(text, e):
                continue
            mark = next((m for m in self._MARK.finditer(text, e) if not _INCH_MARK.match(text, m.start())), None)
            line_end = text.find("\n", e)
            stop = min(x for x in (mark.start() if mark else len(text), line_end, len(text)) if x >= 0)
            cite = self._CITATION.search(text, e, stop)
            stop = cite.start() if cite else stop
            while stop > e and text[stop - 1] in " \t":
                stop -= 1
            if len(text[e:stop].strip()) >= self._SHORTEST:
                yield e, stop, (s, e)

    def _layout(self, text: str) -> tuple[list[tuple[int, int]], set, dict]:
        """The quotes' (start, end) in text order, the marks short pairs took, and
        for the words after a closing mark (_after_closes) the quote before them."""
        taken: set = set()
        spans = list(self._regex_spans(text))
        gaps = zip([0] + [e for _, e in spans], [s for s, _ in spans] + [len(text)])
        spans += [p for s, e in gaps if s < e for p in self._paired(text, s, e, taken)]
        after = {(s, e): before for s, e, before in self._after_closes(text, sorted(spans))}
        spans += list(after)
        for m in _SINGLE_QUOTE.finditer(text):
            words = len(m.group(0)[1:-1].split())
            if not (words >= self._SINGLE_WORDS or (words >= self._SINGLE_CUED_WORDS and self._cued(text, m))):
                continue
            inside = [(s, e) for s, e in spans if s < m.end() and m.start() < e]
            if all(m.start() <= s and e <= m.end() for s, e in inside):
                # 'He said "..." and ...', as quoted in Britain: the outer quote is checked whole
                spans = [x for x in spans if x not in inside] + [(m.start(), m.end())]
        return sorted(spans), taken, after

    def finditer(self, text: str | None):
        text = text or ""
        spans, _, after = self._layout(text)
        for s, e in spans:
            yield self._Span(text, s, e, after.get((s, e)))

    def search(self, text: str | None):
        return next(self.finditer(text), None)

    def findall(self, text: str | None) -> list[str]:
        return [m.group(0) for m in self.finditer(text)]

    # What may stand between a quote's closing mark and a stray mark after it:
    # spaces, punctuation and emphasis marks, around one citation or numbered marker.
    _STRAY_BETWEEN = re.compile(r"[ \t.,;:!?*_]*(?:(?:\[[A-Z]+, \d{4}-\d{2}-\d{2}, sentence_id [0-9a-f]{24}\]"
                                r"|\[\d{1,3}(?:[ \t]*[,–-][ \t]*\d{1,3})*\])[ \t.,;:!?*_]*)?")
    _STRAY_AFTER = re.compile(r"[ \t.,;:!?*_)\]]*(?:\n|\Z)")     # nothing but punctuation to the line end

    def _stray_after_a_quote(self, text: str, i: int, spans: list[tuple[int, int]]) -> bool:
        """Whether the mark at i, with no letter or digit after it on its line,
        stands right after a quote's closing mark on that line, or after a
        citation right after one ('"..." [DBS, 2026-09-01, sentence_id ...]."',
        '"...""'): a stray mark, as nothing stands between them for it to close
        or open (validation, 5 Oct 2026: such a mark took a correct line)."""
        if not self._STRAY_AFTER.match(text, i + 1):
            return False
        ends = [e for _, e in spans if e <= i and text[e - 1] in self._DOUBLE]
        return bool(ends) and bool(self._STRAY_BETWEEN.fullmatch(text, max(ends), i))

    def loose(self, text: str | None) -> list[int]:
        """Positions of the double quote marks the detectors couldn't place: not
        a mark of a quote found, nor inside one, nor one of the two marks around
        a word in quote marks ('"buy"', '”ok”', '»ok«'), nor a stray straight
        mark before a few words at the end of a paragraph, nor a stray mark at
        the end of its line right after a quote's closing mark or a citation
        after one (_stray_after_a_quote), nor an inch mark. Such a mark may
        belong to a quote the detectors missed, so the checks count it as
        evidence they can't verify."""
        text = text or ""
        spans, taken, _ = self._layout(text)
        marks = [m.start() for m in self._MARK.finditer(text)]
        out = [i for i in marks if i not in taken and not _INCH_MARK.match(text, i)
               and not any(s <= i < e for s, e in spans) and not self._stray_after_a_quote(text, i, spans)]
        pairs = {"\u201d": "\u201d", "\u00bb": "\u00ab"}
        short = set()
        for i, j in zip(marks, marks[1:]):
            if i in out and j in out and pairs.get(text[i]) == text[j] and "\n" not in text[i:j] \
                    and len(text[i + 1:j].strip()) < self._SHORTEST and self._word_in_marks(text, i, j) \
                    and not (j + 1 < len(text) and text[j + 1].isalnum()):
                short.update((i, j))
        return [i for i in out if i not in short]


_QUOTE_PATTERN = _QuoteSpans()
_QUOTE_MARKS = "\"\u201c\u201d\u00ab\u00bb\u201e\u201f'\u2018\u2019"
# A markdown blockquote line ("> OCBC has the worst app..."): quoted text without quote marks.
# A line opening with a label and a colon ("> **Note:** ...") is the model's own
# aside, not quoted evidence (4 Oct 2026: notes were flagged as invented quotes).
_BLOCKQUOTE = re.compile(r"^[ \t]*>[ \t]*(?![*_]*[A-Z][\w ]{0,20}[*_]*:)(\S.{9,})$", re.MULTILINE)
_SENTENCE_ID_PATTERN = re.compile(r"sentence[_\s]?id", re.IGNORECASE)
_SENTENCE_ID = re.compile(r"\b[0-9a-f]{24}\b")
# A bare numbered marker ("[2]", "[2, 3]", "[2-3]"), as the reader sees citations once
# number_citations has run. The model cites by copying cite_as, so a marker in its own text
# came from an earlier answer it was shown, or was made up, and points at no source of this
# turn. It is dropped rather than flagged (flagging it flagged real quotes beside it), and
# ignored when a quote is compared with what was retrieved: one stored sentence has a "[1]"
# footnote in it. Found in validation, 4 Oct 2026.
_BARE_MARK = re.compile(r"[ \t]*\[[1-9]\d{0,2}(?:[ \t]*[,–-][ \t]*[1-9]\d{0,2})*\]")

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


def _norm_text(text: str, keep_marks: bool = False) -> str:
    """Lower case, straight quotes and apostrophes, single spaces and, unless
    keep_marks, no bare numbered markers: how quoted text is compared."""
    text = (text or "") if keep_marks else _BARE_MARK.sub("", text or "")
    text = text.replace("’", "'").replace("‘", "'")
    for mark in "“”„‟":
        text = text.replace(mark, '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def _drop_bare_marks(text: str, sources: list[str] | None = None, dropped: list[str] | None = None) -> str:
    """The text without bare numbered markers. Inside quote marks one may be
    part of the sentence quoted: kept there, or, given the retrieved sentences,
    kept only if the quote with its marker is in one of them. A drop that
    leaves a new marker ("[1[2]]" leaves "[1]") is repeated until none is left
    (validation, 4 Oct 2026: the leftover crashed the turn); `dropped`, if
    given, collects every marker dropped."""
    def quote(span: str) -> str:
        if sources is None or any(_norm_text(span.strip(_QUOTE_MARKS), keep_marks=True) in s for s in sources):
            return span
        return _BARE_MARK.sub("", span)

    def once(text: str) -> str:
        out, last = [], 0
        for m in _QUOTE_PATTERN.finditer(text):
            out += [_BARE_MARK.sub("", text[last:m.start()]), quote(m.group(0))]
            last = m.end()
        return "".join(out) + _BARE_MARK.sub("", text[last:])

    text = text or ""
    while (shorter := once(text)) != text:
        if dropped is not None:     # the markers before less those after; one a drop made counts when it goes
            dropped += (Counter(m.strip() for m in _BARE_MARK.findall(text))
                        - Counter(m.strip() for m in _BARE_MARK.findall(shorter))).elements()
        text = shorter
    return text


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


# Fields left out of what the model reads (4 Oct 2026). Each costs prompt
# tokens, and so seconds on a local model whose 4,096-token window also holds
# the system prompt, without helping an answer: counts give way to the shares
# worked out from them, links and ids reach the reader through the numbered
# sources, and the notes explain fields the model is told not to work from.
# The turn's record keeps them all, for the checks and the source list.
# A link stays: the hosted backends' filter (chatbot/backends/base.py) knows a
# Reddit post that came through a news feed only by its reddit.com link, and
# hiding links let such text reach Gemini (caught by
# tests/test_validate_gemini_reddit_privacy.py, 4 Oct 2026).
_HIDDEN_FROM_MODEL = frozenset({
    "sentence_id", "evidence_id", "relevance",
    "positive_n", "neutral_n", "negative_n",
    "recent_7d_unshrunk_score", "baseline_30d_unshrunk_score", "delta_basis", "series_note",
})


def _for_model(obj):
    if isinstance(obj, dict):
        return {k: _for_model(v) for k, v in obj.items() if k not in _HIDDEN_FROM_MODEL}
    if isinstance(obj, list):
        return [_for_model(v) for v in obj]
    return obj


# Fields whose words a model may put in quote marks without citing anything.
# On 4 Oct a reading written as "clearly positive" was taken for an invented
# quote and removed, leaving "with a reading of." in the answer.
# Only wording the code writes counts: a topic name the model could set by
# passing its own text as the aspect would let it quote anything (found in
# validation, 4 Oct 2026), so a topic name counts only if it is a real one.
_WORDING_KEYS = frozenset({"reading", "topic_name", "source_name", "trend_in_words", "month_on_month"})
_TOPIC_NAMES = frozenset(_norm_text(name) for name in [*aspect_taxonomy.labels().values(), "overall"])


def _collect_wording(obj, out: set[str], key=None) -> None:
    if isinstance(obj, str):
        if key in _WORDING_KEYS and (key != "topic_name" or _norm_text(obj) in _TOPIC_NAMES):
            out.add(_norm_text(obj).strip(" .,;:"))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _collect_wording(v, out, k)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_wording(v, out, key)


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
        self.evidence: dict[str, dict] = {}       # sentence_id -> what a search returned for it, this turn or earlier
        self.tool_wording: set[str] = set()       # a reading or topic name a tool returned: quoting it cites nothing
        self.dropped_marks: list[str] = []        # bare markers enforcement dropped from the text: their figures are checked
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
                        self.evidence[item["sentence_id"]] = item

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
        return json.dumps(_for_model(result), default=str)

    def _record(self, call: dict) -> None:
        self.calls.append(call)
        _collect_text(call.get("result"), self.retrieved_text)
        _collect_wording(call.get("result"), self.tool_wording)
        if call["name"] == "search_evidence":
            self.search_evidence_called = True
            if isinstance(call.get("result"), dict):
                for item in call["result"].get("results", []):
                    if item.get("url"):
                        self.verified_urls.add(_norm_url(item["url"]))
                    if item.get("sentence_id"):
                        self.verified_sentence_ids.add(item["sentence_id"])
                        self.evidence[item["sentence_id"]] = item

    def quote_unverified(self, inner: str, strict: bool = False) -> bool:
        """Whether a quote's text (without its marks) is one neither this turn's
        tools nor an earlier turn's search returned. A quote cut with an ellipsis
        counts if each piece of three or more words was returned, each compared
        without the punctuation and spaces at its ends, so a sentence quoted with
        a comma inside the closing mark ('"...night,"') or without its full stop
        is the same quote (validation, 5 Oct 2026: one was removed as invented).
        A quote with no such piece can't be checked: `strict` counts it as
        unverified."""
        if _norm_text(inner).strip(" .,;:") in self.tool_wording:
            return False      # 'a reading of "clearly positive"': the tool's own words, not evidence
        known = self.retrieved_text + self.earlier_text
        pieces = [p.strip(" .,;:!?") for p in re.split(r"\.{3}|…", _norm_text(inner))]
        pieces = [p for p in pieces if len(p.split()) >= 3]
        if not pieces:
            return strict
        return not all(any(p in t for t in known) for p in pieces)

    def quotes_to_check(self, answer: str):
        """The quotes in quote marks the checks read: every one found, but the
        words after a closing mark (_QuoteSpans._after_closes) only where the
        quote before them is not one a search returned (quote_unverified,
        strict: a quote too short to check counts as unverified), or where they
        end where a quote may end, before a citation or a mark that reads as a
        closing one (_QuoteSpans._glued_end: '“...”OCBC will cut its dividend
        next year for sure" [...]."', or with an inch mark, '... by 5"'). After
        a quote a search returned, this turn or an earlier one, they are
        otherwise the model's own words, glued to the mark (validation, 5 Oct
        2026: 'One user: “...”DBS also scored 0.31.' lost its last sentence in
        strip mode)."""
        text = answer or ""
        for m in _QUOTE_PATTERN.finditer(text):
            if m.after is not None and _QUOTE_PATTERN._glued_end(text, m.start() - 1) is None and \
                    not self.quote_unverified(text[m.after[0]:m.after[1]].strip(_QUOTE_MARKS), strict=True):
                continue
            yield m

    def unverified_quotes(self, answer: str, strict: bool = False) -> list[str]:
        """Quotes in the answer (in quote marks, or a markdown blockquote line)
        whose text is unverified (quote_unverified)."""
        spans = [(m.group(0), m.group(0).strip(_QUOTE_MARKS)) for m in self.quotes_to_check(answer)]
        spans += [(m.group(0), m.group(1)) for m in _BLOCKQUOTE.finditer(answer or "")]
        return [span for span, inner in spans if self.quote_unverified(inner, strict)]

    def unverified_urls(self, answer: str) -> list[str]:
        return [u for u in _URL_PATTERN.findall(answer or "")
                if _norm_url(u) not in self.verified_urls]

    def known_ids(self) -> set[str]:
        return self.verified_sentence_ids | self.earlier_ids

    def answer_has_unverified_citation(self, answer: str) -> bool:
        if self.unverified_urls(answer):
            return True
        # A quote mark the quote detectors couldn't place may belong to a quote
        # they missed: evidence that can't be verified, with or without a search.
        if _QUOTE_PATTERN.loose(answer):
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
    """CHATBOT_ENFORCE_EVIDENCE: off, strip (the default, config/chatbot.yaml) or search."""
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


# Strip runs again on its own result until nothing changes, as removing a quote
# can leave a mark or a quote behind; whatever is left after the last pass is
# flagged by the check that follows.
_STRIP_PASSES = 10


def _loose_lines(text: str) -> set[int]:
    """The numbers of the lines holding a quote mark the detectors couldn't place."""
    return {text.count("\n", 0, i) for i in _QUOTE_PATTERN.loose(text)}


def _without_loose_lines(text: str) -> str:
    """The text without each line holding a quote mark the detectors couldn't
    place, with that line's citation: what it quotes can't be checked."""
    lines = _loose_lines(text)
    if not lines:
        return text
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line for k, line in enumerate(text.split("\n")) if k not in lines))


def _unverified_runs(text: str, tracker: "_ToolCallTracker") -> list[str]:
    """The unverified quotes in quote marks, as text to remove. Two or more of
    them on one line with no verified quote between them go as one stretch,
    the words between them too: words between two invented quotes may be a
    third whose marks the detectors read as the others' (validation, 5 Oct
    2026)."""
    runs: list[tuple[int, int]] = []
    open_run = False
    for m in tracker.quotes_to_check(text):
        if not tracker.quote_unverified(m.group(0).strip(_QUOTE_MARKS)):
            open_run = False
            continue
        if open_run and "\n" not in text[runs[-1][1]:m.start()]:
            runs[-1] = (runs[-1][0], m.end())
        else:
            runs.append((m.start(), m.end()))
        open_run = True
    return [text[s:e] for s, e in runs]


def _strip_unverified(answer: str, tracker: "_ToolCallTracker") -> str:
    """After a search: the answer without each line holding a quote mark the
    detectors couldn't place, then without the quotes, links and sentence ids
    no search returned and the words between two such quotes on one line;
    again on the result, until nothing changes. The lines go first, as read in
    the model's own text: a mark that removing a quote would let the detectors
    place is still one they couldn't place where the model wrote it. So are
    the words glued to a closing mark that read as a quote there
    (_ToolCallTracker.quotes_to_check): they go too, though the line of the
    mark that may close them went first ('“...”OCBC will cut ...' and a lone
    mark on the next line)."""
    text = answer
    for _ in range(_STRIP_PASSES):
        glued = [m.group(0) for m in tracker.quotes_to_check(text)
                 if m.after is not None and tracker.quote_unverified(m.group(0).strip(_QUOTE_MARKS))]
        cleaned = _without_loose_lines(text)
        quotes = _unverified_runs(cleaned, tracker) + glued
        quotes += [m.group(0) for m in _BLOCKQUOTE.finditer(cleaned) if tracker.quote_unverified(m.group(1))]
        cleaned = _remove_spans(cleaned, quotes + tracker.unverified_urls(cleaned),
                                unverified_sentence_ids(cleaned, tracker.known_ids()))
        if cleaned == text:
            break
        text = cleaned
    return text


def _strip_unsearched_once(answer: str) -> tuple[str, bool]:
    """One pass of strip_unsearched_evidence, and whether it found a line holding
    a quote mark the detectors couldn't place."""
    loose = _loose_lines(answer)
    head, _, rest = answer.partition("\n\n")
    head_lines = head.split("\n")
    head = _remove_inline("\n".join(line for k, line in enumerate(head_lines) if k not in loose))
    kept, skipping = [], False
    for k, line in enumerate(rest.split("\n"), start=len(head_lines) + 1):
        if _EVIDENCE_HEADING.match(line):
            skipping = True
            continue
        if skipping and _SECTION_HEADING.match(line):
            skipping = False
        if skipping or k in loose or _URL_PATTERN.search(line) or _QUOTE_PATTERN.search(line) \
                or _BLOCKQUOTE.search(line) or _SENTENCE_ID_PATTERN.search(line):
            continue
        kept.append(line)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return head.rstrip() + ("\n\n" + body if body else ""), bool(loose)


def strip_unsearched_evidence(answer: str) -> str:
    """The answer without the evidence a model wrote without searching: the
    evidence section (from its heading to the next known section), any later
    line carrying a quote, URL or sentence id, any line holding a quote mark
    the detectors couldn't place, and any quote, URL or id inside the first
    paragraph, which is otherwise kept as written; again on the result, until
    nothing changes."""
    text, dropped = answer, False
    for _ in range(_STRIP_PASSES):
        cleaned, loose = _strip_unsearched_once(text)
        dropped = dropped or loose
        if cleaned == text:
            break
        text = cleaned
    return text.lstrip("\n") if dropped else text


def _harness_search(tracker: _ToolCallTracker, question: str) -> str:
    """Real quotes for the bank(s) and aspect the model looked up, searched by the harness."""
    banks, aspect = [], None
    for c in tracker.calls:
        args = c.get("arguments") or {}
        if c["name"] == "compare_banks":
            banks = list(BANK_NAMES)
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


def _drop_marks_noted(text: str, tracker: _ToolCallTracker) -> str:
    """_drop_bare_marks, noting on the tracker the markers it dropped, so their
    figures are still checked; a marker removed with its evidence isn't one
    (validation, 4 Oct 2026: such a marker drew a warning about a number the
    reader couldn't see)."""
    return _drop_bare_marks(text, dropped=tracker.dropped_marks)


def enforce_evidence(answer: str, tracker: _ToolCallTracker, question: str, mode: str) -> tuple[str, bool]:
    """(new answer, whether the model's own text still cites unretrieved evidence).
    With no search made, the answer's evidence goes (and in search mode the
    harness finds real quotes); after a search, only the quotes and links the
    searches didn't return go. Answers citing nothing unretrieved pass unchanged,
    but for the bare numbered markers the model wrote outside quotes, which go
    last: the checks read the model's own text, so a marker can't hide the
    quote beside it (validation, 4 Oct 2026: dropping it first left '"..."-',
    which no longer read as a quote)."""
    if mode == "off":
        return answer, tracker.answer_has_unverified_citation(answer)
    if not tracker.answer_has_unverified_citation(answer):
        return _drop_marks_noted(answer, tracker), False
    if tracker.search_evidence_called:
        # The whole answer at once: a quote can wrap onto the next line, and an
        # invented sentence id must go too (4 Oct 2026: both survived).
        cleaned = _drop_marks_noted(_strip_unverified(answer, tracker), tracker)
        return cleaned + EVIDENCE_UNMATCHED_NOTE, tracker.answer_has_unverified_citation(cleaned)
    stripped = _drop_marks_noted(strip_unsearched_evidence(answer), tracker)
    still_flagged = tracker.answer_has_unverified_citation(stripped)  # checked before any harness search
    found = _harness_search(tracker, question) if mode == "search" else ""
    return stripped + (found or EVIDENCE_REMOVED_NOTE), still_flagged


# A citation as search_evidence's cite_as writes it: "[OCBC, 2026-09-02, sentence_id 32e5...]".
_CITE_AS = re.compile(r"\[[A-Z]+, \d{4}-\d{2}-\d{2}, sentence_id ([0-9a-f]{24})\]")


def _cited_date(date: str | None) -> str:
    try:
        d = datetime.strptime(date or "", "%Y-%m-%d")
    except ValueError:
        return date or "undated"
    return f"{d.day} {d:%b %Y}"


def number_citations(answer: str, tracker: _ToolCallTracker) -> str:
    """For the reader (4 Oct 2026: answers showed "[OCBC, 2023-08-01, sentence_id
    32e585f5...]" inline): each citation of a sentence a search returned
    becomes "[1]", "[2]" ..., with the numbered sources listed under the
    answer. It runs after the checks, which read the model's own text; a
    citation no search returned is left as written, and was flagged. A bare
    marker the model wrote itself is dropped first, in every mode, so it can't
    be read as one of these numbers; inside a quote it stays only if the
    sentence quoted has it (one stored sentence has a "[1]" footnote)."""
    order: list[str] = []

    def number(m: re.Match) -> str:
        sid = m.group(1)
        if sid not in tracker.evidence:
            return m.group(0)
        if sid not in order:
            order.append(sid)
        return f"[{order.index(sid) + 1}]"

    body, sep, warnings = answer.partition("\n\n⚠️")
    sources = [_norm_text(e.get("text"), keep_marks=True) for e in tracker.evidence.values()]
    body = _CITE_AS.sub(number, _drop_bare_marks(body, sources))
    if not order:
        return body + sep + warnings
    body = re.sub(r"\(?\bcite_as:?\s*(\[\d+\])\)?", r"\1", body)   # "(cite_as: [1])", the field's name copied too
    lines = []
    for i, sid in enumerate(order, start=1):
        e = tracker.evidence[sid]
        where = f"{e.get('source_name') or source_label(e.get('source'))}, {e.get('bank')}, {_cited_date(e.get('date'))}"
        url = e.get("url") or ""
        if url.startswith("file:"):           # a results report stored on this machine: its name, not its path
            url = os.path.basename(url)
        lines.append(f"- [{i}] {where}" + (f": {url}" if url else ""))
    return body.rstrip() + "\n\nSources:\n" + "\n".join(lines) + sep + warnings


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
        if enforced != _drop_bare_marks(answer):      # evidence went, not only a stray marker
            if verbose:
                logger.warning("evidence written without a search was removed (%s)", mode)
            result.evidence_enforced = mode
        answer = result.answer = enforced

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
    # A marker read as plain numbers ("[12-45]" is 12 and 45, not 12 and -45),
    # and one dropped from the answer checked all the same, so a figure in
    # brackets can't escape the check (validation, 4 Oct 2026). A citation
    # marker is a single digit, which is never checked.
    body = answer.split(EVIDENCE_FOUND_HEADING)[0]
    checked = _BARE_MARK.sub(lambda m: " " + re.sub(r"\D+", " ", m.group(0)) + " ", body)
    checked += "".join("\n" + re.sub(r"\D+", " ", g) for g in tracker.dropped_marks)
    figures = unverified_numbers(checked, [c.get("result") for c in tracker.calls if c.get("by") != "harness"],
                                 question)
    if figures:
        if verbose:
            logger.warning("number check failed: %s not returned by any tool", figures)
        result.unverified_numbers = figures
        result.answer += UNVERIFIED_NUMBER_WARNING.format(
            figures=", ".join(figures), them="it" if len(figures) == 1 else "them")
    result.answer = number_citations(result.answer, tracker)
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
    model_answer: the text before the first warning the harness appends, without
    the numbered markers and the list of sources the reader saw. Neither can be
    checked on a later turn, which has no record of the searches behind them
    (found in validation, 4 Oct 2026)."""
    text = answer.split("\n\n⚠️")[0].split("\n\nSources:\n")[0]
    return _BARE_MARK.sub("", text)


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
                self.state["banks"] = list(BANK_NAMES)
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
