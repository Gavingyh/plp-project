"""
Tool implementations for the agentic chatbot — MVP plan Phase 8.

Plain Python functions, not a framework (see plan Phase 8, "Architecture" for
the rationale: the agent loop is small enough that a framework adds
abstraction without adding capability at this scale).

Every tool that reports a score also reports `n` — the hallucination/
misleading-number defense the plan calls out is enforced HERE, in the data
contract, not left to the model to remember to mention. `get_coverage` exists
specifically so the agent can check "do I have data on this at all" before
answering, rather than confabulating when it doesn't.
"""

from ingest.db import get_connection
from chatbot.retrieval import search_evidence as _search_evidence

MIN_VOLUME_FOR_SCORE = 5  # below this, report insufficient data rather than a number


def get_sentiment(bank: str, aspect: str | None = None) -> dict:
    """Current sentiment index for a bank, optionally filtered to one aspect
    ('ALL' aspect = overall). Returns insufficient_data=True below the volume floor."""
    conn = get_connection()
    try:
        aspect_filter = aspect or "ALL"
        row = conn.execute(
            "SELECT score, n, pos_n, neu_n, neg_n, confidence_mean, model_version, computed_at "
            "FROM sentiment_index WHERE bank = ? AND aspect = ? ORDER BY computed_at DESC LIMIT 1",
            (bank, aspect_filter),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {"bank": bank, "aspect": aspect_filter, "insufficient_data": True,
                "reason": "no sentiment data computed for this bank/aspect combination"}
    score, n, pos, neu, neg, conf, model_version, computed_at = row
    if n < MIN_VOLUME_FOR_SCORE:
        return {"bank": bank, "aspect": aspect_filter, "insufficient_data": True, "n": n,
                "reason": f"only {n} data points, below the minimum of {MIN_VOLUME_FOR_SCORE} "
                          "needed to report a reliable score"}
    return {"bank": bank, "aspect": aspect_filter, "score": score, "n": n,
            "positive_n": pos, "neutral_n": neu, "negative_n": neg,
            "confidence_mean": conf, "model_version": model_version, "computed_at": computed_at,
            "insufficient_data": False}


def compare_banks(aspect: str | None = None) -> dict:
    """Side-by-side sentiment across DBS/OCBC/UOB for one aspect (or overall)."""
    results = {bank: get_sentiment(bank, aspect) for bank in ("DBS", "OCBC", "UOB")}
    return {"aspect": aspect or "ALL", "banks": results}


def get_trend(bank: str, aspect: str | None = None) -> dict:
    """Direction/magnitude of sentiment change over time.

    MVP LIMITATION: sentiment_index currently stores a single all-time
    aggregate per (bank, aspect) — see aggregate/index.py `window` column,
    which is hard-coded to 'all_time' for the MVP. Rolling 7d/30d windows
    (plan Phase 6, step 3) are a documented next step, not yet implemented.
    This tool is wired up now so the chatbot's tool-calling contract is
    stable, but currently returns the single available data point rather
    than a real trend line.
    """
    current = get_sentiment(bank, aspect)
    return {**current, "trend_available": False,
            "note": "Rolling-window trend data isn't implemented yet (MVP scope) — "
                     "only an all-time aggregate is available. See aggregate/index.py."}


def get_coverage(bank: str | None = None, aspect: str | None = None) -> dict:
    """What data actually exists — call this BEFORE answering a question the
    other tools come back empty on, to distinguish 'no data' from 'zero
    sentiment'. This is the cheapest hallucination defense available (plan
    Phase 8, 'Grounding rules')."""
    where, params = ["1=1"], []
    if bank:
        where.append("s.bank = ?"); params.append(bank)
    join = ""
    if aspect:
        join = "JOIN sentence_aspects sa ON sa.sentence_id = s.sentence_id"
        where.append("sa.aspect = ?"); params.append(aspect)
    where_clause = " AND ".join(where)

    conn = get_connection()
    try:
        row = conn.execute(
            f"SELECT COUNT(*), MIN(s.published_at), MAX(s.published_at) "
            f"FROM sentences s {join} WHERE {where_clause}",
            params,
        ).fetchone()
        by_source = conn.execute(
            f"SELECT s.source, COUNT(*) FROM sentences s {join} WHERE {where_clause} GROUP BY s.source",
            params,
        ).fetchall()
    finally:
        conn.close()
    n, earliest, latest = row
    return {"bank": bank or "ALL", "aspect": aspect or "ALL", "n": n,
            "earliest": earliest, "latest": latest,
            "by_source": {src: cnt for src, cnt in by_source}, "has_data": n > 0}


def search_evidence(query: str, bank: str | None = None, aspect: str | None = None,
                     sentiment: str | None = None, k: int = 5) -> dict:
    """RAG evidence search (chatbot/retrieval.py) — quotes with citations for
    any qualitative claim. See plan Phase 8, 'Grounding rules': every
    qualitative claim must cite a sentence_id + url."""
    results = _search_evidence(query, bank=bank, aspect=aspect, sentiment=sentiment, k=k)
    return {"query": query, "results": results, "n_found": len(results)}


# Anthropic tool-use schema for the four structured-data tools + search_evidence.
# See chatbot/agent.py for how these are wired into the tool-calling loop.
TOOL_SCHEMAS = [
    {
        "name": "get_sentiment",
        "description": "Get the current sentiment index for one bank (DBS, OCBC, or UOB), "
                        "optionally for a specific aspect. Always check the insufficient_data "
                        "flag before reporting a score.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bank": {"type": "string", "enum": ["DBS", "OCBC", "UOB"]},
                "aspect": {"type": "string",
                           "description": "One of the frozen aspect keys (see config/aspects.yaml), "
                                          "or omit for overall sentiment."},
            },
            "required": ["bank"],
        },
    },
    {
        "name": "compare_banks",
        "description": "Compare sentiment across all three banks for one aspect, or overall.",
        "input_schema": {
            "type": "object",
            "properties": {"aspect": {"type": "string"}},
        },
    },
    {
        "name": "get_trend",
        "description": "Get sentiment trend/direction for a bank and aspect over time. "
                        "NOTE: currently returns only an all-time snapshot, not a real trend "
                        "(rolling windows not yet implemented) — the tool response says so.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bank": {"type": "string", "enum": ["DBS", "OCBC", "UOB"]},
                "aspect": {"type": "string"},
            },
            "required": ["bank"],
        },
    },
    {
        "name": "get_coverage",
        "description": "Check what data exists for a bank/aspect BEFORE answering — use this "
                        "whenever another tool returns no/thin data, to tell 'we have no data on "
                        "this' apart from 'sentiment happens to be neutral'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bank": {"type": "string", "enum": ["DBS", "OCBC", "UOB"]},
                "aspect": {"type": "string"},
            },
        },
    },
    {
        "name": "search_evidence",
        "description": "Search for actual supporting sentences (with source URL and date) for a "
                        "qualitative claim. Every qualitative statement in your answer must be "
                        "backed by a result from this tool, cited by sentence_id/url.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for, in natural language."},
                "bank": {"type": "string", "enum": ["DBS", "OCBC", "UOB"]},
                "aspect": {"type": "string"},
                "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                "k": {"type": "integer", "description": "Max results, default 5"},
            },
            "required": ["query"],
        },
    },
]

TOOL_FUNCTIONS = {
    "get_sentiment": lambda **kw: get_sentiment(**kw),
    "compare_banks": lambda **kw: compare_banks(**kw),
    "get_trend": lambda **kw: get_trend(**kw),
    "get_coverage": lambda **kw: get_coverage(**kw),
    "search_evidence": lambda **kw: search_evidence(**kw),
}
