"""
Property test of strip mode (DESIGN decision 26, 5 Oct 2026): for thousands of
made-up answers mixing quotes a search returned, invented ones, odd and nested
quote marks of many styles (character references such as "&quot;" too), words
glued to marks, hyphenated words, line breaks, blockquotes in lists and lines
markdown joins to a blockquote, citations and the harness's own heading, every
passage of three or more words a reader sees quoted after strip is text a search
returned, word for word. Nine validations each found a quote shape the detectors
missed; this test asks for the guarantee whatever the shape.

A reader's view comes from tests/quote_marks.py, written apart from the code it
checks: the marks paired in order in each line and each paragraph, an inch mark,
an apostrophe and a possessive read as such, and every blockquote with the lines
joined to it. Fixed seed, no model, no network, no data/plp.db.
"""

import random
import re

import pytest

from chatbot import agent
from chatbot.agent import EVIDENCE_REMOVED_NOTE, EVIDENCE_UNMATCHED_NOTE, _ToolCallTracker, enforce_evidence
from tests.quote_marks import DOUBLE, SINGLE, as_shown, shown_passages, words

REAL = [
    "the app is slow to load at night",
    "branch queues are long on weekends",
    'What do you think of "DBS Robot" with the 0.5% fees?',      # a sentence holding a quote
    'my 6" phone shows the app badly',                            # ... an inch mark
    "fees are far too high for retail customers like me",
    "OCBC's app crashed twice during the banks' busiest week",    # ... an apostrophe, a possessive
]
INVENTED = [
    "OCBC will cut its dividend next year for sure",
    "the bank secretly charges hidden fees",
    "UOB is the worst bank in the world",
    "analysts say DBS shares will crash soon",
    "UOB-will-shut-branches-next-year",                           # one run of hyphenated words
]
WORDS = ["buy", "hold", "Tier 1", "CET1", "PayLah", "fees", "strong buy", "OCBC's app", "DBS"]
PROSE = ["DBS scored 0.31", "users are mixed", "the banks' fees rose", 'it is a 6" phone', "overall it is positive",
         "and", "One user said", "Another wrote:", "As one investor put it,", "Rated", "the '08 crisis",
         "analysts' views", "wrote'OCBC"]
MARKS = ['"', '"', "“", "”", "«", "»", "„", "‟", "'", "‘", "’", "‹", "›", "「", "」", "＂", "❝", "‚", "❯", "❠",
         "&quot;", "&#8221;", '\\"']
STYLES = [('"', '"'), ("“", "”"), ("«", "»"), ("»", "«"), ("„", "“"), ("”", "”"), ("'", "'"), ("‘", "’"),
          ('"', "”"), ("“", '"'), ("»", "»"), ('"', '"'), ("“", "”"), ("'", "'"),
          ("‹", "›"), ("「", "」"), ("＂", "＂"), ("❝", "❞"), ("‚", "‘"), ("❮", "❯"), ("❠", "❞"), ("&quot;", "&quot;"),
          ("&ldquo;", "&rdquo;"), ("&#39;", "&#39;"), ('\\"', '\\"')]
CITES = [f"[DBS, 2026-09-01, sentence_id {'a' * 24}]", f"[OCBC, 2026-09-02, sentence_id {'f' * 24}]",
         "[1]", "[2, 3]", "(Reddit)"]
JOINS = [" ", " ", " ", "", "\n", "\n\n", ". ", ", ", " - ", "\n- ", "\n> ", "**", "*", "_", " | ", "\n1. ",
         "\n> ", "\n- - > ", "\n1. > ", agent.EVIDENCE_FOUND_HEADING + "\n- "]


def _quoted(rng, text):
    opening, closing = rng.choice(STYLES)
    if rng.random() < 0.2:                       # cut short, or never closed
        text = text[:rng.randint(4, len(text))]
    return opening + text + (closing if rng.random() < 0.85 else "")


def _piece(rng):
    k = rng.random()
    if k < 0.25:
        return _quoted(rng, rng.choice(REAL))
    if k < 0.45:
        return _quoted(rng, rng.choice(INVENTED))
    if k < 0.55:
        opening, closing = rng.choice(STYLES)
        return opening + rng.choice(WORDS) + closing
    if k < 0.68:
        return rng.choice(MARKS)
    if k < 0.78:
        return rng.choice(CITES)
    if k < 0.86:                                 # a quote inside a quote, an invented tail after it
        return _quoted(rng, f"{rng.choice(PROSE)} {_quoted(rng, rng.choice(REAL + INVENTED))} {rng.choice(INVENTED)}")
    return rng.choice(PROSE)


def _answer(rng):
    text = "> " if rng.random() < 0.15 else ""
    for _ in range(rng.randint(1, 8)):
        text += _piece(rng) + rng.choice(JOINS)
    return text


def _norm(text):
    text = as_shown(text)
    text = re.sub(r"\[[A-Z]+, \d{4}-\d{2}-\d{2}, sentence_id [0-9a-f]{24}\]|\[\d{1,3}(?:[ \t]*[,–-][ \t]*\d{1,3})*\]",
                  " ", text)
    text = text.replace("’", "'").replace("‘", "'")
    for mark in "“”„‟":
        text = text.replace(mark, '"')
    return re.sub(r"\s+", " ", text).strip().lower()


RETRIEVED = [_norm(t) for t in REAL]
# A letter or digit that is no Chinese or Japanese character (each of those is a word of its own).
_LATIN_WORD = "[^\\W_぀-ヿ㐀-䶿一-鿿豈-﫿]"


