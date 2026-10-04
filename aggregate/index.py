"""
Aggregate per-sentence sentiment into the per-bank, per-aspect index
the dashboard and chatbot read.

Two requirements this implements, both from the original plan:
  - shrinkage toward neutral at low volume: score * n/(n+k), k=5 - without
    this, one Reddit comment can swing the index to +/-1.0 on a single data
    point.
  - `n` is ALWAYS stored and displayed alongside the score - a sentiment
    number without its sample size is flagged in the plan as the main way
    this dashboard could mislead a retail investor.

Source weighting is simple: earnings and
analyst-flagged news outnumber a single Reddit comment. Confidence weighting
is applied via the per-row `confidence` from aspect_sentiment.

Rolling windows (docs/DESIGN.md, step 3): computes '7d', '30d', and 'all_time'
per (bank, aspect), so the dashboard's time-series view and the chatbot's
get_trend tool have real data to show instead of a single snapshot.
Window cutoffs are relative to actual wall-clock time (not the latest data
point) - a live dashboard should show genuine recency, including a thin/empty
7d window if a source hasn't been re-ingested recently, rather than silently
redefining "recent" to hide that gap.

Window cutoffs and series buckets use each timestamp's UTC instant, parsed
(`_utc`): CNA's timestamps carry +08:00 and NewsAPI's "Z", so comparing the
strings put CNA rows up to eight hours on the wrong side of a cutoff or a
month edge (fixed 2026-10-03). Weeks are ISO weeks.

USAGE:
  python -m aggregate.index
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from ingest.db import get_connection, init_db, now_iso

from config import sources
from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

SHRINKAGE_K = 5
MIN_N = 5          # below this many sentences a score is reported as insufficient data
_LABEL_SCORE = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}

# How much one sentence from each source counts, relative to a Reddit
# comment: config/sources.yaml, which also records why earnings counts 1.0.
_SOURCE_WEIGHT = sources.weights()
_DEFAULT_WEIGHT = sources.default_weight()

WINDOWS = {"7d": 7, "30d": 30, "all_time": None}

# 'ALL' means "blended across every source" - the headline number. Individual
# source rows sit alongside it so the dashboard, API and write-up can show
# what the blend is actually made of (retail chatter vs. management framing),
# rather than presenting one opaque figure. This matters here: earnings
# coverage is very unequal across banks (DBS 9,093 sentences, OCBC 1,561,
# UOB 4 - UOB's IR site is WAF-blocked and its PDFs need adding by hand), so
# a blended cross-bank comparison is only trustworthy once a reader can see
# the composition behind it.
SOURCE_ALL = "ALL"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sentiment_index (
    bank            TEXT NOT NULL,
    aspect          TEXT NOT NULL,     -- 'ALL' for the overall per-bank row
    window          TEXT NOT NULL,     -- '7d' | '30d' | 'all_time'
    source          TEXT NOT NULL,     -- 'ALL' for the blended row, else one source
    score           REAL NOT NULL,     -- shrunk, weighted, in [-1, 1]
    n               INTEGER NOT NULL,
    pos_n           INTEGER NOT NULL,
    neu_n           INTEGER NOT NULL,
    neg_n           INTEGER NOT NULL,
    confidence_mean REAL NOT NULL,
    model_version   TEXT NOT NULL,
    computed_at     TEXT NOT NULL,
    PRIMARY KEY (bank, aspect, window, source, model_version)
);
"""


def _fetch_all_rows(conn):
    # Only pairs the sentence is assigned to now: after a change of aspect method, a
    # sentence's old pairs may still have scores, and must not count.
    return conn.execute("""
        SELECT sa.bank, ase.aspect, ase.label, ase.confidence, ase.model_version,
               sa.source, sa.published_at, ase.sentence_id
        FROM aspect_sentiment ase
        JOIN sentences sa ON sa.sentence_id = ase.sentence_id
        JOIN sentence_aspects asg ON asg.sentence_id = ase.sentence_id AND asg.aspect = ase.aspect
    """).fetchall()


