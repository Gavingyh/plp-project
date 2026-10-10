"""
Property test of strip mode (DESIGN decision 26): for thousands of
made-up answers mixing quotes a search returned, invented ones, odd and nested
quote marks of many styles (character references such as "&quot;" too), words
glued to marks, hyphenated words, line breaks, blockquotes in lists and lines
markdown joins to a blockquote, citations and the harness's own heading, every
passage of three or more words a reader sees quoted after strip is text a search
returned, word for word. Nine validations each found a quote shape the detectors
missed; this test asks for the guarantee whatever the shape. Since the eleventh
round the answers also hold carriage returns and other line
separators, marks glued to the word before them ("wrote‘...", "wrote'..."),
citations in brackets, with a label, after a full stop or comma or an
attribution, and before what they cite; and no citation is left vouching for
invented words whose quote marks came off, or for a word or two in quote marks
that no search returned. Since the twelfth round a citation
vouches for its own sentence (_stretches), links cite too, and the answers also
hold links, sentences ended by "!" or a semicolon, citations after an
attribution ("according to"), a full clause, a short introduction ("In one
post") or "e.g.", and quotes glued to the word before across a line break.

A reader's view comes from tests/quote_marks.py, written apart from the code it
checks: the marks paired in order in each line and each paragraph, an inch mark,
an apostrophe and a possessive read as such, and every blockquote with the lines
joined to it. Fixed seed, no model, no network, no data/plp.db.
"""

import os
import random
import re

import pytest

from chatbot import agent
from chatbot.agent import EVIDENCE_REMOVED_NOTE, EVIDENCE_UNMATCHED_NOTE, _ToolCallTracker, enforce_evidence
from difflib import SequenceMatcher

from tests.quote_marks import DOUBLE, SINGLE, as_shown, marked_spans, quoted_positions, shown_passages, words

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
         "analysts' views", "wrote'OCBC", "one user wrote", "Source:", "Users called it", "wrote",
         "According to", "In one post", "Users complain the app is slow at night", "e.g."]
MARKS = ['"', '"', "“", "”", "«", "»", "„", "‟", "'", "‘", "’", "‹", "›", "「", "」", "＂", "❝", "‚", "❯", "❠",
         "&quot;", "&#8221;", '\\"']
STYLES = [('"', '"'), ("“", "”"), ("«", "»"), ("»", "«"), ("„", "“"), ("”", "”"), ("'", "'"), ("‘", "’"),
          ('"', "”"), ("“", '"'), ("»", "»"), ('"', '"'), ("“", "”"), ("'", "'"),
          ("‹", "›"), ("「", "」"), ("＂", "＂"), ("❝", "❞"), ("‚", "‘"), ("❮", "❯"), ("❠", "❞"), ("&quot;", "&quot;"),
          ("&ldquo;", "&rdquo;"), ("&#39;", "&#39;"), ('\\"', '\\"')]
CITES = [f"[DBS, 2026-09-01, sentence_id {'a' * 24}]", f"[OCBC, 2026-09-02, sentence_id {'f' * 24}]",
         "[1]", "[2, 3]", "(Reddit)", f"([DBS, 2026-09-01, sentence_id {'a' * 24}])",
         f"\uff08[OCBC, 2026-09-02, sentence_id {'f' * 24}]\uff09", f"(Source: [DBS, 2026-09-01, sentence_id {'a' * 24}])",
         "[E1]", f"[sentence_id {'f' * 24}]", "(https://r.example/a)", "[post](https://r.example/b)"]
JOINS = [" ", " ", " ", "", "\n", "\n\n", ". ", ", ", " - ", "\n- ", "\n> ", "**", "*", "_", " | ", "\n1. ",
         "\n> ", "\n- - > ", "\n1. > ", agent.EVIDENCE_FOUND_HEADING + "\n- ", "\r", "\r\n", "\r> ",
         "\u2028", "\x0c", ": ", ", one user wrote ", "; ", "! ", " according to "]