def _whole_words(piece):
    """The piece as a pattern that finds it only as whole words: no letter or
    digit glued to an end that is one ("impressive" is no piece of
    "unimpressive", "5%" none of "15%"), nor, at an end that is a digit, the
    rest of a number ("2" is no piece of "2.05%")."""
    left = f"(?<!{_LATIN_WORD})" if re.match(_LATIN_WORD, piece) else ""
    left += r"(?<!\d[-.,/:])" if piece[:1].isdigit() else ""
    right = f"(?!{_LATIN_WORD})" if re.search(f"{_LATIN_WORD}$", piece) else ""
    right += r"(?![-.,/:]\d)" if piece[-1:].isdigit() else ""
    return re.compile(left + re.escape(piece) + right)


def _returned(passage):
    """Every piece of the passage, cut at an ellipsis and trimmed of punctuation,
    quote marks and emphasis at its ends, in one retrieved text, in order, as
    whole words."""
    pieces = [p.strip(" .,;:!?*_" + "".join(DOUBLE | SINGLE)) for p in re.split(r"\.{3}|…", _norm(passage))]
    pieces = [p for p in pieces if p]
    for text in RETRIEVED:
        at = 0
        for p in pieces:
            found = _whole_words(p).search(text, at)
            if not found:
                break
            at = found.end()
        else:
            return bool(pieces)
    return False


def _tracker(searched):
    items = [{"sentence_id": c * 24, "bank": "DBS", "source": "reddit", "date": "2026-09-01", "text": t,
              "url": f"https://r.example/{c}", "cite_as": f"[DBS, 2026-09-01, sentence_id {c * 24}]"}
             for c, t in zip("abcdef", REAL)]
    search = {"name": "search_evidence", "arguments": {"query": "q"}, "result": {"results": items}}
    if searched:
        return _ToolCallTracker.from_calls([search])
    # No search this turn; an earlier turn's search returned the same texts.
    return _ToolCallTracker.from_calls([{"name": "get_sentiment", "arguments": {"bank": "DBS"},
                                         "result": {"score": 0.31}}], earlier=[search])


def test_after_strip_every_passage_in_quote_marks_is_text_a_search_returned():
    rng = random.Random(20261005)
    shown_wrong, flagged, changed_again = [], [], []
    for _ in range(3000):
        answer = _answer(rng)
        for searched in (True, False):
            out, flag = enforce_evidence(answer, _tracker(searched), "q", "strip")
            body = out.split(EVIDENCE_UNMATCHED_NOTE)[0].split(EVIDENCE_REMOVED_NOTE)[0]
            for passage in shown_passages(body):
                cited = re.sub(r"\[[A-Z]+, \d{4}-\d{2}-\d{2}, sentence_id [0-9a-f]{24}\]", " ", passage)
                if words(cited) >= 3 and not _returned(passage):
                    shown_wrong.append((answer, body, passage))
            if flag:
                flagged.append((answer, body))
            if agent._demark(body, _tracker(searched)) != body:      # strip again changes nothing
                changed_again.append((answer, body))
    assert not shown_wrong, shown_wrong[:3]
    assert not flagged, flagged[:3]
    assert not changed_again, changed_again[:3]


def test_the_generated_answers_hold_what_strip_must_handle():
    """The generator is not idle: invented quotes reach strip mode in quote
    marks, some in the less common marks or in a line joined to a blockquote,
    and strip keeps some real quotes in theirs."""
    rng = random.Random(20261005)
    invented_quoted = other_marks = joined = heading = real_kept = 0
    for _ in range(300):
        answer = _answer(rng)
        out, _ = enforce_evidence(answer, _tracker(True), "q", "strip")
        invented = [p for p in shown_passages(answer) if any(i in p for i in INVENTED)]
        invented_quoted += bool(invented)
        other_marks += any(m in answer for m in ("‹", "「", "＂", "❝", "‚", "&quot;", "&ldquo;", "&#39;"))
        joined += any("\n" in p for p in invented)
        heading += agent.EVIDENCE_FOUND_HEADING in answer
        real_kept += any(words(p) >= 3 and _returned(p) for p in shown_passages(out))
    assert invented_quoted > 100 and other_marks > 50 and joined > 20 and heading > 20 and real_kept > 50


# The reader itself: what it sees quoted is what markdown shows quoted.
@pytest.mark.parametrize("text, passage", [
    ('a "b c d" e', "b c d"),
    ("a &quot;b c d&quot; e", "b c d"),                     # a character reference shows the mark
    ("a ‹b c d› e", "b c d"),
    ("a 「b c d」 e", "b c d"),
    ('a "b c\nd" e', "b c\nd"),                             # one paragraph, two lines
    ("> b c d\ne f g", "b c d\ne f g"),                     # a line markdown joins to a blockquote
    ("- - > b c d", "b c d"),                               # a blockquote in a nested list item
    ("x wrote'OCBC b c' y", "OCBC b c"),                    # a mark glued to the word before a capital
])
def test_the_reader_sees_what_markdown_shows_quoted(text, passage):
    assert passage in shown_passages(text)


@pytest.mark.parametrize("text, words_seen", [
    ('a 6" phone and a 5" one', "phone"),                   # inch marks
    ("don't, OCBC's and the banks' fees", "OCBC"),          # apostrophes and a possessive
    ("> b c d\n\ne f g", "e f g"),                          # a blank line ends the blockquote
    ("> b c d\n- e f g", "e f g"),                          # so does a bullet
    ("> **Note:** b c d", "b c d"),                         # an aside
])
def test_the_reader_sees_these_unquoted(text, words_seen):
    assert not any(words_seen in p for p in shown_passages(text))
