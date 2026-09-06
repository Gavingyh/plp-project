"""Per-source text cleaning, applied before sentence segmentation.

Sources differ enough in register that a shared cleaner would either
under-clean Reddit or over-clean news. See MVP plan Phase 2, step 2.
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
    # carries sentiment signal in this register (see plan Phase 2, step 2).
    return _WHITESPACE.sub(" ", text).strip()


def clean_earnings(text: str) -> str:
    # Numeric-table filtering already happened at extraction time (ingest/earnings.py).
    return _WHITESPACE.sub(" ", text).strip()


CLEANERS = {
    "newsapi": clean_news,
    "alphavantage": clean_news,
    "arctic_shift": clean_reddit,
    "earnings": clean_earnings,
}


def clean_for_source(source: str, text: str) -> str | None:
    cleaner = CLEANERS.get(source)
    if cleaner is None:
        return _WHITESPACE.sub(" ", text).strip()
    return cleaner(text)
