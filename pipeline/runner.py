"""Run the existing PDF ingestion/inference pipeline with durable progress.

USAGE (from the project root):
  .venv-plp/bin/python3 -m pipeline.runner --sources earnings sgx_research
  .venv-plp/bin/python3 -m pipeline.runner --history

The runner can run in the terminal or as a separate FastAPI-launched worker.
The shared database is used by default. Imports are
selected by source; downstream stages finish all pending database work.
"""

import argparse
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from pipeline import stages
from pipeline.jobs import PipelineBusy, RunStore, timestamp

STEP_NAMES = (
    ("preflight", "Check prerequisites"),
    ("import", "Import documents"),
    ("preprocess", "Prepare sentences"),
    ("assign", "Assign topics"),
    ("score", "Score sentiment"),
    ("aggregate", "Refresh sentiment index"),
)
logger = logging.getLogger(__name__)


@contextmanager
def _run_log(path: Path):
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    previous_level = root.level
    if root.level > logging.INFO:
        root.setLevel(logging.INFO)
    root.addHandler(handler)
    try:
        yield
    finally:
        root.removeHandler(handler)
        handler.close()
        root.setLevel(previous_level)


def _reconcile(run: dict) -> None:
    try:
        run["imported_documents"] = stages.imported_documents(run)
    except (OSError, sqlite3.Error) as exc:
        run["warnings"].append(
            {
                "stage": "import",
                "message": f"Could not reconcile inserted document IDs: {exc}",
            }
        )


def _recover(store: RunStore) -> None:
    for run in store.recover_interrupted():
        _reconcile(run)
        store.save(run)


def history(store: RunStore | None = None, limit: int = 20) -> list[dict]:
    store = store or RunStore()
    try:
        with store.lock():
            _recover(store)
    except PipelineBusy:
        pass  # The active worker, rather than a PID/timeout guess, owns its status.
    return store.history(limit)


def new_run(
    sources: list[str], store: RunStore, run_id: str, *, queued: bool = False
) -> dict:
    """Build a record; callers save it while holding the pipeline lock."""
    from ingest import db

    record_path = store.path(run_id)
    return {
        "run_id": run_id,
        "status": "queued" if queued else "running",
        "sources": stages.selected_sources(sources),
        "started_at": timestamp(),
        "finished_at": None,
        "pid": None if queued else os.getpid(),
        "db_path": str(Path(db.DB_PATH).resolve()),
        "embeddings_path": str(
            Path(
                os.environ.get("PLP_EMBEDDINGS_PATH")
                or stages.ROOT / "data/sentence_embeddings.npz"
            ).resolve()
        ),
        "model_version": None,
        "current_stage": None,
        "log_path": str(record_path.with_suffix(".log")),
        "import_candidates": [],
        "imported_documents": [],
        "warnings": [],
        "error": None,
        "stages": [
            {
                "key": key,
                "label": label,
                "status": "pending",
                "started_at": None,
                "finished_at": None,
                "metrics": {},
                "files": [],
                "error": None,
            }
            for key, label in STEP_NAMES
        ],
    }


