"""HTTP contract for the manual pipeline; source/model work runs in its worker."""

import logging
from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipeline.jobs import PipelineBusy
from pipeline.service import PipelineService, WorkerLaunchError
from pipeline.stages import selected_sources, collection_window

router = APIRouter(
    prefix="/pipeline",
    tags=["pipeline"],
    responses={503: {"description": "Pipeline worker or run storage unavailable"}},
)
logger = logging.getLogger(__name__)
SourceKey = Literal["earnings", "sgx_research", "google_news", "arctic_shift", "cna"]
RunStatus = Literal[
    "queued", "running", "completed", "completed_with_warnings", "failed", "interrupted"
]


def get_pipeline_service() -> PipelineService:
    return PipelineService()


class SourceOption(BaseModel):
    key: SourceKey
    label: str
    kind: Literal["local_pdf", "online", "local_cache"]
    folder: str
    exists: bool
    pdf_count: int
    article_count: int = 0
    invalid_count: int = 0
    excluded_date_count: int = 0
    error: str | None = None


class PipelineSources(BaseModel):
    sources: list[SourceOption]
    analysis_scope: Literal["all_pending"] = "all_pending"


class StartPipelineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[SourceKey] = Field(min_length=1, max_length=5)
    since: date | None = None
    until: date | None = None

    @field_validator("sources")
    @classmethod
    def unique_sources(cls, value):
        return selected_sources(value)

    @model_validator(mode="after")
    def bounded_collection_window(self):
        window = collection_window(self.sources, self.since, self.until)
        if window:
            self.since, self.until = date.fromisoformat(
                window["since"]
            ), date.fromisoformat(window["until"])
        return self


class PipelineStage(BaseModel):
    key: str
    label: str
    status: Literal["pending", "running", "completed", "failed", "interrupted"]
    started_at: str | None
    finished_at: str | None
    metrics: dict[str, Any]
    files: list[dict[str, Any]]
    error: str | None


class PipelineRun(BaseModel):
    run_id: str
    status: RunStatus
    sources: list[SourceKey]
    collection_window: dict[str, str] | None = None
    source_results: dict[str, Any] = Field(default_factory=dict)
    started_at: str
    finished_at: str | None
    pid: int | None
    db_path: str
    embeddings_path: str
    model_version: str | None
    current_stage: str | None
    log_path: str
    worker_log_path: str | None = None
    worker_exit_code: int | None = None
    import_candidates: list[dict[str, Any]]
    imported_documents: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    error: str | None
    stages: list[PipelineStage]


class PipelineRunResponse(BaseModel):
    run: PipelineRun


class PipelineRunSummary(BaseModel):
    run_id: str
    status: RunStatus
    sources: list[SourceKey]
    started_at: str
    finished_at: str | None
    current_stage: str | None
    model_version: str | None
    error: str | None
    warnings_count: int
    documents_inserted: int


class PipelineHistory(BaseModel):
    runs: list[PipelineRunSummary]
    active_run_id: str | None


def _unavailable(exc: Exception) -> HTTPException:
    logger.error("Pipeline service unavailable: %s", exc, exc_info=True)
    return HTTPException(
        status_code=503,
        detail="Pipeline service unavailable; check API logs and run-directory permissions.",
    )


@router.get("/sources", response_model=PipelineSources)
def pipeline_sources(service: PipelineService = Depends(get_pipeline_service)):
    """Supported local folders and online collectors; never fetches on GET."""
    try:
        return {"sources": service.sources(), "analysis_scope": "all_pending"}
    except OSError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/runs",
    status_code=202,
    response_model=PipelineRunResponse,
    responses={
        409: {"description": "Another manual pipeline run is active"},
        503: {"description": "The background worker could not be started"},
    },
)
def start_pipeline(
    req: StartPipelineRequest,
    response: Response,
    service: PipelineService = Depends(get_pipeline_service),
):
    """Start an incremental run in a separate process and return its queued record.

    This endpoint writes to the configured database. It accepts source keys,
    not paths, commands or model changes. Poll Location for progress; never
    automatically retry a POST whose response was lost.
    """
    try:
        run = service.start(req.sources, since=req.since, until=req.until)
    except PipelineBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (WorkerLaunchError, OSError, ValueError) as exc:
        raise _unavailable(exc) from exc
    response.headers["Location"] = f"/pipeline/runs/{run['run_id']}"
    response.headers["Retry-After"] = "2"
    return {"run": run}


@router.get("/runs", response_model=PipelineHistory)
def pipeline_history(
    limit: int = Query(20, ge=1, le=100),
    service: PipelineService = Depends(get_pipeline_service),
):
    """Newest run summaries and the active ID, recovering stopped workers' metadata."""
    try:
        return service.history(limit)
    except (OSError, ValueError) as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/runs/{run_id}",
    response_model=PipelineRunResponse,
    responses={404: {"description": "Unknown pipeline run"}},
)
def pipeline_status(
    run_id: UUID, service: PipelineService = Depends(get_pipeline_service)
):
    """Full stage metrics, file outcomes, warnings and import manifest for one run."""
    try:
        return {"run": service.get(run_id.hex)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Pipeline run not found") from exc
    except (OSError, ValueError) as exc:
        raise _unavailable(exc) from exc
