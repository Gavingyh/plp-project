"""
What a reader sees quoted, for the tests of strip mode (DESIGN decision
26). Since then a test of an invented quote passes when strip mode removed it,
flagged the answer, or left the invented words outside quote marks: the model's
own words, no longer shown as evidence.

Written apart from chatbot/agent.py, which reads its own output the same way
(_shown_passages), so that each checks the other. A reader sees the answer as
markdown shows it: a character reference ("&quot;", "&#8220;") as the mark it
stands for, and a carriage return, alone or before a line feed, as a line end
(so are the other separators Python breaks lines at, U+2028 among them, to be
safe). Then the quote marks are paired in order, in each line and in each
paragraph (markdown shows the lines of a paragraph as one):

- double marks (" “ ” « » „ ‟ ⹂ 「 」 『 』 〝 〞 〟 ﹁ ﹂ ﹃ ﹄ ＂ ｢ ｣ ❝ ❞ ❠ ″ ‶ 🙶 🙷 🙸):
  first with second, third with fourth. A straight mark or a double prime after
  a digit and before no letter or digit is an inch mark ('a 6" phone'), unless
  it closes a word or two opened with a straight mark ('"Tier 1"'). A mark left
  over opens a passage that runs to the end.
- single marks (' ‘ ’ ‚ ‛ ‹ › ＇ ❛ ❜ ❟ ❮ ❯) alike, but a straight or right-hand
  mark (' ’ ＇) between two letters or digits is an apostrophe ("don't",
  "OCBC's") unless it opens a quote glued to the word before: a capital
  follows it with two letters before it ("wrote'OCBC"; after one letter it is
  a name's, "Côte d'Ivoire"), or neither a capital nor a contraction or possessive
  ending follows it and a straight or right-hand mark later in its paragraph
  closes three or more words after it ("wrote'the bank will cut its dividend
  next year'", on one line or two). Such a mark after an s and before no letter or digit
  ("the banks' fees") opens nothing: read once as closing a passage open
  before it, once as a possessive inside it. A left-hand mark (‘) is neither
  (the eleventh round).
- and, as a reader who pairs only marks that look alike, each family of marks
  on its own (" “ ” „ ‟ ＂ ″ ‶ ⹂ ❝ ❞ ❠; « »; 「 」 ｢ ｣; ' ‘ ’ ＇ ‚ ‛; ‹ ›; ❮ ❯; ...).
- a blockquote line ("> ...", "- > ...", "1. - > ...") quotes what follows its
  marks, and every line after it that markdown joins to it: up to a blank line
  or, indented by at most three spaces, another blockquote line, a bullet, an
  item numbered 1, a heading, a code fence or a rule. Not when it opens with
  the label of an aside ("> **Note:** ...").

Words are runs of letters and digits; an apostrophe before a contraction's
ending ("OCBC's", "don't") and a point, comma, dash, slash or colon between
digits ("0.31", "2026-09-25") part none, and each Chinese or Japanese character
is a word.

Test data only: no model, no network, no data/plp.db.
"""

import html
import re

