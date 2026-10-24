"""Orchestrate real SQLite stages with tiny local fixtures and fake model output.

No network, real PDFs, model inference, or writes to the shared database.
"""

import subprocess
import sys
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import runner, stages
from pipeline.jobs import RunStore


@pytest.fixture
def small_pipeline(temp_db, tmp_path, monkeypatch):
    from ingest import earnings_extract, sgx_research_extract
    from preprocess import pipeline as preprocess
    from aspects import assign, embed_store, llm_classify
    from sentiment import score

    folders = {}
    for source, module in (
        ("earnings", earnings_extract),
        ("sgx_research", sgx_research_extract),
    ):
        folder = tmp_path / source
        folder.mkdir()
        monkeypatch.setattr(module, "PDF_DIR", str(folder))
        folders[source] = folder
    bank_folder = folders["earnings"] / "DBS"
    bank_folder.mkdir()
    (bank_folder / "1Q26-new.pdf").touch()
    monkeypatch.setattr(
        earnings_extract,
        "extract_prose",
        lambda path: [
            "DBS reported strong growth in fee income from its wealth management business."
        ],
    )
    monkeypatch.setattr(preprocess, "segment", lambda text: [(text, 0, len(text))])
    embeddings = tmp_path / "embeddings.npz"
    monkeypatch.setenv("PLP_EMBEDDINGS_PATH", str(embeddings))
    monkeypatch.setattr(embed_store, "STORE_PATH", str(embeddings))
    monkeypatch.setattr(
        embed_store,
        "embed_sentences",
        lambda texts: np.ones((len(texts), 768), dtype=np.float32),
    )
    monkeypatch.setattr(assign, "update_search_vectors", lambda: {})
    monkeypatch.setattr(assign, "_load_config", lambda: {"assignment_method": "llm"})
    monkeypatch.setattr(
        llm_classify,
        "classify_rows",
        lambda rows: pd.DataFrame(
            {
                "sentence_id": rows["sentence_id"],
                "aspect": ["wealth_business"] * len(rows),
            }
        ),
    )
    monkeypatch.setattr(
        score, "classify_sentences", lambda texts: [("positive", 0.9)] * len(texts)
    )
    # Prerequisite validation has its own tests. Everything after it uses the
    # existing functions/SQL, except PDF text extraction and model predictions.
    monkeypatch.setattr(
        stages, "preflight", lambda sources: {"model_version": score.MODEL_VERSION}
    )
    return temp_db, RunStore(tmp_path / "jobs"), folders


def counts(db):
    conn = db.get_connection()
    try:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "documents",
                "sentences",
                "sentence_aspects",
                "aspect_sentiment",
                "sentiment_index",
            )
        }
    finally:
        conn.close()


def test_full_run_uses_existing_stages_and_rerun_skips_duplicates(small_pipeline):
    db, store, _ = small_pipeline
    first = runner.run_pipeline(["earnings"], store=store)
    baseline = counts(db)
    assert first["status"] == "completed"
    assert first["db_path"] == db.DB_PATH
    assert (
        baseline["documents"]
        == baseline["sentences"]
        == baseline["sentence_aspects"]
        == baseline["aspect_sentiment"]
        == 1
    )
    assert baseline["sentiment_index"] > 0
    assert [stage["status"] for stage in first["stages"]] == ["completed"] * 6
    assert first["imported_documents"] == first["import_candidates"]
    assert len(first["imported_documents"]) == 1
    assert first["finished_at"] and Path(first["log_path"]).is_file()
    assert "Stage completed: aggregate" in Path(first["log_path"]).read_text()
    assert store.get(first["run_id"]) == first

    second = runner.run_pipeline(["earnings"], store=store)
    assert second["status"] == "completed"
    assert counts(db) == baseline
    assert second["imported_documents"] == []
    assert second["stages"][1]["files"][0]["status"] == "already_stored"
    assert second["stages"][2]["metrics"]["sentences_kept"] == 0
    assert second["stages"][3]["metrics"]["newly_assigned"] == 0
    assert second["stages"][4]["metrics"]["newly_scored"] == 0
    assert len(store.history()) == 2


