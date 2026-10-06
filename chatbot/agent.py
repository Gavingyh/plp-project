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

import html
import json
import os
import re
import sys
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from datetime import datetime

from dotenv import load_dotenv

from chatbot.backends import get_backend
from config import aspect_taxonomy
from config.sources import label as source_label
from config.logging_config import get_logger, setup_logging
from chatbot import intent as intents
from chatbot import progress
from chatbot import settings
from chatbot.guards import _ABBREVIATION, is_evidence_text_key, unverified_numbers, unverified_sentence_ids
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
    marks none of them could place (validation, 5 Oct 2026: a quote holding an
    inch mark ran on to the next quote's opening mark, and left that quote
    outside every span), which the replay counts.

    With glued=False the words glued to a closing mark are never a quote: a
    word in quote marks stays one whatever follows it, and no words after a
    closing mark are read as a quote (_opens_glued, _after_closes). Strip mode
    reads quotes so (DESIGN decision 26): such words are the model's own, and
    taking off the quote marks around them (_demark) does what removing them
    as a quote did, without removing correct text (the ninth validation, 5 Oct
    2026). Since the twelfth round (6 Oct 2026) off mode flags what strip mode
    changes, so the other reading decides only which numbered markers inside
    a quote stay (_drop_bare_marks) and what the replay counts."""

    def __init__(self, glued: bool = True):
        self.glued = glued

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
        "OCBC"', '"buy-now"s offer') it only closes a word in quote marks.
        Never with glued=False."""
        if not self.glued:
            return False
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
        after = {(s, e): before for s, e, before in self._after_closes(text, sorted(spans))} if self.glued else {}
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

    def loose(self, text: str | None) -> list[int]:
        """Positions of the double quote marks the detectors couldn't place: not
        a mark of a quote found, nor inside one, nor one of the two marks around
        a word in quote marks ('"buy"', '”ok”', '»ok«'), nor a stray straight
        mark before a few words at the end of a paragraph, nor an inch mark.
        Such a mark may belong to a quote the detectors missed. Until the ninth
        validation (5 Oct 2026) it flagged the answer and took its line in
        strip mode; now taking off the quote marks strip mode can't vouch for
        (_demark) covers it, and only the replay counts these
        (scripts/replay_checks.py). The rule that placed a stray mark at the
        end of its line after a quote, from f511f83, went: it hid an opening
        mark there and the invented quote it opened on the next line."""
        text = text or ""
        spans, taken, _ = self._layout(text)
        marks = [m.start() for m in self._MARK.finditer(text)]
        out = [i for i in marks if i not in taken and not _INCH_MARK.match(text, i)
               and not any(s <= i < e for s, e in spans)]
        pairs = {"\u201d": "\u201d", "\u00bb": "\u00ab"}
        short = set()
        for i, j in zip(marks, marks[1:]):
            if i in out and j in out and pairs.get(text[i]) == text[j] and "\n" not in text[i:j] \
                    and len(text[i + 1:j].strip()) < self._SHORTEST and self._word_in_marks(text, i, j) \
                    and not (j + 1 < len(text) and text[j + 1].isalnum()):
                short.update((i, j))
        return [i for i in out if i not in short]


_QUOTE_PATTERN = _QuoteSpans()
_STRIP_QUOTES = _QuoteSpans(glued=False)       # how strip mode reads quotes (decision 26)
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
# A citation as cite_as writes it, inside a passage: not part of what is quoted.
_CITE_IN_TEXT = re.compile(r"\[[A-Z]+, \d{4}-\d{2}-\d{2}, sentence_id [0-9a-f]{24}\]")
# What is trimmed from the ends of each piece of a quoted passage before it is
# looked up: spaces, punctuation, markdown emphasis and quote marks (_PIECE_ENDS,
# with every mark strip mode reads, below).

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


def _returned_in(passage: str, texts: list[str]) -> bool:
    """Whether one of these retrieved texts (normalised, as _collect_text
    keeps them) holds the passage word for word: every piece of it, cut at an
    ellipsis, without citations, numbered markers and the punctuation, quote
    marks and emphasis at its ends, in that one text, in order, each as whole
    words (_whole_words_at)."""
    norm = _norm_text(_CITE_IN_TEXT.sub(" ", passage or ""))
    pieces = [p for p in (p.strip(_PIECE_ENDS) for p in re.split(r"\.{3}|…", norm)) if p]
    for text in texts if pieces else ():
        at = 0
        for p in pieces:
            at = _whole_words_at(text, p, at)
            if at < 0:
                break
            at += len(p)
        else:
            return True
    return False


# A word as the figure check reads one: a run of letters and digits, with an apostrophe
# inside it ("bank's"), the rest of a number ("0.54", "1,234", "2026-09-25") and a per cent
# sign after a digit ("37%").
_FIGURE_WORD = re.compile(r"[^\W_]+(?:['\u2019][^\W_]+)*(?:[-.,/:][^\W_]+)*(?:(?<=\d)%)?")
# Words too common to tie a figure to a sentence (the eleventh validation, 6 Oct 2026: "37% of
# the" in a retrieved "Around 37% of the bank's profit ..." vouched for "37% of the posts").
_COMMON_WORDS = frozenset("the of a an in on at to for and or per cent percent is was were are by with from "
                          "about around".split())
_FIGURE_NEAR = 3                # how many words on each side of a figure, common words skipped, are its neighbours
_FIGURE_SHARED = 2              # how many of them the retrieved sentence must have round the same figure
_ELLIPSIS = re.compile(r"\.{3}|\u2026")
# Where a retrieved text's sentences part, once _norm_text has made it lower case.
_RETRIEVED_BREAK = re.compile(r"[.!?;](?=\s)|\.{3}|\u2026")


def _figure_words(text: str, breaks: list[int]) -> list[tuple[str, int, int, int]]:
    """(word, start, end, part) of each word (_FIGURE_WORD), lower case, with
    the number of the stretch between two breaks (sentence starts, ellipses)
    it stands in."""
    out = []
    for m in _FIGURE_WORD.finditer(text):
        out.append((m.group(0).lower().replace("\u2019", "'"), m.start(), m.end(), bisect_right(breaks, m.start())))
    return out


def _neighbours(words: list[tuple[str, int, int, int]], k: int) -> set[str]:
    """The three words nearest words[k] on either side, in its stretch, common
    words (_COMMON_WORDS) skipped: in "the payment was due on 17th" those of
    17th are "due" and "payment", where three words in a row would be "was",
    "due" and "on"."""
    out: set[str] = set()
    for step in (-1, 1):
        j, found = k + step, 0
        while 0 <= j < len(words) and words[j][3] == words[k][3] and found < _FIGURE_NEAR:
            if words[j][0] not in _COMMON_WORDS:
                out.add(words[j][0])
                found += 1
            j += step
    return out


def evidence_figures(answer: str, tool_results) -> list[tuple[int, int]]:
    """(start, end) of each word holding a figure that stands in the answer
    as a retrieved sentence in these tool results writes it: at least two of
    the three words nearest it on either side in its sentence, common words
    skipped ("the", "of", "per cent" and the like, _COMMON_WORDS), are among
    the three nearest the same figure, so counted, in one retrieved sentence;
    an ellipsis parts the words on its two sides. Or it stands inside a passage in quote
    marks, or a blockquote, that one retrieved text holds word for word
    (_returned_in) and that holds two or more words besides its figures,
    common words aside. The figure check (chatbot/guards.py) takes such a
    figure for that sentence's own; any other figure must match a numeric
    field (the tenth validation, 6 Oct 2026: the "37" of a retrieved "I paid
    37 dollars in fees" vouched for "37 negative posts"; the eleventh: three
    words in a row such as "37% of the" vouched for "37% of the posts"). The
    caller reads the answer as the checks do (_decoded_marks)."""
    texts: list[str] = []
    _collect_text(tool_results, texts)
    if not texts or not any(ch.isdigit() for ch in answer):
        return []
    retrieved = [_figure_words(t, [m.end() for m in _RETRIEVED_BREAK.finditer(t)]) for t in texts]
    breaks = sorted(_sentence_starts(answer) + [m.start() for m in _ELLIPSIS.finditer(answer)])
    words = _figure_words(answer, breaks)
    quoted = []         # passages a search returned word for word, with two or more words besides figures
    for s, e, _ in _shown_passages(answer):
        inner = [w for w, ws, we, _ in words if s <= ws and we <= e]
        if len({w for w in inner if not any(ch.isdigit() for ch in w)} - _COMMON_WORDS) >= _FIGURE_SHARED \
                and _returned_in(answer[s:e], texts):
            quoted.append((s, e))
    out = []
    for k, (w, s, e, _) in enumerate(words):
        if not any(ch.isdigit() for ch in w):
            continue
        if any(qs <= s and e <= qe for qs, qe in quoted):
            out.append((s, e))
            continue
        near = _neighbours(words, k)
        if len(near) < _FIGURE_SHARED:
            continue
        if any(rw == w and len(near & _neighbours(rwords, j)) >= _FIGURE_SHARED
               for rwords in retrieved for j, (rw, _, _, _) in enumerate(rwords)):
            out.append((s, e))
    return out


