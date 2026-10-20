"""Launch a separate local worker; inference never runs in a request handler."""

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from uuid import uuid4

from pipeline import runner, stages
from pipeline.jobs import ACTIVE_STATUSES, PipelineBusy, RunStore, timestamp

logger = logging.getLogger(__name__)


class WorkerLaunchError(RuntimeError):
    pass


def run_summary(run: dict) -> dict:
    """List views do not need every PDF outcome or import-manifest row."""
    keys = (
        "run_id",
        "status",
        "sources",
        "started_at",
        "finished_at",
        "current_stage",
        "model_version",
        "error",
    )
    return {
        **{key: run[key] for key in keys},
        "warnings_count": len(run["warnings"]),
        "documents_inserted": len(run["imported_documents"]),
    }


class PipelineService:
    def __init__(self, store: RunStore | None = None, *, popen=None):
        self.store = store or RunStore()
        self._popen = popen or subprocess.Popen

    def sources(self) -> list[dict]:
        return stages.describe_sources()

    def start(self, sources: list[str], *, since=None, until=None) -> dict:
        sources = stages.selected_sources(sources)
        window = stages.collection_window(sources, since, until)
        with self.store.lock() as lease:
            runner._recover(self.store)
            run = runner.new_run(
                sources, self.store, uuid4().hex, queued=True, window=window
            )
            run["worker_log_path"] = str(
                self.store.path(run["run_id"]).with_suffix(".worker.log")
            )
            self.store.save(run)
            environment = os.environ.copy()
            environment.update(
                PLP_DB_PATH=run["db_path"],
                PLP_EMBEDDINGS_PATH=run["embeddings_path"],
                HF_HUB_OFFLINE="1",
                LOG_FILE="none",
                PYTHONUNBUFFERED="1",
            )
            command = [
                sys.executable,
                "-m",
                "pipeline.runner",
                "--sources",
                *sources,
                "--run-id",
                run["run_id"],
                "--state-dir",
                str(self.store.directory.resolve()),
                "--lock-fd",
                str(lease.descriptor),
            ]
            if window:
                command.extend(["--since", window["since"], "--until", window["until"]])
            try:
                with Path(run["worker_log_path"]).open("a", encoding="utf-8") as output:
                    process = self._popen(
                        command,
                        cwd=str(stages.ROOT),
                        env=environment,
                        stdin=subprocess.DEVNULL,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                        pass_fds=(lease.descriptor,),
                    )
            except OSError as exc:
                run.update(
                    status="failed",
                    finished_at=timestamp(),
                    error=f"Cannot launch pipeline worker: {exc}",
                )
                self.store.save(run)
                raise WorkerLaunchError(run["error"]) from exc
            lease.hand_off()
        # The parent must close its descriptor before the reaper can acquire
        # the lock for a worker which exited immediately during startup.
        try:
            threading.Thread(
                target=self._reap,
                args=(process, run["run_id"]),
                daemon=True,
                name=f"pipeline-{run['run_id'][:8]}",
            ).start()
        except RuntimeError:
            logger.exception(
                "Cannot start worker reaper; polling will recover its status"
            )
        return run

    def _reap(self, process, run_id: str) -> None:
        exit_code = process.wait()
        try:
            with self.store.lock():
                run = self.store.get(run_id)
                if run["status"] in ACTIVE_STATUSES:
                    state = "interrupted" if exit_code < 0 else "failed"
                    message = f"Pipeline worker exited with code {exit_code} before recording completion."
                    run.update(status=state, finished_at=timestamp(), error=message)
                    for stage in run["stages"]:
                        if stage["status"] == "running":
                            stage.update(
                                status=state,
                                finished_at=run["finished_at"],
                                error=message,
                            )
                    runner._reconcile(run)
                run["worker_exit_code"] = exit_code
                self.store.save(run)
        except PipelineBusy:
            # A new worker may already have recovered this completed process.
            pass
        except (OSError, ValueError):
            logger.exception("Cannot record pipeline worker exit: %s", run_id)

    def get(self, run_id: str) -> dict:
        try:
            with self.store.lock():
                runner._recover(self.store)
        except PipelineBusy:
            pass
        return self.store.get(run_id)

    def history(self, limit: int = 20) -> dict:
        runs = runner.history(self.store, limit)
        return {
            "runs": [run_summary(run) for run in runs],
            "active_run_id": next(
                (run["run_id"] for run in runs if run["status"] in ACTIVE_STATUSES),
                None,
            ),
        }