def test_selected_source_does_not_import_the_other_folder(small_pipeline, monkeypatch):
    from ingest import earnings_extract, sgx_research_extract

    db, store, folders = small_pipeline
    (folders["sgx_research"] / "research.PDF").touch()

    def build(path):
        return {
            "doc_id": "research-1",
            "source": "sgx_research",
            "source_detail": "broker",
            "bank": "OCBC",
            "doc_type": "analyst_report",
            "title": "Research",
            "url": "u",
            "body": "OCBC reported strong growth in fee income from its wealth management business.",
            "published_at": "2026-05-01",
            "raw": {"read_by": "text"},
        }

    monkeypatch.setattr(sgx_research_extract, "build_document", build)

    def refuse(*a, **k):
        pytest.fail("unselected earnings collector was called")

    monkeypatch.setattr(earnings_extract, "pull", refuse)
    run = runner.run_pipeline(["sgx_research"], store=store)
    assert run["status"] == "completed"
    assert {item["source"] for item in run["imported_documents"]} == {"sgx_research"}
    assert counts(db)["documents"] == 1


def test_both_sources_run_once_in_deterministic_order(small_pipeline, monkeypatch):
    from ingest import sgx_research_extract

    _, store, _ = small_pipeline
    called = []
    real_pull = sgx_research_extract.pull

    def pull(**kwargs):
        called.append("sgx_research")
        return real_pull(**kwargs)

    monkeypatch.setattr(sgx_research_extract, "pull", pull)
    run = runner.run_pipeline(["sgx_research", "earnings", "earnings"], store=store)
    assert run["sources"] == ["earnings", "sgx_research"]
    assert called == ["sgx_research"]
    assert set(run["stages"][1]["metrics"]) == {"earnings", "sgx_research"}


@pytest.mark.parametrize(
    "bad", [[], ["unknown"], ["earnings", "../secret"], "earnings", [None]]
)
def test_invalid_sources_are_rejected_before_a_job_is_created(tmp_path, bad):
    store = RunStore(tmp_path / "jobs")
    with pytest.raises(ValueError):
        runner.run_pipeline(bad, store=store)
    assert not store.directory.exists()


def test_extraction_failures_are_visible_but_good_files_still_finish(
    small_pipeline, monkeypatch
):
    from ingest import earnings_extract

    db, store, folders = small_pipeline
    (folders["earnings"] / "DBS" / "2Q26-broken.pdf").touch()
    real_extract = earnings_extract.extract_prose

    def extract(path):
        if "broken" in path:
            raise ValueError("Unreadable PDF")
        return real_extract(path)

    monkeypatch.setattr(earnings_extract, "extract_prose", extract)
    run = runner.run_pipeline(["earnings"], store=store)
    assert run["status"] == "completed_with_warnings"
    assert counts(db)["sentences"] == 1
    assert any("Unreadable PDF" in warning["message"] for warning in run["warnings"])
    assert run["stages"][1]["metrics"]["earnings"]["files"] == {
        "extracted": 1,
        "failed": 1,
    }


def test_no_prose_and_unknown_earnings_dates_are_reported(small_pipeline, monkeypatch):
    from ingest import earnings_extract

    _, store, folders = small_pipeline
    (folders["earnings"] / "DBS" / "undated.pdf").touch()
    real_extract = earnings_extract.extract_prose
    monkeypatch.setattr(
        earnings_extract,
        "extract_prose",
        lambda path: [] if "1Q26" in path else real_extract(path),
    )
    run = runner.run_pipeline(["earnings"], store=store)
    assert run["status"] == "completed_with_warnings"
    assert any("No usable prose" in warning["message"] for warning in run["warnings"])
    assert any(
        "using the import date" in warning["message"] for warning in run["warnings"]
    )


def test_failure_keeps_inserted_ids_stops_later_stages_and_can_resume(
    small_pipeline, monkeypatch
):
    db, store, _ = small_pipeline
    real_assign = stages.assign_topics

    def fail():
        raise RuntimeError("Topic model unavailable")

    monkeypatch.setattr(stages, "assign_topics", fail)
    run = runner.run_pipeline(["earnings"], store=store)
    assert run["status"] == "failed" and run["current_stage"] == "assign"
    assert counts(db)["documents"] == counts(db)["sentences"] == 1
    assert counts(db)["aspect_sentiment"] == 0
    assert len(run["imported_documents"]) == 1
    assert run["stages"][3]["status"] == "failed"
    assert run["stages"][4]["status"] == run["stages"][5]["status"] == "pending"
    assert "Topic model unavailable" in store.get(run["run_id"])["error"]
    monkeypatch.setattr(stages, "assign_topics", real_assign)
    resumed = runner.run_pipeline(["earnings"], store=store)
    assert resumed["status"] == "completed" and resumed["imported_documents"] == []
    assert counts(db)["documents"] == counts(db)["aspect_sentiment"] == 1


def test_keyboard_interrupt_is_persisted_and_releases_lock(small_pipeline, monkeypatch):
    _, store, _ = small_pipeline

    def interrupt():
        raise KeyboardInterrupt()

    monkeypatch.setattr(stages, "preprocess", interrupt)
    with pytest.raises(KeyboardInterrupt):
        runner.run_pipeline(["earnings"], store=store)
    saved = store.history()[0]
    assert saved["status"] == "interrupted"
    assert saved["stages"][2]["status"] == "interrupted"
    assert len(saved["imported_documents"]) == 1
    with store.lock():
        pass


