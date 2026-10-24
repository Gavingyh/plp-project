"""
Deterministic checks on the model's answer, after it runs: the output half of
the guardrails of the Conversational UIs module (DESIGN decision 19).

  - unverified_numbers(answer, tool_results, question): figures in the answer
    that match nothing the tools returned.
  - unverified_sentence_ids(answer, retrieved_ids): sentence ids the answer
    cites that were never retrieved.
  - unverified_years(answer, tool_results, question): years in the answer
    that no tool returned and the user did not type.
  - unverified_readings(answer, tool_results): a score described as "neutral"
    or "slightly/moderately/clearly positive/negative" in words no tool
    returned as a reading.

They compare the answer with what the tools returned, so they are rules by
design. The input side, deciding what a question asks for (advice, small
talk, off-topic, a banking-service request), moved to a model-based intent
classifier (chatbot/intent.py, config/intents.yaml); the
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
# "declined 4321" for dates and hid the figures.
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


# A date written without its year ("runs to September 25th", "to 24 Sep") is
# skipped only when a tool returned that month and day: its data_runs_to, a
# sentence's date. Guessing dates by their shape hid real figures in three
# validations ("0.45 may", "July 18\nAugust 24", "21 Oct tweets"):
# a count and a day look alike, but only a day matches a date the tools gave.
_MONTH_NUMBER = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                 "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
# A day is never followed by a decimal, a thousands group or a per cent sign:
# "September 25.7%" and "Sept 25,000" are figures, whatever date the tools
# returned (found in validation). A range of returned days ("Sept 25-26",
# "September 20 to 25") is a date too.
_YEARLESS_DATE = re.compile(
    rf"\b(?P<month1>{_MONTH})[ \t]+(?P<day1>\d{{1,2}})(?P<ord1>st|nd|rd|th)?\b"
    rf"(?:[ \t]*(?:[-–]|to\b|and\b)[ \t]*(?P<day1b>\d{{1,2}})(?P<ord1b>st|nd|rd|th)?\b)?(?![.,]\d|[ \t]*%)"
    rf"|(?<![\w.])(?P<day2>\d{{1,2}})(?:st|nd|rd|th)?[ \t]+(?:of[ \t]+)?(?P<month2>{_MONTH})",
    re.IGNORECASE)
# After a month, a returned day, ordinal or not, is a date only where it
# clearly reads as one; anywhere else it is a figure to check (validation:
# with data to 25 September, "In September 25 customers complained" hid
# the 25, under a rule that took the day for a date unless a count word from a
# fixed list followed it). After "in" ("in early", "in mid", "in late") it is
# always checked: "in September" names the month, so a number after it is a
# count ("In September 25 (DBS), 45 (OCBC) posts were negative"; the tenth
# round). Otherwise it reads as a date after "on", "as of", "as at",
# "the", "dated" or "runs to" (or "ran", "run", "running" to): "On September 25
# DBS scored 0.31", "the September 25 data"; a range also after "from" or
# "between". Or before a line end, punctuation other than "%", "," or an
# opening bracket (a dash, an em dash too, only when no digit follows it),
# "and", "&", "to" or "/" not before a number, an article or determiner, or a
# word such as "until" or "when" (_DATE_ENDS_HERE). Before a comma it reads as
# a date when no number follows in the rest of its clause, or just one, right
# after the comma ("September 25, 45 posts"); and after "by", "up to",
# "through", "until", "till", "to", "since", "ends", "ended", "covers" or
# "covering" when no number follows the comma ("By September 25, DBS scored
# 0.31": the ninth validation found these flagged). Before an
# opening bracket, ( or [, it reads as a date only when the bracket holds no
# digit and no word of approximation, and its clause ends right after the
# closing bracket, or, after one of those words, a comma follows it with no
# number right after ("The latest post is September 25 (the end of the data).";
# but "September 25 (45 posts).", "Negative posts: September 25 (45 in
# August).", "In September 25 (out of 40) posts" and "September 25 (approx.)."
# are checked). A clause ends at a line end, or at ".", ";", ":", "!" or "?"
# before a line end or before a space and a capital or a digit, never at the
# full stop of an abbreviation such as "vs.", "approx." or "i.e." (the ninth
# validation: "In September 25, vs. 45 in August" hid the 25 at the "." of
# "vs."). Before any other word, listed or not, or a number, it is checked
# ("September 25 or so posts", "September 25th sentences"), and so are both
# ends of such a range. A share after the day or the range ("25 per cent", "25
# to 30% of posts") means both numbers are checked.
_SHARE = r"(?:%|[ \t]+(?:per[ \t]?cent|percent|pct)\b)"
_SHARE_AFTER = re.compile(rf"{_SHARE}|[ \t]*(?:to\b|[-–])[ \t]*\d+(?:\.\d+)?[ \t]*{_SHARE}", re.IGNORECASE)
_READS_AS_DATE_BEFORE = re.compile(
    r"(?:\b(?:on|the|dated)|\bas[ \t]+(?:of|at)|\b(?:runs|ran|run|running)[ \t]+to)[ \t]+\Z", re.IGNORECASE)
_RANGE_READS_AS_DATE_BEFORE = re.compile(r"\b(?:from|between)[ \t]+\Z", re.IGNORECASE)
_IN_BEFORE = re.compile(r"\bin[ \t]+(?:(?:early|mid|late)[ \t-]+)?[*_]*\Z", re.IGNORECASE)
_COMMA_READS_AS_DATE_BEFORE = re.compile(
    r"\b(?:by|up[ \t]+to|through|until|till|to|since|ends|ended|covers|covering)[ \t]+\Z", re.IGNORECASE)
_DATE_ENDS_HERE = re.compile(
    r"[ \t]*(?:\n|\Z)"                                             # a line end or the end of the text
    r"|[ \t]*(?:[.;:!?)\]\"'’”*_]|[-–—](?![ \t]*\d))"              # punctuation but %, a comma or bracket
    r"|[ \t]*(?:and\b|&|to\b|/)(?![ \t]*\d)"                       # "and", "&", "to" or "/" not before a number
    r"|[ \t]+(?:the|a|an|this|that|its|their"                      # an article or determiner
    r"|until|till|through|when|while|after|before|since|during|as)\b",
    re.IGNORECASE)
_CLAUSE_END = re.compile(r"\n|[.;:!?](?=[ \t]*(?:\n|\Z)|\s+[A-Z0-9])")
_ABBREVIATION = re.compile(r"\b(?:vs|v|approx|appx|abt|est|avg|i\.e|e\.g|etc|incl|excl|cf|no|nos|ca|c|viz|esp"
                           r"|resp|fig|pp|p|mr|mrs|ms|dr|st|jr|sr|inc|ltd|co|corp|bhd|pte|plc|u\.s|u\.k"
                           r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.", re.IGNORECASE)
_COMMA = re.compile(r"[ \t]*,")
_OPENING_BRACKET = re.compile(r"[ \t]*[(\[]")
_ONE_NUMBER = re.compile(r"[ \t]*[-+−]?\d+(?:,\d{3})*(?:\.\d+)?%?")
_NUMBER_NEXT = re.compile(r"[ \t]*[-+−]?\d")
_ENDS_AFTER_BRACKET = re.compile(r"[ \t]*(?:\n|\Z|[.;:!?)\]\"'’”*_])")
# In a bracket after a day: a digit ("(out of 45)", "(45 in August)") or a word of
# approximation ("(approx.)", "(about)", "(or so)") makes the day a count to check.
_COUNT_IN_BRACKET = re.compile(r"\d|~|\b(?:approx|approximately|appx|about|around|roughly|nearly|almost|some|est"
                               r"|estimated|or[ \t]+so|give[ \t]+or[ \t]+take)\b", re.IGNORECASE)


def _no_number_to_clause_end(text: str, pos: int) -> bool:
    """Whether no digit stands from pos to the end of its clause."""
    skip = [m.span() for m in _ABBREVIATION.finditer(text, pos)]
    end = next((m.start() for m in _CLAUSE_END.finditer(text, pos)
                if not any(s <= m.start() < e for s, e in skip)), len(text))
    return not any(ch.isdigit() for ch in text[pos:end])


def _date_ends_at_comma(text: str, after: int, before: str) -> bool:
    """Whether a day before a comma, `after` just past it, reads as a date."""
    if _COMMA_READS_AS_DATE_BEFORE.search(before) and not _NUMBER_NEXT.match(text, after):
        return True
    if _no_number_to_clause_end(text, after):
        return True
    one = _ONE_NUMBER.match(text, after)
    return bool(one) and _no_number_to_clause_end(text, one.end())


def _closing_bracket(text: str, i: int) -> int | None:
    """Where the bracket opened at i closes on its line, if it does."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "\n":
            return None
        if text[j] in "([":
            depth += 1
        elif text[j] in ")]":
            depth -= 1
            if depth == 0:
                return j
    return None


