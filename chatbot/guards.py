"""
Deterministic checks around the model: one before it runs, two after.

The Conversational UIs module puts guardrails at three points: input and
intent, context and action, output and outcome. The tools already bound the
context (they only read this project's own store). This module covers the
other two, in code rather than in the prompt, because the prompt alone was
measured not to hold: advice-seeking questions were declined 3 of 7 times on
every model tested, and nothing checked that a number in an answer was a
number a tool returned. See docs/DESIGN.md decision 19.

Input (before the model runs):
  - advice_reply(question): buy/sell/hold questions and price predictions get
    a fixed, reviewed reply. Templates for critical responses, generation for
    the rest.
  - scope_reply(question): questions only about banks this system doesn't
    cover, or about nothing it covers at all, get a fixed reply instead of an
    answer from the model's memory.

Output (after the model answers):
  - unverified_numbers(answer, tool_results, question): figures in the answer
    that match nothing the tools returned.
  - unverified_sentence_ids(answer, retrieved_ids): sentence ids the answer
    cites that were never retrieved.

Both input checks are pattern-based. They will miss some phrasings and catch
the occasional false positive; the point is that the common cases are
handled the same way every time, which the prompt alone did not achieve.
"""

import re
from itertools import permutations

from ingest.base import detect_banks

# --- input: advice and prediction ------------------------------------------

_ACTION = r"(?:buy|sell|hold|invest|get in|get out|enter|exit|add to|average down|accumulate|dump|keep|load up|top up|go long|short)"
_ADVICE_PATTERNS = [
    rf"\bshould (?:i|we)\b[^?.!]*\b{_ACTION}\b",
    rf"\b(?:is it|is now|now is|would it be) (?:a |the )?(?:good|right|bad|wise|smart|great) (?:time|idea|moment|point) to {_ACTION}\b",
    r"\b(?:buy|sell|hold)\s*(?:,|/|or)\s*(?:buy|sell|hold)\b",
    r"\bworth (?:buying|investing|holding|selling|a buy|getting)\b",
    rf"\b(?:recommend|recommendation|advise|advice)\b[^?.!]*\b(?:{_ACTION}|stock|stocks|shares?|position)\b",
    r"\bwhich (?:bank|stock|one|of (?:them|the three|these))\b[^?.!]*\b(?:should (?:i|we)|to buy|best (?:buy|investment|pick))\b",
    r"\b(?:best|better|good|safest) (?:investment|buy|pick|stock to (?:buy|own))\b",
    r"\bwhat (?:should|would) (?:i|you) do with my\b",
    r"\bam i (?:right|wrong|safe|smart|crazy) to\b",
    r"\bis (?:dbs|ocbc|uob|it|the stock) (?:a )?(?:buy|sell|good buy|bargain)\b",
]
# Forecasts are the same request in another form: acting on a predicted price.
_PREDICTION_PATTERNS = [
    r"\bwill (?:dbs|ocbc|uob|it|the (?:stock|shares?|share price|price))\b[^?.!]*\b(?:go up|go down|rise|fall|drop|crash|rally|recover|hit|reach|double|outperform)\b",
    r"\b(?:predict|forecast)\b[^?.!]*\b(?:price|share|stock|return)",
    r"\bwhere (?:will|is) (?:dbs|ocbc|uob|the (?:stock|share price))[^?.!]*\b(?:head|going|be)\b",
]
_ADVICE_RES = [re.compile(p, re.IGNORECASE) for p in _ADVICE_PATTERNS + _PREDICTION_PATTERNS]


def is_advice_seeking(question: str) -> bool:
    return any(p.search(question or "") for p in _ADVICE_RES)


def advice_reply(question: str, context_banks: list[str] | None = None) -> str | None:
    """A fixed reply if the question asks what to do with the stock, else None.
    `context_banks` names the subject when the question doesn't ("Should I buy it?")."""
    if not is_advice_seeking(question):
        return None
    banks = detect_banks(question) or list(context_banks or [])
    subject = " / ".join(banks) if banks else "these banks"
    example_bank = banks[0] if banks else "DBS"
    return (
        f"I can't tell you whether to buy, sell or hold {subject}, or where the share price is "
        "heading. This assistant reports what retail investors, the news and the banks "
        "themselves are saying, and none of it is financial advice.\n\n"
        "What I can show you instead:\n"
        f"- the overall sentiment on {subject} and how it has moved recently\n"
        "- sentiment on one aspect, such as dividends, net interest margin, asset quality, "
        "the wealth business, retail banking or the share price\n"
        "- how the three banks compare\n"
        "- the quotes behind any of these\n\n"
        f"For example: \"How has sentiment on {example_bank}'s dividends changed recently?\""
    )


# --- input: scope ------------------------------------------------------------

_OTHER_BANKS = re.compile(
    r"\b(?:maybank|hsbc|standard chartered|stanchart|citi(?:bank|group)?|cimb|rhb|"
    r"bank of china|icbc|jp ?morgan|chase|bank of america|wells fargo|goldman|"
    r"hang seng|public bank|bangkok bank|kasikorn|mandiri|bca|sbi|hdfc|trust bank|gxs|maribank)\b",
    re.IGNORECASE)