def _one_per_sentence(pairs: dict, sentence_id: str, key, item) -> None:
    """Keep, per sentence, the pair with the highest confidence.

    A sentence matched to several aspects has one (sentence, aspect) row per
    aspect. Rows that aggregate across aspects must count the sentence once:
    counting every pair weights a sentence by how many aspects it matched,
    and sentences that match many aspects (earnings-style prose) are far more
    positive than those that match few, so the 2026-09-30 re-run at 6.4
    aspects per sentence lifted DBS's headline from about +0.06 to +0.23.
    Base FinBERT gives every pair of a sentence the same label, so the choice
    of pair only matters for an aspect-conditioned model."""
    current = pairs.get((key, sentence_id))
    if current is None or item[1] > current[1]:
        pairs[(key, sentence_id)] = item


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


def _utc(published_at: str | None) -> datetime | None:
    """The UTC instant of an ISO timestamp ("+08:00", "+00:00" or "Z"; no
    offset is read as UTC), or None if it can't be parsed."""
    try:
        t = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _period(published_at: str | None, bucket: str) -> str | None:
    """The series bucket a timestamp falls in, by its UTC date: `YYYY-MM`,
    `YYYY-Qn`, or the ISO week `YYYY-Www` (weeks start on Monday and week 1
    holds the year's first Thursday, so there is no week 00 and the last days
    of December can belong to the next year's week 1)."""
    t = _utc(published_at)
    if t is None:
        return None
    if bucket == "month":
        return f"{t.year:04d}-{t.month:02d}"
    if bucket == "quarter":
        return f"{t.year:04d}-Q{(t.month + 2) // 3}"
    year, week, _ = t.isocalendar()
    return f"{year:04d}-W{week:02d}"


_BUCKETS = ("week", "month", "quarter")


def compute_time_series(bank: str, aspect: str | None = None, bucket: str = "month",
                        source: str = SOURCE_ALL, min_n: int = MIN_N) -> list[dict]:
    """Sentiment per time bucket, as a continuous series.

    The stored index holds three fixed windows (7d/30d/all_time), which is
    enough to say "up or down" and not enough to plot anything. This computes
    the same statistic over arbitrary buckets instead.

    Scoring goes through _summarize, the identical weighting and shrinkage the
    stored index uses. That is the point: a chart computed a slightly
    different way would quietly disagree with the headline number and there
    would be no way to tell which was right.

    Buckets below min_n are returned with sufficient=False rather than
    dropped, so a thin stretch shows up as a gap in the chart instead of
    silently interpolating over data that isn't there.
    """
    if bucket not in _BUCKETS:
        raise ValueError(f"bucket must be one of {sorted(_BUCKETS)}, got {bucket!r}")

    import config.model_version as current_model
    where = ["sa.bank = ?", "sa.published_at IS NOT NULL", "ase.model_version = ?"]
    params: list = [bank, current_model.MODEL_VERSION]
    if aspect and aspect != "ALL":
        where.append("ase.aspect = ?")
        params.append(aspect)
    if source and source != SOURCE_ALL:
        where.append("sa.source = ?")
        params.append(source)

    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT sa.published_at, ase.label, ase.confidence, sa.source, "
            f"ase.sentence_id "
            f"FROM aspect_sentiment ase "
            f"JOIN sentences sa ON sa.sentence_id = ase.sentence_id "
            f"JOIN sentence_aspects asg ON asg.sentence_id = ase.sentence_id AND asg.aspect = ase.aspect "
            f"WHERE {' AND '.join(where)}",
            params,
        ).fetchall()
    finally:
        conn.close()

    buckets: dict[str, list] = {}
    per_sentence: dict = {}
    across = not aspect or aspect == "ALL"
    for published_at, label, confidence, row_source, sentence_id in rows:
        if label not in _LABEL_SCORE:   # the stored index fails on it too: never "no data"
            raise ValueError(f"unknown sentiment label {label!r} on {sentence_id}")
        period = _period(published_at, bucket)
        if period is None:
            continue
        item = (label, confidence, _SOURCE_WEIGHT.get(row_source, _DEFAULT_WEIGHT))
        if across:   # same rule as the stored index: each sentence once
            _one_per_sentence(per_sentence, sentence_id, period, item)
        else:
            buckets.setdefault(period, []).append(item)
    for (period, _sentence_id), item in per_sentence.items():
        buckets.setdefault(period, []).append(item)

    series = []
    for period in sorted(buckets):
        score, n, pos, neu, neg, conf = _summarize(buckets[period])
        series.append({"period": period, "score": score, "n": n,
                       "pos_n": pos, "neu_n": neu, "neg_n": neg,
                       "confidence_mean": conf, "sufficient": n >= min_n})
    return series


