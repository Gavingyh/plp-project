"""Durable run records and a process lock for the local/Docker pipeline.

Only the manual runner participates in this lock. Do not run the old batch
commands concurrently with it. macOS and Linux release flock after a crash;
no timeout or PID guess can accidentally unlock a slow, still-running job.
"""

try:
    import fcntl
except ImportError:  # Keep existing API/data/chat routes usable on native Windows.
    fcntl = None
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "data/run/pipeline"
ACTIVE_STATUSES = {"queued", "running"}


class LockLease:
    """Keep the same OS lock held while a child inherits its descriptor."""

    def __init__(self, descriptor: int):
        self.descriptor = descriptor
        self.transferred = False

    def hand_off(self) -> None:
        self.transferred = True


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
        backend = fcntl
        if backend is None:
            raise OSError(
                "Manual pipeline workers require macOS or Linux; use Docker on Windows."
            )
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / "worker.lock").open("a") as stream:
            try:
                backend.flock(stream.fileno(), backend.LOCK_EX | backend.LOCK_NB)
            except BlockingIOError as exc:
                raise PipelineBusy(
                    "A manual pipeline run is already in progress."
                ) from exc
            lease = LockLease(stream.fileno())
            try:
                yield lease
            finally:
                # LOCK_UN would also unlock the child's inherited descriptor.
                # After handoff, close only our copy; the child keeps the lock.
                if not lease.transferred:
                    backend.flock(stream.fileno(), backend.LOCK_UN)

    @contextmanager
    def inherited_lock(self, descriptor: int):
        """Adopt the descriptor passed by the launcher, closing it on exit."""
        backend = fcntl
        if backend is None:
            raise OSError(
                "Manual pipeline workers require macOS or Linux; use Docker on Windows."
            )
        expected = (self.directory / "worker.lock").stat()
        actual = os.fstat(descriptor)
        if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
            raise ValueError(
                "Inherited descriptor does not belong to this pipeline lock"
            )
        with os.fdopen(descriptor, "a") as stream:
            backend.flock(stream.fileno(), backend.LOCK_EX | backend.LOCK_NB)
            try:
                yield
            finally:
                backend.flock(stream.fileno(), backend.LOCK_UN)

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
