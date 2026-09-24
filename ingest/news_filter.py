"""
Relevance filter and cross-source dedup shared by every news adapter.

Every news pull (yahoo_news, google_news, newsapi, alphavantage) goes through
filter_and_dedup() before upsert_documents(), so the same rules apply whichever
source an article came from:

1. Bank mention. The title (plus snippet, where the source has one) must name
   DBS, OCBC or UOB. Search engines return plenty of results that don't, e.g. a
   "UOB Singapore" query returns general Singapore economy stories.

2. Broker and venue false positives. Names like "UOB Kay Hian" (a separately
   listed broker), "DBS Vickers" and "OCBC Arena" contain a bank's name but
   are not about the bank's own business. These phrases are masked before the
   bank-mention check, so "UOB Kay Hian upgrades DBS" counts as a DBS article
   and "UOB Kay Hian names top picks" counts as no bank at all.
   The masking is news-only. ingest/base.py's detect_banks is left alone,
   because Reddit complaints about a DBS Vickers trading account are
   plausibly about DBS the group.

3. Cross-source dedup. The same story arrives via Yahoo and Google News, and
   wire copy is syndicated across outlets. A candidate is a duplicate when its
   normalised URL matches an existing news document, or its normalised title
   is >= TITLE_SIMILARITY similar to one published within DUP_WINDOW_DAYS.
   The first copy stored wins, and adapters run Yahoo first because Yahoo
   carries a summary, not just a headline.

Nothing is silently dropped. Every article rejected by rule 1, 2 or 3, every
article kept but containing a masked phrase, and every kept headline that
reads like the bank's economists commenting on something else, is written to
data/news_flagged.csv with the reason, so the rules can be audited.
"""

import csv
import os
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit

from ingest.db import get_connection, init_db, now_iso

from config.logging_config import get_logger


logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAGGED_PATH = os.path.join(BASE_DIR, "data", "news_flagged.csv")

NEWS_SOURCES = ("newsapi", "alphavantage", "yahoo_news", "google_news")

TITLE_SIMILARITY = 0.90
DUP_WINDOW_DAYS = 3

# Bank-mention aliases for news text. Superset of ingest/base.py BANKS: adds
# the US OTC ADR tickers, which Yahoo headlines use ("FBP or DBSDY: ..."),
# and POSB, DBS's own retail savings brand (part of DBS Bank, not a
# subsidiary). Separately branded subsidiaries (OCBC's Bank of Singapore and
# Great Eastern) are not aliased; their headlines land in news_flagged.csv.
_NEWS_ALIASES = {
    "DBS": ["DBS", "DBS Bank", "DBS Group", "D05.SI", "DBSDY", "POSB"],
    "OCBC": ["OCBC", "OCBC Bank", "Oversea-Chinese Banking", "O39.SI", "OVCHY"],
    "UOB": ["UOB", "United Overseas Bank", "U11.SI", "UOVEY"],
}
_MENTION = {
    bank: re.compile(r"\b(?:" + "|".join(re.escape(a) for a in aliases) + r")\b", re.IGNORECASE)
    for bank, aliases in _NEWS_ALIASES.items()
}

