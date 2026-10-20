"""Uncached HTTP calls for manual updates; never import a worker or a model."""

from uuid import UUID

from dashboard.api_client import ApiError, request_json

ACTIVE = {"queued", "running"}
TERMINAL = {"completed", "completed_with_warnings", "failed", "interrupted"}
SOURCES = {
    "earnings": "Bank earnings PDFs",
    "sgx_research": "Broker research PDFs",
    "google_news": "Google News",
    "arctic_shift": "Reddit",
    "cna": "CNA article cache",
}
ONLINE_SOURCES = {"google_news", "arctic_shift"}
SOURCE_VERSION_ERROR = (
    "The API and dashboard source definitions do not match. "
    "Restart both services to load the latest code, then refresh this page."
)


def _valid_run(row):
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("status"), str)
        or row["status"] not in ACTIVE | TERMINAL
    ):
        return False
    try:
        UUID(row["run_id"])
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    return (
        isinstance(row.get("sources"), list)
        and bool(row["sources"])
        and all(
            isinstance(source, str) and source in SOURCES for source in row["sources"]
        )
    )


def load_sources() -> list[dict]:
    rows = request_json("GET", "/pipeline/sources").get("sources")
    if not isinstance(rows, list) or any(
        not isinstance(row, dict)
        or not isinstance(row.get("key"), str)
        or row.get("key") not in SOURCES
        or row.get("kind")
        != (
            "local_cache"
            if row.get("key") == "cna"
            else "online" if row.get("key") in ONLINE_SOURCES else "local_pdf"
        )
        or not isinstance(row.get("folder"), str)
        or type(row.get("exists")) is not bool
        or type(row.get("pdf_count")) is not int
        or row["pdf_count"] < 0
        or (
            row.get("key") == "cna"
            and (
                type(row.get("article_count")) is not int
                or row["article_count"] < 0
                or type(row.get("invalid_count")) is not int
                or row["invalid_count"] < 0
                or type(row.get("excluded_date_count")) is not int
                or row["excluded_date_count"] < 0
            )
        )
        or (row.get("error") is not None and not isinstance(row["error"], str))
        for row in rows
    ):
        raise ApiError(SOURCE_VERSION_ERROR)
    if {row["key"] for row in rows} != set(SOURCES) or len(rows) != len(SOURCES):
        raise ApiError(SOURCE_VERSION_ERROR)
    return sorted(rows, key=lambda row: list(SOURCES).index(row["key"]))


def load_history() -> dict:
    payload = request_json("GET", "/pipeline/runs", params={"limit": 20})
    rows = payload.get("runs")
    if not isinstance(rows, list) or any(not _valid_run(row) for row in rows):
        raise ApiError("The API returned invalid pipeline history.")
    active = next((row["run_id"] for row in rows if row["status"] in ACTIVE), None)
    if "active_run_id" not in payload or payload["active_run_id"] != active:
        raise ApiError("The API returned inconsistent pipeline status.")
    return payload


def _run(payload: dict) -> dict:
    run = payload.get("run")
    if (
        not isinstance(run, dict)
        or not _valid_run(run)
        or not isinstance(run.get("stages"), list)
    ):
        raise ApiError("The API returned an invalid pipeline run.")
    return run


def load_run(run_id: str) -> dict:
    return _run(request_json("GET", f"/pipeline/runs/{UUID(run_id).hex}"))


def start_run(sources: list[str], *, since=None, until=None) -> dict:
    """Exactly one POST, only after the user clicks Run selected sources."""
    body = {"sources": sources}
    if since is not None or until is not None:
        body.update(since=since, until=until)
    return _run(request_json("POST", "/pipeline/runs", body=body))