def _compute_rows_for_window(all_rows, window_name: str, days: int | None):
    cutoff = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Keyed by (bank, aspect, source, model_version); 'ALL' is used for the
    # blended-across-sources and blended-across-aspects rows respectively, so a
    # single grouping pass produces every combination the consumers need.
    groups = defaultdict(list)
    across_aspects: dict = {}   # (group key, sentence_id) -> one item per sentence
    for bank, aspect, label, confidence, model_version, source, published_at, sentence_id in all_rows:
        if cutoff is not None:
            t = _utc(published_at)
            if t is None or t < cutoff:
                continue
        item = (label, confidence, _SOURCE_WEIGHT.get(source, _DEFAULT_WEIGHT))
        groups[(bank, aspect, source, model_version)].append(item)          # per aspect, per source
        groups[(bank, aspect, SOURCE_ALL, model_version)].append(item)      # per aspect, blended
        _one_per_sentence(across_aspects, sentence_id, (bank, "ALL", source, model_version), item)      # per source, all aspects
        _one_per_sentence(across_aspects, sentence_id, (bank, "ALL", SOURCE_ALL, model_version), item)  # the headline number
    for (key, _sentence_id), item in across_aspects.items():
        groups[key].append(item)

    out = []
    ts = now_iso()
    for (bank, aspect, source, model_version), items in groups.items():
        score, n, pos, neu, neg, conf = _summarize(items)
        out.append((bank, aspect, window_name, source, score, n, pos, neu, neg,
                     conf, model_version, ts))
    return out


def _ensure_schema(conn):
    """Creates sentiment_index, migrating an older copy that predates the
    `source` column. Safe to drop and rebuild: every row is fully derived from
    aspect_sentiment and recomputed from scratch on each run anyway."""
    conn.executescript(_SCHEMA)
    columns = {r[1] for r in conn.execute("PRAGMA table_info(sentiment_index)")}
    if "source" not in columns:
        conn.execute("DROP TABLE sentiment_index")
        conn.executescript(_SCHEMA)
        conn.commit()


def rebuild(conn) -> int:
    """Recompute sentiment_index on this connection without committing, so a
    caller (scripts/rescore.py) can make it part of its own transaction. The
    table must exist (_ensure_schema, which commits, so call it first)."""
    all_rows = _fetch_all_rows(conn)

    out = []
    for window_name, days in WINDOWS.items():
        out.extend(_compute_rows_for_window(all_rows, window_name, days))

    if out:
        conn.execute("DELETE FROM sentiment_index")  # full recompute each run - cheap at this scale
        conn.executemany(
            """INSERT INTO sentiment_index
               (bank, aspect, window, source, score, n, pos_n, neu_n, neg_n,
                confidence_mean, model_version, computed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            out,
        )
    return len(out)


def run() -> int:
    init_db()
    conn = get_connection()
    _ensure_schema(conn)
    n = rebuild(conn)
    conn.commit()
    conn.close()
    return n


if __name__ == "__main__":
    setup_logging()
    n = run()
    logger.info(f"Recomputed sentiment_index: {n} (bank, aspect, window, source) rows")