def _reads_as_date_after(text: str, end: int, before: str) -> bool:
    """Whether what follows a returned day (or range), at end, makes it read as a date."""
    if _DATE_ENDS_HERE.match(text, end):
        return True
    comma = _COMMA.match(text, end)
    if comma:
        return _date_ends_at_comma(text, comma.end(), before)
    bracket = _OPENING_BRACKET.match(text, end)
    close = _closing_bracket(text, bracket.end() - 1) if bracket else None
    if close is None or _COUNT_IN_BRACKET.search(text, bracket.end(), close):
        return False                    # no bracket, or "(45 posts)", "(approx.)": a count
    if _ENDS_AFTER_BRACKET.match(text, close + 1):
        return True                     # "September 25 (the end of the data)."
    comma = _COMMA.match(text, close + 1)
    return bool(comma) and bool(_COMMA_READS_AS_DATE_BEFORE.search(before)) \
        and not _NUMBER_NEXT.match(text, comma.end())     # "By September 25 (DBS), the score was 0.31."


_ISO_DAY = re.compile(r"\b\d{4}-(\d{2})-(\d{2})")
# Where tools write dates. Only these count: a date in the model's own search
# query, in a link or in a quoted sentence would let the model vouch for itself.
_DATE_KEYS = frozenset({"data_runs_to", "date", "earliest", "latest", "as_of_date", "published_at"})