class _ToolCallTracker:
    """Records what search_evidence actually returned, so the final answer can
    be checked against what was truly retrieved - not what the model claims.
    Also keeps a general call log (every tool, its arguments, and its result),
    used by chatbot/eval_gold_set.py to check whether the model called the
    tool a question actually calls for."""

    def __init__(self, earlier: list[dict] | None = None):
        self.on_step = None                      # progress callback (chatbot/progress.py), or None
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
        progress.notify(self.on_step, progress.describe_call(name, tool_input, result))
        if by == "model":
            progress.notify(self.on_step, progress.Step("think", "Reading the results and writing the answer", done=False))
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

    def shown_verified(self, passage: str) -> bool:
        """Whether a passage may stand in quote marks once strip mode has run
        (DESIGN decision 26): the tools' own wording (a reading, a real topic
        name: tool_wording), or text a search returned, this turn or an
        earlier one: every piece of it, cut at an ellipsis, of any length,
        without citations, numbered markers and the punctuation, quote marks
        and emphasis at its ends, in one retrieved text, in order, each as
        whole words (_whole_words_at: "... impressive" is no piece of
        "unimpressive", "... 5%" none of "15%"; the tenth round, 6 Oct 2026).
        Stricter than quote_unverified, which lets pieces under three words
        pass after a search and takes each piece from any text."""
        if _norm_text(_CITE_IN_TEXT.sub(" ", passage or "")).strip(" .,;:") in self.tool_wording:
            return True
        return _returned_in(passage, self.retrieved_text + self.earlier_text)

    def quotes_to_check(self, answer: str, pattern: "_QuoteSpans | None" = None):
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
        strip mode). Strip mode passes _STRIP_QUOTES, which reads no such words."""
        text, pattern = answer or "", pattern or _QUOTE_PATTERN
        for m in pattern.finditer(text):
            if m.after is not None and pattern._glued_end(text, m.start() - 1) is None and \
                    not self.quote_unverified(text[m.after[0]:m.after[1]].strip(_QUOTE_MARKS), strict=True):
                continue
            yield m

    def unverified_quotes(self, answer: str, strict: bool = False, pattern: "_QuoteSpans | None" = None) -> list[str]:
        """Quotes in the answer (in quote marks, or a markdown blockquote line,
        read without its citations and the marks at its ends, _quoted_line, as
        strip mode reads it) whose text is unverified (quote_unverified)."""
        spans = [(m.group(0), m.group(0).strip(_QUOTE_MARKS)) for m in self.quotes_to_check(answer, pattern)]
        spans += [(m.group(0), _quoted_line(m.group(1))) for m in _BLOCKQUOTE.finditer(answer or "")]
        return [span for span, inner in spans if self.quote_unverified(inner, strict)]

    def unverified_urls(self, answer: str) -> list[str]:
        return [u for u in _URL_PATTERN.findall(answer or "")
                if _norm_url(u) not in self.verified_urls]

    def known_ids(self) -> set[str]:
        return self.verified_sentence_ids | self.earlier_ids

    def _unretrieved_ids(self, answer: str) -> bool:
        """A link or sentence id no search returned; with no search this turn, a
        sentence_id reference without a retrieved id ("[insert sentence_id]"),
        or a numbered evidence marker ("[E1]", "[E1, E2]"), which points at no
        retrieved sentence (the eleventh validation, 6 Oct 2026)."""
        if self.unverified_urls(answer) or unverified_sentence_ids(answer, self.known_ids()):
            return True
        if self.search_evidence_called:
            return False
        if _EVIDENCE_MARKER.search(answer or ""):
            return True
        mentions = len(_SENTENCE_ID_PATTERN.findall(answer or ""))
        return mentions > len([i for i in _SENTENCE_ID.findall(answer or "") if i in self.earlier_ids])

    def cites_unretrieved(self, answer: str, pattern: "_QuoteSpans | None" = None) -> bool:
        """Whether the answer cites evidence no search returned: a link or a
        sentence id, or a quote the detectors find (pattern; _QUOTE_PATTERN by
        default) that no search returned. No search this turn: evidence is real
        only if an earlier turn's search returned it, word for word. Otherwise
        any quote, and any sentence_id reference without a retrieved id (a
        placeholder like "[insert sentence_id]"), is fabricated: both were seen
        in real answers."""
        if self._unretrieved_ids(answer):
            return True
        return bool(self.unverified_quotes(answer, strict=not self.search_evidence_called, pattern=pattern))

    def answer_has_unverified_citation(self, answer: str) -> bool:
        """Whether strip mode would change the answer, as the model wrote it:
        the flag in `off` mode, which changes no answer, and which so raises
        exactly what strip mode would remove or take off, and no more (the
        eleventh validation, 6 Oct 2026: a blockquote a search returned, with
        its citation, was flagged, and strip kept it). That is evidence no search
        returned (a quote, link or sentence id, an evidence marker with no
        search), quote marks a search doesn't vouch for (a passage of three or
        more words a search didn't return word for word, whatever shape its
        marks take; DESIGN decision 26), and a citation that would vouch for
        such words or for a word or two in quote marks no search returned. A
        word or two in quote marks that no citation vouches for ('rated
        "buy"'), an inch mark ('a 6" phone'), an apostrophe, a quote a search
        returned and a bare numbered marker strip mode drops raise none. Line
        endings and character references are read as strip mode reads them
        (_decoded_marks)."""
        text = _decoded_marks(answer)
        stripped, _ = _strip_evidence(text, self, note=False)
        return _demark(stripped, self, original=text) != _drop_bare_marks(text)

    def shows_unverified(self, answer: str) -> bool:
        """After strip mode: whether the answer still shows evidence no search
        returned: a link or sentence id, or a passage a reader sees quoted
        (_shown_passages) that isn't one. Strip leaves none, by construction:
        this is the flag strip mode returns. It reads the whole answer, before
        the harness adds anything."""
        text = _decoded_marks(answer)
        return self._unretrieved_ids(text) or bool(_unshown(text, self))

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
    for q in (quotes if quotes is not None else _STRIP_QUOTES.findall(text)):
        text = text.replace(q, "")
    if quotes is None:
        text = _BLOCKQUOTE.sub("", text)
    for u in (urls if urls is not None else _URL_PATTERN.findall(text)):
        text = text.replace(u, "")
    for sid in ids or []:
        text = re.sub(rf"(?:sentence[_\s]?id[:\s]*)?{sid}", "", text, flags=re.IGNORECASE)
    if quotes is None:
        text = re.sub(r"\[?[^\[\]\n]{0,40}sentence[_\s]?id[^\[\]\n]{0,40}\]?", "", text, flags=re.IGNORECASE)
        text = _EVIDENCE_MARKER.sub("", text)
    text = re.sub(r"\(\s*\)|\[\s*\]|\*\*|\*(?=\W)|(?<=\W)\*", "", text)
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


_CITATION_MARK = re.compile(r"\[E\d+\]|\[[^\[\]\n]*sentence[_\s]?id[^\[\]\n]*\]", re.IGNORECASE)
# A numbered evidence marker ("[E1]"), or a run or list of them ("[E1][E2]", "[E1], [E2]",
# "[E1, E2]"): with no search made it cites nothing, and goes with the evidence (the eleventh
# round, 6 Oct 2026: one stayed after words whose quote marks went with the quotes around
# them; the eleventh validation: runs and lists of them stayed, unflagged).
_E_MARK = r"\[E\d+(?:[ \t]*[,–-][ \t]*E?\d+)*\]"
_EVIDENCE_MARKER = re.compile(rf"[ \t]*{_E_MARK}(?:[ \t]*(?:[,;&/]|\band\b)?[ \t]*{_E_MARK})*", re.IGNORECASE)


def _remove_spans(text: str, spans: list[str], ids: list[str]) -> str:
    """Remove these quotes, links and sentence ids, editing only the lines they
    are on: the rest of the answer keeps its markdown (4 Oct 2026: a whole-answer
    tidy-up took bold and bullets from correct lines). A removed quote's own
    citation mark ("[E9]") goes with it, and so does a backslash right before
    it, which escaped its opening mark in markdown ('\\"...'); a line left empty
    goes too."""
    mark = "\x00"
    for span in sorted(set(spans), key=len, reverse=True):      # a quote may wrap a line
        # Where a reader may read a removed quote's mark as opening the words after it, no
        # citation may vouch for those words (the eleventh round, 6 Oct 2026). The opening
        # mark of a quote left open that the detectors end at the next quote, which it opens
        # too, stays, for _demark to take off with such a citation; and after a closing mark
        # with words glued to it ('...”analysts say ... [1]') the citation that ends them on
        # that line, before any other quote mark, goes with the quote. The words stay: strip
        # mode reads words glued to a closing mark as the model's own (DESIGN decision 26).
        if _ANY_MARK.match(span) and not _ANY_MARK.match(span[-1]):
            text = re.sub(re.escape(span) + rf"[ \t]*(?=[{re.escape(_DOUBLE_SHOWN + _SINGLE_SHOWN)}])",
                          lambda m: span[0], text)
        elif _ANY_MARK.match(span[-1]):
            text = re.sub(re.escape(span) + rf"(?=[*_`]*[^\W_])([^\n{re.escape(_DOUBLE_SHOWN + _SINGLE_SHOWN)}]*?)"
                          rf"[ \t]*(?:{_CITATION})", lambda m: span + m.group(1), text, flags=re.IGNORECASE)
        # A quote that wraps a line leaves its line breaks, and what opens each line after them
        # ("1. ", "- ", "> "): the lines around it stay apart, so removing it brings no citation
        # next to words of another line (the eleventh round, 6 Oct 2026).
        gap = mark + "".join("\n" + (lead.group(0) if (lead := _LIST_LEAD.match(line)) else "") + mark
                             for line in span.split("\n")[1:])
        text = text.replace("\\" + span, gap).replace(span, gap)
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
# can leave a quote behind.
_STRIP_PASSES = 10


def _unverified_runs(text: str, tracker: "_ToolCallTracker") -> list[str]:
    """The unverified quotes in quote marks, as text to remove, read as strip
    mode reads them (_STRIP_QUOTES). Two or more of them on one line with no
    verified quote between them go as one stretch, the words between them too:
    words between two invented quotes may be a third whose marks the detectors
    read as the others' (validation, 5 Oct 2026)."""
    runs: list[tuple[int, int]] = []
    open_run = False
    for m in tracker.quotes_to_check(text, _STRIP_QUOTES):
        if not tracker.quote_unverified(m.group(0).strip(_QUOTE_MARKS)):
            open_run = False
            continue
        if open_run and "\n" not in text[runs[-1][1]:m.start()]:
            runs[-1] = (runs[-1][0], m.end())
        else:
            runs.append((m.start(), m.end()))
        open_run = True
    return [text[s:e] for s, e in runs]


# --- strip mode shows only quotes a search returned (DESIGN decision 26) ------------
# Nine validations (4 and 5 Oct 2026) each found a quote shape the detectors of
# the day missed or misread. So strip mode no longer relies on finding every
# quote: after it removes the quotes the detectors find and no search returned,
# it takes the quote marks off everything else that a search doesn't vouch for,
# keeping the words. What is left in quote marks is, by construction, text a
# search returned word for word, a word or two ('"buy"'), or the tools' own
# wording; _unshown checks the result as a reader would read its marks.

# Every character a reader may take for a quote mark: those Unicode lists as
# quotation marks (" “ ” « » „ ‟ ⹂ 「 」 『 』 〝 〞 〟 ﹁ ﹂ ﹃ ﹄ ＂ ｢ ｣, and the single
# ' ‘ ’ ‚ ‛ ‹ › ＇), the quotation mark ornaments (❝ ❞ ❠ 🙶 🙷 🙸, and the single
# ❛ ❜ ❟ ❮ ❯) and the double primes (″ ‶). The double ones pair with each other in
# order, as do the single ones, apart from apostrophes (the tenth round, 5 Oct
# 2026: ‹...›, 「...」 and ＂...＂ kept their marks after strip, unflagged).
_DOUBLE_SHOWN = ('"\u201c\u201d\u00ab\u00bb\u201e\u201f\u2e42\u300c\u300d\u300e\u300f\u301d\u301e\u301f'
                 '\ufe41\ufe42\ufe43\ufe44\uff02\uff62\uff63\u275d\u275e\u2760\u2033\u2036'
                 '\U0001f676\U0001f677\U0001f678')
_SINGLE_SHOWN = "'\u2018\u2019\u201a\u201b\u2039\u203a\uff07\u275b\u275c\u275f\u276e\u276f"
# The single marks that may be an apostrophe or a possessive: ' ’ ＇. A left-hand mark
# (‘ ‚ ‹ and the double ones) never is: 'wrote‘the bank will ...’' opens a quote (the
# tenth validation, 6 Oct 2026, found ‘ read as an apostrophe there).
_APOSTROPHES = "'\u2019\uff07"
_INCHES = '"\u2033'                     # double marks that may be an inch mark: " ″
_ANY_MARK = re.compile(f"[{_DOUBLE_SHOWN}{_SINGLE_SHOWN}]")
_PIECE_ENDS = " .,;:!?*_" + _DOUBLE_SHOWN + _SINGLE_SHOWN
# The marks a reader pairs: all the double ones in order, all the single ones in order,
# and, as a reader who pairs only marks that look alike, each family on its own (the
# tenth round, 5 Oct 2026: '‹' read as paired with the possessive in "banks'", while a
# reader sees it open to the end, the invented words after it too).
_READINGS = (_DOUBLE_SHOWN, _SINGLE_SHOWN,
             '"\u201c\u201d\u201e\u201f\uff02\u2033\u2036\u2e42\u275d\u275e\u2760\U0001f676\U0001f677\U0001f678',
             "\u00ab\u00bb", "\u300c\u300d\uff62\uff63\ufe41\ufe42", "\u300e\u300f\ufe43\ufe44",
             "\u301d\u301e\u301f", "'\u2018\u2019\uff07\u201a\u201b", "\u2039\u203a", "\u275b\u275c\u275f",
             "\u276e\u276f")
# A character reference markdown shows as the character ("&quot;", "&#8220;",
# "&ldquo;"): one that shows a quote mark is read as that mark.
_CHAR_REF = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
# Chinese and Japanese are written without spaces: each character counts as a word.
_CJK = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# A line markdown shows as a blockquote ("> ...", "- > ...", "1. - > ...", ">> ..."): its
# lead-in, its ">" marks, and what it quotes.
_QUOTE_LINE = re.compile(r"^([ \t]*(?:(?:[-*+]|\d{1,9}[.)])[ \t]+)*)((?:>[ \t]?)+)(.*)$", re.MULTILINE)
# A line that ends the paragraph a blockquote line opens: a blank line, or, indented
# by at most three spaces, another blockquote line, a bullet, an ordered item numbered
# 1, a heading, a code fence or a rule. Any other line after a blockquote line is shown
# inside the blockquote (markdown's lazy continuation: "> a real quote" and, on the next
# line, "an invented one"; the tenth round, 5 Oct 2026).
_ENDS_LAZY = re.compile(r"[ \t]*$|[ ]{0,3}(?:>|[-*+][ \t]+\S|1[.)][ \t]+\S|#{1,6}(?:[ \t]|$)|```|~~~"
                        r"|(?:[-*_][ \t]*){3,}$)")
# A blockquote line that opens with the label of an aside ("> **Note:** ...") is the
# model's own note, not a quote (4 Oct 2026: notes were flagged as invented quotes).
_ASIDE = re.compile(r"[*_]*(?:notes?|n\.b\.|caveats?|disclaimer|tip|warning|important|reminder|update|aside"
                    r"|summary|takeaways?|bottom line|key points?|context)[*_]*[ \t]*:", re.IGNORECASE)
# Two marks around a word or two are a pair when their styles match: the second
# closes what the first opens ('"buy"', '“fees”', '„Tier 1“', '»DBS«', '‘hold’', '「应用」').
_CLOSES = {'"': '"', "\u201c": "\u201d", "\u201e": "\u201c\u201d", "\u201f": "\u201d", "\u201d": "\u201d",
           "\u00ab": "\u00bb", "\u00bb": "\u00ab\u00bb", "'": "'", "\u2018": "\u2019", "\u2019": "\u2019",
           "\u201a": "\u2018\u2019", "\u201b": "\u2019", "\u2039": "\u203a", "\u203a": "\u2039\u203a",
           "\u300c": "\u300d", "\u300e": "\u300f", "\u301d": "\u301e\u301f", "\ufe41": "\ufe42", "\ufe43": "\ufe44",
           "\uff02": "\uff02", "\uff07": "\uff07", "\uff62": "\uff63", "\u275d": "\u275e", "\u275b": "\u275c",
           "\u2760": "\u275d\u275e", "\u275f": "\u275b\u275c", "\u276e": "\u276f", "\u276f": "\u276e\u276f",
           "\u2033": "\u2033", "\u2036": "\u2033", "\u2e42": "\u201c\u201d",
           "\U0001f676": "\U0001f677", "\U0001f678": "\U0001f676\U0001f677"}


# Line endings other than a line feed: a carriage return, alone or before a line feed,
# which markdown reads as a line ending, and the separators Python's str.splitlines
# breaks a line at (\x0b, \x0c, \x1c to \x1e, \x85, U+2028, U+2029). The checks read
# each as a line feed (the tenth validation, 6 Oct 2026: a blockquote after a lone
# carriage return passed strip mode unflagged).
_LINE_END = re.compile("\r\n?|[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")


def _unix_lines(text: str) -> str:
    """The text with every line ending a line feed (_LINE_END)."""
    return _LINE_END.sub("\n", text or "")


def _decoded_marks(text: str) -> str:
    """The text as the checks read it: every line ending a line feed
    (_unix_lines), and every character reference that markdown shows as a
    quote mark ("&quot;", "&#8220;", "&ldquo;") written as that mark, so that
    strip mode reads the lines and marks a reader sees (the tenth round, 5 Oct
    2026: a quote in "&quot;" marks kept them, unflagged)."""
    text = _unix_lines(text)
    if "&" not in text:
        return text

    def one(m: re.Match) -> str:
        ch = html.unescape(m.group(0))
        return ch if len(ch) == 1 and _ANY_MARK.match(ch) else m.group(0)

    return _CHAR_REF.sub(one, text)


def _word_count(text: str) -> int:
    """Words as a reader counts them: each run of letters and digits, any other
    character between two runs parting them ("OCBC-will-cut" is three words),
    but an apostrophe before a contraction's ending ("OCBC's", "don't") or a
    point, comma, dash, slash or colon between digits ("0.31", "1,234",
    "2026-09-25"); and each Chinese or Japanese character."""
    text = re.sub(r"(?<=[^\W_])['\u2019](?=(?:s|t|d|m|ll|re|ve)(?![^\W_]))", "", text or "", flags=re.IGNORECASE)
    text = re.sub(r"(?<=\d)[-.,/:](?=\d)", "", text)
    return sum(max(1, len(_CJK.findall(w))) for w in re.findall(r"[^\W_]+", text))


def _glued(a: str, b: str) -> bool:
    """Whether two characters side by side are parts of one word: both letters
    or digits, neither a Chinese or Japanese character (each is a word)."""
    return a.isalnum() and b.isalnum() and not (_CJK.match(a) or _CJK.match(b))


_IN_A_NUMBER = "-.,/:"      # between two digits, part of one number ("2.05", "1,234", "2026-09-25")


def _whole_words_at(text: str, piece: str, at: int) -> int:
    """Where piece first stands in text from `at` on as whole words, or -1: no
    letter or digit glued to either of its ends, nor the rest of a number ("2"
    of "2.05%"). A quoted piece is the source's words, not part of one ("...
    impressive" is not in "unimpressive", "... 5%" not in "15%", "the app is
    sl" not in "the app is slow")."""
    while (at := text.find(piece, at)) >= 0:
        end = at + len(piece)
        before, after = text[max(at - 2, 0):at], text[end:end + 2]
        cut_before = _glued(before[-1:], piece[:1]) or (
            piece[:1].isdigit() and len(before) == 2 and before[1] in _IN_A_NUMBER and before[0].isdigit())
        cut_after = _glued(piece[-1:], after[:1]) or (
            piece[-1:].isdigit() and len(after) == 2 and after[0] in _IN_A_NUMBER and after[1].isdigit())
        if not (cut_before or cut_after):
            return at
        at += 1
    return -1


# What may follow an apostrophe inside a word: the ending of a contraction or a
# possessive ("OCBC's", "don't", "we're", "they've").
_CONTRACTION = re.compile(r"(?:s|t|d|m|ll|re|ve)(?![^\W_])", re.IGNORECASE)


_BLANK_LINE = re.compile(r"\n[ \t]*\n")


def _closes_later(text: str, i: int) -> bool:
    """Whether a straight or right-hand single mark later in the paragraph of
    the one at i (up to a blank line: markdown shows a paragraph's lines as
    one, and the eleventh validation, 6 Oct 2026, found a closing mark on the
    next line missed), after no space and before no letter or digit, could
    close a passage of three or more words that the one at i opens."""
    blank = _BLANK_LINE.search(text, i + 1)
    end = len(text) if blank is None else blank.start()
    return any(text[j] in _APOSTROPHES and not text[j - 1].isspace()
               and not (j + 1 < len(text) and text[j + 1].isalnum()) and _word_count(text[i + 1:j]) >= 3
               for j in range(i + 1, end))


def _mark_role(text: str, i: int) -> str:
    """What the quote mark at i is to a reader. "inch": a straight double mark
    or a double prime after a digit, before no letter or digit ('a 6" phone').
    "apostrophe": a straight or right-hand single mark (' ’ ＇) between
    two letters or digits, unless it opens a quote glued to the word before:
    where a capital follows it and two letters stand before it ("wrote'OCBC
    ..."; after one letter it is a name's, "Côte d'Ivoire"), or where neither
    a capital nor a contraction or possessive ending follows it ("don't",
    "OCBC's") and a mark later in its paragraph could close a passage of three
    or more words after it ("wrote'the bank will cut its dividend next year'";
    the tenth validation, 6 Oct 2026, found it read as an apostrophe). A
    left-hand mark (‘) is never one. "possessive": a straight or right-hand single mark
    after an s, before no letter or digit ("the banks' fees", "DBS' app"): it
    closes a quote open before it and opens none. Anything else: "quote"."""
    prev = text[i - 1] if i > 0 else ""
    nxt = text[i + 1] if i + 1 < len(text) else ""
    if text[i] in _INCHES:
        return "inch" if prev.isdigit() and not nxt.isalnum() else "quote"
    if text[i] not in _APOSTROPHES:
        return "quote"
    if prev.isalnum() and nxt.isalnum():
        if nxt.isupper() and prev.isalpha() and i >= 2 and text[i - 2].isalpha():
            return "quote"
        if nxt.isupper() or _CONTRACTION.match(text, i + 1) or not _closes_later(text, i):
            return "apostrophe"         # "Côte d'Ivoire", "OCBC's", "don't"
        return "quote"
    if prev and prev in "sS" and not nxt.isalnum():
        return "possessive"
    return "quote"


def _short_pair(text: str, a: int, b: int) -> bool:
    """Two marks on one line, in matching styles, around a word or two, with no
    space just inside either: '"buy"', not the gap '" and "' between two quotes."""
    inner = text[a + 1:b]
    return text[b] in _CLOSES.get(text[a], "") and "\n" not in inner and inner[:1].strip() != "" \
        and inner[-1:].strip() != "" and 1 <= _word_count(inner) <= 2


def _verified_pair(text: str, a: int, b: int, tracker: "_ToolCallTracker") -> bool:
    """Two marks in one paragraph around text a search returned, which the
    detectors didn't read as one quote: the second part of a real sentence
    holding a quote of its own ('„What do you think of "DBS Robot" with the
    fees?“', where they find the first part only)."""
    inner = text[a + 1:b]
    return not re.search(r"\n[ \t]*\n", inner) and _word_count(inner) > 0 and tracker.shown_verified(inner)


def _line_start(chars: list[str], i: int) -> int:
    """Where the line holding chars[i] starts."""
    while i > 0 and chars[i - 1] != "\n":
        i -= 1
    return i


def _without_marks(text: str, positions, cuts=(), mapped: bool = False):
    """The text without the marks at these positions, keeping the words, and
    without the spans `cuts` gives as (start, end) (citations, a blockquote's
    ">"); a mark between two words, or after punctuation and before a word,
    gives way to a space ('wrote"OCBC' -> 'wrote OCBC'), and a backslash that
    escaped a mark goes with it. With mapped, also where each character of the
    result stands in the text (a space that replaced a mark: the mark's place)."""
    spans: list[tuple[int, int]] = []
    for s, e in sorted(cuts):
        if spans and s <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(e, spans[-1][1]))
        else:
            spans.append((s, e))

    def cut(j: int) -> bool:
        return any(s <= j < e for s, e in spans)

    marks = [(i, -1) for i in set(positions) if not cut(i)]
    chars, where = list(text), list(range(len(text)))
    # From the end, so each place to the left still holds; what stands right of a mark is
    # final, and what stands left of it is read past the spans still to be cut.
    for i, end in sorted(spans + marks, reverse=True):
        if end >= 0:
            del chars[i:end], where[i:end]
            continue
        if i > 0 and chars[i - 1] == "\\" and not cut(i - 1):
            del chars[i - 1], where[i - 1]          # '\"' is markdown's way to write '"'
            i -= 1
        j = i - 1
        while j >= 0 and cut(j):
            j -= 1
        prev = chars[j] if j >= 0 else ""
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if prev and (prev.isalnum() or prev in ".,;:!?") and nxt.isalnum():
            chars[i] = " "
        elif prev in (" ", "\t") and nxt in (" ", "\t"):
            del chars[i:i + 2], where[i:i + 2]      # 'a stray " here' -> 'a stray here'
        elif prev in (" ", "\t") and nxt in ("\n", "") and j == i - 1 \
                and not _LIST_LEAD.fullmatch("".join(chars[_line_start(chars, i):i])):
            del chars[i - 1:i + 1], where[i - 1:i + 1]   # no space left at a line's end, but after "- "
        else:
            del chars[i], where[i]
    return ("".join(chars), where) if mapped else "".join(chars)


