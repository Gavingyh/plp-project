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

USAGE:
  python -m aggregate.index
"""

from collections import defaultdict

from ingest.db import get_connection, init_db, now_iso

SHRINKAGE_K = 5
_LABEL_SCORE = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}

# Source weight: how much one item from this source counts relative to a
# baseline Reddit comment (weight 1.0). Earnings commentary and
# analyst-flagged news carry more signal per item than a single social post.
_SOURCE_WEIGHT = {"earnings": 3.0, "newsapi": 1.5, "alphavantage": 1.5, "arctic_shift": 1.0}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sentiment_index (
    bank            TEXT NOT NULL,
    aspect          TEXT NOT NULL,     -- 'ALL' for the overall per-bank row
    window          TEXT NOT NULL,     -- 'all_time' for the MVP; rolling windows are a later refinement
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


def _compute_rows():
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT sa.bank, ase.aspect, ase.label, ase.confidence, ase.model_version, sa.source
            FROM aspect_sentiment ase
            JOIN sentences sa ON sa.sentence_id = ase.sentence_id
        """).fetchall()
    finally:
        conn.close()

    # group[(bank, aspect, model_version)] -> list of (label, confidence, weight)
    groups = defaultdict(list)
    overall = defaultdict(list)  # group[(bank, model_version)] for the aspect='ALL' row
    for bank, aspect, label, confidence, model_version, source in rows:
        weight = _SOURCE_WEIGHT.get(source, 1.0)
        groups[(bank, aspect, model_version)].append((label, confidence, weight))
        overall[(bank, model_version)].append((label, confidence, weight))

    def summarize(items):
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

    out = []
    ts = now_iso()
    for (bank, aspect, model_version), items in groups.items():
        score, n, pos, neu, neg, conf = summarize(items)
        out.append((bank, aspect, "all_time", score, n, pos, neu, neg, conf, model_version, ts))
    for (bank, model_version), items in overall.items():
        score, n, pos, neu, neg, conf = summarize(items)
        out.append((bank, "ALL", "all_time", score, n, pos, neu, neg, conf, model_version, ts))
    return out


def run() -> int:
    init_db()
    conn = get_connection()
    conn.executescript(_SCHEMA)
    rows = _compute_rows()
    if rows:
        conn.execute("DELETE FROM sentiment_index")  # full recompute each run — cheap at this scale
        conn.executemany(
            """INSERT INTO sentiment_index
               (bank, aspect, window, score, n, pos_n, neu_n, neg_n, confidence_mean,
                model_version, computed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
    conn.close()
    return len(rows)


if __name__ == "__main__":
    n = run()
    print(f"Recomputed sentiment_index: {n} (bank, aspect) rows")
