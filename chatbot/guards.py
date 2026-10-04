"""
Deterministic checks on the model's answer, after it runs: the output half of
the guardrails of the Conversational UIs module (DESIGN decision 19).

  - unverified_numbers(answer, tool_results, question): figures in the answer
    that match nothing the tools returned.
  - unverified_sentence_ids(answer, retrieved_ids): sentence ids the answer
    cites that were never retrieved.

They compare the answer with what the tools returned, so they are rules by
design. The input side, deciding what a question asks for (advice, small
talk, off-topic, a banking-service request), moved to a model-based intent
classifier on 4 Oct 2026 (chatbot/intent.py, config/intents.yaml); the
regex lists that did it before were brittle with paraphrases and other
languages.
"""

import re
from itertools import permutations


# --- output: numbers -----------------------------------------------------------

# A figure: not glued to a preceding word, so names like "COVID-19" or "3Q24" aren't figures.
_NUMBER = re.compile(r"(?<![\w.])(?<![A-Za-z]-)[-+−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?"
                     r"|(?<![\w.])(?<![A-Za-z]-)[-+−]?\d+(?:\.\d+)?%?")
# Month names and their abbreviations only: "[a-z]*" also took "market 1234" and
# "declined 4321" for dates and hid the figures (4 Oct 2026).
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
          r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?")

_STRIP_FIRST = [
    re.compile(r"https?://\S+"),                   # URLs carry ids and dates
    re.compile(rf"\b{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b", re.IGNORECASE),  # "September 24th, 2026"
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH},?\s+\d{{4}}\b", re.IGNORECASE),  # "24 September 2026"
    re.compile(rf"\b{_MONTH}\s+\d{{4}}\b", re.IGNORECASE),                                   # "September 2026"
    re.compile(r"\b[0-9a-f]{24}\b"),               # sentence ids
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?"),  # ISO dates and timestamps
    re.compile(r"^\s*\d+[.)]\s", re.MULTILINE),     # numbered-list markers
    re.compile(r"\b\d+\s*(?:-|\s)?(?:day|d|week|month|year)s?\b", re.IGNORECASE),  # "7-day", "30d"
]


# What in a tool result may vouch for an answer (an allow-list, 4 Oct 2026):
# numeric data fields, and the text of retrieved evidence. Everything else a
# tool returns is the system's own wording or the model's arguments echoed
# back (a search query, a window, a "reason" quoting them), timestamps, ids
# and links, whose digits are not figures. A skip-list of such fields missed
# new ones twice; an allow-list can't.
EVIDENCE_TEXT_KEYS = frozenset({"text"})        # a retrieved sentence's own words
# The retrieval score: true as written ("relevance of at least 0.58"), but not
# a figure about a bank, so never read as a percentage or a ratio ("81%").
NON_DATA_NUMBER_KEYS = frozenset({"relevance"})


def is_evidence_text_key(key) -> bool:
    return str(key) in EVIDENCE_TEXT_KEYS


def _percent_fields(obj, out: list[float]) -> None:
    """Values whose field name says they are already percentages ("implied_upside_pct": 0.9)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k) in NON_DATA_NUMBER_KEYS:
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool) and re.search(r"pct|percent", str(k)):
                out.append(float(v))
            else:
                _percent_fields(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _percent_fields(v, out)


def _count_ratios(obj, out: list[float]) -> None:
    """100·a/b for the whole-number counts within one result object (positive_n
    over n, say), the percentages an answer can honestly derive. Pairing every
    number with every other accepted almost any percentage (3 Oct 2026). An
    object made only of counts is a breakdown (analysts per rating): each
    count's share of their total is derivable too (4 Oct 2026)."""
    if isinstance(obj, dict):
        counts = [float(v) for v in obj.values() if isinstance(v, int) and not isinstance(v, bool)]
        out.extend(100 * a / b for a, b in permutations(counts, 2) if b and 0 <= a <= b)
        if obj and len(counts) == len(obj) and min(counts) >= 0 and sum(counts):
            out.extend(100 * c / sum(counts) for c in counts)
        for v in obj.values():
            _count_ratios(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _count_ratios(v, out)


def _collect_numbers(obj, out: list[float], text_out: list[float], key=None) -> None:
    """Numeric data fields into `out`; figures written inside retrieved evidence
    (a sentence's "$0.54 per share") into `text_out`, which may be quoted but
    are not used to derive percentages. Other strings vouch for nothing."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        (text_out if str(key) in NON_DATA_NUMBER_KEYS else out).append(float(obj))
    elif isinstance(obj, str):
        if is_evidence_text_key(key):
            for m in _NUMBER.finditer(obj):
                try:
                    text_out.append(_parse(m.group(0))[0])
                except ValueError:
                    pass
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _collect_numbers(v, out, text_out, k)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out, text_out, key)


def _parse(token: str) -> tuple[float, int, bool]:
    """(value, decimals shown, is_percent)"""
    is_pct = token.endswith("%")
    t = token.rstrip("%").replace(",", "").replace("−", "-").lstrip("+")
    decimals = len(t.split(".")[1]) if "." in t else 0
    return float(t), decimals, is_pct


def _matches(value: float, decimals: int, candidates: list[float], signed: bool = False) -> bool:
    """A figure written with an explicit + or - must match the value's sign;
    one written without a sign may be its size ("fell by 0.05" for -0.05)."""
    tol = 0.5 * 10 ** (-decimals) + 1e-9
    step = 10 ** (-decimals)
    for c in candidates:
        v, c = (value, c) if signed else (abs(value), abs(c))
        # rounded to the shown decimals, or cut off there ("at least 0.58" for 0.5853)
        if abs(v - c) <= tol or (abs(c) >= abs(v) and abs(c) - abs(v) < step and v * c >= 0):
            return True
    return False


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
    # A percentage is a fraction times 100, a field named as a percentage, a
    # ratio of two counts (below) or a figure in retrieved text: 0.12 written
    # as "0.12%" is a hundred times too small, and a count of 23 written as
    # "23%" is not a share (accepting any value above 1 let counts pass, 4 Oct).
    percent_fields: list[float] = []
    _percent_fields(tool_results, percent_fields)
    percent_candidates = [v * 100 for v in values] + percent_fields + quoted
    ratios: list[float] = []
    _count_ratios(tool_results, ratios)

    flagged = []
    for m in _NUMBER.finditer(text):
        token = m.group(0)
        value, decimals, is_pct = _parse(token)
        plain = token.rstrip("%").replace(",", "").lstrip("+-−")
        if plain in question_numbers:
            continue
        # A year is written without a comma: "2,045 sentences" is a count to check.
        if decimals == 0 and not is_pct and (abs(value) < 10 or (1990 <= value <= 2100 and "," not in token)):
            continue
        signed = token[0] in "+-−"
        if _matches(value, decimals, percent_candidates if is_pct else candidates, signed):
            continue
        if (is_pct or decimals > 0) and _matches(value, decimals, ratios, signed):
            continue
        flagged.append(token)
    return flagged


# --- output: sentence ids --------------------------------------------------------

_SENTENCE_ID = re.compile(r"\b[0-9a-f]{24}\b")


def unverified_sentence_ids(answer: str, retrieved_ids: set[str]) -> list[str]:
    """24-character sentence ids cited in the answer that were never retrieved."""
    return [sid for sid in _SENTENCE_ID.findall(answer or "") if sid not in retrieved_ids]