# --- what a citation vouches for: its own sentence (the twelfth round, 6 Oct 2026) -------
# Until the eleventh round strip mode cut only a citation right after a mark it took off, so
# an invented passage that lost its marks kept a real citation after a full stop, a comma, a
# bracket or "one user wrote", and a word or two in quote marks kept theirs and its citation:
# both read as sourced (the tenth validation). The eleventh round let a citation vouch for
# its paragraph or list item back to the citation before it or a quote a search returned;
# the eleventh validation found that cut a correct citation after a scare quote in the
# sentence before ('DBS markets it as a "super app". Users complain ... [1].'), let a
# returned word or two ('"slow" [1]') shield invented words before it, and missed a citation
# before the words it cites ('According to [1], one user called OCBC "a scam".') or written
# as a link. Since the twelfth round a citation vouches for its own sentence (_reach).
# A citation in any form a model writes one: as cite_as writes it or another bracket
# naming a sentence id, a numbered marker ("[1]", "[2, 3]", "[E1]"), or a sentence id
# written bare; and a run of them ("[1][2]", "[1], [2]").
_CITATION = (r"\[[^\[\]\n]*(?:sentence[_\s]?id|\b[0-9a-f]{24}\b)[^\[\]\n]*\]"
             r"|\[E?[1-9]\d{0,2}(?:[ \t]*[,–-][ \t]*E?[1-9]\d{0,2})*\]"
             r"|\bsentence[_\s]?id\b[ \t]*:?[ \t]*[0-9a-f]{24}\b"
             r"|\b[0-9a-f]{24}\b")
