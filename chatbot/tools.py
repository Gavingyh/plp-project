"""
Tool implementations for the agentic chatbot — see docs/DESIGN.md.

Plain Python functions, not a framework: the agent loop is small enough that
a framework would add abstraction without adding capability at this scale.

Every tool that reports a score also reports `n` — the misleading-number
defense is enforced HERE, in the data contract, not left to the model to
remember to mention. `get_coverage` exists specifically so the agent can
check "do I have data on this at all" before answering, rather than
confabulating when it doesn't.
"""

import os

import yaml

from aggregate.index import compute_time_series
from ingest.db import get_connection
from chatbot.retrieval import search_evidence as _search_evidence

MIN_VOLUME_FOR_SCORE = 5  # below this, report insufficient data rather than a number

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ASPECTS_CONFIG_PATH = os.path.join(_BASE_DIR, "config", "aspects.yaml")


def _load_aspect_keys() -> list[str]:
    """Real aspect keys from config/aspects.yaml, so the tool schema's enum
    and the actual taxonomy can never drift apart. A model given an open
    string field for `aspect` was observed passing "dividend policy" (a
    space, matching how the question was phrased) instead of the real key
    "dividend_policy", silently producing insufficient_data on a perfectly
    valid question. Falls back to the four proposal aspects if the config
    can't be read, so tool schemas still build during tests that don't need
    the real file."""
    try:
        with open(_ASPECTS_CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        return list(config["aspects"].keys())
    except Exception:
        return ["dividend_policy", "asset_quality", "net_interest_margin",
                "management_guidance", "other"]


ASPECT_KEYS = _load_aspect_keys()


def normalize_aspect(aspect: str | None) -> str | None:
    """Best-effort correction for the failure mode above: lowercases and
    replaces spaces/hyphens with underscores, then only accepts the result if
    it matches a real aspect key. A genuinely wrong aspect is left as-is
    rather than guessed at, so it still surfaces as insufficient_data instead
    of silently mapping to the wrong aspect."""
    if aspect is None:
        return None
    candidate = aspect.strip().lower().replace(" ", "_").replace("-", "_")
    return candidate if candidate in ASPECT_KEYS else aspect


def get_sentiment(bank: str, aspect: str | None = None, window: str = "all_time") -> dict:
    """Sentiment index for a bank, optionally filtered to one aspect ('ALL' aspect
    = overall) and one window ('7d', '30d', or 'all_time' — see aggregate/index.py).
    Returns insufficient_data=True below the volume floor, or if no row exists at
    all for this window (e.g. genuinely nothing published in the last 7 days)."""
    conn = get_connection()
    try:
        aspect_filter = aspect or "ALL"
        row = conn.execute(
            "SELECT score, n, pos_n, neu_n, neg_n, confidence_mean, model_version, computed_at "
            # source='ALL' is the blended headline row; per-source rows sit
            # alongside it (see aggregate/index.py) and must not be picked up
            # here by accident.
            "FROM sentiment_index WHERE bank = ? AND aspect = ? AND window = ? "
            "AND source = 'ALL' ORDER BY computed_at DESC LIMIT 1",
            (bank, aspect_filter, window),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {"bank": bank, "aspect": aspect_filter, "window": window, "insufficient_data": True,
                "reason": f"no sentiment data computed for this bank/aspect/window combination "
                          f"(window={window!r} may genuinely have zero items, or the pipeline "
                          "hasn't been run since new data came in)"}
    score, n, pos, neu, neg, conf, model_version, computed_at = row
    if n < MIN_VOLUME_FOR_SCORE:
        return {"bank": bank, "aspect": aspect_filter, "window": window,
                "insufficient_data": True, "n": n,
                "reason": f"only {n} data points, below the minimum of {MIN_VOLUME_FOR_SCORE} "
                          "needed to report a reliable score"}
    return {"bank": bank, "aspect": aspect_filter, "window": window, "score": score, "n": n,
            "positive_n": pos, "neutral_n": neu, "negative_n": neg,
            "confidence_mean": conf, "model_version": model_version, "computed_at": computed_at,
            "insufficient_data": False}


def compare_banks(aspect: str | None = None, window: str = "all_time") -> dict:
    """Side-by-side sentiment across DBS/OCBC/UOB for one aspect (or overall)."""
    results = {bank: get_sentiment(bank, aspect, window) for bank in ("DBS", "OCBC", "UOB")}
    return {"aspect": aspect or "ALL", "window": window, "banks": results}


def get_trend(bank: str, aspect: str | None = None) -> dict:
    """Direction/magnitude of sentiment change: compares the 7d window against
    the 30d window (both from aggregate/index.py's rolling windows). Falls back
    to reporting all_time alone if either rolling window has insufficient data —
    a trend computed from a handful of items either side is noise, not signal."""
    recent = get_sentiment(bank, aspect, window="7d")
    baseline = get_sentiment(bank, aspect, window="30d")
    fallback = get_sentiment(bank, aspect, window="all_time")

    if recent["insufficient_data"] or baseline["insufficient_data"]:
        return {**fallback, "trend_available": False,
                "note": "Not enough recent data to compute a 7d-vs-30d trend "
                        f"(7d insufficient={recent['insufficient_data']}, "
                        f"30d insufficient={baseline['insufficient_data']}) — "
                        "showing the all-time snapshot instead."}

    delta = round(recent["score"] - baseline["score"], 4)
    direction = "improving" if delta > 0.02 else "declining" if delta < -0.02 else "stable"

    # A two-point comparison can only say "up" or "down". The monthly series
    # gives the shape behind that. Capped at 12 points and trimmed to
    # period/score/n on purpose: this goes into the model's context, and a
    # long table of numbers is more surface to misquote, not more insight.
    try:
        series = [{"period": p["period"], "score": p["score"], "n": p["n"]}
                  for p in compute_time_series(bank, aspect, bucket="month")
                  if p["sufficient"]][-12:]
    except Exception:
        series = []

    return {"bank": bank, "aspect": aspect or "ALL", "trend_available": True,
            "direction": direction, "delta_7d_vs_30d": delta,
            "recent_7d": recent, "baseline_30d": baseline,
            "monthly_series": series,
            "series_note": "monthly, same weighting and shrinkage as the index; "
                           "thin months omitted" if series else "no monthly series available"}


def get_coverage(bank: str | None = None, aspect: str | None = None) -> dict:
    """What data actually exists — call this BEFORE answering a question the
    other tools come back empty on, to distinguish 'no data' from 'zero
    sentiment'. This is the cheapest hallucination defense available; see
    docs/DESIGN.md, grounding rules."""
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


def get_analyst_consensus(bank: str) -> dict:
    """Latest analyst consensus (ratings + price targets) for one bank.

    This is consensus *aggregate* data from Yahoo Finance, NOT the contents of
    any analyst report — say so when reporting it. Returns has_data=False when
    no snapshot exists yet.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT as_of_date, n_analysts, recommendation_key, recommendation_mean, "
            "target_mean, target_high, target_low, current_price, "
            "strong_buy, buy, hold, sell, strong_sell "
            "FROM analyst_consensus WHERE bank = ? ORDER BY as_of_date DESC LIMIT 1",
            (bank,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {"bank": bank, "has_data": False,
                "reason": "no analyst consensus snapshot stored yet — "
                          "run `python -m ingest.yahoo_analyst`"}

    (as_of, n, key, mean, t_mean, t_high, t_low, price,
     s_buy, buy_, hold, sell_, s_sell) = row
    upside = None
    if t_mean is not None and price:
        upside = round(100 * (t_mean - price) / price, 1)
    return {
        "bank": bank, "has_data": True, "as_of_date": as_of,
        "n_analysts": n, "consensus_rating": key, "rating_mean_1best_5worst": mean,
        "target_mean": t_mean, "target_high": t_high, "target_low": t_low,
        "current_price": price, "implied_upside_pct": upside,
        "rating_breakdown": {"strong_buy": s_buy, "buy": buy_, "hold": hold,
                              "sell": sell_, "strong_sell": s_sell},
        "source_note": "Yahoo Finance consensus aggregate, not analyst report text",
    }


def search_evidence(query: str, bank: str | None = None, aspect: str | None = None,
                     sentiment: str | None = None, k: int = 5) -> dict:
    """RAG evidence search (chatbot/retrieval.py) — quotes with citations for
    any qualitative claim. See docs/DESIGN.md, 'Grounding rules': every
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
                "aspect": {"type": "string", "enum": ASPECT_KEYS,
                           "description": "One of the frozen aspect keys, using underscores "
                                          "(e.g. \"dividend_policy\", not \"dividend policy\"), "
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
            "properties": {"aspect": {"type": "string", "enum": ASPECT_KEYS}},
        },
    },
    {
        "name": "get_trend",
        "description": "Get sentiment trend/direction for a bank and aspect: compares the last "
                        "7 days against the last 30 days. Falls back to an all-time snapshot "
                        "(trend_available=false) if either window is too thin to compare.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bank": {"type": "string", "enum": ["DBS", "OCBC", "UOB"]},
                "aspect": {"type": "string", "enum": ASPECT_KEYS},
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
                "aspect": {"type": "string", "enum": ASPECT_KEYS},
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
                "aspect": {"type": "string", "enum": ASPECT_KEYS},
                "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                "k": {"type": "integer", "description": "Max results, default 5"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_analyst_consensus",
        "description": "Get professional analyst consensus for one bank: number of analysts, "
                        "consensus rating, average/high/low price targets, and implied upside. "
                        "This is consensus aggregate data, NOT the text or reasoning of any "
                        "analyst report — do not claim to know why analysts hold that view.",
        "input_schema": {
            "type": "object",
            "properties": {"bank": {"type": "string", "enum": ["DBS", "OCBC", "UOB"]}},
            "required": ["bank"],
        },
    },
]

