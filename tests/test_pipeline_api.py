"""Exercise HTTP dispatch with real child processes/locks and no model/data work."""

import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.pipeline import get_pipeline_service
from pipeline.jobs import RunStore
from pipeline.service import PipelineService

# Replace only the model-running worker with this controlled process. It
# inherits the launcher's real descriptor and exercises the real RunStore.
STUB_WORKER = r"""
import argparse, os, time
from pathlib import Path
from pipeline.jobs import RunStore, timestamp
p = argparse.ArgumentParser()
p.add_argument('--sources', nargs='+')
p.add_argument('--run-id')
p.add_argument('--state-dir')
p.add_argument('--lock-fd', type=int)
p.add_argument('--since')
p.add_argument('--until')
a = p.parse_args()
mode = os.environ['PIPELINE_TEST_MODE']
control = Path(os.environ['PIPELINE_TEST_CONTROL'])
store = RunStore(a.state_dir)
with store.inherited_lock(a.lock_fd):
    if mode == 'crash':
        raise SystemExit(7)
    run = store.get(a.run_id)
    if mode != 'queued':
        run.update(status='running', pid=os.getpid(), current_stage='preprocess')
        run['stages'][0].update(status='completed', finished_at=timestamp())
        run['stages'][2].update(status='running', started_at=timestamp())
        store.save(run)
    (control / (a.run_id + '.ready')).touch()
    deadline = time.monotonic() + 20
    while not (control / (a.run_id + '.release')).exists():
        if time.monotonic() > deadline:
            raise SystemExit(8)
        time.sleep(.01)
    if mode == 'warnings':
        run['warnings'].append({'stage': 'import', 'file': 'fixture.pdf', 'message': 'No prose'})
    run.update(status='completed_with_warnings' if mode == 'warnings' else 'completed',
               finished_at=timestamp(), model_version='fixture-model', current_stage='aggregate')
    for stage in run['stages']:
        stage.update(status='completed', finished_at=timestamp())
    run['stages'][-1]['metrics'] = {'index_rows': 12}
    store.save(run)
"""


def eventually(check, *, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = check()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError("Expected worker/status condition was not reached")


@pytest.fixture
def pipeline_api(temp_db, tmp_path, monkeypatch):
    from ingest import earnings_extract, sgx_research_extract

    for source, module in (
        ("earnings", earnings_extract),
        ("sgx_research", sgx_research_extract),
    ):
        folder = tmp_path / source
        folder.mkdir()
        monkeypatch.setattr(module, "PDF_DIR", str(folder))
    control = tmp_path / "control"
    control.mkdir()
    state = SimpleNamespace(
        store=RunStore(tmp_path / "jobs"),
        processes=[],
        calls=[],
        mode="wait",
        control=control,
    )

    def launch(command, **kwargs):
        state.calls.append((command, kwargs.copy()))
        environment = kwargs["env"].copy()
        environment.update(
            PIPELINE_TEST_MODE=state.mode, PIPELINE_TEST_CONTROL=str(control)
        )
        kwargs["env"] = environment
        process = subprocess.Popen(
            [command[0], "-c", STUB_WORKER, *command[3:]], **kwargs
        )
        state.processes.append(process)
        return process

    state.service = PipelineService(state.store, popen=launch)
    app.dependency_overrides[get_pipeline_service] = lambda: state.service
    state.client = TestClient(app)
    try:
        yield state
    finally:
        app.dependency_overrides.pop(get_pipeline_service, None)
        for run in state.store.history():
            (control / f"{run['run_id']}.release").touch()
        for process in state.processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        # Wait for the reaper's final write so pytest can remove the temp tree.
        eventually(
            lambda: all(
                run["status"] not in ("queued", "running")
                for run in state.service.history()["runs"]
            )
        )
        state.client.close()


def start(state, sources=None):
    response = state.client.post(
        "/pipeline/runs", json={"sources": sources or ["earnings"]}
    )
    assert response.status_code == 202, response.text
    return response


def finish(state, run_id):
    (state.control / f"{run_id}.release").touch()

    def done():
        run = state.client.get(f"/pipeline/runs/{run_id}").json()["run"]
        return run if run["status"] not in ("queued", "running") else None

    return eventually(done)


def test_source_inventory_and_empty_history_never_start_a_worker(pipeline_api):
    state = pipeline_api
    response = state.client.get("/pipeline/sources")
    assert response.status_code == 200
    assert {item["key"] for item in response.json()["sources"]} == {
        "earnings",
        "sgx_research",
        "google_news",
        "arctic_shift",
    }
    assert response.json()["analysis_scope"] == "all_pending"
    assert state.client.get("/pipeline/runs").json() == {
        "runs": [],
        "active_run_id": None,
    }
    assert not state.calls


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"sources": []},
        {"sources": ["reddit"]},
        {"sources": "earnings"},
        {"sources": ["../file"]},
        {"sources": [None]},
        {"sources": ["earnings"], "db_path": "/tmp/other.db"},
        {"sources": ["earnings"], "command": "echo test"},
    ],
)
def test_invalid_input_cannot_start_a_worker(pipeline_api, body):
    state = pipeline_api
    assert state.client.post("/pipeline/runs", json=body).status_code == 422
    assert not state.calls and state.store.history() == []