# Words that make a question plausibly about this system's subject even when
# no bank is named ("how is sentiment on dividends?").
_DOMAIN = re.compile(
    r"\b(?:sentiment|dividend|payout|margin|nim|asset quality|provision|npl|guidance|outlook|"
    r"bank|banks|banking|analyst|consensus|rating|target price|earnings|results?|profit|"
    r"interest|loan|deposit|shares?|stock|investor|compare|comparison|trend|news|reddit|"
    r"evidence|quotes?|aspect|coverage|data)\b", re.IGNORECASE)


def scope_reply(question: str) -> str | None:
    """A fixed reply if the question is about banks this system doesn't cover,
    or about nothing it covers at all."""
    if detect_banks(question):
        return None  # at least one covered bank: let the model answer that part
    m = _OTHER_BANKS.search(question or "")
    if m:
        return (
            f"I only cover Singapore's three listed banks, DBS, OCBC and UOB, so I have no data "
            f"on {m.group(0)}. I can show sentiment on any of the three, compare them, or find "
            "the quotes behind a score."
        )
    if not _DOMAIN.search(question or ""):
        return (
            "That's outside what I can help with. I answer questions about sentiment on "
            "Singapore's three listed banks, DBS, OCBC and UOB: how sentiment looks overall or on "
            "an aspect such as dividends, margins, asset quality, wealth or retail banking, how it has "
            "changed, how the banks compare, and the quotes behind a score."
        )
    return None


# --- output: numbers -----------------------------------------------------------

# A figure: not glued to a preceding word, so names like "COVID-19" or "3Q24" aren't figures.
_NUMBER = re.compile(r"(?<![\w.])(?<![A-Za-z]-)[-+−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?"
                     r"|(?<![\w.])(?<![A-Za-z]-)[-+−]?\d+(?:\.\d+)?%?")
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_STRIP_FIRST = [
    re.compile(r"https?://\S+"),                   # URLs carry ids and dates
    re.compile(rf"\b{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b", re.IGNORECASE),  # "September 24th, 2026"
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH},?\s+\d{{4}}\b", re.IGNORECASE),  # "24 September 2026"
    re.compile(rf"\b{_MONTH}\s+\d{{4}}\b", re.IGNORECASE),                                   # "September 2026"
    re.compile(r"\b[0-9a-f]{24}\b"),               # sentence ids
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ][\d:.+Z-]*)?"),  # ISO dates and timestamps
    re.compile(r"^\s*\d+[.)]\s", re.MULTILINE),     # numbered-list markers
    re.compile(r"\b\d+\s*(?:-|\s)?(?:day|d|week|month|year)s?\b", re.IGNORECASE),  # "7-day", "30d"
]


def _collect_numbers(obj, out: list[float], text_out: list[float]) -> None:
    """Numeric fields into `out`; figures written inside text fields (a retrieved
    sentence's "$0.54 per share") into `text_out`, which may be quoted but are
    not used to derive percentages."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, str):
        for m in _NUMBER.finditer(obj):
            try:
                text_out.append(_parse(m.group(0))[0])
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out, text_out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out, text_out)


def _parse(token: str) -> tuple[float, int, bool]:
    """(value, decimals shown, is_percent)"""
    is_pct = token.endswith("%")
    t = token.rstrip("%").replace(",", "").replace("−", "-").lstrip("+")
    decimals = len(t.split(".")[1]) if "." in t else 0
    return float(t), decimals, is_pct


def _matches(value: float, decimals: int, candidates: list[float]) -> bool:
    tol = 0.5 * 10 ** (-decimals) + 1e-9
    return any(abs(abs(value) - abs(c)) <= tol for c in candidates)


def unverified_numbers(answer: str, tool_results: list, question: str = "") -> list[str]:
    """Figures in the answer that no tool returned.

    A figure counts as verified if it equals a tool value at the precision it
    is written with, or that value times 100 (a score or share written as a
    percentage), or one tool value as a percentage of another ("12% of
    mentions were positive"), or a figure written inside retrieved text (a
    quoted "$0.54 per share"). Years, dates (ISO or written out), list markers,
    window lengths, numbers under 10 and numbers the user typed are not checked.
    """
    text = answer or ""
    for pat in _STRIP_FIRST:
        text = pat.sub(" ", text)
    question_numbers = {m.group(0).rstrip("%").replace(",", "") for m in _NUMBER.finditer(question or "")}

    values: list[float] = []
    quoted: list[float] = []
    _collect_numbers(tool_results, values, quoted)
    values = list({round(v, 10) for v in values})
    candidates = values + [v * 100 for v in values] + quoted
    small = [v for v in values if v != 0][:400]
    ratios = [100 * a / b for a, b in permutations(small, 2) if b and abs(a) <= abs(b)]

    flagged = []
    for m in _NUMBER.finditer(text):
        token = m.group(0)
        value, decimals, is_pct = _parse(token)
        plain = token.rstrip("%").replace(",", "").lstrip("+-−")
        if plain in question_numbers:
            continue
        if decimals == 0 and not is_pct and (abs(value) < 10 or 1990 <= value <= 2100):
            continue
        if _matches(value, decimals, candidates):
            continue
        if (is_pct or decimals > 0) and _matches(value, decimals, ratios):
            continue
        flagged.append(token)
    return flagged


# --- output: sentence ids --------------------------------------------------------

_SENTENCE_ID = re.compile(r"\b[0-9a-f]{24}\b")


def unverified_sentence_ids(answer: str, retrieved_ids: set[str]) -> list[str]:
    """24-character sentence ids cited in the answer that were never retrieved."""
    return [sid for sid in _SENTENCE_ID.findall(answer or "") if sid not in retrieved_ids]