def run_pipeline(
    sources: list[str],
    *,
    store: RunStore | None = None,
    run_id: str | None = None,
    lock_fd: int | None = None,
) -> dict:
    """Execute once; failed runs return their saved record. Invalid/busy requests raise.

    Never retries automatically or rolls back earlier committed stages.
    KeyboardInterrupt is persisted as interrupted and then propagated.
    """
    sources = stages.selected_sources(sources)
    from dotenv import load_dotenv

    load_dotenv(stages.ROOT / ".env")
    from ingest import db

    store = store or RunStore()
    run_id = run_id or uuid4().hex
    record_path = store.path(run_id)  # validate before creating files
    lock = store.lock() if lock_fd is None else store.inherited_lock(lock_fd)
    with lock:
        if lock_fd is None:
            _recover(store)
            if record_path.exists():
                raise ValueError(f"Run {run_id} already exists; use a new run ID.")
            run = new_run(sources, store, run_id)
        else:
            run = store.get(run_id)
            if (
                run["status"] != "queued"
                or run["sources"] != sources
                or run["db_path"] != str(Path(db.DB_PATH).resolve())
            ):
                raise ValueError("Worker configuration does not match the reserved run")
            run.update(status="running", pid=os.getpid())
        store.save(run)
        current = None
        import_stage = run["stages"][1]

        def report(event):
            import_stage["files"].append(event)
            if event["status"] in ("failed", "skipped") or event.get("warning"):
                run["warnings"].append(
                    {
                        "stage": "import",
                        "source": event["source"],
                        "file": event["file"],
                        "message": event.get("warning") or event["message"],
                    }
                )
            store.save(run)

        def before_insert(docs):
            run["import_candidates"].extend(
                {
                    "doc_id": doc["doc_id"],
                    "source": doc["source"],
                    "title": doc["title"],
                    "url": doc["url"],
                }
                for doc in docs
            )
            store.save(run)

        tasks = {
            "preflight": lambda: stages.preflight(sources),
            "import": lambda: stages.import_sources(
                sources, report=report, before_insert=before_insert
            ),
            "preprocess": stages.preprocess,
            "assign": stages.assign_topics,
            "score": stages.score_sentiment,
            "aggregate": stages.aggregate,
        }
        with _run_log(record_path.with_suffix(".log")):
            try:
                for current in run["stages"]:
                    key = current["key"]
                    run["current_stage"] = key
                    current.update(status="running", started_at=timestamp())
                    store.save(run)
                    logger.info("Stage started: %s", key)
                    current["metrics"] = tasks[key]()
                    if key == "preflight":
                        run["model_version"] = current["metrics"]["model_version"]
                    if key == "import":
                        _reconcile(run)
                    current.update(status="completed", finished_at=timestamp())
                    store.save(run)
                    logger.info("Stage completed: %s", key)
                run["status"] = (
                    "completed_with_warnings" if run["warnings"] else "completed"
                )
            except BaseException as exc:
                interrupted = not isinstance(exc, Exception)
                run["status"] = "interrupted" if interrupted else "failed"
                run["error"] = f"{type(exc).__name__}: {exc}"
                if current is not None:
                    current.update(
                        status=run["status"],
                        finished_at=timestamp(),
                        error=run["error"],
                    )
                logger.exception(
                    "Pipeline %s at %s", run["status"], run["current_stage"]
                )
                if interrupted:
                    raise
            finally:
                _reconcile(run)
                if run["status"] == "completed" and run["warnings"]:
                    run["status"] = "completed_with_warnings"
                run["finished_at"] = timestamp()
                store.save(run)
        return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--sources", nargs="+", choices=list(stages.SOURCES))
    action.add_argument(
        "--history",
        action="store_true",
        help="show runs and recover interrupted workers",
    )
    parser.add_argument(
        "--run-id", help="optional UUID hex identifier for a background worker"
    )
    parser.add_argument(
        "--state-dir", help="directory for run records (default: data/run/pipeline)"
    )
    parser.add_argument("--lock-fd", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    # Set offline mode before importing any model libraries in this process.
    os.environ["HF_HUB_OFFLINE"] = "1"
    from config.logging_config import setup_logging

    setup_logging()
    try:
        if args.history:
            print(
                json.dumps(
                    history(RunStore(args.state_dir) if args.state_dir else None),
                    indent=2,
                )
            )
            return 0
        run = run_pipeline(
            args.sources,
            run_id=args.run_id,
            store=RunStore(args.state_dir) if args.state_dir else None,
            lock_fd=args.lock_fd,
        )
    except PipelineBusy as exc:
        logger.error("%s", exc)
        return 3
    except (ValueError, OSError) as exc:
        logger.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        return 130
    print(json.dumps(run, indent=2))
    return 0 if run["status"] in ("completed", "completed_with_warnings") else 1


if __name__ == "__main__":
    raise SystemExit(main())