def test_start_returns_before_work_finishes_and_status_is_pollable(
    pipeline_api, temp_db
):
    state = pipeline_api
    response = start(state, ["sgx_research", "earnings"])
    run = response.json()["run"]
    run_id = run["run_id"]
    assert response.headers["location"] == f"/pipeline/runs/{run_id}"
    assert response.headers["retry-after"] == "2"
    assert run["status"] == "queued" and run["pid"] is None
    assert run["sources"] == ["earnings", "sgx_research"]
    eventually(lambda: (state.control / f"{run_id}.ready").exists())
    current = state.client.get(response.headers["location"]).json()["run"]
    assert current["status"] == "running" and current["current_stage"] == "preprocess"
    assert state.processes[0].poll() is None
    assert state.client.get("/health").json() == {"status": "ok"}
    command, options = state.calls[0]
    assert command[:3] == [os.sys.executable, "-m", "pipeline.runner"]
    assert options["env"]["PLP_DB_PATH"] == temp_db.DB_PATH
    assert options["env"]["HF_HUB_OFFLINE"] == "1"
    assert options["start_new_session"] is True and options["pass_fds"]
    assert state.service.history()["active_run_id"] == run_id
    finished = finish(state, run_id)
    assert finished["status"] == "completed" and finished["stages"][-1]["metrics"] == {
        "index_rows": 12
    }
    summary = state.client.get("/pipeline/runs").json()
    assert summary["active_run_id"] is None and summary["runs"][0]["run_id"] == run_id
    assert "stages" not in summary["runs"][0]


@pytest.mark.parametrize("mode", ["queued", "wait"])
def test_duplicate_start_is_blocked_during_startup_and_processing(pipeline_api, mode):
    state = pipeline_api
    state.mode = mode
    run_id = start(state).json()["run"]["run_id"]
    eventually(lambda: (state.control / f"{run_id}.ready").exists())
    assert (
        state.client.post(
            "/pipeline/runs", json={"sources": ["sgx_research"]}
        ).status_code
        == 409
    )
    assert len(state.calls) == 1
    assert state.client.get(f"/pipeline/runs/{run_id}").json()["run"]["status"] in (
        "queued",
        "running",
    )
    finish(state, run_id)


def test_two_overlapping_requests_reserve_only_one_worker(pipeline_api):
    from concurrent.futures import ThreadPoolExecutor

    state = pipeline_api
    state.mode = "queued"
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [
            pool.submit(
                state.client.post, "/pipeline/runs", json={"sources": ["earnings"]}
            )
            for _ in range(2)
        ]
        responses = [request.result(timeout=8) for request in requests]
    assert sorted(response.status_code for response in responses) == [202, 409]
    assert len(state.calls) == 1


def test_status_survives_a_new_service_instance_without_resending(pipeline_api):
    state = pipeline_api
    run_id = start(state).json()["run"]["run_id"]
    eventually(lambda: (state.control / f"{run_id}.ready").exists())
    replacement = PipelineService(RunStore(state.store.directory))
    assert replacement.get(run_id)["status"] == "running"
    assert replacement.history()["active_run_id"] == run_id
    assert len(state.calls) == 1
    finish(state, run_id)
    assert replacement.get(run_id)["status"] == "completed"


def test_warnings_are_preserved_in_status_and_history(pipeline_api):
    state = pipeline_api
    state.mode = "warnings"
    run_id = start(state).json()["run"]["run_id"]
    eventually(lambda: (state.control / f"{run_id}.ready").exists())
    run = finish(state, run_id)
    assert (
        run["status"] == "completed_with_warnings"
        and run["warnings"][0]["message"] == "No prose"
    )
    assert state.client.get("/pipeline/runs").json()["runs"][0]["warnings_count"] == 1


def test_process_crash_before_runner_start_does_not_leave_a_permanent_queue(
    pipeline_api,
):
    state = pipeline_api
    state.mode = "crash"
    run_id = start(state).json()["run"]["run_id"]
    state.processes[0].wait(timeout=5)
    eventually(lambda: state.store.get(run_id)["status"] not in ("queued", "running"))
    run = state.client.get(f"/pipeline/runs/{run_id}").json()["run"]
    assert run["status"] == "failed" and "code 7" in run["error"]


def test_killed_worker_is_interrupted_and_another_run_can_start(pipeline_api):
    state = pipeline_api
    run_id = start(state).json()["run"]["run_id"]
    eventually(lambda: (state.control / f"{run_id}.ready").exists())
    state.processes[0].kill()
    state.processes[0].wait(timeout=5)
    run = eventually(
        lambda: (
            value
            if (value := state.client.get(f"/pipeline/runs/{run_id}").json()["run"])[
                "status"
            ]
            == "interrupted"
            else None
        )
    )
    assert run["finished_at"] and run["stages"][2]["status"] == "interrupted"
    next_id = start(state).json()["run"]["run_id"]
    assert next_id != run_id
    finish(state, next_id)