TOOL_FUNCTIONS = {
    "get_sentiment": lambda **kw: get_sentiment(**kw),
    "compare_banks": lambda **kw: compare_banks(**kw),
    "get_trend": lambda **kw: get_trend(**kw),
    "get_coverage": lambda **kw: get_coverage(**kw),
    "search_evidence": lambda **kw: search_evidence(**kw),
    "get_analyst_consensus": lambda **kw: get_analyst_consensus(**kw),
}

_SCHEMA_BY_TOOL = {t["name"]: t["input_schema"] for t in TOOL_SCHEMAS}


def coerce_tool_arguments(tool_name: str, arguments: dict) -> dict:
    """Coerces string-typed arguments to the type declared in the tool's own
    input_schema (integer/number/boolean) before the tool function sees them.

    WHY THIS EXISTS: local models called via Ollama don't reliably respect a
    JSON schema's declared types — observed with llama3.2:3b, which called
    search_evidence with k="5" (a string) instead of k=5, which crashed the
    list-slice inside chatbot/retrieval.py with a TypeError. Claude has not
    been observed doing this, but this coercion is cheap and harmless for a
    backend that already sends correct types, so it runs for every backend
    rather than only for local models.

    Also normalizes `aspect` (see normalize_aspect) — the same model called
    get_sentiment with aspect="dividend policy" instead of "dividend_policy",
    silently producing insufficient_data on a valid question. The schema's
    enum constraint should prevent this going forward; this is the
    defense-in-depth backstop for a model that ignores it anyway.
    """
    schema = _SCHEMA_BY_TOOL.get(tool_name)
    if not schema:
        return arguments
    properties = schema.get("properties", {})
    coerced = {}
    for key, value in arguments.items():
        prop_type = properties.get(key, {}).get("type")
        if prop_type == "integer" and isinstance(value, str):
            try:
                value = int(value)
            except ValueError:
                pass
        elif prop_type == "number" and isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                pass
        elif prop_type == "boolean" and isinstance(value, str):
            value = value.strip().lower() in ("true", "1", "yes")
        elif key == "aspect" and isinstance(value, str):
            value = normalize_aspect(value)
        coerced[key] = value
    return coerced