def _tool_days(obj, out: set, key=None) -> None:
    """(month, day) of every date in a tool result's date fields."""
    if isinstance(obj, str):
        if key in _DATE_KEYS:
            out.update((int(m.group(1)), int(m.group(2))) for m in _ISO_DAY.finditer(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _tool_days(v, out, k)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _tool_days(v, out, key)


def _without_tool_dates(text: str, tool_results) -> str:
    days: set = set()
    _tool_days(tool_results, days)

    def blank(m: re.Match) -> str:
        written = m.group("month1") or m.group("month2")
        if written == "may":                     # the verb: "12 may be bots"
            return m.group(0)
        month = _MONTH_NUMBER[written[:3].lower()]
        if m.group("day2"):                      # "25 September"
            return " " if (month, int(m.group("day2"))) in days else m.group(0)
        if (month, int(m.group("day1"))) not in days:
            return m.group(0)
        if _SHARE_AFTER.match(m.string, m.end()):        # "25 per cent", "25 to 30% of posts": both checked
            return m.group(0)
        ranged = m.group("day1b") is not None
        before = m.string[:m.start()]
        if _IN_BEFORE.search(before) or not (
                _READS_AS_DATE_BEFORE.search(before) or (ranged and _RANGE_READS_AS_DATE_BEFORE.search(before))
                or _reads_as_date_after(m.string, m.end(), before)):
            return m.group(0)                    # "In September 25 customers": the day, and a range's both ends, checked
        if not ranged or (month, int(m.group("day1b"))) in days:
            return " "                           # "Data runs to September 25", "Sept 25-26."
        first_end = m.end("ord1") if m.group("ord1") else m.end("day1")
        return " " + m.string[first_end:m.end()]     # "Sept 25-27.": the first day alone; the second is checked

    return _YEARLESS_DATE.sub(blank, text) if days else text


# What in a tool result may vouch for an answer (an allow-list):
# numeric data fields anywhere, and the text of retrieved evidence for a figure
# written with its words around it (unverified_numbers). Everything else a tool
# returns is the system's own wording or the model's arguments echoed back (a
# search query, a window, a "reason" quoting them), timestamps, ids and links,
# whose digits are not figures. A skip-list of such fields missed new ones
# twice; an allow-list can't.
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
    number with every other accepted almost any percentage. An
    object made only of counts is a breakdown (analysts per rating): each
    count's share of their total is derivable too."""
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


def _collect_numbers(obj, out: list[float], as_written: list[float], key=None) -> None:
    """Numeric data fields into `out`; those that vouch only as written, not
    as a percentage (NON_DATA_NUMBER_KEYS), into `as_written`. Strings vouch
    for nothing here: a figure written inside a retrieved sentence ("$0.54 per
    share") vouches only for itself, written with that sentence's words around
    it (unverified_numbers, chatbot.agent.evidence_figures; until the tenth
    validation it vouched for the same number anywhere in the
    answer, a count of posts too)."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        (as_written if str(key) in NON_DATA_NUMBER_KEYS else out).append(float(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _collect_numbers(v, out, as_written, k)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out, as_written, key)


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
    mentions were positive"). A figure written as a retrieved sentence writes
    it, two or more of the three words nearest it on either side, common words
    such as "the" and "of" skipped, being among those nearest it in that
    sentence, or inside a quote of that sentence ('"DBS pays $0.54 per
    share"'), is that sentence's own and not checked
    (chatbot.agent.evidence_figures); a figure in retrieved text vouches for
    nothing else (the tenth and eleventh validations).
    Years, dates with their year (ISO or written out), a date without its
    year that matches one a tool returned, list markers, window lengths,
    numbers under 10 and numbers the user typed are not checked.
    """
    # chatbot.agent, which reads quotes as strip mode does, imports this module, so
    # it is imported here, when the check runs. It reads the answer with its line
    # endings and character references as the other checks do.
    from chatbot.agent import _decoded_marks, evidence_figures
    text = _decoded_marks(answer)
    for s, e in evidence_figures(text, tool_results):       # the retrieved sentence's own figures
        text = text[:s] + " " * (e - s) + text[e:]
    for pat in _STRIP_FIRST:
        text = pat.sub(" ", text)
    text = _without_tool_dates(text, tool_results)
    question_numbers = {m.group(0).rstrip("%").replace(",", "") for m in _NUMBER.finditer(question or "")}

    values: list[float] = []
    as_written: list[float] = []
    _collect_numbers(tool_results, values, as_written)
    values = list({round(v, 10) for v in values})
    candidates = values + [v * 100 for v in values] + as_written
    # A percentage is a fraction times 100, a field named as a percentage or a
    # ratio of two counts (below): 0.12 written as "0.12%" is a hundred times too
    # small, and a count of 23 written as "23%" is not a share (accepting any
    # value above 1 let counts pass).
    percent_fields: list[float] = []
    _percent_fields(tool_results, percent_fields)
    percent_candidates = [v * 100 for v in values] + percent_fields + as_written
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



# --- output: years -------------------------------------------------------------

_YEAR = re.compile(r"(?<!\d)(?<!\d[.,])(?:19|20)\d{2}(?!\d|[.,]\d)")   # not "0.2023", "2,023" or "20231"


def _collect_years(obj, out: set[str]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_years(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_years(v, out)
    elif isinstance(obj, str):
        out.update(_YEAR.findall(obj))
    elif isinstance(obj, int) and not isinstance(obj, bool) and 1900 <= obj <= 2099:
        out.add(str(obj))


def unverified_years(answer: str, tool_results: list, question: str = "") -> list[str]:
    """Years in the answer that no tool returned and the user did not type.

    unverified_numbers leaves years alone, so a person rating the answers
    found what no check did: "the data runs to September 2023" in three of 26
    answers, where the tools said 2026-09-25. A year counts as returned if it
    appears in any value a tool gave, a date ("2026-09-25"), a period
    ("2026-Q2", "August 2026") or a retrieved sentence's text."""
    known: set[str] = set(_YEAR.findall(question or ""))
    _collect_years(tool_results, known)
    flagged = []
    for y in _YEAR.findall(answer or ""):
        if y not in known and y not in flagged:
            flagged.append(y)
    return flagged

# --- output: sentence ids --------------------------------------------------------

_SENTENCE_ID = re.compile(r"\b[0-9a-f]{24}\b")


def unverified_sentence_ids(answer: str, retrieved_ids: set[str]) -> list[str]:
    """24-character sentence ids cited in the answer that were never retrieved."""
    return [sid for sid in _SENTENCE_ID.findall(answer or "") if sid not in retrieved_ids]


# --- output: readings --------------------------------------------------------------

# A score in words, as chatbot.tools.reading writes it. "neutral" alone is also a share of
# sentences ("30% neutral", "the neutral share"), which is not a reading, so those are left out.
_READING = re.compile(
    r"(?<!\bnot )(?<!\bno )(?<![\d%] )(?<![\d%])\b"
    r"(?:(?:slightly|moderately|clearly)\s+(?:positive|negative)|neutral)\b"
    r"(?!\s+(?:sentences?|shares?|mentions?|comments?|posts?|items?|articles?|reports?|results?|ones)\b)"
    r"(?!\s*\(?\s*\d+(?:\.\d+)?\s*%)", re.IGNORECASE)
# Words inside quote marks are a retrieved sentence's, not the answer's own reading of a score.
_QUOTED = re.compile(r'["“][^"“”]*["”]')


def _collect_readings(obj, out: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k) == "reading" and isinstance(v, str):
                out.add(v.strip().lower())
            else:
                _collect_readings(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_readings(v, out)


def returned_readings(tool_results: list) -> set[str]:
    """Every reading the tools returned, lower case."""
    out: set[str] = set()
    _collect_readings(tool_results, out)
    return out


def unverified_readings(answer: str, tool_results: list) -> list[str]:
    """Readings the answer gives a score that no tool returned as a reading.

    The tools put each score in words (`reading`: "neutral", "slightly",
    "moderately" or "clearly" positive or negative, bands in
    config/chatbot.yaml). An answer once called a topic "neutral" and
    "slightly positive" beside a score the tool read as "clearly positive". A
    reading in the answer must be one a tool returned for this question; it is
    not checked against which score it describes, so a bank's overall
    reading can vouch for a topic's. Words in quote marks are evidence, and
    "neutral" as a share of sentences is not a reading; neither is checked.
    """
    returned = returned_readings(tool_results)
    text = _QUOTED.sub(" ", answer or "")
    found = {re.sub(r"\s+", " ", m.group(0).lower()) for m in _READING.finditer(text)}
    return sorted(found - returned)
