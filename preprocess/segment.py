"""
Sentence segmentation via spaCy, with abbreviation exceptions for financial
text (S$1.2b, Q3 FY25, p.a., etc.) that naive splitters break on.

See docs/DESIGN.md, step 1.
"""

import re

import spacy
from spacy.language import Language

_MIN_SENTENCE_LEN = 15  # chars - drops fragments a naive split can still produce

# Abbreviations spaCy's default sentencizer doesn't know, common in bank
# earnings/analyst text. Adding them as special-case tokenizer exceptions
# prevents a false sentence break right after the period.
# Not "Q1." to "Q4." or "FY.": those end sentences ("Profit rose in Q3."), and as
# special cases they kept the full stop inside the token, so the sentence never
# ended there.
_FINANCIAL_ABBREVIATIONS = [
    "p.a.", "e.g.", "i.e.", "vs.", "approx.", "est.", "no.", "Jan.", "Feb.", "Mar.", "Apr.", "Jun.", "Jul.",
    "Aug.", "Sep.", "Sept.", "Oct.", "Nov.", "Dec.", "Mr.", "Mrs.", "Ms.", "Dr.",
]

# Special cases are case-sensitive: "vs." alone let "Vs." end a headline mid-figure.
_ABBREVIATION_FORMS = sorted({form for a in _FINANCIAL_ABBREVIATIONS
                              for form in (a, a[0].upper() + a[1:], a.upper())})
# Slide bullets: spaCy doesn't split on them, so one "sentence" carried several
# points of opposite polarity ("Fee income up 7% ▪ Trading income declines 34%").
_BULLET = re.compile(r"\s*[▪•●◦■]\s*")

# Of those, the ones that never end a sentence: the parser may still start a
# new sentence after "Vs." even when the tokenizer keeps it whole, so a break
# after them is forbidden. "Q3." and "p.a." can end one, so they are not here.
_NEVER_FINAL = {form for a in ("vs.", "e.g.", "i.e.", "approx.", "Mr.", "Mrs.", "Ms.", "Dr.")
                for form in (a, a[0].upper() + a[1:], a.upper())}


@Language.component("no_break_after_abbreviation")
def _no_break_after_abbreviation(doc):
    for i, tok in enumerate(doc[:-1]):
        if tok.text in _NEVER_FINAL:
            doc[i + 1].is_sent_start = False
    return doc


_nlp: Language | None = None


def _get_nlp() -> Language:
    global _nlp
    if _nlp is None:
        nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer", "tagger"])
        for abbr in _ABBREVIATION_FORMS:
            nlp.tokenizer.add_special_case(abbr, [{"ORTH": abbr}])
        nlp.add_pipe("no_break_after_abbreviation", before="parser")
        _nlp = nlp
    return _nlp


def segment(text: str) -> list[tuple[str, int, int]]:
    """Returns [(sentence_text, char_start, char_end), ...], filtering fragments
    below _MIN_SENTENCE_LEN (naive splits on financial abbreviations still slip
    through occasionally even with the exceptions above)."""
    if not text or not text.strip():
        return []
    doc = _get_nlp()(text)
    out = []
    for sent in doc.sents:
        for s, start, end in _split_bullets(sent.text, sent.start_char):
            if len(s) >= _MIN_SENTENCE_LEN:
                out.append((s, start, end))
    return out


def _split_bullets(text: str, offset: int) -> list[tuple[str, int, int]]:
    """The pieces of a sentence between bullet glyphs, stripped, with their
    offsets in the document."""
    pieces, pos = [], 0
    for m in list(_BULLET.finditer(text)) + [None]:
        stop = m.start() if m else len(text)
        chunk = text[pos:stop]
        lead = len(chunk) - len(chunk.lstrip())
        s = chunk.strip()
        if s:
            pieces.append((s, offset + pos + lead, offset + pos + lead + len(s)))
        if m:
            pos = m.end()
    return pieces
