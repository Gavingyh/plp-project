"""Collect supported online sources, preserving partial results and failures.

Only the worker imports adapters. Storage failures propagate; provider failures
are reported per source so another selected source can still be collected.
"""

from datetime import date, datetime, time, timedelta, timezone
from contextlib import closing

ONLINE_SOURCES = {"google_news", "arctic_shift", "newsapi"}
MAX_COLLECTION_DAYS = 31


def collection_window(sources, since=None, until=None) -> dict | None:
    """Resolve a bounded UTC window [since, until), once at job submission."""
    if not ONLINE_SOURCES.intersection(sources):
        if since is not None or until is not None:
            raise ValueError("Collection dates require an online source.")
        return None
    if (since is None) != (until is None):
        raise ValueError("Provide both since and until, or omit both.")
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    if since is None:
        start, end = tomorrow - timedelta(days=7), tomorrow
    else:
        try:
            start, end = date.fromisoformat(str(since)), date.fromisoformat(str(until))
        except (TypeError, ValueError) as exc:
            raise ValueError("Collection dates must be YYYY-MM-DD.") from exc
    if not 0 < (end - start).days <= MAX_COLLECTION_DAYS:
        raise ValueError(f"Select between 1 and {MAX_COLLECTION_DAYS} collection days.")
    if end > tomorrow:
        raise ValueError("Collection dates cannot extend beyond today (UTC).")
    return {"since": start.isoformat(), "until": end.isoformat()}


def collect(source, window, *, report, before_insert):
    from ingest import db

    since, until = window["since"], window["until"]
    if source in {"google_news", "newsapi"}:
        from ingest import news_filter

        if source == "newsapi":
            from ingest import newsapi as adapter
        else:
            from ingest import google_news as adapter

        adapter.FAILED_WINDOWS.clear()
        gaps = adapter.FAILED_WINDOWS
        batches = adapter.iter_batches(since, until)
        index = news_filter.load_index()
    elif source == "arctic_shift":
        from ingest import arctic_shift as adapter

        adapter.INCOMPLETE_WINDOWS.clear()
        gaps = adapter.INCOMPLETE_WINDOWS

        def daily_batches():
            start, end = date.fromisoformat(since), date.fromisoformat(until)
            while start < end:
                nxt = start + timedelta(days=1)
                yield start.isoformat(), adapter.pull(
                    start.isoformat(), nxt.isoformat()
                )
                start = nxt

        batches = daily_batches()
        with closing(db.get_connection()) as conn:
            known = {row[0] for row in conn.execute("SELECT doc_id FROM documents")}
    else:
        raise ValueError(f"Unsupported online source: {source}")
    result = {
        "status": "running",
        "since": since,
        "until": until,
        "fetched": 0,
        "duplicates": 0,
        "filtered": 0,
        "documents_inserted": 0,
        "batches_completed": 0,
        "incomplete_windows": [],
        "error": None,
    }

    def progress():
        report({"kind": "collection", "source": source, "result": dict(result)})

    progress()
    low = datetime.combine(date.fromisoformat(since), time(), tzinfo=timezone.utc)
    high = datetime.combine(date.fromisoformat(until), time(), tzinfo=timezone.utc)
    iterator = iter(batches)
    while True:
        try:
            label, docs = next(iterator)
        except StopIteration:
            break
        except Exception as exc:
            # Only provider/adapter iteration is caught here. Database errors
            # below fail the job instead of masquerading as a provider outage.
            result["error"] = f"{type(exc).__name__}: {exc}"
            break
        result["fetched"] += len(docs)
        eligible = []
        for doc in docs:
            try:
                published = datetime.fromisoformat(
                    doc["published_at"].replace("Z", "+00:00")
                )
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                inside = low <= published < high
            except (ValueError, KeyError, TypeError, AttributeError):
                inside = False
            if inside:
                eligible.append(doc)
            else:
                result["filtered"] += 1
        if source in {"google_news", "newsapi"}:
            kept, stats = news_filter.filter_and_dedup(eligible, index)
            result["duplicates"] += stats["already_stored"] + stats["duplicate"]
            result["filtered"] += (
                stats["no_bank_mention"] + stats["false_positive_only"]
            )
        else:
            kept = []
            for doc in eligible:
                if doc["doc_id"] in known:
                    result["duplicates"] += 1
                else:
                    kept.append(doc)
                    known.add(doc["doc_id"])
        before_insert(kept)
        attempted, inserted = db.upsert_documents(kept)
        result["documents_inserted"] += inserted
        result["duplicates"] += attempted - inserted
        result["batches_completed"] += 1
        result["current_batch"] = label
        result["incomplete_windows"] = list(gaps)
        progress()
    result["incomplete_windows"] = list(gaps)
    if source == "newsapi" and gaps and not result["error"]:
        result["error"] = "; ".join(gaps[:3])
    problem = bool(gaps or result["error"])
    result["status"] = (
        "partial"
        if result["fetched"] and problem
        else "failed" if problem else "completed"
    )
    progress()
    return result