def _quoted(rng, text):
    opening, closing = rng.choice(STYLES)
    if rng.random() < 0.2:                       # cut short, or never closed
        text = text[:rng.randint(4, len(text))]
    return opening + text + (closing if rng.random() < 0.85 else "")


# A word or two in quote marks that a search returned ("slow") or didn't ("a scam"), and
# what may stand between a quote and the citation after or before it.
SHORT = ["slow", "a scam", "unusable", "weekends", "total scam"]
CITE_AFTER = [" ", "", ". ", ", ", " - ", " (", ", one user wrote ", "; see ", ". Source: ",
              " at night for most users ", ".\n"]
CITE_BEFORE = [": ", " ", " - ", ":\n", ", ", ", as one user put it, "]


def _piece(rng):
    k = rng.random()
    if k < 0.22:
        return _quoted(rng, rng.choice(REAL))
    if k < 0.40:
        return _quoted(rng, rng.choice(INVENTED))
    if k < 0.49:
        opening, closing = rng.choice(STYLES)
        return opening + rng.choice(WORDS) + closing
    if k < 0.60:
        return rng.choice(MARKS)
    if k < 0.68:
        return rng.choice(CITES)
    if k < 0.75:                                 # a quote inside a quote, an invented tail after it
        return _quoted(rng, f"{rng.choice(PROSE)} {_quoted(rng, rng.choice(REAL + INVENTED))} {rng.choice(INVENTED)}")
    if k < 0.88:                                 # a quote, or a word or two in quote marks, and a citation
        opening, closing = rng.choice(STYLES)
        kind = rng.random()
        quoted = _quoted(rng, rng.choice(REAL)) if kind < 0.4 else _quoted(rng, rng.choice(INVENTED)) \
            if kind < 0.7 else opening + rng.choice(SHORT) + closing
        if rng.random() < 0.75:
            return quoted + rng.choice(CITE_AFTER) + rng.choice(CITES)
        return rng.choice(CITES) + rng.choice(CITE_BEFORE) + quoted
    if k < 0.90:                                 # a quote glued to the word before, across a line break
        opening, closing = rng.choice(["''", "\u2019\u2019", "\u2018\u2019"])
        words = rng.choice(INVENTED + REAL).split(" ")
        cut = rng.randint(1, max(1, len(words) - 1))
        return f"wrote{opening}{' '.join(words[:cut])}\n{' '.join(words[cut:])}{closing}"
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


# Citations as strip mode leaves them (bare numbered markers are dropped before), links to a
# returned post among them, and the words of the invented sentences that no real sentence,
# prose, term, citation or join holds: one of those after strip stands where its quote marks
# came off.
_CITED = re.compile(r"\[[A-Z]+, \d{4}-\d{2}-\d{2}, sentence_id [0-9a-f]{24}\]|\[E\d+\]|\[sentence_id [0-9a-f]{24}\]"
                    r"|\[post\]\(https://r\.example/[a-f]\)|https://r\.example/[a-f]")
_TOKEN = re.compile(r"[a-z0-9]+")
# A passage's words are counted without its citations and numbered markers, as the guarantee says.
_CITED_OR_MARKER = re.compile(rf"{_CITED.pattern}|\[\d{{1,3}}(?:[ \t]*[,–-][ \t]*\d{{1,3}})*\]")
_ELSEWHERE = {t for text in REAL + PROSE + WORDS + CITES + JOINS + MARKS + [EVIDENCE_REMOVED_NOTE, EVIDENCE_UNMATCHED_NOTE]
              for t in _TOKEN.findall(text.lower())}