_CITATIONS = re.compile(rf"(?:{_CITATION})(?:[ \t]*(?:[,;&/]|\band\b)?[ \t]*(?:{_CITATION}))*", re.IGNORECASE)
# A link, which cites as a citation does ('One user called OCBC "a scam" (https://...)': the
# eleventh validation): a markdown link ("[post](https://...)"), or one written out, with or
# without its scheme, without the punctuation after it.
_LINK = (r"\[[^\[\]\n]{0,80}\]\([ \t]*(?:https?://|www\.)[^\s()]*[ \t]*\)"
         r"|(?:https?://|www\.)[^\s)\]}\"'“”<>]*[^\s)\]}\"'“”<>.,;:!?]"
         r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}/(?:[^\s)\]}\"'“”<>]*[^\s)\]}\"'“”<>.,;:!?])?")
# The citations and links strip mode reads as vouching for words, and runs of them. A link
# is no citation to take out of a passage's words: a retrieved sentence may hold one.
_CITE_RUNS = re.compile(rf"(?:{_CITATION}|{_LINK})(?:[ \t]*(?:[,;&/]|\band\b)?[ \t]*(?:{_CITATION}|{_LINK}))*",
                        re.IGNORECASE)
# A line that opens a block of its own in markdown: a list item, a heading, a table row or
# a code fence. The lines of one paragraph, a blockquote's too, read as one.
_OPENS_BLOCK = re.compile(r"[ \t]*(?:(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)|#{1,6}(?:[ \t]|$)|\||```|~~~)")
_HEADING_LINE = re.compile(r"[ \t]*#{1,6}(?:[ \t]|$)")
_WORD_NEXT = re.compile(r"[*_`]*[^\W_]")         # a letter or digit next, emphasis marks aside
_HAS_WORD = re.compile(r"[^\W_]")
# Around a citation cut: brackets holding nothing else but a label ("(Source: [1])").
_BRACKET_BEFORE = re.compile(r"[ \t]*[(\[（][ \t]*(?:(?:sources?|cite_as|see|ref|via|e\.g\.|eg)[ \t]*[:,]?[ \t]*)?\Z",
                             re.IGNORECASE)
_BRACKET_AFTER = re.compile(r"[ \t]*[)\]）]")
_DASH_BEFORE = re.compile(r"[ \t]+[-–—]\Z")
_LIST_LEAD = re.compile(r"[ \t]*(?:(?:[-*+]|\d{1,9}[.)]|>)[ \t]+)+")    # "- ", "1. ", "- > " at a line's start
_LEAD_OUT = re.compile(r"[ \t]*(?:[:\u2013\u2014-][ \t]*)?")                 # what follows a citation that leads a line
_LABEL_BEFORE = re.compile(r"[ \t]*(?<![^\W_])(?:sources?|cite_as|see|ref|via)[ \t]*:?[ \t]*\Z", re.IGNORECASE)
_LINE_ENDS_NEXT = re.compile(r"[ \t]*(?:\n|\Z)")
_LABEL_ENDS_NEXT = re.compile(r"[ \t]*(?:[.!?;,)\]）]|\n|\Z)")        # what may follow a label left holding nothing
# A label before a citation, which is no word of what it cites ("Source: [1]", "see [1]").
_LABEL = re.compile(r"(?<![^\W_])(?:sources?|cite_as|see|ref|refs|via|cf|e\.g|eg)(?![^\W_])\.?[ \t]*:?", re.IGNORECASE)
# Before a citation, the attribution it completes ("According to [1], ..."), and the words
# that introduce a source: after them the citation vouches for the words that follow it.
_ATTRIBUTION = re.compile(r"(?<![^\W_])(?:according[ \t]+to|as[ \t]+per|per)[ \t]*\Z", re.IGNORECASE)
_INTRODUCES = frozenset({"to", "per", "by", "from", "in", "on", "via", "see", "cf"})
_INTRODUCTION_WORDS = 4
_SENTENCE_START_BEFORE = re.compile(r"(?:\A|\n[ \t]*(?:(?:[-*+]|\d{1,9}[.)]|>)[ \t]+)*|[.!?;][\"'”’»›)\]*_]*[ \t]+)\Z")
_COLON_NEXT = re.compile(r"[ \t]*[*_]*[ \t]*:")
_ENDS_SENTENCE = re.compile(r"[.!?]+|;")
_CLOSERS = "\"'”’»›)]）*_`" + _DOUBLE_SHOWN + _SINGLE_SHOWN


