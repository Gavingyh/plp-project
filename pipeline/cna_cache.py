"""Import cached CNA article text without discovery or network collection."""

from datetime import date, datetime
import json
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

CACHE_PATH = Path(__file__).resolve().parents[1] / "data/cna/articles.jsonl"
COVERAGE_START = date(2023, 1, 1)  # Same start as ingest.cna_archive's CLI.
SINGAPORE = ZoneInfo("Asia/Singapore")


def _in_coverage(records):
    today = datetime.now(SINGAPORE).date()
    return [
        record
        for record in records
        if COVERAGE_START
        <= datetime.fromisoformat(record["published"]).astimezone(SINGAPORE).date()
        <= today
    ]


def _records():
    """Read JSONL using the archive loader's last-record-per-ID rule."""
    latest, issues = {}, []
    count = 0
    with Path(CACHE_PATH).open(encoding="utf-8") as stream:
        for line, text in enumerate(stream, 1):
            if not text.strip():
                continue
            count += 1
            try:
                row = json.loads(text)
                if not isinstance(row, dict) or type(row.get("id")) not in (str, int):
                    raise ValueError("Expected an article object with an id")
                if not str(row["id"]).strip():
                    raise ValueError("Article id is empty")
            except (ValueError, TypeError) as exc:
                issues.append({"line": line, "message": str(exc)})
                continue
            latest[str(row["id"])] = (line, row)
    valid = []
    for identity, (line, row) in latest.items():
        try:
            if row.get("error"):
                raise ValueError(f"Cached fetch failed: {str(row['error'])[:300]}")
            for key in ("title", "text", "published", "url", "section"):
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise ValueError(f"Missing or invalid {key}")
            url = urlsplit(row["url"])
            if (
                url.scheme not in {"http", "https"}
                or url.hostname
                not in {"channelnewsasia.com", "www.channelnewsasia.com"}
                or url.username
                or url.password
            ):
                raise ValueError("Expected an original CNA article URL")
            published = datetime.fromisoformat(row["published"].replace("Z", "+00:00"))
            if published.tzinfo is None:
                published = published.replace(tzinfo=SINGAPORE)
            valid.append({**row, "id": identity, "published": published.isoformat()})
        except ValueError as exc:
            issues.append({"line": line, "id": identity, "message": str(exc)})
    return (
        valid,
        issues,
        count,
        count - len(latest) - sum("id" not in issue for issue in issues),
    )


def inventory() -> dict:
    path = Path(CACHE_PATH)
    result = {
        "key": "cna",
        "label": "CNA article cache",
        "kind": "local_cache",
        "folder": str(path.parent),
        "exists": path.is_file(),
        "pdf_count": 0,
        "article_count": 0,
        "invalid_count": 0,
        "excluded_date_count": 0,
        "error": None,
    }
    if not path.is_file():
        result["error"] = "Place articles.jsonl in data/cna on the API machine."
        return result
    try:
        valid, issues, _, _ = _records()
        eligible = _in_coverage(valid)
        result.update(
            article_count=len(eligible),
            invalid_count=len(issues),
            excluded_date_count=len(valid) - len(eligible),
        )
    except (OSError, UnicodeError) as exc:
        result.update(exists=False, error=f"Cannot read articles.jsonl: {exc}")
    return result


def import_cache(*, report, before_insert) -> dict:
    # Existing document conversion and shared relevance/dedup rules, worker only.
    from ingest import cna_archive, db, news_filter

    result = {
        "kind": "local_cache",
        "status": "running",
        "fetched": 0,
        "duplicates": 0,
        "filtered": 0,
        "documents_inserted": 0,
        "incomplete_windows": [],
        "error": None,
        "cache_file": str(CACHE_PATH),
    }

    def progress():
        report({"kind": "source_result", "source": "cna", "result": dict(result)})

    progress()
    valid, issues, count, superseded = _records()
    eligible = _in_coverage(valid)
    outside_coverage = len(valid) - len(eligible)
    result.update(
        fetched=count,
        invalid_records=len(issues),
        superseded_records=superseded,
        excluded_date_records=outside_coverage,
        coverage_start=COVERAGE_START.isoformat(),
    )
    for issue in issues:
        report(
            {
                "source": "cna",
                "file": f"articles.jsonl:{issue['line']}",
                "status": "unusable",
                "message": issue["message"],
            }
        )
    docs = [cna_archive.to_document(row) for row in eligible]
    kept, stats = news_filter.filter_and_dedup(docs)
    result.update(
        duplicates=stats["already_stored"] + stats["duplicate"] + superseded,
        filtered=stats["no_bank_mention"]
        + stats["false_positive_only"]
        + len(issues)
        + outside_coverage,
        filter_stats=stats,
    )
    before_insert(kept)
    attempted, inserted = db.upsert_documents(kept)
    result["documents_inserted"] = inserted
    result["duplicates"] += attempted - inserted
    result["status"] = "partial" if issues else "completed"
    if issues:
        result["warning_message"] = (
            f"{len(issues)} cached CNA record(s) skipped because of prior fetch errors "
            "or invalid fields. Review input outcomes for details."
        )
        if not valid:
            result.update(
                status="failed", error="No usable CNA articles in articles.jsonl."
            )
    progress()
    return result