INVENTED_ONLY = {t for text in INVENTED for t in _TOKEN.findall(text.lower())} - _ELSEWHERE
# A line that opens a block of its own: a list item, a heading, a table row, a code fence.
_OPENS_BLOCK = re.compile(r"[ \t]*(?:[-*+](?:[ \t]|$)|\d+[.)](?:[ \t]|$)|#{1,6}(?:[ \t]|$)|\||```|~~~)")
_QUOTE_LINE = re.compile(r"[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)*>")
# A line markdown doesn't join to the blockquote line before it.
_NOT_JOINED = re.compile(r"[ \t]*$|[ ]{0,3}(?:>|[-*+][ \t]+\S|1[.)][ \t]+\S|#{1,6}(?:[ \t]|$)|```|~~~|(?:[-*_][ \t]*){3,}$)")
_LEAD = re.compile(r"[ \t]*(?:(?:[-*+]|\d+[.)]|>)[ \t]+)+")
_LABELS = re.compile(r"(?<![^\W_])(?:sources?|cite_as|see|refs?|via|cf|e\.g|eg)(?![^\W_])\.?[ \t]*:?", re.IGNORECASE)
_INTRODUCING = {"to", "per", "by", "from", "in", "on", "via", "see", "cf"}
_SHORT_FORMS = re.compile(r"\b(?:e\.g|i\.e|vs|etc|approx)\.$", re.IGNORECASE)    # those the answers here hold


def _block_starts(text):
    """Where a paragraph or block starts: the start, after a blank line or a
    heading, at a line that opens a block, and at a blockquote line after a
    line outside a blockquote."""
    starts, at, after_break, in_quote = [], 0, True, False
    for line in text.split("\n"):
        quote = bool(_QUOTE_LINE.match(line))
        if after_break or _OPENS_BLOCK.match(line) or (quote and not in_quote):
            starts.append(at)
        after_break = not line.strip() or bool(re.match(r"[ \t]*#{1,6}(?:[ \t]|$)", line))
        in_quote = quote or (in_quote and not _NOT_JOINED.match(line))
        at += len(line) + 1
    return starts


def _sentence_starts(text):
    """Where a sentence starts: at a block start, and after a full stop, "!" or
    "?" (not an ellipsis, not "e.g."), any closing marks after it, then spaces
    and anything but a lower-case letter; or after a semicolon and a space."""
    starts = set(_block_starts(text))
    for m in re.finditer(r"[.!?]+|;", text):
        end, mark = m.end(), m.group(0)
        if mark != ";" and (mark.count(".") > 1 or _SHORT_FORMS.search(text[max(0, m.start() - 6):end])):
            continue
        while end < len(text) and (text[end] in "\"'”’»›)]）*_`" or text[end] in DOUBLE | SINGLE):
            end += 1
        if end < len(text) and text[end] not in " \t\n":
            continue
        nxt = end
        while nxt < len(text) and text[nxt] in " \t\n":
            nxt += 1
        if nxt < len(text) and (mark == ";" or not text[nxt].islower()):
            starts.add(nxt)
    return sorted(starts)


def _stretches(body, cites, k, starts, blocks):
    """What the k-th citation (run) vouches for: (stretches before it, the
    stretch after it, whether it introduces that). Its sentence before it, back
    to a citation there, and the sentence before it too where only labels stand
    before it; its sentence after it, up to a citation. It introduces the words
    after it where at most four words stand before it, labels and a list item's
    lead aside, and no quote mark right before it; or a word such as "to" or
    "by" right before it; or a colon after it."""
    cs, ce = cites[k]
    sentence = max(p for p in starts if p <= cs)
    lo = max([sentence] + [e for s, e in cites if sentence <= e <= cs])
    back = [(lo, cs)]
    lead = _LEAD.match(body, lo) if lo == 0 or body[lo - 1] == "\n" else None
    before = re.findall(r"[^\W_]+", _LABELS.sub(" ", _CITED.sub(" ", body[lead.end() if lead and lead.end() <= cs else lo:cs])))
    if not before and lo == sentence and sentence not in blocks:
        prev = max(p for p in starts if p < sentence)
        back.append((max([prev] + [e for s, e in cites if prev <= e <= sentence]), sentence))
    after = (ce, min([p for p in starts if p > ce] + [s for s, e in cites if s >= ce] + [len(body)]))
    after_quote = body[:cs].rstrip(" \t([\uff08")[-1:] in DOUBLE | SINGLE
    introduces = (not after_quote and (len(before) <= 4 or before[-1].lower() in _INTRODUCING)) \
        or bool(re.match(r"[ \t]*[*_]*[ \t]*:", body[ce:]))
    return back, after, introduces


