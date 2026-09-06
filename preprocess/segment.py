"""
Sentence segmentation via spaCy, with abbreviation exceptions for financial
text (S$1.2b, Q3 FY25, p.a., etc.) that naive splitters break on.

See MVP plan Phase 2, step 1.
"""

import spacy
from spacy.language import Language

_MIN_SENTENCE_LEN = 15  # chars — drops fragments a naive split can still produce

# Abbreviations spaCy's default sentencizer doesn't know, common in bank
# earnings/analyst text. Adding them as special-case tokenizer exceptions
# prevents a false sentence break right after the period.
_FINANCIAL_ABBREVIATIONS = [
    "p.a.", "e.g.", "i.e.", "vs.", "approx.", "est.", "no.", "Q1.", "Q2.",
    "Q3.", "Q4.", "FY.", "Jan.", "Feb.", "Mar.", "Apr.", "Jun.", "Jul.",
    "Aug.", "Sep.", "Sept.", "Oct.", "Nov.", "Dec.", "Mr.", "Mrs.", "Ms.", "Dr.",
]

_nlp: Language | None = None


def _get_nlp() -> Language:
    global _nlp
    if _nlp is None:
        nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer", "tagger"])
        for abbr in _FINANCIAL_ABBREVIATIONS:
            nlp.tokenizer.add_special_case(abbr, [{"ORTH": abbr}])
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
        s = sent.text.strip()
        if len(s) >= _MIN_SENTENCE_LEN:
            out.append((s, sent.start_char, sent.end_char))
    return out