def _block_starts(text: str) -> list[int]:
    """Where each paragraph or block of the text starts: at the text's start,
    at a line after a blank line or a heading, at a line that opens a block
    (_OPENS_BLOCK), and at a blockquote line after a line outside a blockquote
    (markdown starts a blockquote there, ending the paragraph before; the
    eleventh validation: a returned blockquote lost its citation to a line
    above it). The lines of one paragraph, a blockquote's too, are one block."""
    starts, after_break, in_quote = [], True, False
    for s, e in _lines(text):
        line = text[s:e]
        quote = bool(_QUOTE_LINE.match(text, s, e))
        if after_break or _OPENS_BLOCK.match(line) or (quote and not in_quote):
            starts.append(s)
        after_break = not line.strip() or bool(_HEADING_LINE.match(line))
        in_quote = quote or (in_quote and not _ENDS_LAZY.match(line))
    return starts


def _sentence_starts(text: str) -> list[int]:
    """Where each sentence of the text starts, in order: at each block start
    (_block_starts), and after each sentence end: a full stop, "!" or "?" (not
    an ellipsis's points nor an abbreviation's full stop, "vs.", "e.g.", as in
    chatbot.guards._ABBREVIATION), with any closing marks or brackets after it,
    then spaces or a line break and anything but a lower-case letter; or a
    semicolon and a space (it parts two clauses as a full stop does). A single
    line break is no sentence end: markdown shows a paragraph's lines as one."""
    starts = set(_block_starts(text))
    for m in _ENDS_SENTENCE.finditer(text):
        s, e = m.span()
        mark = m.group(0)
        if mark == ";":
            if any(r.end() == e for r in _CHAR_REF.finditer(text, max(0, s - 12), e)):
                continue                                    # "&amp;" is no clause end
        elif mark.count(".") > 1 or text[s - 1:s] == "\u2026" or text[e:e + 1] == "\u2026" \
                or (mark == "." and any(a.end() == e for a in _ABBREVIATION.finditer(text, max(0, s - 6), e))):
            continue                                        # "...", "e.g.", "vs."
        j = e
        while j < len(text) and text[j] in _CLOSERS:
            j += 1
        if j < len(text) and text[j] not in " \t\n":
            continue                                        # "0.31", "U.S"
        k = j
        while k < len(text) and text[k] in " \t\n":
            k += 1
        if k < len(text) and (mark == ";" or not text[k].islower()):
            starts.add(k)
    return sorted(starts)


def _words_before(text: str, lo: int, cs: int) -> list[str]:
    """The words between lo and the citation at cs, without citations, links,
    labels ("Source:") and a list item's lead ("1. ")."""
    if text.rfind("\n", 0, lo) + 1 == lo and (lead := _LIST_LEAD.match(text, lo)) and lead.end() <= cs:
        lo = lead.end()
    return re.findall(r"[^\W_]+", _LABEL.sub(" ", _CITE_RUNS.sub(" ", text[lo:cs])))


def _reach(text: str, cs: int, ce: int, left: list[tuple[int, int]], starts: list[int],
           blocks: set[int]) -> tuple[list[tuple[int, int]], tuple[int, int], bool]:
    """What the citation run at text[cs:ce] vouches for (the twelfth round, 6
    Oct 2026; the eleventh validation found the paragraph too wide and too
    narrow a reach): (start, end) of the stretches before it, of the stretch
    after it, and whether it introduces the words after it. It vouches for its
    own sentence (_sentence_starts), back to the citation before it there and
    on to the one after it (left: the citation runs still standing); and where
    nothing but labels stands before it in its sentence ("... for sure. [1]",
    "... for sure. Source: [1]"), for the sentence before it in its paragraph
    or list item too, back to a citation there. It introduces the words after
    it where no more than four words stand before it in its sentence
    ("According to [1], ...", "In one post [1], ..."), labels and a list item's
    lead aside, and no quote mark right before it, or a word that introduces a
    source does ("as reported by [1], ..."), or a colon follows it ("[1]:
    ..."). After a citation that doesn't introduce them, only words that stood
    in quote marks count, from three words (_unvouched): a word or two there is
    often a term or a scare quote ('Users complain the app is slow at night
    [1], despite the "super app" label.' keeps its citation)."""
    sentence = max((p for p in starts if p <= cs), default=0)
    lo = max([sentence] + [e for s, e in left if sentence <= e <= cs])
    back = [(lo, cs)]
    before = _words_before(text, lo, cs)
    if not before and lo == sentence and sentence not in blocks:
        prev = max((p for p in starts if p < sentence), default=0)
        back.append((max([prev] + [e for s, e in left if prev <= e <= sentence]), sentence))
    after = (ce, min([p for p in starts if p > ce] + [s for s, e in left if s >= ce] + [len(text)]))
    cites_a_quote = _ANY_MARK.match(text[:cs].rstrip(" \t([\uff08")[-1:] or " ")     # '"slow" [1], ...'
    introduces = (not cites_a_quote and (len(before) <= _INTRODUCTION_WORDS or before[-1].lower() in _INTRODUCES)) \
        or bool(_COLON_NEXT.match(text, ce))
    return back, after, introduces


def _vouches_for(words: str, any_length: bool, tracker: "_ToolCallTracker") -> bool:
    """Whether a citation would vouch for these words that stood in quote
    marks, citations aside, and that no search returned: any number of them,
    or with any_length false (after a citation that doesn't introduce them,
    _reach) three or more."""
    words = _CITATIONS.sub(" ", words)
    return bool(_HAS_WORD.search(words)) and (any_length or _word_count(words) >= 3) \
        and not tracker.shown_verified(words)


def _opens_words(text: str, p: int) -> bool:
    """Whether the mark at p opens the words after it: a letter or digit right
    after it, emphasis marks aside, and none right before it."""
    return not (p > 0 and text[p - 1].isalnum()) and bool(_WORD_NEXT.match(text, p + 1))


def _cut_for(text: str, s: int, e: int) -> tuple[int, int]:
    """What goes with the citations at text[s:e]: the spaces before them,
    brackets holding nothing else but a label ("(Source: [1])"), a colon right
    after them ("[1]: ..."), a label left holding nothing ("Source:", "see")
    or a dash left at the end of a line, the attribution they complete at a
    sentence's start, with the comma after them ("According to [1], one user
    ..." -> "one user ..."), and a full stop, comma or colon before them where
    another such mark follows them ('next year›, [1].' -> 'next year.')."""
    line = text.rfind("\n", 0, s) + 1
    if (attribution := _ATTRIBUTION.search(text, max(0, s - 16), s)) \
            and (comma := re.compile(r"[ \t]*,[ \t]*").match(text, e)) \
            and _SENTENCE_START_BEFORE.search(text[:attribution.start()]):
        return attribution.start(), comma.end()
    if not _LIST_LEAD.fullmatch(text, line, s):    # not the space after "- " that makes a list item
        while s > 0 and text[s - 1] in " \t":
            s -= 1
    before, after = _BRACKET_BEFORE.search(text, max(0, s - 24), s), _BRACKET_AFTER.match(text, e)
    if before and after:
        s, e = before.start(), after.end()
        while s < len(text) and text[s] in " \t" and _LIST_LEAD.fullmatch(text, line, s + 1):
            s += 1                                       # '- ([1]) words' keeps its "- "
    if colon := re.match(r"[ \t]*:", text[e:e + 8]):
        e += colon.end()                                # '[1]: words': the colon is the citation's
    if _LABEL_ENDS_NEXT.match(text, e) and (label := _LABEL_BEFORE.search(text, max(0, s - 16), s)):
        s = label.start()                               # '... for sure. Source: [1]' -> '... for sure.'
    if _LINE_ENDS_NEXT.match(text, e) and (dash := _DASH_BEFORE.search(text, max(0, s - 8), s)):
        s = dash.start()
    if _LIST_LEAD.fullmatch(text, line, s) or s == line:
        e = _LEAD_OUT.match(text, e).end()              # '- [1]: words' -> '- words'
    if s > 0 and text[s - 1] in ".,;:" and e < len(text) and text[e] in ".,;:!?":
        s -= 1
    return s, e


def _unreturned_short(text: str, tracker: "_ToolCallTracker") -> list[tuple[int, int]]:
    """(opening, closing) of each word or two in quote marks (_short_pair) in
    the text, its marks paired in order as strip mode pairs them, that no
    search returned (_ToolCallTracker.shown_verified)."""
    marks = [(m.start(), _mark_role(text, m.start())) for m in _ANY_MARK.finditer(text)]
    marks = [(i, role) for i, role in marks if role != "apostrophe"]
    out, k = [], 0
    while k + 1 < len(marks):
        (i, role), (j, after) = marks[k], marks[k + 1]
        if role == "quote" and after in ("quote", "possessive", "inch") and _short_pair(text, i, j):
            if not tracker.shown_verified(text[i + 1:j]):
                out.append((i, j))
            k += 2
            continue
        k += 1
    return out


