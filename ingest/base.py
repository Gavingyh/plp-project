"""Shared config and helpers for all ingest adapters."""

import re
import time
import requests

from config.logging_config import get_logger


logger = get_logger(__name__)

# Canonical bank aliases, shared by every source so bank attribution is
# consistent whether the mention came from a news headline, a Reddit comment,
# or an earnings PDF.
BANKS = {
    # POSB last: DBS's retail brand since 1998. Order matters:
    # Alpha Vantage reads the ticker at position 2, and NewsAPI queries only
    # aliases with a space or a dot, so "POSB" never widens a news query.
    "DBS": ["DBS Bank", "DBS Group", "D05.SI", "DBS", "POSB"],
    "OCBC": ["OCBC Bank", "Oversea-Chinese Banking", "O39.SI", "OCBC"],
    "UOB": ["United Overseas Bank", "UOB Bank", "U11.SI", "UOB"],
}
BANK_NAMES = tuple(BANKS)   # ("DBS", "OCBC", "UOB"): the only banks the project covers

_BANK_PATTERNS = {
    bank: re.compile(r"\b(?:" + "|".join(re.escape(a) for a in aliases) + r")\b", re.IGNORECASE)
    for bank, aliases in BANKS.items()
}

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5  # doubled each retry: 5s, 10s, 20s


def detect_banks(text: str) -> list[str]:
    """Which of DBS/OCBC/UOB are named in this text. Order is stable (DBS, OCBC, UOB)."""
    if not text:
        return []
    return [bank for bank, pat in _BANK_PATTERNS.items() if pat.search(text)]


def resolve_bank(text: str, fallback: str | None = None) -> str | None:
    """Single bank if exactly one is named; 'MULTI' if more than one; fallback otherwise.

    Document-level attribution only - sentence-level re-attribution happens in
    preprocess/, since a MULTI document usually has each bank named
    in a different sentence.
    """
    found = detect_banks(text)
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        return "MULTI"
    return fallback


def request_with_retries(url, params, timeout=15, headers=None):
    """GET with a few retries on transient failures (timeouts, 429, 5xx).
    Does NOT retry on 4xx auth errors (401/403) - a bad key won't fix itself."""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout, headers=headers)
            if resp.status_code in (401, 403):
                resp.raise_for_status()
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.exceptions.HTTPError(
                    f"{resp.status_code}, retryable", response=resp
                )
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt == MAX_RETRIES:
                break
            wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warning(f"request failed ({e}); retrying in {wait}s "
                  f"(attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)
    raise last_exc
