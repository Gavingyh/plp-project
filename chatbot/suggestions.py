"""
Suggested questions for a chat UI to offer as clickable prompts.

Generated from what the sentiment store actually contains, not hardcoded.
A suggestion the system cannot answer is worse than no suggestion: the user
clicks it, gets "insufficient data", and reasonably concludes the whole
thing is broken. So every suggestion here is checked against real row counts
first - aspect questions only for (bank, aspect) pairs above the volume
floor, trend questions only where the 7d window also has data, and analyst
questions only for banks with a stored consensus snapshot.

DELIBERATELY NOT SUGGESTED: advice-seeking questions ("Should I buy DBS?")
and out-of-scope questions. The chatbot is built to decline those, so
putting them in front of a user as an invitation would be wrong for a tool
that carries a not-financial-advice disclaimer. They live in
chatbot/eval_gold_set.py, where the point is to test the refusal.
"""

from chatbot.tools import MIN_VOLUME_FOR_SCORE
from ingest.db import get_connection

# Question-friendly phrasings. Deliberately not reusing the display labels in
# config/aspects.yaml - "Asset Quality / Provisioning" reads badly mid-
# sentence, and "other" is a catch-all bucket that makes no sense as a
# question ("sentiment on other?"), so it is excluded entirely.
_ASPECT_PHRASING = {
    "dividend_policy": "dividend policy",
    "asset_quality": "asset quality",
    "net_interest_margin": "net interest margin",
    "management_guidance": "management guidance",
}

# Simplest and most reliable question types first.
_CATEGORY_ORDER = ["overall", "aspect", "compare", "consensus", "trend", "evidence"]


def _available(window: str = "all_time") -> list[tuple[str, str, int]]:
    """(bank, aspect, n) rows above the volume floor for a given window."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT bank, aspect, n FROM sentiment_index "
            "WHERE window = ? AND source = 'ALL' AND n >= ? ORDER BY n DESC",
            (window, MIN_VOLUME_FOR_SCORE),
        ).fetchall()
    except Exception:
        return []  # table may not exist on a fresh install
    finally:
        conn.close()


def _banks_with_consensus() -> list[str]:
    conn = get_connection()
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT bank FROM analyst_consensus ORDER BY bank").fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def build_candidates() -> list[dict]:
    """Every question the current data can actually answer."""
    all_time = _available("all_time")
    recent = {(b, a) for b, a, _ in _available("7d")}

    overall = [(b, n) for b, a, n in all_time if a == "ALL"]
    aspects = [(b, a, n) for b, a, n in all_time if a in _ASPECT_PHRASING]

    candidates: list[dict] = []

    for bank, n in overall:
        candidates.append({
            "category": "overall", "bank": bank, "support": n,
            "question": f"What is the overall sentiment on {bank}?"})

    for bank, aspect, n in aspects:
        candidates.append({
            "category": "aspect", "bank": bank, "support": n,
            "question": f"What is the sentiment for {bank} on {_ASPECT_PHRASING[aspect]}?"})

    # Comparisons need every bank to have the aspect, or the answer is lopsided.
    by_aspect: dict[str, set[str]] = {}
    for bank, aspect, _ in aspects:
        by_aspect.setdefault(aspect, set()).add(bank)
    for aspect, banks in by_aspect.items():
        if len(banks) == 3:
            total = sum(n for b, a, n in aspects if a == aspect)
            candidates.append({
                "category": "compare", "bank": None, "support": total,
                "question": f"Compare DBS, OCBC and UOB on {_ASPECT_PHRASING[aspect]}."})

    # Trends need the 7d window too, or get_trend has nothing recent to
    # compare against and the answer doesn't address what was asked.
    for bank, aspect, n in aspects:
        if (bank, aspect) in recent:
            candidates.append({
                "category": "trend", "bank": bank, "support": n,
                "question": f"Has sentiment on {bank}'s {_ASPECT_PHRASING[aspect]} "
                            f"changed recently?"})

    for bank, aspect, n in aspects:
        candidates.append({
            "category": "evidence", "bank": bank, "support": n,
            "question": f"Show me evidence about {bank}'s {_ASPECT_PHRASING[aspect]}."})

    for bank in _banks_with_consensus():
        candidates.append({
            "category": "consensus", "bank": bank, "support": 0,
            "question": f"What do analysts think of {bank}?"})

    return candidates


def get_suggestions(limit: int = 6) -> list[dict]:
    """A varied, answerable set of starter questions.

    Varies on two axes, because sorting by support alone returns six
    questions about DBS - it has by far the most data, so it wins every
    category - which reads as a dashboard that only covers one bank. So
    this takes one question per category in rotation, and within a category
    prefers a bank that hasn't appeared yet.
    """
    by_category: dict[str, list[dict]] = {}
    for c in sorted(build_candidates(), key=lambda c: -c["support"]):
        by_category.setdefault(c["category"], []).append(c)

    picked: list[dict] = []
    seen_banks: set[str] = set()
    seen_questions: set[str] = set()

    while len(picked) < limit:
        progressed = False
        for category in _CATEGORY_ORDER:
            if len(picked) >= limit:
                break
            bucket = [c for c in by_category.get(category, [])
                      if c["question"] not in seen_questions]
            if not bucket:
                continue
            # Prefer an under-represented bank; fall back to best-supported.
            fresh = [c for c in bucket if c["bank"] and c["bank"] not in seen_banks]
            choice = fresh[0] if fresh else bucket[0]
            picked.append(choice)
            seen_questions.add(choice["question"])
            if choice["bank"]:
                seen_banks.add(choice["bank"])
            progressed = True
        if not progressed:
            break  # every category exhausted

    return [{"question": p["question"], "category": p["category"]} for p in picked]