def test_spawn_failure_is_visible_and_releases_the_reservation(
    pipeline_api, monkeypatch
):
    state = pipeline_api
    original = state.service._popen

    def unavailable(*args, **kwargs):
        raise OSError("Cannot start Python")

    monkeypatch.setattr(state.service, "_popen", unavailable)
    assert (
        state.client.post("/pipeline/runs", json={"sources": ["earnings"]}).status_code
        == 503
    )
    saved = state.store.history()[0]
    assert saved["status"] == "failed" and "Cannot start Python" in saved["error"]
    monkeypatch.setattr(state.service, "_popen", original)
    run_id = start(state).json()["run"]["run_id"]
    finish(state, run_id)


def test_status_not_found_and_invalid_identifiers(pipeline_api):
    state = pipeline_api
    assert state.client.get(f"/pipeline/runs/{uuid4().hex}").status_code == 404
    assert state.client.get("/pipeline/runs/not-a-uuid").status_code == 422
    assert state.client.get("/pipeline/runs?limit=0").status_code == 422
    assert state.client.get("/pipeline/runs?limit=101").status_code == 422
    assert not state.calls


def test_unsupported_worker_platform_does_not_break_existing_api_routes(
    pipeline_api, monkeypatch
):
    import pipeline.jobs as jobs

    state = pipeline_api
    with monkeypatch.context() as changes:
        changes.setattr(jobs, "fcntl", None)
        assert state.client.get("/health").status_code == 200
        assert state.client.get("/banks").status_code == 200
        assert state.client.get("/pipeline/sources").status_code == 200
        assert (
            state.client.post(
                "/pipeline/runs", json={"sources": ["earnings"]}
            ).status_code
            == 503
        )
        assert not state.calls


def test_real_cli_worker_adopts_reservation_and_reports_preflight_failure(
    temp_db, tmp_path, monkeypatch
):
    # The actual worker is used here, with a deliberately nonexistent DB so
    # preflight MUST stop before PDF extraction, model loads or network calls.
    missing = tmp_path / "missing.db"
    monkeypatch.setattr(temp_db, "DB_PATH", str(missing))
    store = RunStore(tmp_path / "real-worker-jobs")
    service = PipelineService(store)
    queued = service.start(["earnings"])
    run_id = queued["run_id"]

    def finished():
        run = service.get(run_id)
        return run if run["status"] not in ("queued", "running") else None

    run = eventually(finished)
    assert run["status"] == "failed" and run["current_stage"] == "preflight"
    assert run["stages"][0]["status"] == "failed" and run["import_candidates"] == []
    assert not missing.exists()


def test_online_request_carries_fixed_window_into_the_reserved_worker(pipeline_api):
    state = pipeline_api
    response = state.client.post(
        "/pipeline/runs",
        json={
            "sources": ["arctic_shift", "google_news"],
            "since": "2024-05-01",
            "until": "2024-05-08",
        },
    )
    assert response.status_code == 202, response.text
    run = response.json()["run"]
    assert run["sources"] == ["google_news", "arctic_shift"]
    assert run["collection_window"] == {"since": "2024-05-01", "until": "2024-05-08"}
    assert run["source_results"] == {}
    command, _ = state.calls[-1]
    assert command[command.index("--since") + 1] == "2024-05-01"
    assert command[command.index("--until") + 1] == "2024-05-08"
    eventually(lambda: (state.control / f"{run['run_id']}.ready").exists())
    finish(state, run["run_id"])


@pytest.mark.parametrize(
    "body",
    [
        {"sources": ["google_news"], "since": "2024-05-01"},
        {"sources": ["google_news"], "since": "2024-05-01", "until": "2024-06-02"},
        {"sources": ["arctic_shift"], "since": "2024-05-01", "until": "2024-05-01"},
        {"sources": ["arctic_shift"], "since": "2099-01-01", "until": "2099-01-02"},
        {"sources": ["earnings"], "since": "2024-05-01", "until": "2024-05-08"},
        {"sources": ["google_news"], "since": "invalid", "until": "2024-05-08"},
        {"sources": ["google_news"], "url": "https://untrusted.test"},
        {"sources": ["cna"]},
        {"sources": ["yahoo_news"]},
    ],
)
def test_collection_options_are_validated_before_reserving_a_worker(pipeline_api, body):
    state = pipeline_api
    assert state.client.post("/pipeline/runs", json=body).status_code == 422
    assert not state.calls and state.store.history() == []


def test_online_default_is_a_persisted_seven_day_window(pipeline_api):
    from datetime import date

    state = pipeline_api
    response = start(state, ["google_news"])
    run = response.json()["run"]
    window = run["collection_window"]
    assert (
        date.fromisoformat(window["until"]) - date.fromisoformat(window["since"])
    ).days == 7
    finish(state, run["run_id"])