def _vouches_wrongly(body, answer):
    """The citations that vouch for invented words some reading of the answer
    showed in quote marks, or for a word or two in quote marks that no search
    returned. A citation vouches for its own sentence (_stretches; since the
    twelfth round: before, for its paragraph or block back to the
    citation before it or a passage a search returned): for words that stood
    in quote marks before it, or after it where it introduces them, and after
    it otherwise for such words in a run of three or more. Invented words no
    reading of the answer showed quoted, where they stand, are the model's
    own, as words written without quote marks are: each character of the
    result is matched to the answer's (difflib, as strip mode only takes
    characters out, but for a mark that gives way to a space)."""
    quoted = marked = None
    cites = []          # citations in a row ("[1] [2]", "[1], [2]") vouch together
    for m in _CITED.finditer(body):
        if cites and re.fullmatch(r"[ \t]*(?:[,;&/]|and)?[ \t]*", body[cites[-1][1]:m.start()]):
            cites[-1] = (cites[-1][0], m.end())
        else:
            cites.append(m.span())
    spans = marked_spans(body)
    # a word or two in two quote marks, with no space just inside either ('"buy"', not the gap '" and "')
    unreturned = [(s, e) for s, e in spans if 1 <= words(body[s:e]) <= 2 and not _returned(body[s:e])
                  and body[s:s + 1].strip() and body[e - 1:e].strip() and body[e:e + 1] in DOUBLE | SINGLE]
    starts, blocks = _sentence_starts(body), set(_block_starts(body))
    wrong = []
    for k, (cs, ce) in enumerate(cites):
        back, after, introduces = _stretches(body, cites, k, starts, blocks)
        reach = back + ([after] if introduces else [])
        for (a, b), any_length in [(span, True) for span in reach] + ([] if introduces else [(after, False)]):
            invented = [m.span() for m in _TOKEN.finditer(body.lower(), a, b) if m.group(0) in INVENTED_ONLY
                        and not any(s <= m.start() < e for s, e in (c.span() for c in _CITED.finditer(body, a, b)))]
            if invented and quoted is None:
                quoted, marked = _was_quoted(answer, body), _was_quoted(answer, body, marks_only=True)
            within = quoted if any_length else marked     # after it, not introduced: in quote marks, from three words
            for s, e in invented:
                if not any(within[i] for i in range(s, e)):
                    continue
                lo, hi = s, e           # the run of quoted characters round it, in the stretch
                while lo > a and within[lo - 1]:
                    lo -= 1
                while hi < b and within[hi]:
                    hi += 1
                if any_length or words(_CITED_OR_MARKER.sub(" ", body[lo:hi])) >= 3:
                    wrong.append((body[a:b], body[cs:ce]))
                    break
            if any_length and any(a <= s - 1 and e < b for s, e in unreturned):
                wrong.append((body[a:b], body[cs:ce]))
    return wrong


def _was_quoted(answer, body, marks_only=False):
    """For each character of body (strip mode's result): whether the answer,
    as a reader sees it, had it in quote marks or a blockquote where it stood;
    with marks_only, in quote marks."""
    shown, inside = as_shown(answer), quoted_positions(answer)
    if marks_only:
        inside = [False] * len(shown)
        for s, e in marked_spans(answer):
            inside[s:e] = [True] * (e - s)
    out = [False] * len(body)
    for a, b, size in SequenceMatcher(None, shown, body, autojunk=False).get_matching_blocks():
        out[b:b + size] = inside[a:a + size]
    return out


