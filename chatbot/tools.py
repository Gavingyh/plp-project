"""
Tool implementations for the agentic chatbot - see docs/DESIGN.md.

Plain Python functions, not a framework: the agent loop is small enough that
a framework would add abstraction without adding capability at this scale.

Every tool that reports a score also reports `n` - the misleading-number
defense is enforced HERE, in the data contract, not left to the model to
remember to mention. `get_coverage` exists specifically so the agent can
check "do I have data on this at all" before answering, rather than
confabulating when it doesn't.
"""

import re
import sqlite3

import config.model_version as current_model
from aggregate.index import MIN_N, SHRINKAGE_K, compute_time_series
from chatbot import settings
from chatbot.retrieval import search_evidence as _search_evidence
from config import aspect_taxonomy
from config import sources as source_config
from config.logging_config import get_logger
from ingest.base import BANK_NAMES
from ingest.db import get_connection

logger = get_logger(__name__)

MIN_VOLUME_FOR_SCORE = MIN_N  # below this, report insufficient data rather than a number



def _load_aspect_keys() -> list[str]:
    """Real aspect keys from config/aspects.yaml, so the tool schema's enum
    and the actual taxonomy can never drift apart. A model given an open
    string field for `aspect` was observed passing "dividend policy" (a
    space, matching how the question was phrased) instead of the real key
    "dividend_policy", silently producing insufficient_data on a perfectly
    valid question. A missing or broken file is an error: falling back to a
    built-in list (the proposal's four) made the API reject
    real aspects without saying why."""
    return aspect_taxonomy.keys()


ASPECT_KEYS = _load_aspect_keys()


def normalize_aspect(aspect: str | None) -> str | None:
    """Best-effort correction for the failure mode above: lowercases and
    replaces spaces/hyphens with underscores, then only accepts the result if
    it matches a real aspect key. An unknown aspect is left as-is
    rather than guessed at, so it still surfaces as insufficient_data instead
    of silently mapping to the wrong aspect."""
    if aspect is None:
        return None
    candidate = aspect.strip().lower().replace(" ", "_").replace("-", "_")
    return candidate if candidate in ASPECT_KEYS else aspect


def version_has_rows() -> bool:
    """Whether sentiment_index holds any row for the configured model version.
    False means config/model_version.py names a version the index was never
    computed for, which every reader would otherwise report as "no data"."""
    conn = get_connection()
    try:
        return conn.execute("SELECT 1 FROM sentiment_index WHERE model_version = ? LIMIT 1",
                            (current_model.MODEL_VERSION,)).fetchone() is not None
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e):
            raise          # a locked or broken database must not read as "no rows for this version"
        return False   # the table doesn't exist before the first aggregation
    finally:
        conn.close()