# Names that contain a bank's name but are about another business. Each
# entry is (label, pattern). Matches are masked before the mention check.
FALSE_POSITIVES = [
    ("UOB Kay Hian", r"UOB[\s-]*Kay[\s-]*Hian|UOBKH"),
    ("DBS Vickers", r"DBS[\s-]*Vickers"),
    ("OCBC Securities", r"OCBC[\s-]*Securities"),
    ("OCBC Arena", r"OCBC[\s-]*Arena"),
    ("OCBC Square", r"OCBC[\s-]*Square"),
    ("OCBC Cycle", r"OCBC[\s-]*Cycle"),
    ("DBS Marina Regatta", r"DBS[\s-]*Marina[\s-]*Regatta"),
    ("UOB Plaza", r"UOB[\s-]*Plaza"),
    ("UOB Painting of the Year", r"UOB[\s-]*Painting[\s-]*of[\s-]*the[\s-]*Year"),
    # The bank's research desk or economists commenting on something else
    # ("DBS analysts", "OCBC economist Selena Ling"). Only the bank token is
    # masked (lookahead), so "UOB analysts say DBS ..." still counts for DBS.
    ("research attribution",
     r"\b(?:DBS|OCBC|UOB)(?=(?:'s|’s)?\s+(?:Group\s+Research|Investment\s+Research|Global\s+Research"
     r"|research|analysts?|economists?|chief\s+economist|strategists?|CIO\b|Chief\s+Investment\s+Office))"),
    # A headline that opens with the bank, or a named analyst at it, issuing a
    # rating or forecast call on another company: "DBS maintains 'buy' on IHH",
    # "OCBC cuts gold forecasts", "OCBC's Lim raises fair value for SingPost".
    # Deliberately needs a rating word, so "DBS raises dividend" doesn't match.
    ("rating call",
     r"^\s*(?:DBS|OCBC|UOB)(?=(?:'s|’s)?\s+(?:\w+\s+){0,2}(?:maintains|keeps|reiterates|upgrades|downgrades"
     r"|raises|lifts|cuts|trims|lowers|initiates|optimistic|bullish|bearish)\b[^.]*?"
     r"(?:\bbuy\b|\bsell\b|\bhold\b|target\s+price|fair\s+value|\bTPs?\b|\bcall\b|\brating\b"
     r"|\bforecasts?\b))"),
]

# Headlines that credit the bank as the speaker at the end: "Vietnam currency
# to strengthen: UOB", "..., says OCBC's Menon". Most are the bank's
# economists or research desk on something else, but a real minority are
# about the bank ("Review: OCBC Rewards Card", "Citibank deal to complete by
# Nov: UOB"). So these are kept, and only flagged for human review.
_COMMENTARY_HINT = re.compile(
    r"(?:[:\-–—]|,?\s+says)\s*(?:DBS|OCBC|UOB)(?:'s|’s)?(?:\s+[\w-]+){0,4}\s*$", re.IGNORECASE)

# When that credited speaker is talking about a currency, rates, commodities
# or the macro economy, the headline is one of the banks' daily market notes,
# syndicated in bulk by FX sites since 2026 ("Australian Dollar: Gradual
# upside within capped range – UOB"). Those are about the market, not the
# bank, so the credit is masked like a broker name.
_MARKET_TOPIC = re.compile(
    r"\b(?:dollar|yen|yuan|renminbi|RMB|won|ringgit|rupiah|peso|baht|euro|pound|sterling|"
    r"franc|rupee|dong|NEER|USD|SGD|EUR|JPY|CNH|AUD|NZD|GBP|KRW|INR|IDR|MYR|THB|PHP|VND|"
    r"TWD|HKD|FX|oil|gold|silver|copper|brent|Fed|Federal\s+Reserve|FOMC|BoJ|BoE|ECB|PBoC|RBA|"
    r"RBI|BSP|central\s+bank|rate\s+(?:cut|hike)s?|yields?|Treasur(?:y|ies)|inflation|CPI|GDP|"
    r"recession|tariffs?|STI|Straits\s+Times\s+Index|Nikkei|Hang\s+Seng|S&P)\b", re.IGNORECASE)
# (CNY is left out: in Singapore headlines it is Chinese New Year as often as
# the yuan.) The bank's own news can share that shape, "Singapore's best FX
# bank: DBS", "Tokenized Physical Gold: DBS Unveils ...", so awards and
# launches are exempt, as are own results.
_MARKET_NOTE_EXEMPT = re.compile(
    r"\bbest\b[^:–—-]*\bbank\b|\baward|\bunveil|\blaunch|\bintroduc", re.IGNORECASE)
_FALSE_POSITIVE_RES = [(label, re.compile(p, re.IGNORECASE)) for label, p in FALSE_POSITIVES]

# A "rating call" headline that also talks about the bank's own results is
# the bank's news, not a call on someone else: "UOB CEO lowers loan growth
# forecast as first-quarter profit leaps", "OCBC keeps earnings guidance".
_OWN_PERFORMANCE = re.compile(
    r"\b(?:profit|guidance|loan\s+growth|net\s+interest|NIM|dividends?)\b", re.IGNORECASE)

_FLAG_FIELDS = ["flagged_at", "reason", "kept", "source", "doc_id", "banks", "phrases",
                "duplicate_of", "published_at", "title", "url"]