def _seeds():
    """The fixed seed, and any others STRIP_PROPERTY_SEEDS names ("1-60", "3,7"), for a
    longer run by hand: HF_HUB_OFFLINE=1 STRIP_PROPERTY_SEEDS=1-60 .venv-plp/bin/python3 -m
    pytest -q tests/test_chatbot_strip_property.py."""
    seeds = [20261005]
    for part in filter(None, os.environ.get("STRIP_PROPERTY_SEEDS", "").replace(" ", "").split(",")):
        lo, _, hi = part.partition("-")
        seeds += range(int(lo), int(hi or lo) + 1)
    return seeds


@pytest.mark.parametrize("seed", _seeds())
def test_after_strip_every_passage_in_quote_marks_is_text_a_search_returned(seed):
    rng = random.Random(seed)
    shown_wrong, cited_wrong, flagged, changed_again = [], [], [], []
    for _ in range(3000):
        answer = _answer(rng)
        for searched in (True, False):
            out, flag = enforce_evidence(answer, _tracker(searched), "q", "strip")
            body = out.split(EVIDENCE_UNMATCHED_NOTE)[0].split(EVIDENCE_REMOVED_NOTE)[0]
            for passage in shown_passages(body):
                if words(_CITED_OR_MARKER.sub(" ", passage)) >= 3 and not _returned(passage):   # markers aside
                    shown_wrong.append((answer, body, passage))
            cited_wrong += [(answer, body, wrong) for wrong in _vouches_wrongly(body, answer)]
            if flag:
                flagged.append((answer, body))
            if agent._demark(body, _tracker(searched)) != body:      # strip again changes nothing
                changed_again.append((answer, body))
    assert not shown_wrong, shown_wrong[:3]
    assert not cited_wrong, cited_wrong[:3]
    assert not flagged, flagged[:3]
    assert not changed_again, changed_again[:3]


def test_the_generated_answers_hold_what_strip_must_handle():
    """The generator is not idle: invented quotes reach strip mode in quote
    marks, some in the less common marks or in a line joined to a blockquote,
    and strip keeps some real quotes in theirs; answers hold carriage returns
    and other line separators and marks glued to the word before them, across
    a line break too; and strip cuts citations from invented words that lost
    their marks, links among them, and keeps some citations after real
    quotes."""
    rng = random.Random(20261005)
    invented_quoted = other_marks = joined = heading = real_kept = line_ends = glued = cut = cite_kept = 0
    glued_lines = links_cut = 0
    for _ in range(300):
        answer = _answer(rng)
        out, _ = enforce_evidence(answer, _tracker(True), "q", "strip")
        invented = [p for p in shown_passages(answer) if any(i in p for i in INVENTED)]
        invented_quoted += bool(invented)
        other_marks += any(m in answer for m in ("‹", "「", "＂", "❝", "‚", "&quot;", "&ldquo;", "&#39;"))
        joined += any("\n" in p for p in invented)
        heading += agent.EVIDENCE_FOUND_HEADING in answer
        real_kept += any(words(p) >= 3 and _returned(p) for p in shown_passages(out))
        line_ends += bool(re.search("[\r\u2028\x0c]", answer))
        glued += bool(re.search(r"[^\W\d_]\u2018|wrote'", answer))
        cut += len(_CITED.findall(out)) < len(_CITED.findall(answer)) \
            and bool(set(_TOKEN.findall(out.lower())) & INVENTED_ONLY)
        cite_kept += bool(_CITED.search(out))
        glued_lines += bool(re.search("wrote['\u2018\u2019][^\n]*\n", answer))
        links_cut += out.count("r.example") < answer.count("r.example")
    assert invented_quoted > 100 and other_marks > 50 and joined > 20 and heading > 20 and real_kept > 50
    assert line_ends > 100 and glued > 20 and cut > 20 and cite_kept > 20, (line_ends, glued, cut, cite_kept)
    assert glued_lines > 10 and links_cut > 10, (glued_lines, links_cut)


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
