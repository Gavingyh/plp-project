"""Per-source text cleaning, applied before sentence segmentation.

Sources differ enough in register that a shared cleaner would either
under-clean Reddit or over-clean news. See docs/DESIGN.md, step 2.
"""

import re

_NEWSAPI_TRUNCATION = re.compile(r"\[\+\d+\s*chars\]\s*$")
_DATELINE = re.compile(r"^\([A-Za-z ]+\)\s*[-–—]\s*")  # e.g. "(Reuters) - "
_URL = re.compile(r"https?://\S+")
_REDDIT_QUOTE_LINE = re.compile(r"^>.*$", re.MULTILINE)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\(https?://[^)]+\)")
_MARKDOWN_EMPHASIS = re.compile(r"[*_]{1,3}([^*_]+)[*_]{1,3}")
_WHITESPACE = re.compile(r"\s+")

_AUTOMOD_MARKERS = ("i am a bot", "this action was performed automatically",
                     "contact the moderators of this subreddit")


def clean_news(text: str) -> str:
    text = _NEWSAPI_TRUNCATION.sub("", text)
    text = _DATELINE.sub("", text)
    text = _URL.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


# CNA full text (ingest/cna_archive.py) comes one paragraph per line: headline,
# standfirst, then the story. Datelines take three forms: "SINGAPORE: ",
# "WASHINGTON, Sept 19 : " and "Sept 18 : ". Bank names are excluded so a
# paragraph opening "DBS: ..." keeps its subject.
_CNA_DATELINE = re.compile(
    r"^(?!(?:DBS|OCBC|UOB|POSB)\b)"
    r"(?:[A-Z][A-Z .'’-]{1,40}(?:,\s*[A-Z][a-z]{2,4}\.?\s+\d{1,2})?|[A-Z][a-z]{2,4}\.?\s+\d{1,2})"
    r"\s*:\s+")
_CNA_BULLET = re.compile(r"^[•·▪\-–]\s+")
_CNA_BOILERPLATE = re.compile(
    r"^(source:|listen to this article|this audio is (?:ai-)?generated|"
    r"get (?:cna|whatsapp|telegram)|follow (?:cna|us) on|read more:|related:)", re.IGNORECASE)
_TERMINAL = re.compile(r"[.!?:;…\"'”’)\]]$")


def clean_cna(text: str) -> str:
    """Paragraph lines into sentences: drop subheadings, footnotes and
    boilerplate, strip the dateline, and end every paragraph with a full stop
    so the headline and standfirst don't run into the first sentence."""
    kept = []
    for i, line in enumerate(l.strip() for l in text.split("\n")):
        line = _CNA_BULLET.sub("", line)
        if not line or _CNA_BOILERPLATE.match(line):
            continue
        letters = [c for c in line if c.isalpha()]
        if letters and line.upper() == line and len(line) < 100:
            continue  # ALL-CAPS subheading
        if line.startswith("(") and line.endswith(")"):
            continue  # "($1 = 156.8600 yen)"
        if i < 3:
            line = _CNA_DATELINE.sub("", line)
        if not _TERMINAL.search(line):
            line += "."
        kept.append(line)
    return clean_news(" ".join(kept))


def clean_reddit(text: str) -> str | None:
    """Returns None for bot/AutoModerator comments — caller should drop them."""
    lowered = text.lower()
    if any(marker in lowered for marker in _AUTOMOD_MARKERS):
        return None
    text = _REDDIT_QUOTE_LINE.sub("", text)          # quoted parent text isn't the commenter's own view
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _MARKDOWN_EMPHASIS.sub(r"\1", text)
    text = _URL.sub("", text)
    # Deliberately NOT lowercasing — FinBERT is cased-aware and casing/emphasis
    # carries sentiment signal in this register (see docs/DESIGN.md, step 2).
    return _WHITESPACE.sub(" ", text).strip()


def clean_earnings(text: str) -> str:
    # Numeric-table filtering already happened at extraction time (ingest/earnings_extract.py).
    return _WHITESPACE.sub(" ", text).strip()


CLEANERS = {
    "newsapi": clean_news,
    "alphavantage": clean_news,
    "yahoo_news": clean_news,
    "google_news": clean_news,
    "cna": clean_cna,
    "arctic_shift": clean_reddit,
    "earnings": clean_earnings,
    "sgx_research": clean_earnings,   # PDF prose, tables already dropped at extraction
}


def clean_for_source(source: str, text: str) -> str | None:
    cleaner = CLEANERS.get(source)
    if cleaner is None:
        return _WHITESPACE.sub(" ", text).strip()
    return cleaner(text)