def _unvouched(text: str, quoted: list[bool], marked: list[bool], tracker: "_ToolCallTracker") -> tuple[list, list]:
    """The citations to cut from the text, as (start, end) spans, and the
    positions of quote marks to take off with them (_vouched_only). quoted[j]:
    whether text[j] stood in quote marks or a blockquote, in words no search
    returned, in what strip mode read; marked[j], whether in quote marks; so do
    words the text shows quoted that no search returned. A citation goes where
    its reach (_reach) holds any such words, a returned word or two or a
    returned quote beside them excusing nothing (the eleventh validation, 6 Oct
    2026: '‹...›, "slow" [1]' kept its citation), or a word or two in quote
    marks no search returned, which loses its marks. After a citation that
    doesn't introduce the words after it, only words that stood in quote
    marks count, from three words: a word or two there is often a term or a
    scare quote, and a line a blockquote joins to the citation's line its
    attribution ('> "..." [1]', then a line naming who wrote it)."""
    runs = [m.span() for m in _CITE_RUNS.finditer(text)]
    if not runs:
        return [], []
    starts, blocks = _sentence_starts(text), set(_block_starts(text))
    passages = [(s, e, kind) for s, e, kind in _shown_passages(text) if _HAS_WORD.search(_CITATIONS.sub(" ", text[s:e]))]
    quoted, marked = list(quoted), list(marked)
    for s, e, kind in passages:         # and words the text itself shows quoted: strip run again changes nothing
        if not tracker.shown_verified(_CITATIONS.sub(" ", text[s:e])):
            quoted[s:e] = [True] * (e - s)
            if kind == "marks":
                marked[s:e] = [True] * (e - s)
    short = _unreturned_short(text, tracker)
    gone: set[int] = set()          # runs cut: they bound no other's words, so look again without them
    while True:
        cuts, marks, cut_now = [], [], set()
        left = [r for k, r in enumerate(runs) if k not in gone]
        for k, (cs, ce) in enumerate(runs):
            cut = k in gone
            back, after, introduces = _reach(text, cs, ce, left, starts, blocks)
            reach = back + ([after] if introduces else [])
            for lo, hi in reach:
                pairs = [(a, b) for a, b in short if lo <= a and b < hi]
                marks += [p for pair in pairs for p in pair]
                cut = cut or bool(pairs)
            for (lo, hi), within in [(span, quoted) for span in reach] + ([] if introduces else [(after, marked)]):
                at = lo
                while at < hi:          # each stretch of words that stood in quote marks
                    if not within[at]:
                        at += 1
                        continue
                    end = at
                    while end < hi and within[end]:
                        end += 1
                    cut = cut or _vouches_for(text[at:end], within is quoted, tracker)
                    at = end
            if cut:
                cuts.append(_cut_for(text, cs, ce))
                cut_now.add(k)
        if cut_now == gone:
            return cuts, marks
        gone = cut_now


def _vouched_only(before: str, after: str, where: list[int], tracker: "_ToolCallTracker",
                  carried: tuple[list[bool], list[bool]] | None = None) -> tuple[str, list[int]]:
    """after, what strip mode made of before (after[j] stands at before[where[j]]),
    without each citation that vouches for words that stood in quote marks in
    before, as a reader pairs them (_shown_passages), and that no search
    returned, or for a word or two in quote marks that no search returned,
    whose marks then go too (the eleventh round, 6 Oct 2026: an invented
    passage that lost its marks kept a real citation after a full stop, a
    comma, a bracket or "one user wrote", and a word or two kept its marks and
    its citation, both reading as sourced). A citation, a link, or a run of
    them ("[1][2]", "[1], [2]"), vouches for its own sentence (_reach, since
    the twelfth round). Read on the result, so whatever the passes took off,
    and in what order, is known; carried, what a reader saw quoted in the
    answer as the model wrote it (_quoted_in), counts too. Also where each
    character of the result stands in after."""
    spans = [(s, e, kind == "marks") for s, e, kind in _shown_passages(before)]
    # A mark taken off that opens no words may close the words before it, back to the mark
    # before it or its paragraph's start ('... next year for sure” [1]', where the opening
    # mark went with a quote before; until the eleventh round strip mode cut a citation right
    # after any mark it took off, unless a stray one right after a quote kept).
    left = {w for j, w in enumerate(where) if after[j] == before[w]}
    marks = [m.start() for m in _ANY_MARK.finditer(before) if _mark_role(before, m.start()) != "apostrophe"]
    for k, p in enumerate(marks):
        if p not in left and not _opens_words(before, p):
            start = max(marks[k - 1] + 1 if k else 0, before.rfind("\n\n", 0, p) + 1)
            spans.append((start, p, True))
    quoted, marked = [False] * len(before), [False] * len(before)      # in quote marks or a blockquote; in marks
    if carried is not None:
        quoted, marked = list(carried[0]), list(carried[1])
    for s, e, in_marks in spans:
        inner = _CITATIONS.sub(" ", before[s:e])
        if _HAS_WORD.search(inner) and not tracker.shown_verified(inner):
            quoted[s:e] = [True] * (e - s)
            if in_marks:
                marked[s:e] = [True] * (e - s)
    kept = list(range(len(after)))      # where each character of the result stands in after
    for _ in range(_STRIP_PASSES):
        same = [after[j] == before[w] for j, w in enumerate(where)]
        cuts, marks = _unvouched(after, [quoted[w] and same[j] for j, w in enumerate(where)],
                                 [marked[w] and same[j] for j, w in enumerate(where)], tracker)
        if not cuts and not marks:
            break
        after, moved = _without_marks(after, marks, cuts, mapped=True)
        where, kept = [where[j] for j in moved], [kept[j] for j in moved]
    return after, kept


def _lines(text: str) -> list[tuple[int, int]]:
    """(start, end) of each line."""
    out, pos = [], 0
    for line in text.split("\n"):
        out.append((pos, pos + len(line)))
        pos += len(line) + 1
    return out


def _blocks(text: str):
    """(start, end) of each line, then of each paragraph: markdown shows the
    lines of a paragraph as one, so a quote mark may pair across them."""
    lines, paragraphs, start = _lines(text), [], None
    for s, e in lines:
        if text[s:e].strip():
            start = s if start is None else start
            last = e
        elif start is not None:
            paragraphs.append((start, last))
            start = None
    if start is not None:
        paragraphs.append((start, last))
    return lines + paragraphs


def _blockquotes(text: str) -> list[tuple[int, int]]:
    """(start, end) of what each blockquote line shows inside its blockquote:
    its own text, and every line after it that markdown joins to it (lazy
    continuation), up to a blank line, another blockquote line or a line that
    opens a block of its own (_ENDS_LAZY); not the text of an aside ("> **Note:**
    ...")."""
    lines, out = _lines(text), []
    for m in _QUOTE_LINE.finditer(text):
        if _ASIDE.match(m.group(3)):
            continue
        end = m.end(3)
        k = next(n for n, (s, _) in enumerate(lines) if s == m.start()) + 1
        while k < len(lines) and not _ENDS_LAZY.match(text, lines[k][0], lines[k][1]):
            end = lines[k][1]
            k += 1
        out.append((m.start(3), end))
    return out


def _pairs(text: str, marks: list[int], roles: dict, hi: int, possessive_closes: bool):
    """(start, end) of the passages these marks show, paired in order, first
    with second, third with fourth: a mark shaped like an inch mark is none
    ('a 6" phone') unless it closes a word or two opened with a straight mark
    ('"Tier 1"'), an apostrophe is none, and a possessive ("banks'") closes a
    passage open before it, if possessive_closes, and opens none; one left
    over opens a passage to hi."""
    out, opened = [], None
    for i in marks:
        role = roles[i]
        if role == "apostrophe" or (role == "possessive" and not possessive_closes):
            continue
        if role == "inch" and not (opened is not None and text[opened] == '"'
                                   and _word_count(text[opened + 1:i]) <= 2):
            continue
        if opened is not None:
            out.append((opened + 1, i))
            opened = None
        elif role != "possessive":
            opened = i
    if opened is not None:
        out.append((opened + 1, hi))
    return out


def _shown_passages(text: str) -> list[tuple[int, int, str]]:
    """(start, end, kind) of every passage a reader sees quoted: "marks" for
    one in quote marks, in each line and in each paragraph (_blocks), and
    "blockquote" for what a blockquote shows (_blockquotes). The marks are
    paired in order (_pairs), as each reading in _READINGS pairs them: all the
    double ones together, all the single ones, and each family of marks that
    look alike on its own; and with a possessive read both ways, as closing a
    passage and as a possessive inside one ("'the banks' fees are high'")."""
    roles = {m.start(): _mark_role(text, m.start()) for m in _ANY_MARK.finditer(text)}
    out = set()
    for lo, hi in _blocks(text):
        here = [i for i in roles if lo <= i < hi]
        for reading in _READINGS:
            marks = [i for i in here if text[i] in reading]
            if not marks:
                continue
            for possessive_closes in ((True, False) if any(roles[i] == "possessive" for i in marks) else (True,)):
                out.update((s, e, "marks") for s, e in _pairs(text, marks, roles, hi, possessive_closes))
    return sorted(out) + [(s, e, "blockquote") for s, e in _blockquotes(text)]


def _unshown(text: str, tracker: "_ToolCallTracker") -> list[tuple[int, int, str]]:
    """The passages a reader sees quoted (_shown_passages) of three or more
    words, citations and numbered markers aside, that are no text a search
    returned (_ToolCallTracker.shown_verified): what strip mode never shows."""
    return [(s, e, kind) for s, e, kind in _shown_passages(text)
            if _word_count(_BARE_MARK.sub(" ", _CITE_IN_TEXT.sub(" ", text[s:e]))) >= 3
            and not tracker.shown_verified(text[s:e])]


def _kept_quotes(text: str, tracker: "_ToolCallTracker") -> list[tuple[int, int]]:
    """(start, end) of each quote the detectors find (_STRIP_QUOTES) whose
    every piece a search returned, or which is the tools' own wording
    (_ToolCallTracker.shown_verified): strip mode keeps its marks. A quote the
    detectors end at a possessive ("'... the banks' busiest week'") may run on
    past it: its marks are left to the pairing in _demark_once, which reads
    past possessives."""
    return [(m.start(), m.end()) for m in _STRIP_QUOTES.finditer(text)
            if tracker.shown_verified(m.group(0).strip(_QUOTE_MARKS)) and _mark_role(text, m.end() - 1) != "possessive"]


