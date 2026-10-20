"""Online ingestion with temporary SQLite, captured HTTP and fake model output."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from pipeline import runner, stages
from pipeline.collection import collect, collection_window
from test_pipeline_runner import small_pipeline, counts  # noqa: F401 - shared fixture


def document(source, key, *, title=None, published="2024-05-02T08:00:00+00:00"):
    title = title or (
        "DBS customers praised improvements to mobile banking and faster payment processing."
        if source == "arctic_shift"
        else "DBS reported strong growth in fee income from its wealth management business."
    )
    return {
        "doc_id": f"{source}-{key}",
        "source": source,
        "source_detail": "fixture",
        "bank": "DBS",
        "doc_type": "article" if source == "google_news" else "comment",
        "title": title if source == "google_news" else None,
        "body": title,
        "published_at": published,
        "url": f"https://example.test/{source}/{key}",
        "raw": {},
    }


@pytest.fixture
def online(monkeypatch, tmp_path, temp_db):
    from ingest import google_news, arctic_shift, news_filter

    monkeypatch.setattr(news_filter, "FLAGGED_PATH", str(tmp_path / "flagged.csv"))
    monkeypatch.setattr(google_news, "FAILED_WINDOWS", [])
    monkeypatch.setattr(arctic_shift, "INCOMPLETE_WINDOWS", [])
    return temp_db, google_news, arctic_shift


def test_default_window_is_seven_utc_days_and_explicit_window_is_preserved():
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    assert collection_window(["google_news"]) == {
        "since": (tomorrow - timedelta(days=7)).isoformat(),
        "until": tomorrow.isoformat(),
    }
    assert collection_window(["earnings"]) is None
    assert collection_window(["arctic_shift"], "2024-05-01", "2024-06-01") == {
        "since": "2024-05-01",
        "until": "2024-06-01",
    }


@pytest.mark.parametrize(
    "sources,since,until",
    [
        (["earnings"], "2024-05-01", "2024-05-02"),
        (["google_news"], "2024-05-01", None),
        (["arctic_shift"], None, "2024-05-02"),
        (["google_news"], "2024-05-02", "2024-05-01"),
        (["google_news"], "2024-05-01", "2024-05-01"),
        (["google_news"], "2024-05-01", "2024-06-02"),
        (["google_news"], "invalid", "2024-06-02"),
        (["google_news"], "2099-01-01", "2099-01-02"),
    ],
)
def test_invalid_windows_are_rejected_before_creating_a_run(
    tmp_path, sources, since, until
):
    from pipeline.jobs import RunStore

    store = RunStore(tmp_path / "runs")
    with pytest.raises(ValueError):
        runner.run_pipeline(sources, store=store, since=since, until=until)
    assert not store.directory.exists()


def test_google_dedup_relevance_and_date_bounds_are_used_on_every_batch(
    online, monkeypatch
):
    db, google, _ = online
    first = document("google_news", "a")
    noise = document(
        "google_news", "noise", title="The weather was unusually warm today"
    )
    older = document("google_news", "old", published="2024-04-30T23:59:59Z")
    upper = document("google_news", "upper", published="2024-05-03T00:00:00Z")
    existing = {
        **document("yahoo_news", "cross-source"),
        "url": "https://example.test/existing",
    }
    db.upsert_documents([existing])
    cross = {**document("google_news", "cross-source"), "url": existing["url"]}
    # The new title must differ from the already-stored article for news dedup.
    first["title"] = first["body"] = (
        "OCBC announces a new digital service for small business customers."
    )
    monkeypatch.setattr(
        google,
        "iter_batches",
        lambda *a: iter(
            [("first", [first, noise, older, upper, cross]), ("second", [first])]
        ),
    )
    events, manifests = [], []
    result = collect(
        "google_news",
        {"since": "2024-05-01", "until": "2024-05-03"},
        report=events.append,
        before_insert=lambda docs: manifests.extend(docs),
    )
    assert result["status"] == "completed"
    assert result["fetched"] == 6 and result["documents_inserted"] == 1
    assert result["duplicates"] == 2 and result["filtered"] == 3
    assert len(manifests) == 1 and events[0]["result"]["status"] == "running"
    assert events[-1]["result"]["status"] == "completed"
    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2


def test_reditt_uses_daily_windows_skips_duplicates_and_resets_old_errors(
    online, monkeypatch
):
    _, _, arc = online
    arc.INCOMPLETE_WINDOWS.append("stale failure from another run")
    calls = []

    def pull(since, until):
        calls.append((since, until))
        # Repeat the same ID and return an out-of-window candidate.
        return [
            document("arctic_shift", "one"),
            document("arctic_shift", "one"),
            document("arctic_shift", "old", published="2020-01-01T00:00:00Z"),
        ]

    monkeypatch.setattr(arc, "pull", pull)
    result = collect(
        "arctic_shift",
        {"since": "2024-05-01", "until": "2024-05-03"},
        report=lambda e: None,
        before_insert=lambda docs: None,
    )
    assert calls == [("2024-05-01", "2024-05-02"), ("2024-05-02", "2024-05-03")]
    assert result["documents_inserted"] == 1 and result["duplicates"] == 3
    assert result["status"] == "completed" and not result["incomplete_windows"]


def test_adapter_exception_after_a_batch_preserves_committed_documents(
    online, monkeypatch
):
    db, google, _ = online

    def batches(*args):
        yield "first", [document("google_news", "one")]
        raise RuntimeError("Provider unavailable")

    monkeypatch.setattr(google, "iter_batches", batches)
    events = []
    result = collect(
        "google_news",
        {"since": "2024-05-01", "until": "2024-05-03"},
        report=events.append,
        before_insert=lambda docs: None,
    )
    assert result["status"] == "partial" and result["documents_inserted"] == 1
    assert "Provider unavailable" in result["error"]
    with db.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1


def test_storage_failure_is_fatal_not_converted_into_provider_warning(
    online, monkeypatch
):
    db, google, _ = online
    monkeypatch.setattr(
        google,
        "iter_batches",
        lambda *a: iter([("first", [document("google_news", "one")])]),
    )
    monkeypatch.setattr(
        db, "upsert_documents", Mock(side_effect=RuntimeError("Disk full"))
    )
    with pytest.raises(RuntimeError, match="Disk full"):
        collect(
            "google_news",
            {"since": "2024-05-01", "until": "2024-05-03"},
            report=lambda e: None,
            before_insert=lambda docs: None,
        )


def test_online_only_run_completes_existing_analysis_and_rerun_is_incremental(
    small_pipeline, online, monkeypatch
):
    db, store, _ = small_pipeline
    _, google, arc = online
    monkeypatch.setattr(
        google,
        "iter_batches",
        lambda *a: iter([("first", [document("google_news", "one")])]),
    )
    monkeypatch.setattr(arc, "pull", lambda *a: [document("arctic_shift", "one")])
    run = runner.run_pipeline(
        ["google_news", "arctic_shift"],
        store=store,
        since="2024-05-01",
        until="2024-05-03",
    )
    assert run["status"] == "completed", run["error"]
    assert counts(db)["documents"] == counts(db)["aspect_sentiment"] == 2
    assert set(run["source_results"]) == {"google_news", "arctic_shift"}
    assert run["collection_window"] == {"since": "2024-05-01", "until": "2024-05-03"}
    baseline = counts(db)
    again = runner.run_pipeline(
        ["google_news", "arctic_shift"],
        store=store,
        since="2024-05-01",
        until="2024-05-03",
    )
    assert again["status"] == "completed" and not again["imported_documents"]
    assert counts(db) == baseline


def test_failed_source_does_not_block_another_source_or_hide_the_failure(
    small_pipeline, online, monkeypatch
):
    db, store, _ = small_pipeline
    _, google, arc = online

    def batches(*a):
        google.FAILED_WINDOWS.append("DBS first window: HTTP 503")
        yield "first", []

    monkeypatch.setattr(google, "iter_batches", batches)
    monkeypatch.setattr(arc, "pull", lambda *a: [document("arctic_shift", "one")])
    run = runner.run_pipeline(
        ["google_news", "arctic_shift"],
        store=store,
        since="2024-05-01",
        until="2024-05-03",
    )
    assert run["status"] == "completed_with_warnings"
    assert run["source_results"]["google_news"]["status"] == "failed"
    assert run["source_results"]["arctic_shift"]["status"] == "completed"
    assert run["warnings"][0]["incomplete_windows"] == ["DBS first window: HTTP 503"]
    assert counts(db)["aspect_sentiment"] == 1


def test_all_sources_failed_marks_job_failed_and_preserves_source_metrics(
    small_pipeline, online, monkeypatch
):
    _, store, _ = small_pipeline
    _, google, _ = online

    def batches(*a):
        google.FAILED_WINDOWS.append("Window request failed")
        yield "first", []

    monkeypatch.setattr(google, "iter_batches", batches)
    analyse = Mock(side_effect=AssertionError("analysis should not run"))
    monkeypatch.setattr(stages, "preprocess", analyse)
    run = runner.run_pipeline(
        ["google_news"], store=store, since="2024-05-01", until="2024-05-03"
    )
    assert run["status"] == "failed" and run["current_stage"] == "import"
    assert run["source_results"]["google_news"]["status"] == "failed"
    assert run["stages"][1]["metrics"]["google_news"]["status"] == "failed"
    analyse.assert_not_called()


def test_true_empty_result_is_success_and_incomplete_results_are_not(
    online, monkeypatch
):
    _, _, arc = online
    monkeypatch.setattr(arc, "pull", lambda *a: [])
    window = {"since": "2024-05-01", "until": "2024-05-02"}
    assert (
        collect(
            "arctic_shift", window, report=lambda e: None, before_insert=lambda d: None
        )["status"]
        == "completed"
    )

    def partial(*args):
        arc.INCOMPLETE_WINDOWS.append("comments could not be fetched")
        return [document("arctic_shift", "one")]

    monkeypatch.setattr(arc, "pull", partial)
    result = collect(
        "arctic_shift", window, report=lambda e: None, before_insert=lambda d: None
    )
    assert (
        result["status"] == "partial" and result["documents_inserted"] == 0
    )  # candidate is outside this window


def test_online_commit_then_crash_is_reconciled_in_source_results(
    small_pipeline, online, monkeypatch
):
    db, store, _ = small_pipeline
    _, google, _ = online
    monkeypatch.setattr(
        google,
        "iter_batches",
        lambda *a: iter([("first", [document("google_news", "one")])]),
    )
    upsert = db.upsert_documents

    def crash_after_commit(docs):
        upsert(docs)
        raise RuntimeError("Stopped after commit")

    monkeypatch.setattr(db, "upsert_documents", crash_after_commit)
    run = runner.run_pipeline(
        ["google_news"], store=store, since="2024-05-01", until="2024-05-03"
    )
    assert run["status"] == "failed"
    assert len(run["imported_documents"]) == 1
    assert run["source_results"]["google_news"]["documents_inserted"] == 1
    assert run["source_results"]["google_news"]["status"] == "failed"