def mask_false_positives(text: str) -> tuple[str, list[str]]:
    """Replace broker/venue names with a neutral token and report which fired."""
    found = []
    credit = _COMMENTARY_HINT.search(text)
    if (credit and _MARKET_TOPIC.search(text[:credit.start()])
            and not _OWN_PERFORMANCE.search(text) and not _MARKET_NOTE_EXEMPT.search(text)):
        found.append("market note")
        text = text[:credit.start()] + " _masked_ "
    for label, pat in _FALSE_POSITIVE_RES:
        if label == "rating call" and _OWN_PERFORMANCE.search(text):
            continue
        if pat.search(text):
            found.append(label)
            text = pat.sub(" _masked_ ", text)
    return text, found


def doc_text(title: str | None, body: str | None) -> str:
    """The text the rules run on. Every adapter builds body as the title, or
    title + ". " + snippet, so the body alone is used when it starts with the
    title. Concatenating would repeat the title, and the start-anchored
    "rating call" rule would mask only the first copy."""
    title, body = title or "", body or ""
    return body if body.startswith(title) else f"{title} {body}".strip()


def mentioned_banks(text: str) -> tuple[list[str], list[str]]:
    """(banks named after masking, false-positive phrases masked)."""
    masked, phrases = mask_false_positives(text or "")
    return [b for b, pat in _MENTION.items() if pat.search(masked)], phrases