def test_candidate_manifest_survives_an_exception_after_import_commit(
    small_pipeline, monkeypatch
):
    db, store, _ = small_pipeline
    real_upsert = db.upsert_documents

    def commit_then_fail(docs):
        real_upsert(docs)
        raise RuntimeError("Stopped just after commit")

    monkeypatch.setattr(db, "upsert_documents", commit_then_fail)
    run = runner.run_pipeline(["earnings"], store=store)
    assert run["status"] == "failed" and run["current_stage"] == "import"
    assert counts(db)["documents"] == 1
    assert run["imported_documents"] == run["import_candidates"]


def test_final_reconciliation_warning_is_not_reported_as_clean_success(
    small_pipeline, monkeypatch
):
    _, store, _ = small_pipeline
    original = stages.imported_documents
    calls = 0

    def reconcile(run):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("Could not read import manifest")
        return original(run)

    monkeypatch.setattr(stages, "imported_documents", reconcile)
    run = runner.run_pipeline(["earnings"], store=store)
    assert run["status"] == "completed_with_warnings"
    assert len(run["imported_documents"]) == 1
    assert "Could not reconcile" in run["warnings"][-1]["message"]


def test_analysis_also_finishes_existing_pending_documents(small_pipeline):
    db, store, _ = small_pipeline
    db.upsert_documents(
        [
            {
                "doc_id": "pending-news",
                "source": "yahoo_news",
                "bank": "DBS",
                "doc_type": "article",
                "title": "News",
                "url": "u",
                "published_at": "2026-01-01",
                "body": "DBS reported higher net interest income from its expanding loan portfolio.",
            }
        ]
    )
    run = runner.run_pipeline(["earnings"], store=store)
    assert run["status"] == "completed"
    assert (
        counts(db)["documents"]
        == counts(db)["sentences"]
        == counts(db)["aspect_sentiment"]
        == 2
    )
    assert {doc["source"] for doc in run["imported_documents"]} == {"earnings"}


def test_second_process_is_refused_while_first_holds_the_lock(tmp_path):
    store = RunStore(tmp_path / "jobs")
    script = """
import sys
from pipeline.jobs import RunStore, PipelineBusy
try:
    with RunStore(sys.argv[1]).lock():
        sys.exit(0)
except PipelineBusy:
    sys.exit(3)
"""
    with store.lock():
        result = subprocess.run(
            [sys.executable, "-c", script, str(store.directory)],
            capture_output=True,
            text=True,
        )
    assert result.returncode == 3, result.stderr
    with store.lock():
        pass


def test_history_recovers_a_dead_worker_and_reconciles_its_manifest(small_pipeline):
    db, store, _ = small_pipeline
    run = runner.run_pipeline(["earnings"], store=store)
    run.update(status="running", finished_at=None, imported_documents=[])
    run["stages"][-1].update(status="running", finished_at=None)
    store.save(run)  # Simulate SIGKILL after commit, before final JSON write.
    recovered = runner.history(RunStore(store.directory))[0]
    assert recovered["status"] == "interrupted" and recovered["finished_at"]
    assert recovered["stages"][-1]["status"] == "interrupted"
    assert recovered["imported_documents"] == run["import_candidates"]
    assert counts(db)["documents"] == 1


def test_history_does_not_mark_a_live_worker_interrupted(small_pipeline, monkeypatch):
    _, store, _ = small_pipeline
    real_preprocess = stages.preprocess

    def observe():
        saved = runner.history(RunStore(store.directory))[0]
        assert saved["status"] == "running"
        assert saved["current_stage"] == "preprocess"
        return real_preprocess()

    monkeypatch.setattr(stages, "preprocess", observe)
    assert runner.run_pipeline(["earnings"], store=store)["status"] == "completed"


def test_run_id_cannot_escape_the_run_directory(tmp_path):
    store = RunStore(tmp_path / "jobs")
    with pytest.raises(ValueError):
        runner.run_pipeline(["earnings"], store=store, run_id="../../anything")
    assert not store.directory.exists()


def test_finished_run_cannot_be_overwritten(small_pipeline):
    _, store, _ = small_pipeline
    run = runner.run_pipeline(["earnings"], store=store)
    with pytest.raises(ValueError, match="already exists"):
        runner.run_pipeline(["earnings"], store=store, run_id=run["run_id"])
    assert store.get(run["run_id"])["status"] == "completed"