def _demark(text: str, tracker: "_ToolCallTracker", original: str | None = None) -> str:
    """The text with the quote marks taken off what a search doesn't vouch for
    (_demark_once), again on the result until nothing changes: the detectors
    can read the marks left in a new way once others are gone, and strip mode
    run again on its own answer changes nothing; then without the citations
    that would vouch for words no search returned (_vouched_only), whether
    they stood in quote marks in the text or, given the answer as the model
    wrote it (original), of which strip mode's first step made the text, in
    that (_quoted_in). A character reference that shows a quote mark is read as
    the mark (_decoded_marks). All of the text is read: the harness adds its
    own evidence only afterwards, so nothing the model wrote passes as the
    harness's (the tenth round, 5 Oct 2026: an answer that wrote the harness's
    heading kept the quote marks after it)."""
    text = _decoded_marks(text)
    before, where = text, list(range(len(text)))
    carried = _quoted_in(_decoded_marks(original), text, tracker) \
        if original is not None and _decoded_marks(original) != text else None
    for _ in range(_STRIP_PASSES):
        for _ in range(_STRIP_PASSES):
            once, moved = _demark_once(text, tracker)
            if once == text:
                break
            text, where = once, [where[j] for j in moved]
        # taking a word or two's marks off with a citation can pair the marks left anew
        vouched, moved = _vouched_only(before, text, where, tracker, carried)
        if vouched == text:
            break
        text, where = vouched, [where[j] for j in moved]
    return text


def _quoted_in(original: str, text: str, tracker: "_ToolCallTracker") -> tuple[list[bool], list[bool]]:
    """For each character of text, which strip mode's first step made of
    original by taking characters out: whether it stands among words that a
    reader saw quoted in original (in quote marks or a blockquote,
    _shown_passages), and that no search returned; and whether in quote marks.
    The words are matched in order (difflib). A removed quote's mark may have
    opened words it leaves standing, and what it took out may have joined
    their sentence to a citation's (the twelfth round, 6 Oct 2026: a
    full stop, a semicolon or a blockquote's ">" between them went with it), so
    the last step reads them as quoted all the same."""
    quoted, marked = [False] * len(text), [False] * len(text)
    ours, theirs = list(re.finditer(r"[^\W_]+", original)), list(re.finditer(r"[^\W_]+", text))
    match: dict[int, int] = {}
    for i, j, n in SequenceMatcher(None, [m.group(0) for m in ours], [m.group(0) for m in theirs],
                                   autojunk=False).get_matching_blocks():
        match.update((i + k, j + k) for k in range(n))
    starts = [m.start() for m in ours]
    for s, e, kind in _shown_passages(original):
        inner = _CITATIONS.sub(" ", original[s:e])
        if not _HAS_WORD.search(inner) or tracker.shown_verified(inner):
            continue
        found = [match[i] for i in range(bisect_left(starts, s), bisect_left(starts, e))
                 if i in match and ours[i].end() <= e]
        if found:
            lo, hi = theirs[min(found)].start(), theirs[max(found)].end()
            quoted[lo:hi] = [True] * (hi - lo)
            if kind == "marks":
                marked[lo:hi] = [True] * (hi - lo)
    return quoted, marked


def _demark_once(head: str, tracker: "_ToolCallTracker") -> tuple[str, list[int]]:
    """The text with the quote marks taken off what a search doesn't vouch for,
    the words kept (DESIGN decision 26), and where each of its characters
    stands in head. Kept as written: each quote the detectors find whose every
    piece a search returned or which is the tools' own wording (_kept_quotes),
    and each blockquote line that is. Kept too: an inch mark, an apostrophe, a
    possessive, two marks on one line in matching styles around a word or two
    with no quote mark between them ('rated "buy"', '“fees”'), and two marks
    with no other between them around text a search returned (_verified_pair).
    Every other quote mark (_ANY_MARK) goes, and every other blockquote ">"
    (but an aside's). Then, as a reader pairs the marks left and joins lines to
    a blockquote (_shown_passages), a line where they show a passage of three
    or more words in quote marks that no search returned (a pair of kept marks
    read across a quote, say) loses all its quote marks but those three kinds,
    and a blockquote line whose blockquote shows such a passage loses its ">";
    again, until none is left. A line left holding nothing goes, so that what
    stood around it stays one paragraph, as it was shown."""
    kept = _kept_quotes(head, tracker)
    marks = []      # (position, role) of each mark outside a kept quote; a kept quote stands in as a barrier
    for m in _ANY_MARK.finditer(head):
        i = m.start()
        quote = next(((s, e) for s, e in kept if s <= i < e), None)
        if quote:
            if not marks or marks[-1] != (quote[0], "kept"):
                marks.append((quote[0], "kept"))
            continue
        role = _mark_role(head, i)
        if role != "apostrophe":
            marks.append((i, role))
    remove, k = set(), 0
    while k < len(marks):
        i, role = marks[k]
        following = marks[k + 1] if k + 1 < len(marks) else (None, None)
        # past possessives, the next mark may close a quote that holds them ("'the banks' fees ...'")
        n = next((n for n in range(k + 1, len(marks)) if marks[n][1] != "possessive"), None)
        if role == "quote" and n is not None and n > k + 1 and marks[n][1] == "quote" \
                and _verified_pair(head, i, marks[n][0], tracker):
            k = n + 1
            continue
        if role == "quote" and following[1] in ("quote", "possessive", "inch") \
                and (_short_pair(head, i, following[0]) or _verified_pair(head, i, following[0], tracker)):
            k += 2          # '"buy"', '"Tier 1"' (its closing mark shaped like an inch mark), "'Investors'"
            continue
        if role == "quote":
            remove.add(i)
            # a single mark's possessive-looking partner closes what it opened ("'long queue times'")
            if head[i] in _SINGLE_SHOWN and following[1] == "possessive" and "\n" not in head[i:following[0]]:
                remove.add(following[0])
                k += 1
        k += 1
    blockquoted = set()     # (start, end) of the ">" marks of each blockquote line no search vouches for
    for m in _QUOTE_LINE.finditer(head):
        shown = _without_marks(m.group(3), [p - m.start(3) for p in remove if m.start(3) <= p < m.end(3)])
        if not (tracker.shown_verified(shown) or _ASIDE.match(m.group(3))):
            blockquoted.add((m.start(2), m.end(2)))
    lines = _lines(head)
    out, where = head, list(range(len(head)))
    for _ in range(2 * head.count("\n") + 4):
        full, moved = _without_marks(head, remove, sorted(blockquoted), mapped=True)
        olds, news, at, keep = head.split("\n"), full.split("\n"), 0, []
        for n, (old, new) in enumerate(zip(olds, news)):
            if new.strip() or not old.strip():
                keep.append((n, at, at + len(new)))
            at += len(new) + 1
        # without the lines left holding nothing, each kept line with the line break after it
        out = "\n".join(full[a:b] for _, a, b in keep)
        where = [w for i, (_, a, b) in enumerate(keep) for w in moved[a:b + (i + 1 < len(keep))]]
        bad = _unshown(out, tracker)
        if not bad:
            break
        marked = {keep[n][0] for s, e, kind in bad if kind == "marks"
                  for n in range(out.count("\n", 0, s), out.count("\n", 0, e) + 1)}
        quoted = {keep[out.count("\n", 0, s)][0] for s, _, kind in bad if kind == "blockquote"}
        before = (len(remove), len(blockquoted))
        remove.update(m.start() for n in marked for m in _ANY_MARK.finditer(head, *lines[n])
                      if _mark_role(head, m.start()) == "quote")
        blockquoted.update((m.start(2), m.end(2)) for m in _QUOTE_LINE.finditer(head)
                           if head.count("\n", 0, m.start()) in marked | quoted)
        if (len(remove), len(blockquoted)) == before:
            break       # nothing left to take off on those lines (_demark runs again on the result)
    return out, where


def _quoted_line(text: str) -> str:
    """What a blockquote line quotes, as it is compared with what was retrieved:
    without citations, and without the quote marks, punctuation and emphasis
    at its ends ('> "..." [DBS, ...].' quotes the sentence in the marks; until
    the tenth round, 5 Oct 2026, such a line was compared whole, marks and
    citation too, and removed as invented)."""
    return _CITE_IN_TEXT.sub(" ", text).strip(_PIECE_ENDS)


def _without_spilled_citations(text: str, quotes: list[str], tracker: "_ToolCallTracker") -> str:
    """The text without each citation that would vouch for words a reader sees
    quoted in it, outside the quotes strip mode removes, and that no search
    returned: the words of a passage (_shown_passages) whose opening or
    closing mark goes with such a quote, but which run on outside it ("'One
    said ‚...‘ invented words', [1]", where the detectors end the quote at ‘;
    the eleventh round, 6 Oct 2026), or of any other passage a reader sees as
    the model wrote it, whose marks, once the quote's go, pair otherwise (the
    twelfth round: '"... ❠What do you think of "DBS Robot" with the 0.5%
    fees?❞ invented words [1], "..."', where the marks in order paired ❞ with
    the mark after the citation). The citation goes where such words, in its
    reach (_reach: its sentence), are no text a search returned; the words
    stay, and the second step (_demark) reads them as the model's own."""
    gone = sorted((m.start(), m.end()) for q in set(quotes) for m in re.finditer(re.escape(q), text))
    if not gone:
        return text

    def inside(p: int) -> bool:
        return any(s <= p < e for s, e in gone)

    spilled = []        # (start, end, in quote marks) of the words of such passages outside the quotes removed
    for s, e, kind in _shown_passages(text):
        at = s
        for gs, ge in [(gs, ge) for gs, ge in gone if ge > s and gs < e] + [(e, e)]:
            if min(gs, e) > at and _HAS_WORD.search(_CITATIONS.sub(" ", text[at:min(gs, e)])):
                spilled.append((at, min(gs, e), kind == "marks"))
            at = max(at, ge)
    if not spilled:
        return text
    starts, blocks = _sentence_starts(text), set(_block_starts(text))
    runs = [m.span() for m in _CITE_RUNS.finditer(text) if not inside(m.start())]   # the others go with their quote
    cuts = []
    for cs, ce in runs:
        back, after, introduces = _reach(text, cs, ce, runs, starts, blocks)    # as _unvouched reads them
        reach = [(span, True) for span in back + ([after] if introduces else [])] + ([] if introduces else [(after, False)])
        if any(_vouches_for(text[max(a, lo):min(b, hi)], any_length, tracker)
               for (lo, hi), any_length in reach for a, b, in_marks in spilled
               if a < hi and b > lo and (any_length or in_marks)):
            cuts.append(_cut_for(text, cs, ce))
    return _without_marks(text, [], cuts) if cuts else text