def normalise_url(url: str) -> str:
    """Scheme-, www- and tracking-parameter-insensitive URL key."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query)
                             if not k.lower().startswith(("utm_", "guccounter", "guce_"))))
    return f"{host}{parts.path.rstrip('/')}" + (f"?{query}" if query else "")


def normalise_title(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    m = SequenceMatcher(None, a, b)
    return m.real_quick_ratio() >= TITLE_SIMILARITY and m.quick_ratio() >= TITLE_SIMILARITY \
        and m.ratio() >= TITLE_SIMILARITY


def _day(published_at: str) -> int:
    try:
        return datetime.fromisoformat(published_at.replace("Z", "+00:00")).toordinal()
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc).toordinal()


class _Index:
    """Existing news documents keyed for the two dedup checks."""

    def __init__(self):
        self.doc_ids: set[str] = set()
        self.urls: dict[str, str] = {}
        self.by_day: dict[int, list[tuple[str, str]]] = {}

    def add(self, doc_id: str, title: str, url: str, published_at: str):
        self.doc_ids.add(doc_id)
        key = normalise_url(url)
        if key:
            self.urls.setdefault(key, doc_id)
        self.by_day.setdefault(_day(published_at), []).append((normalise_title(title), doc_id))

    def find_duplicate(self, title: str, url: str, published_at: str) -> str | None:
        key = normalise_url(url)
        if key and key in self.urls:
            return self.urls[key]
        norm = normalise_title(title)
        d = _day(published_at)
        for day in range(d - DUP_WINDOW_DAYS, d + DUP_WINDOW_DAYS + 1):
            for other, doc_id in self.by_day.get(day, ()):
                if _similar(norm, other):
                    return doc_id
        return None


def load_index() -> _Index:
    init_db()
    idx = _Index()
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(NEWS_SOURCES))
        for doc_id, title, url, published_at in conn.execute(
            f"SELECT doc_id, title, url, published_at FROM documents WHERE source IN ({placeholders})",
            NEWS_SOURCES,
        ):
            idx.add(doc_id, title, url, published_at)
    finally:
        conn.close()
    return idx


def filter_and_dedup(docs: list[dict], index: _Index | None = None) -> tuple[list[dict], dict]:
    """Apply the relevance and dedup rules. Returns (docs to insert, stats).

    A doc whose doc_id is already stored, or was already kept earlier in this
    batch (Google returns the same article for overlapping queries), is
    skipped and counted as already_stored. That check runs first so a
    re-run doesn't flag every article as a duplicate of itself.
    """
    index = index or load_index()
    kept, flagged = [], []
    stats = {"input": len(docs), "already_stored": 0, "no_bank_mention": 0,
             "false_positive_only": 0, "duplicate": 0, "kept": 0, "kept_with_phrase": 0,
             "kept_possible_commentary": 0}

    for d in docs:
        if d["doc_id"] in index.doc_ids:
            stats["already_stored"] += 1
            continue
        banks, phrases = mentioned_banks(doc_text(d.get("title"), d.get("body")))
        row = {"source": d["source"], "doc_id": d["doc_id"], "banks": "|".join(banks),
               "phrases": "|".join(phrases), "duplicate_of": "",
               "published_at": d["published_at"], "title": d.get("title") or "", "url": d["url"]}

        if not banks:
            reason = "false_positive_only" if phrases else "no_bank_mention"
            stats[reason] += 1
            flagged.append({**row, "reason": reason, "kept": 0})
            continue

        dup = index.find_duplicate(d.get("title") or d["body"], d["url"], d["published_at"])
        if dup:
            stats["duplicate"] += 1
            flagged.append({**row, "reason": "duplicate", "kept": 0, "duplicate_of": dup})
            continue

        d = {**d, "bank": banks[0] if len(banks) == 1 else "MULTI"}
        if phrases:
            stats["kept_with_phrase"] += 1
            d["raw"] = {**(d.get("raw") or {}), "_masked_phrases": phrases}
            flagged.append({**row, "reason": "kept_with_false_positive_phrase", "kept": 1})
        if _COMMENTARY_HINT.search(d.get("title") or ""):
            stats["kept_possible_commentary"] += 1
            flagged.append({**row, "reason": "kept_possible_bank_commentary", "kept": 1})
        index.add(d["doc_id"], d.get("title") or d["body"], d["url"], d["published_at"])
        kept.append(d)
        stats["kept"] += 1

    _append_flagged(flagged)
    return kept, stats


def audit_stored() -> dict:
    """Re-check stored news against the current rules, without changing the DB.

    For when the rules are tightened after a pull: a stored article that the
    current rules would reject is flagged `stored_fails_current_rules` in
    news_flagged.csv, and one matching the commentary hint is flagged
    `kept_possible_bank_commentary`. Removing rows is left to a person.
    """
    init_db()
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(NEWS_SOURCES))
        rows = conn.execute(
            f"""SELECT doc_id, source, title, body, published_at, url FROM documents
                WHERE source IN ({placeholders})""", NEWS_SOURCES).fetchall()
    finally:
        conn.close()
    flagged, stats = [], {"checked": len(rows), "fails_current_rules": 0, "possible_commentary": 0}
    for doc_id, source, title, body, published_at, url in rows:
        banks, phrases = mentioned_banks(doc_text(title, body))
        row = {"source": source, "doc_id": doc_id, "banks": "|".join(banks),
               "phrases": "|".join(phrases), "duplicate_of": "", "published_at": published_at,
               "title": title or "", "url": url, "kept": 1}
        if not banks:
            stats["fails_current_rules"] += 1
            flagged.append({**row, "reason": "stored_fails_current_rules"})
        elif _COMMENTARY_HINT.search(title or ""):
            stats["possible_commentary"] += 1
            flagged.append({**row, "reason": "kept_possible_bank_commentary"})
    _append_flagged(flagged, replace_reasons=("stored_fails_current_rules",))
    return stats


def _append_flagged(rows: list[dict], path: str | None = None,
                    replace_reasons: tuple[str, ...] = ()) -> None:
    """Merge into the review CSV, keyed on (doc_id, reason), so re-runs don't grow it.
    Rows with a reason in replace_reasons are dropped first, so a re-audit
    under changed rules doesn't leave stale flags behind."""
    path = path or FLAGGED_PATH
    if not rows and not replace_reasons:
        return
    existing = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["reason"] not in replace_reasons:
                    existing[(r["doc_id"], r["reason"])] = r
    stamp = now_iso()
    for r in rows:
        existing.setdefault((r["doc_id"], r["reason"]), {**r, "flagged_at": stamp})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_FLAG_FIELDS)
        w.writeheader()
        for r in sorted(existing.values(), key=lambda r: (r["reason"], r["published_at"])):
            w.writerow({k: r.get(k, "") for k in _FLAG_FIELDS})


def recent_window(days_back: int) -> tuple[str, str]:
    """(since, until) ISO dates covering the last `days_back` days, for daily runs."""
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=days_back)).isoformat(), (today + timedelta(days=1)).isoformat()
