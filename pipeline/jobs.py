"""Durable run records and a process lock for the local/Docker pipeline.

Only the manual runner participates in this lock. Do not run the old batch
commands concurrently with it. macOS and Linux release flock after a crash;
no timeout or PID guess can accidentally unlock a slow, still-running job.
"""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "data/run/pipeline"
ACTIVE_STATUSES = {"running"}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineBusy(RuntimeError):
    """Another manual pipeline run owns the lock."""


class RunStore:
    def __init__(self, directory: str | Path = DEFAULT_DIRECTORY):
        self.directory = Path(directory)

    def path(self, run_id: str) -> Path:
        if UUID(run_id).hex != run_id:
            raise ValueError("run_id must be a UUID in hexadecimal form")
        return self.directory / f"{run_id}.json"

    def save(self, run: dict) -> None:
        """Readers see the previous complete record or the new complete one."""
        path = self.path(run["run_id"])
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.directory, delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(run, stream, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def get(self, run_id: str) -> dict:
        return json.loads(self.path(run_id).read_text(encoding="utf-8"))

    def history(self, limit: int = 20) -> list[dict]:
        if limit < 1:
            raise ValueError("limit must be positive")
        runs = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in self.directory.glob("*.json")
        ]
        return sorted(runs, key=lambda run: run["started_at"], reverse=True)[:limit]

    @contextmanager
    def lock(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "worker.lock").open("a") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise PipelineBusy(
                    "A manual pipeline run is already in progress."
                ) from exc
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def recover_interrupted(self) -> list[dict]:
        """Call while holding lock(): no live worker can own these records."""
        interrupted = []
        for path in self.directory.glob("*.json"):
            run = json.loads(path.read_text(encoding="utf-8"))
            if run["status"] not in ACTIVE_STATUSES:
                continue
            run["status"] = "interrupted"
            run["finished_at"] = timestamp()
            run["error"] = (
                "The worker stopped before recording completion. Rerun to finish pending work."
            )
            for stage in run["stages"]:
                if stage["status"] == "running":
                    stage["status"] = "interrupted"
                    stage["finished_at"] = run["finished_at"]
                    stage["error"] = run["error"]
            self.save(run)
            interrupted.append(run)
        return interrupted