DOUBLE = set('"“”«»„‟⹂「」『』〝〞〟﹁﹂﹃﹄＂｢｣❝❞❠″‶\U0001f676\U0001f677\U0001f678')
SINGLE = set("'‘’‚‛‹›＇❛❜❟❮❯")
MAY_BE_APOSTROPHE = set("'’＇")         # a left-hand mark (‘) never is one
MAY_BE_INCH = set('"″')
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")
_REFERENCE = re.compile(r"&(#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
_BLOCKQUOTE = re.compile(r"^[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)*(?:>[ \t]?)+(.*)$")
_NOT_JOINED = re.compile(r"^(?:[ \t]*$|[ ]{0,3}(?:>|[-*+][ \t]+\S|1[.)][ \t]+\S|#{1,6}(?:[ \t]|$)|```|~~~"
                         r"|(?:[-*_][ \t]*){3,}$))")
_ASIDE = re.compile(r"[*_]*(note|notes|n\.b\.|caveat|caveats|disclaimer|tip|warning|important|reminder|update|aside"
                    r"|summary|takeaway|takeaways|bottom line|key point|key points|context)[*_]*[ \t]*:", re.IGNORECASE)


def as_shown(text: str) -> str:
    """The text with each character reference that stands for a quote mark
    written as that mark, as markdown shows it, and each line ending a line
    feed."""
    def one(m):
        ch = html.unescape(m.group(0))
        return ch if ch in DOUBLE or ch in SINGLE else m.group(0)
    text = re.sub("\r\n|[\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]", "\n", text or "")
    return _REFERENCE.sub(one, text)


def words(text: str) -> int:
    """Runs of letters and digits; an apostrophe before a contraction's ending
    and a point, comma, dash, slash or colon between digits part none; a
    Chinese or Japanese character is a word of its own."""
    text = re.sub(r"(?<=\w)['’](?=(s|t|d|m|ll|re|ve)\b)", "", text or "", flags=re.IGNORECASE)
    text = re.sub(r"(?<=\d)[-.,/:](?=\d)", "", text)
    count = 0
    for run in re.findall(r"[^\W_]+", text):
        count += max(1, len(_CJK.findall(run)))
    return count


def _single_kind(text: str, i: int) -> str:
    if text[i] not in MAY_BE_APOSTROPHE:
        return "mark"
    before = text[i - 1] if i > 0 else " "
    after = text[i + 1] if i + 1 < len(text) else " "
    if before.isalnum() and after.isalnum():
        if after.isupper() and before.isalpha() and i > 1 and text[i - 2].isalpha():
            return "mark"
        if after.isupper() or re.match(r"(s|t|d|m|ll|re|ve)(?![^\W_])", text[i + 1:], re.IGNORECASE):
            return "apostrophe"         # "Côte d'Ivoire", "don't", "OCBC's"
        blank = re.compile(r"\n[ \t]*\n").search(text, i)     # to the paragraph's end: its lines show as one
        for j in range(i + 1, len(text) if blank is None else blank.start()):
            closes = text[j] in MAY_BE_APOSTROPHE and not text[j - 1].isspace() \
                and not (j + 1 < len(text) and text[j + 1].isalnum())
            if closes and words(text[i + 1:j]) >= 3:
                return "mark"           # "wrote'the bank will cut ... next year'"
        return "apostrophe"
    if before in "sS" and not after.isalnum():
        return "possessive"
    return "mark"


def _inch(text: str, i: int) -> bool:
    return text[i] in MAY_BE_INCH and i > 0 and text[i - 1].isdigit() \
        and not (i + 1 < len(text) and text[i + 1].isalnum())


# Families of marks that look alike: a reader may pair only these with each other.
FAMILIES = ['"“”„‟＂″‶⹂❝❞❠\U0001f676\U0001f677\U0001f678', "«»", "「」｢｣﹁﹂", "『』﹃﹄", "〝〞〟",
            "'‘’＇‚‛", "‹›", "❛❜❟", "❮❯"]


def _paired(text: str, lo: int, hi: int, marks, possessive_closes: bool) -> list[tuple[int, int]]:
    """(start, end) of the passages these marks show in text[lo:hi], paired in
    order: from just after the opening mark to the closing mark, or to hi."""
    out, start = [], None
    for i in range(lo, hi):
        if text[i] not in marks:
            continue
        if text[i] in DOUBLE:
            if _inch(text, i):
                closes_a_word = start is not None and text[start] == '"' and words(text[start + 1:i]) <= 2
                if not closes_a_word:
                    continue
            kind = "mark"
        else:
            kind = _single_kind(text, i)
            if kind == "apostrophe" or (kind == "possessive" and not possessive_closes):
                continue
        if start is not None:
            out.append((start + 1, i))
            start = None
        elif kind == "mark":
            start = i
    if start is not None:
        out.append((start + 1, hi))
    return out


def _passages_in(text: str, lo: int, hi: int) -> list[tuple[int, int]]:
    """Every way a reader may pair the marks here: all the double ones in order,
    all the single ones, each family on its own; a possessive read both as
    closing a passage and as a possessive inside one."""
    out = []
    for marks in [DOUBLE, SINGLE] + [set(f) for f in FAMILIES]:
        for possessive_closes in (True, False):
            out += _paired(text, lo, hi, marks, possessive_closes)
    return out


def _blockquoted(lines: list[str]) -> list[str]:
    """What each blockquote line shows inside its blockquote: its own text and
    the lines markdown joins to it."""
    out = []
    for k, line in enumerate(lines):
        m = _BLOCKQUOTE.match(line)
        if not m or _ASIDE.match(m.group(1)):
            continue
        shown = [m.group(1)]
        for later in lines[k + 1:]:
            if _NOT_JOINED.match(later):
                break
            shown.append(later)
        out.append("\n".join(shown))
    return out


def marked_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) in as_shown(text) of every passage a reader sees in quote
    marks, line by line and paragraph by paragraph."""
    text = as_shown(text)
    blocks, offset = [], 0
    for line in text.split("\n"):
        blocks.append((offset, offset + len(line)))
        offset += len(line) + 1
    paragraph = []
    for lo, hi in blocks + [(offset, offset)]:
        if lo < len(text) and text[lo:hi].strip():
            paragraph.append((lo, hi))
            continue
        if paragraph:
            blocks.append((paragraph[0][0], paragraph[-1][1]))
        paragraph = []
    return [span for lo, hi in blocks for span in _passages_in(text, lo, hi)]


def quoted_positions(text: str) -> list[bool]:
    """For each character of as_shown(text): whether a reader sees it quoted,
    in quote marks in any of the readings above or in a blockquote."""
    text = as_shown(text)
    out = [False] * len(text)
    for s, e in marked_spans(text):
        out[s:e] = [True] * (e - s)
    at = 0
    lines = text.split("\n")
    starts = []
    for line in lines:
        starts.append(at)
        at += len(line) + 1
    for k, line in enumerate(lines):
        m = _BLOCKQUOTE.match(line)
        if not m or _ASIDE.match(m.group(1)):
            continue
        end = k + 1
        while end < len(lines) and not _NOT_JOINED.match(lines[end]):
            end += 1
        s, e = starts[k] + m.start(1), starts[end - 1] + len(lines[end - 1])
        out[s:e] = [True] * (e - s)
    return out


def shown_passages(text: str) -> list[str]:
    """Every passage a reader sees quoted: in quote marks, line by line and
    paragraph by paragraph, and in a blockquote."""
    text = as_shown(text)
    return [text[s:e] for s, e in marked_spans(text)] + _blockquoted(text.split("\n"))


def in_quote_marks(text: str, phrase: str) -> bool:
    """Whether a reader sees the phrase quoted in the text (in quote marks or a
    blockquote), however its spaces fall."""
    want = " ".join(phrase.split())
    return any(want in " ".join(passage.split()) for passage in shown_passages(text))


def removed_flagged_or_unquoted(out: str, flagged: bool, phrase: str) -> bool:
    """The contract for an invented quote since strip mode shows only quotes a
    search returned (DESIGN decision 26): removed, or flagged, or no longer in
    quote marks."""
    return phrase not in out or flagged or not in_quote_marks(out, phrase)
