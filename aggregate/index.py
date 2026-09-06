"""
Phase 6: aggregate per-sentence sentiment into the per-bank, per-aspect index
the dashboard and chatbot read.

Key MVP-plan requirements implemented here (Phase 6, step 2):
  - shrinkage toward neutral at low volume: score * n/(n+k), k=5 — without
    this, one Reddit comment can swing the index to +/-1.0 on a single data
    point.
  - `n` is ALWAYS stored and displayed alongside the score — a sentiment
    number without its sample size is flagged in the plan as the main way
    this dashboard could mislead a retail investor.

Source weighting is deliberately simple for the MVP: earnings and
analyst-flagged news outnumber a single Reddit comment. Confidence weighting
is applied via the per-row `confidence` from aspect_sentiment.

Rolling windows (plan Phase 6, step 3): computes '7d', '30d', and 'all_time'
per (bank, aspect), so the dashboard's time-series view and the chatbot's
get_trend tool have real data to show instead of a single snapshot.
Window cutoffs are relative to actual wall-clock time (not the latest data
point) — a live dashboard should show genuine recency, including a thin/empty
7d window if a source hasn't been re-ingested recently, rather than silently
redefining "recent" to hide that gap.

KNOWN CAVEAT: window filtering compares `published_at` strings directly
against an ISO cutoff string rather than parsing to datetime — this is
correct for day-granularity windows given every source's timestamps are UTC,
but relies on comparing digits *before* any "Z" vs "+00:00" suffix
difference between sources (NewsAPI uses "Z", our own now_iso() uses
"+00:00"); the two would only compare incorrectly at the literal boundary
instant, which day-level windows never hit in practice. Worth switching to
parsed datetimes if sub-day windows are ever added.

USAGE:
  python -m aggregate.index
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from ingest.db import get_connection, init_db, now_iso

SHRINKAGE_K = 5
_LABEL_SCORE = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}

# Source weight: how much one item from this source counts relative to a
# baseline Reddit comment (weight 1.0). Earnings commentary and
# analyst-flagged news carry more signal per item than a single social post.
_SOURCE_WEIGHT = {"earnings": 3.0, "newsapi": 1.5, "alphavantage": 1.5, "arctic_shift": 1.0}

WINDOWS = {"7d": 7, "30d": 30, "all_time": None}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sentiment_index (
    bank            TEXT NOT NULL,
    aspect          TEXT NOT NULL,     -- 'ALL' for the overall per-bank row
    window          TEXT NOT NULL,     -- '7d' | '30d' | 'all_time'
    score           REAL NOT NULL,     -- shrunk, weighted, in [-1, 1]
    n               INTEGER NOT NULL,
    pos_n           INTEGER NOT NULL,
    neu_n           INTEGER NOT NULL,
    neg_n           INTEGER NOT NULL,
    confidence_mean REAL NOT NULL,
    model_version   TEXT NOT NULL,
    computed_at     TEXT NOT NULL,
    PRIMARY KEY (bank, aspect, window, model_version)
);
"""


def _fetch_all_rows(conn):
    return conn.execute("""
        SELECT sa.bank, ase.aspect, ase.label, ase.confidence, ase.model_version,
               sa.source, sa.published_at
        FROM aspect_sentiment ase
        JOIN sentences sa ON sa.sentence_id = ase.sentence_id
    """).fetchall()


def _summarize(items):
    n = len(items)
    pos = sum(1 for l, _, _ in items if l == "positive")
    neu = sum(1 for l, _, _ in items if l == "neutral")
    neg = sum(1 for l, _, _ in items if l == "negative")
    weighted_sum = sum(_LABEL_SCORE[l] * c * w for l, c, w in items)
    weight_total = sum(c * w for _, c, w in items) or 1e-9
    raw_score = weighted_sum / weight_total
    shrunk = raw_score * (n / (n + SHRINKAGE_K))
    conf_mean = sum(c for _, c, _ in items) / n if n else 0.0
    return round(shrunk, 4), n, pos, neu, neg, round(conf_mean, 4)


def _compute_rows_for_window(all_rows, window_name: str, days: int | None):
    cutoff = None
    if days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    groups = defaultdict(list)     # (bank, aspect, model_version) -> [(label, confidence, weight)]
    overall = defaultdict(list)    # (bank, model_version) -> [...] for the aspect='ALL' row
    for bank, aspect, label, confidence, model_version, source, published_at in all_rows:
        if cutoff is not None and published_at < cutoff:
            continue
        weight = _SOURCE_WEIGHT.get(source, 1.0)
        groups[(bank, aspect, model_version)].append((label, confidence, weight))
        overall[(bank, model_version)].append((label, confidence, weight))

    out = []
    ts = now_iso()
    for (bank, aspect, model_version), items in groups.items():
        score, n, pos, neu, neg, conf = _summarize(items)
        out.append((bank, aspect, window_name, score, n, pos, neu, neg, conf, model_version, ts))
    for (bank, model_version), items in overall.items():
        score, n, pos, neu, neg, conf = _summarize(items)
        out.append((bank, "ALL", window_name, score, n, pos, neu, neg, conf, model_version, ts))
    return out


def run() -> int:
    init_db()
    conn = get_connection()
    conn.executescript(_SCHEMA)
    all_rows = _fetch_all_rows(conn)

    out = []
    for window_name, days in WINDOWS.items():
        out.extend(_compute_rows_for_window(all_rows, window_name, days))

    if out:
        conn.execute("DELETE FROM sentiment_index")  # full recompute each run — cheap at this scale
        conn.executemany(
            """INSERT INTO sentiment_index
               (bank, aspect, window, score, n, pos_n, neu_n, neg_n, confidence_mean,
                model_version, computed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            out,
        )
        conn.commit()
    conn.close()
    return len(out)


if __name__ == "__main__":
    n = run()
    print(f"Recomputed sentiment_index: {n} (bank, aspect, window) rows")
