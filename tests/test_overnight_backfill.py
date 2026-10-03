"""
scripts/overnight_backfill.py with ingest/arctic_shift.py as its child: a month
is marked done only when every window in it was fetched.

The backfill marks a month done when the child exits 0 and never fetches a
marked month again. So a pull that loses a window to a failing page must not
exit 0. Here the child, `python -m ingest.arctic_shift`, runs in-process with
the network replaced, so no request leaves the machine and data/ is never
written.
"""

import importlib.util
import os
import runpy
import subprocess
import sys
import time
import warnings
from types import SimpleNamespace

import pytest
import requests

import config.logging_config as logging_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_backfill():
    spec = importlib.util.spec_from_file_location(
        "overnight_backfill", os.path.join(ROOT, "scripts", "overnight_backfill.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Resp:
    status_code, text, headers = 200, "", {}

    def json(self):
        return {"data": []}   # an empty page: the archive has nothing more


def _archive_down(*args, **kwargs):
    raise requests.exceptions.ConnectionError("archive unreachable")


def _archive_empty(*args, **kwargs):
    return _Resp()


def _run_child_in_process(monkeypatch):
    """Stands in for subprocess.run: runs the child's entry point here and
    turns its exit into a return code, as the real subprocess would."""
    def run(cmd, **kwargs):
        assert cmd[1:3] == ["-m", "ingest.arctic_shift"]
        monkeypatch.setattr(sys, "argv", cmd[2:])
        code = 0
        with warnings.catch_warnings():
            # The module is already imported by other tests; running it again
            # as __main__ is what `python -m` does in a fresh process.
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                runpy.run_module("ingest.arctic_shift", run_name="__main__")
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        return subprocess.CompletedProcess(cmd, code, "", "")
    return run


@pytest.fixture
def backfill(temp_db, tmp_path, monkeypatch):
    ob = _load_backfill()
    monkeypatch.setattr(ob, "MARKER_FILE", tmp_path / ".backfill_progress.txt")
    monkeypatch.setattr(ob, "setup_logging", lambda **kwargs: None)
    monkeypatch.setattr(logging_config, "setup_logging", lambda *a, **k: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(ob, "subprocess", SimpleNamespace(run=_run_child_in_process(monkeypatch)))
    monkeypatch.setattr(sys, "argv", ["overnight_backfill.py", "--since", "2025-03-01",
                                      "--until", "2025-04-01"])
    return ob


def test_a_month_that_lost_a_window_is_not_marked_done(backfill, monkeypatch):
    monkeypatch.setattr(requests, "get", _archive_down)
    backfill.run()
    assert not backfill.MARKER_FILE.exists() or backfill.MARKER_FILE.read_text() == ""


def test_a_month_fetched_in_full_is_marked_done(backfill, monkeypatch):
    monkeypatch.setattr(requests, "get", _archive_empty)
    backfill.run()
    assert backfill.MARKER_FILE.read_text().splitlines() == ["2025-03-01:2025-04-01"]


def test_the_pull_exits_non_zero_and_names_the_windows_it_lost(temp_db, monkeypatch, caplog):
    monkeypatch.setattr(requests, "get", _archive_down)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(logging_config, "setup_logging", lambda *a, **k: None)
    code = _run_child_in_process(monkeypatch)(
        [sys.executable, "-m", "ingest.arctic_shift", "--since", "2025-03-01",
         "--until", "2025-04-01"]).returncode
    assert code != 0
    final = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert final and final[-1].startswith("INCOMPLETE")
    assert "r/singaporefi posts from 2025-03-01 to 2025-04-01" in final[-1]
    assert "r/singaporefi comments from 2025-03-01 to 2025-04-01" in final[-1]


def test_the_backfill_knows_the_pulls_incomplete_exit_code():
    import ingest.arctic_shift as arc
    assert _load_backfill().INCOMPLETE_EXIT == arc.EXIT_INCOMPLETE != 0