def get_sentiment(bank: str, aspect: str | None = None, window: str = "all_time") -> dict:
    """Sentiment index for a bank, optionally filtered to one aspect ('ALL' aspect
    = overall) and one window ('7d', '30d', or 'all_time' - see aggregate/index.py).
    Returns insufficient_data=True below the volume floor, or if no row exists at
    all for this window (e.g. nothing published in the last 7 days)."""
    conn = get_connection()
    try:
        aspect_filter = aspect or "ALL"
        row = conn.execute(
            "SELECT score, n, pos_n, neu_n, neg_n, confidence_mean, model_version, computed_at "
            # source='ALL' is the blended headline row; per-source rows sit
            # alongside it (see aggregate/index.py) and must not be picked up
            # here by accident.
            "FROM sentiment_index WHERE bank = ? AND aspect = ? AND window = ? "
            "AND source = 'ALL' AND model_version = ? ORDER BY computed_at DESC LIMIT 1",
            (bank, aspect_filter, window, current_model.MODEL_VERSION),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        if not version_has_rows():
            version = current_model.MODEL_VERSION
            logger.warning("sentiment_index has no rows for model version %r (config/model_version.py)", version)
            return {"bank": bank, "aspect": aspect_filter, "window": window, "insufficient_data": True,
                    "reason": f"the index has no rows for model version {version!r}: re-run "
                              "aggregate.index after re-scoring, or check config/model_version.py"}
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
    results = {bank: get_sentiment(bank, aspect, window) for bank in BANK_NAMES}
    return {"aspect": aspect or "ALL", "window": window, "banks": results}


def _unshrunk(result: dict) -> float:
    """The window's score before aggregate/index.py's n/(n+k) shrinkage."""
    n = result["n"]
    return result["score"] * (n + SHRINKAGE_K) / n


def _monthly_series(bank: str, aspect: str | None) -> tuple[list[dict], str | None]:
    """(the last months with enough sentences, an error or None).

    A two-point comparison can only say "up" or "down". The monthly series
    gives the shape behind that. Capped at 12 points and trimmed to
    period/score/n on purpose: this goes into the model's context, and a
    long table of numbers is more surface to misquote, not more insight."""
    try:
        return [{"period": p["period"], "score": p["score"], "n": p["n"]}
                for p in compute_time_series(bank, aspect, bucket="month")
                if p["sufficient"]][-settings.get("trend.monthly_points"):], None
    except (sqlite3.Error, ValueError) as e:
        # A database error or a bad stored label is not "no data": log it and say so in the note.
        logger.warning("monthly series failed for %s/%s: %s", bank, aspect or "ALL", e)
        return [], str(e)


def get_trend(bank: str, aspect: str | None = None) -> dict:
    """Direction/magnitude of sentiment change: compares the 7d window against
    the 30d window (both from aggregate/index.py's rolling windows). Falls back
    to reporting all_time alone if either rolling window has insufficient data -
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

    # The stored scores are shrunk towards 0 by n/(n+k) (aggregate/index.py).
    # The 7d window is far thinner than the 30d one, so comparing the shrunk
    # scores reads a thin week as a fall: UOB once showed "declining"
    # (-0.045) when its unshrunk 7d score was 0.12 above the 30d one. Undo
    # the shrinkage on both before comparing; both windows are at or above
    # the volume floor here, so neither is a handful of items.
    recent_unshrunk, baseline_unshrunk = round(_unshrunk(recent), 4), round(_unshrunk(baseline), 4)
    delta = round(recent_unshrunk - baseline_unshrunk, 4)
    stable = settings.get("trend.stable_within")
    direction = "improving" if delta > stable else "declining" if delta < -stable else "stable"

    series, series_error = _monthly_series(bank, aspect)
    return {"bank": bank, "aspect": aspect or "ALL", "trend_available": True,
            "direction": direction, "delta_7d_vs_30d": delta,
            "recent_7d": recent, "baseline_30d": baseline,
            "monthly_series": series,
            "recent_7d_unshrunk_score": recent_unshrunk,
            "baseline_30d_unshrunk_score": baseline_unshrunk,
            "delta_basis": "recent_7d_unshrunk_score minus baseline_30d_unshrunk_score: the "
                           f"scores before the index's n/(n+{SHRINKAGE_K}) shrinkage, which pulls a "
                           "thin window towards 0",
            "series_note": ("monthly, same weighting and shrinkage as the index; thin months omitted"
                            if series else
                            f"monthly series unavailable: {series_error}" if series_error else
                            "no monthly series available")}


def get_coverage(bank: str | None = None, aspect: str | None = None) -> dict:
    """What data actually exists - call this BEFORE answering a question the
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
    any analyst report - say so when reporting it. Returns has_data=False when
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
    """RAG evidence search (chatbot/retrieval.py) - quotes with citations for
    any qualitative claim. See docs/DESIGN.md, 'Grounding rules': every
    qualitative claim must cite a sentence_id + url."""
    return _package_evidence(query, _search_evidence(query, bank=bank, aspect=aspect, sentiment=sentiment, k=k))


def _package_evidence(query: str, results: list[dict]) -> dict:
    # Packaged for citing, per the grounded-generation contract (CNI Day 2):
    # a short id, the date without a timestamp, and a ready-made citation the
    # model can copy, so it has no reason to compose one. The retrieval score
    # is renamed so it can't be mistaken for a sentiment score.
    packaged = []
    for i, r in enumerate(results, start=1):
        date = (r.get("published_at") or "")[:10]
        item = {"evidence_id": f"E{i}", "sentence_id": r["sentence_id"], "bank": r.get("bank"),
                "source": r.get("source"), "date": date, "text": r.get("text"), "url": r.get("url"),
                "cite_as": f"[{r.get('bank')}, {date}, sentence_id {r['sentence_id']}]",
                "relevance": r.get("score")}
        if "aspect" in r:
            item["aspect"], item["sentiment"] = r.get("aspect"), r.get("sentiment")
        packaged.append(item)
    return {"query": query, "results": packaged, "n_found": len(packaged)}


# --- What the chatbot's model is given ---------------------------------------------
#
# The API returns the functions above as they are. The chatbot's model gets
# the same results plus what a retail investor needs to read them, worked
# out here rather than left to the model: a local model gave a score
# as "0.122 out of 1", called +0.124 "slightly negative", said a trend was
# "not available" when 66 months of it existed, and cited earnings-report
# boilerplate (docs/evidence/chatbot-answers-2026-10-04.md). So each score
# comes with its reading in words and its shares of positive, neutral and
# negative sentences; a bank's overall score with its strongest and weakest
# topics; a comparison with its ranking; a trend with its latest months even
# when the 7- and 30-day windows are too thin; and evidence without repeats,
# spread across sources. Fields a reader can't use are left out: computed_at,
# when the index was built, reads like the date of the data.

_NOT_FOR_THE_READER = ("model_version", "confidence_mean", "computed_at")


def reading(score: float) -> str:
    """A score in words: "neutral", or "slightly", "moderately" or "clearly"
    positive or negative (bands in config/chatbot.yaml, `reading`)."""
    size, side = abs(score), "positive" if score > 0 else "negative"
    if size < settings.get("reading.neutral_below"):
        return "neutral"
    if size < settings.get("reading.slightly_below"):
        return f"slightly {side}"
    if size < settings.get("reading.moderately_below"):
        return f"moderately {side}"
    return f"clearly {side}"


def _topic_name(aspect: str | None) -> str | None:
    """The topic's readable name; None for an aspect that isn't a real one, so
    the model's own text never comes back to it as a topic name."""
    if not aspect or aspect == "ALL":
        return "overall"
    return aspect_taxonomy.labels().get(aspect)


def _for_reader(result: dict) -> dict:
    """A copy of a get_sentiment-shaped result with the topic's name, the
    score's reading and the shares of positive, neutral and negative sentences."""
    out = {k: v for k, v in result.items() if k not in _NOT_FOR_THE_READER}
    if "aspect" in out:
        out["topic_name"] = _topic_name(out["aspect"])
    if out.get("insufficient_data") is False and out.get("n"):
        out["reading"] = reading(out["score"])
        for label in ("positive", "neutral", "negative"):
            out[f"{label}_pct"] = round(100 * out[f"{label}_n"] / out["n"], 1)
    return out


def _data_runs_to(bank: str | None = None) -> str | None:
    """The date of the newest stored sentence, for one bank or any."""
    conn = get_connection()
    try:
        sql = "SELECT MAX(substr(published_at, 1, 10)) FROM sentences" + (" WHERE bank = ?" if bank else "")
        return conn.execute(sql, (bank,) if bank else ()).fetchone()[0]
    finally:
        conn.close()


def _topics(bank: str, window: str) -> tuple[list[dict], list[dict]]:
    """The bank's highest- and lowest-scoring named topics in this window,
    among those with enough sentences to report; none appears in both."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT aspect, score, n FROM sentiment_index WHERE bank = ? AND window = ? AND source = 'ALL' "
            "AND model_version = ? AND aspect NOT IN ('ALL', 'other') AND n >= ? ORDER BY score DESC",
            (bank, window, current_model.MODEL_VERSION, MIN_VOLUME_FOR_SCORE)).fetchall()
    finally:
        conn.close()
    topics = [{"topic_name": _topic_name(a), "score": s, "n": n, "reading": reading(s)} for a, s, n in rows]
    k = settings.get("topics_each_way")
    return topics[:k], topics[k:][::-1][:k]


def chat_get_sentiment(bank: str, aspect: str | None = None, window: str = "all_time") -> dict:
    """One bank's score, with the other two banks' for the same topic and
    window: told to say how a bank compares, a local model asked about DBS
    alone said it ranked above OCBC, and asked about OCBC that it ranked below
    both. OCBC was the highest of the three."""
    out = _for_reader(get_sentiment(bank, aspect, window))
    if out.get("insufficient_data") is False:
        peers = chat_compare_banks(aspect, window)
        out["ranking_high_to_low"] = peers["ranking_high_to_low"]
        out["other_banks"] = {b: {k: r[k] for k in ("score", "reading")} for b, r in peers["banks"].items()
                              if b != bank and r.get("insufficient_data") is False}
        if out["aspect"] == "ALL":
            out["strongest_topics"], out["weakest_topics"] = _topics(bank, window)
    out["data_runs_to"] = _data_runs_to(bank)
    return out


def chat_compare_banks(aspect: str | None = None, window: str = "all_time") -> dict:
    result = compare_banks(aspect, window)
    banks = {b: _for_reader(r) for b, r in result["banks"].items()}
    ranked = sorted((b for b, r in banks.items() if r.get("insufficient_data") is False),
                    key=lambda b: banks[b]["score"], reverse=True)
    return {**result, "topic_name": _topic_name(result["aspect"]), "banks": banks,
            "ranking_high_to_low": ranked, "data_runs_to": _data_runs_to()}


def _month_on_month(series: list[dict]) -> dict:
    """The latest month with enough sentences against the one before it in
    the series. As with 7d against 30d, the change is between the scores
    before shrinkage, so a thinner month doesn't read as a fall."""
    if len(series) < 2:
        return {"month_on_month_available": False}
    latest, previous = series[-1], series[-2]
    change = round(_unshrunk(latest) - _unshrunk(previous), 4)
    direction = _settled(_direction(change), latest["score"] - previous["score"])
    words = (f"{_month_name(latest)} {_compared(direction)} {_month_name(previous)}." if direction != "unclear"
             else f"{_month_name(latest)} against {_month_name(previous)}: {_TOO_FEW}.")
    out = {"month_on_month_available": True,
           "latest_month": {**latest, "reading": reading(latest["score"])},
           "previous_month": {**previous, "reading": reading(previous["score"])},
           "change_from_previous_month": change,
           "month_on_month": direction,
           "trend_in_words": words}
    if direction == "unclear":
        del out["change_from_previous_month"]     # it would contradict the printed scores
    return out


# When the printed scores and the change before shrinkage disagree: the gap is
# smaller than the shrinkage on the thinner period, so neither way can be said.
_TOO_FEW = "too close to call, as one of them has few sentences"


def _direction(change: float) -> str:
    stable = settings.get("trend.stable_within")
    return "up" if change > stable else "down" if change < -stable else "about the same"


def _settled(direction: str, printed_change: float) -> str:
    """The direction, or "unclear" when the scores the sentence prints point
    another way. The printed scores are the index's, which pull a thin period
    towards 0; the direction is worked out before that pull. Saying "up" beside
    a lower printed score contradicts the figures (found in validation:
    "(+0.27, 6 sentences) was up on (+0.44, 200 sentences)")."""
    plain = {"improving": "up", "declining": "down", "stable": "about the same"}.get(direction, direction)
    return direction if _direction(printed_change) == plain else "unclear"


_COMPARED = {"up": "was up on", "improving": "was up on", "down": "was down on", "declining": "was down on"}


def _compared(direction: str) -> str:
    return _COMPARED.get(direction, "was about the same as")


def _figures(score: float, n: int) -> str:
    return f"({score:+.2f}, {n:,} sentences)"


def _month_name(point: dict) -> str:
    """ "September 2026 (+0.34, 167 sentences)": the month, its score and its count."""
    year, month = point["period"].split("-")
    name = ("January February March April May June July August September October November "
            "December").split()[int(month) - 1]
    return f"{name} {year} {_figures(point['score'], point['n'])}"


# A sentiment result's figures, which chat_get_trend moves under
# all_time_not_recent when the trend falls back to the all-time window.
_FIGURE_FIELDS = ("window", "score", "n", "positive_n", "neutral_n", "negative_n", "confidence_mean",
                  "reading", "positive_pct", "neutral_pct", "negative_pct", "insufficient_data")


def chat_get_trend(bank: str, aspect: str | None = None) -> dict:
    """The trend with one sentence that states it (trend_in_words): the last 7
    days against the last 30 when both have enough sentences, else the latest
    month against the one before. One comparison, written out, because
    a local model reading the series gave August's +0.2185 as
    "-0.2185", gave a month's change as its score, and blended a rising week
    with a falling month."""
    out = _for_reader(get_trend(bank, aspect))
    for window in ("recent_7d", "baseline_30d"):
        if isinstance(out.get(window), dict):
            out[window] = _for_reader(out[window])
    if out.get("trend_available"):
        recent, base = out["recent_7d"], out["baseline_30d"]
        out["direction"] = _settled(out["direction"], recent["score"] - base["score"])
        if out["direction"] == "unclear":
            out.pop("delta_7d_vs_30d", None)       # the change before shrinkage, which the printed scores contradict
        week, month = (f"The last 7 days {_figures(recent['score'], recent['n'])}",
                       f"the last 30 days {_figures(base['score'], base['n'])}")
        out["trend_in_words"] = (f"{week} {_compared(out['direction']).replace('was', 'were')} {month}."
                                 if out["direction"] != "unclear" else f"{week} against {month}: {_TOO_FEW}.")
    else:                                    # the 7- and 30-day windows were too thin
        # The fallback is the all-time figure. Asked about "the last 7 days", a
        # local model reported it as the week's in every run, although the note
        # said otherwise. So it is kept apart, under a name that says what it
        # is, beside how many sentences the recent windows hold.
        figures = {k: out.pop(k) for k in _FIGURE_FIELDS if k in out}
        counts = {w: get_sentiment(bank, aspect, w).get("n", 0) for w in ("7d", "30d")}
        series, error = _monthly_series(bank, aspect)
        months = _month_on_month(series)
        older = (f" The monthly figures below are for {_month_name(months['latest_month']).split(' (')[0]} and "
                 f"{_month_name(months['previous_month']).split(' (')[0]}, not for the last 7 or 30 days."
                 if months.get("month_on_month_available") else "")
        # First, so it is read first: the answer to a question about a recent window.
        out = {"recent_windows": (f"There is no figure for the last 7 days ({counts['7d']} sentences) or the last "
                                  f"30 days ({counts['30d']} sentences): at least {MIN_VOLUME_FOR_SCORE} are needed. "
                                  "Say so, and give no score for those periods." + older),
               **out, "all_time_not_recent": figures}
        out.update(months)
        out["note"] = ("Too few sentences in the last 7 or 30 days for that comparison; "
                       "trend_in_words compares the latest months instead." if len(series) > 1 else
                       f"No recent trend: {error or 'fewer than two months with enough sentences'}.")
        out["monthly_series"] = series
    out["monthly_series"] = out.get("monthly_series", [])[-settings.get("trend.chat_months"):]
    out["data_runs_to"] = _data_runs_to(bank)
    return out


def _words(text: str | None) -> set[str]:
    """A sentence's words without digits, so "3Q24" and "3Q23" read the same."""
    return set(re.findall(r"[a-z]+", (text or "").lower()))


def _same_wording(a: set[str], b: set[str]) -> bool:
    return bool(a | b) and len(a & b) / len(a | b) >= settings.get("evidence.same_wording")


def _pick_evidence(pool: list[dict], k: int, polar_boost: float) -> list[dict]:
    """Up to k of the ranked pool: positive and negative sentences raised by
    polar_boost; a wording already picked skipped (a results report repeats a
    sentence every quarter with only the quarter changed); and at most
    evidence.max_per_source from one source, unless too few others match."""
    cap = settings.get("evidence.max_per_source")
    ranked = sorted(pool, key=lambda r: r.get("score", 0.0)
                    + (polar_boost if r.get("sentiment") in ("positive", "negative") else 0.0), reverse=True)
    picked, held_back, per_source, seen = [], [], {}, []
    for r in ranked:
        words = _words(r.get("text"))
        if any(_same_wording(words, w) for w in seen):
            continue
        seen.append(words)
        if per_source.get(r.get("source"), 0) >= cap:
            held_back.append(r)
            continue
        per_source[r.get("source")] = per_source.get(r.get("source"), 0) + 1
        picked.append(r)
        if len(picked) == k:
            break
    return (picked + held_back)[:k]


def chat_search_evidence(query: str, bank: str | None = None, aspect: str | None = None,
                         sentiment: str | None = None, k: int = 5) -> dict:
    k = max(int(k), 0)
    pool = _search_evidence(query, bank=bank, aspect=aspect, sentiment=sentiment,
                            k=k * settings.get("evidence.pool_factor"))
    boost = 0.0 if sentiment else settings.get("evidence.polar_boost")
    out = _package_evidence(query, _pick_evidence(pool, k, boost))
    for item in out["results"]:
        item["source_name"] = source_config.label(item.get("source"))
    out.update(_evidence_context(bank, aspect))
    return out


def _evidence_context(bank: str | None, aspect: str | None) -> dict:
    """What a search alone leaves the model to guess: the bank's score for
    the topic, read as get_sentiment reads it, and the date the data runs to.
    Asked what people say and how they feel, a local model
    searched only, called the mood "neutral" with no score fetched, and gave
    a quote's date as the date the data runs to. A database without the
    tables (a fresh copy) leaves the context out."""
    out = {}
    try:
        if bank:
            r = _for_reader(get_sentiment(bank, aspect))
            # Named for what it is: given the bank's overall score under a neutral name, the
            # model reported it as the score for the topic it had asked about.
            # The neutral share too: a model that worked it out from the other two was flagged
            # for a figure no tool returned (found in validation).
            out["topic_score" if aspect else "bank_overall_score"] = {
                k: r[k] for k in ("topic_name", "reading", "score", "n", "positive_pct", "neutral_pct",
                                  "negative_pct", "insufficient_data") if k in r}
        out["data_runs_to"] = _data_runs_to(bank)
    except sqlite3.Error as e:
        logger.warning("no score or data date for the evidence: %s", e)
    return out


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
                "bank": {"type": "string", "enum": list(BANK_NAMES)},
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
        "description": "Get how sentiment for a bank (and aspect) has moved: the last 7 days "
                        "against the last 30 (trend_available=false when either is too thin), and "
                        "the latest month with data against the month before it "
                        "(latest_month, previous_month, month_on_month). Use it for any 'recently' "
                        "or 'has it changed' question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bank": {"type": "string", "enum": list(BANK_NAMES)},
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
                "bank": {"type": "string", "enum": list(BANK_NAMES)},
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
                "bank": {"type": "string", "enum": list(BANK_NAMES)},
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
            "properties": {"bank": {"type": "string", "enum": list(BANK_NAMES)}},
            "required": ["bank"],
        },
    },
]