def _strip_unverified(answer: str, tracker: "_ToolCallTracker") -> tuple[str, bool]:
    """After a search: the answer without the quotes (read as _STRIP_QUOTES
    reads them), blockquote lines, links and sentence ids no search returned,
    and the words between two such quotes on one line; again on the result,
    until nothing changes. And whether anything was removed. enforce_evidence
    then takes the quote marks off whatever a search doesn't vouch for (_demark)."""
    text, removed = answer, False
    for _ in range(_STRIP_PASSES):
        quotes = _unverified_runs(text, tracker)
        quotes += [m.group(0) for m in _BLOCKQUOTE.finditer(text) if tracker.quote_unverified(_quoted_line(m.group(1)))]
        text = _without_spilled_citations(text, quotes, tracker)
        cleaned = _remove_spans(text, quotes + tracker.unverified_urls(text),
                                unverified_sentence_ids(text, tracker.known_ids()))
        if cleaned == text:
            break
        text, removed = cleaned, True
    return text, removed


def _strip_unsearched_once(answer: str) -> str:
    """One pass of strip_unsearched_evidence."""
    head, _, rest = answer.partition("\n\n")
    head = _remove_inline(head)
    kept, skipping = [], False
    for line in rest.split("\n"):
        if _EVIDENCE_HEADING.match(line):
            skipping = True
            continue
        if skipping and _SECTION_HEADING.match(line):
            skipping = False
        if skipping or _URL_PATTERN.search(line) or _STRIP_QUOTES.search(line) \
                or _BLOCKQUOTE.search(line) or _SENTENCE_ID_PATTERN.search(line):
            continue
        kept.append(_EVIDENCE_MARKER.sub("", line))
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return head.rstrip() + ("\n\n" + body if body else "")


def strip_unsearched_evidence(answer: str) -> str:
    """The answer without the evidence a model wrote without searching: the
    evidence section (from its heading to the next known section), any later
    line carrying a quote, URL or sentence id, and any quote, URL or id inside
    the first paragraph, which is otherwise kept as written; again on the
    result, until nothing changes. Quotes are read as strip mode reads them
    (_STRIP_QUOTES); enforce_evidence then takes the quote marks off what is
    left (_demark)."""
    text = answer
    for _ in range(_STRIP_PASSES):
        cleaned = _strip_unsearched_once(text)
        if cleaned == text:
            break
        text = cleaned
    return text


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
    """(new answer, whether the answer still cites unretrieved evidence).
    `off` changes nothing and flags an answer that cites evidence no search
    returned or stands anything in quote marks a search doesn't vouch for
    (answer_has_unverified_citation). `strip` and `search` (DESIGN decision 26):
    with no search made, the answer's evidence goes (and in search mode the
    harness finds real quotes); after a search, only the quotes, links and ids
    the searches didn't return go, and a note says so. Then, either way, the
    quote marks come off whatever a search doesn't vouch for, the words staying,
    and so does each citation that would vouch for such words (_demark), so
    what is left in quote marks is text a search returned word for word, a
    word or two, or the tools' own wording; the flag is then
    whether anything shown still isn't (shows_unverified), which strip leaves
    nothing to raise. A character reference markdown shows as a quote mark
    ("&quot;") is read, and left, as that mark, and every line ending as a
    line feed, which the answer returned keeps (_decoded_marks); the harness's
    own text is added after all this. Bare numbered markers the model wrote outside quotes go
    after the quotes no search returned and before the marks come off: the
    checks read the model's own text, so a marker can't hide the quote beside
    it (validation, 4 Oct 2026: dropping it first left '"..."-', which no
    longer read as a quote), and strip run on its own answer changes nothing."""
    if mode == "off":
        return answer, tracker.answer_has_unverified_citation(answer)
    text, removed = _strip_evidence(_decoded_marks(answer), tracker)
    cleaned = _demark(text, tracker, original=answer)
    flagged = tracker.shows_unverified(cleaned)       # checked before any harness search
    if tracker.search_evidence_called:
        return cleaned + (EVIDENCE_UNMATCHED_NOTE if removed else ""), flagged
    if not removed:
        return cleaned, flagged
    found = _harness_search(tracker, question) if mode == "search" else ""
    return cleaned + (found or EVIDENCE_REMOVED_NOTE), flagged


def _strip_evidence(answer: str, tracker: _ToolCallTracker, note: bool = True) -> tuple[str, bool]:
    """Strip mode before the quote marks come off: the answer without the
    evidence no search returned, and its bare numbered markers; and whether any
    evidence went. After a search, the quotes, links and ids no search returned
    (_strip_unverified), the whole answer at once: a quote can wrap onto the
    next line, and an invented sentence id must go too (4 Oct 2026: both
    survived). With no search, the answer's evidence (strip_unsearched_evidence)
    if it cites any no search returned, as read by _STRIP_QUOTES. With note,
    the markers dropped are noted on the tracker (_drop_marks_noted), so their
    figures are checked; off mode, which only asks what strip would change,
    notes none."""
    drop = (lambda text: _drop_marks_noted(text, tracker)) if note else _drop_bare_marks
    if tracker.search_evidence_called:
        cleaned, removed = _strip_unverified(answer, tracker)
        return drop(cleaned), removed
    if not tracker.cites_unretrieved(answer, _STRIP_QUOTES):
        return drop(answer), False
    return drop(strip_unsearched_evidence(answer)), True


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
    evidence_enforced: str | None = None     # "strip" or "search" if CHATBOT_ENFORCE_EVIDENCE removed evidence


def answer_turn(question: str, backend_name: str | None = None, history: list | None = None,
                state: dict | None = None, verbose: bool = True, backend=None,
                earlier_calls: list | None = None, on_step=None) -> TurnResult:
    """One turn: the answer and everything behind it. on_step, if given, is
    called with each step as it happens (chatbot/progress.py), for a display
    of the turn's working while the reader waits."""
    previous = next((h["content"] for h in reversed(history or []) if h.get("role") == "user"), None)
    progress.notify(on_step, progress.Step("read", "Reading your question", done=False))
    intent = intents.classify_intent(question, state, previous)
    reply = intents.reply_for(intent, question, state)
    if reply:
        if verbose:
            logger.info("intent %s: answered with its fixed reply", intent)
        progress.notify(on_step, progress.Step("intent", "Answered with a set reply",
                                               _FIXED_REPLY_KIND.get(intent, "a question this assistant doesn't answer")))
        progress.notify(on_step, progress.Step("done", "Done"))
        return TurnResult(question=question, answer=reply, guard=intent, intent=intent)
    progress.notify(on_step, progress.Step("intent", "Understood the question"))

    backend = backend or get_backend(backend_name)
    if verbose:
        logger.info("backend: %s (%s)", backend.name, getattr(backend, "model", "?"))

    tracker = _ToolCallTracker(earlier_calls)
    tracker.on_step = on_step
    progress.notify(on_step, progress.Step("think", "Deciding what to look up, then writing the answer", done=False))
    answer = backend.ask(question, with_state(SYSTEM_PROMPT, state), TOOL_SCHEMAS,
                         tracker.execute, verbose=verbose, history=history)
    progress.notify(on_step, progress.Step("check", "Checking quotes and figures against the data", done=False))
    if not (answer or "").strip(" \n{}[]\"'"):
        # An empty answer, or a bare "{}" from a model that tried to emit a tool call
        # as text. The replacement is the harness's own text, so it skips the checks.
        progress.notify(on_step, progress.Step("done", "Done", "the model gave no answer"))
        return TurnResult(question=question, answer=EMPTY_ANSWER_REPLY, calls=tracker.calls)
    result = TurnResult(question=question, answer=answer, calls=tracker.calls, intent=intent)

    mode = enforce_evidence_mode()
    enforced, flagged = enforce_evidence(answer, tracker, question, mode)
    if enforced != answer:
        # Evidence went, not only a stray marker or the quote marks around the model's own words.
        plain = _drop_bare_marks(_decoded_marks(answer))
        if enforced not in (plain, _demark(plain, tracker)):
            if verbose:
                logger.warning("evidence no search returned was removed (%s)", mode)
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
    progress.notify(on_step, progress.Step("check", "Checked quotes and figures", _check_summary(result)))
    progress.notify(on_step, progress.Step("done", "Done"))
    return result


# What a set reply answered, for the progress display.
_FIXED_REPLY_KIND = {"advice": "an investment-advice question", "other_bank": "a bank this assistant doesn't cover",
                     "greeting": "a greeting", "thanks": "thanks", "goodbye": "a goodbye",
                     "help": "a question about what this assistant does", "service": "a banking-service request",
                     "injection": "a request to change the assistant's instructions",
                     "feedback": "feedback", "off_topic": "an off-topic question"}


def _check_summary(result: TurnResult) -> str:
    """One line on what the checks did to this answer."""
    notes = []
    if result.evidence_enforced:
        notes.append("removed quotes no search returned")
    if result.citation_unverified:
        notes.append("flagged evidence it couldn't confirm")
    if result.unverified_numbers:
        notes.append("flagged " + ", ".join(result.unverified_numbers))
    return "; ".join(notes) if notes else "everything matches what the tools returned"


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

    def ask(self, question: str, verbose: bool = False, on_step=None) -> TurnResult:
        earlier = [c for t in self.turns[-HISTORY_TURNS:] for c in t.calls if c.get("name") == "search_evidence"]
        r = answer_turn(question, backend_name=self.backend_name, history=self.history(),
                        state=self.state, verbose=verbose, earlier_calls=earlier, on_step=on_step)
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