# The chatbot's model calls the reader-facing versions (above); the API calls the plain ones.
TOOL_FUNCTIONS = {
    "get_sentiment": lambda **kw: chat_get_sentiment(**kw),
    "compare_banks": lambda **kw: chat_compare_banks(**kw),
    "get_trend": lambda **kw: chat_get_trend(**kw),
    "get_coverage": lambda **kw: get_coverage(**kw),
    "search_evidence": lambda **kw: chat_search_evidence(**kw),
    "get_analyst_consensus": lambda **kw: get_analyst_consensus(**kw),
}

_SCHEMA_BY_TOOL = {t["name"]: t["input_schema"] for t in TOOL_SCHEMAS}


def coerce_tool_arguments(tool_name: str, arguments: dict) -> dict:
    """Coerces string-typed arguments to the type declared in the tool's own
    input_schema (integer/number/boolean) before the tool function sees them.

    Local models don't always respect a schema's declared types:
    llama3.2:3b called search_evidence with k="5" (a string), which crashed
    the list slice in chatbot/retrieval.py. The coercion costs nothing for a
    backend that sends correct types, so it runs for every backend.

    Also normalizes `aspect` (see normalize_aspect) - the same model called
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
        if value is None:
            continue        # a null for an optional argument means "not given"; the tool's default applies
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
