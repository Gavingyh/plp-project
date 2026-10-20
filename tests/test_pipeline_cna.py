"""Cached CNA imports use temporary data, real pipeline stages and fake inference."""

import json
from unittest.mock import Mock

import pytest

from pipeline import cna_cache, runner, stages
from test_pipeline_runner import small_pipeline, counts  # noqa: F401


def article(identity="a", **changes):
    return {
        "id": identity,
        "section": "business",
        "url": f"https://www.channelnewsasia.com/business/dbs-results-{identity}",
        "title": "DBS reports higher wealth management income",
        "text": "DBS reported strong growth in fee income from its wealth management business.",
        "published": "2023-02-01T12:00:00+08:00",
        "fetched_from": "live",
        **changes,
    }


@pytest.fixture
def cache(tmp_path, monkeypatch):
    from ingest import news_filter
    import requests

    path = tmp_path / "cna/articles.jsonl"
    path.parent.mkdir()
    monkeypatch.setattr(cna_cache, "CACHE_PATH", path)
    monkeypatch.setattr(news_filter, "FLAGGED_PATH", str(tmp_path / "flagged.csv"))
    network = Mock(side_effect=AssertionError("CNA cache imports must not fetch URLs"))
    monkeypatch.setattr(requests, "get", network)
    return path, network


def write(path, records):
    path.write_text("".join(json.dumps(row) + "\n" for row in records))


def test_cna_cache_full_pipeline_and_duplicate_rerun(small_pipeline, cache):
    db, store, _ = small_pipeline
    path, network = cache
    write(path, [article()])
    first = runner.run_pipeline(["cna"], store=store)
    assert first["status"] == "completed", first["error"]
    assert first["collection_window"] is None
    baseline = counts(db)
    assert (
        baseline["documents"]
        == baseline["sentences"]
        == baseline["aspect_sentiment"]
        == 1
    )
    assert baseline["sentiment_index"] > 0
    assert first["source_results"]["cna"]["documents_inserted"] == 1
    second = runner.run_pipeline(["cna"], store=store)
    assert second["status"] == "completed"
    assert counts(db) == baseline
    assert second["source_results"]["cna"]["duplicates"] == 1
    assert second["imported_documents"] == []
    network.assert_not_called()


def test_invalid_records_are_reported_while_usable_articles_finish(
    small_pipeline, cache
):
    db, store, _ = small_pipeline
    path, network = cache
    write(
        path,
        [
            article(),
            article("noise", title="Weather report", text="Warm weather continues."),
            {"id": "failed", "error": "no text (live status 404)"},
        ],
    )
    with path.open("a") as stream:
        stream.write("{invalid JSON\n")
    inventory = cna_cache.inventory()
    assert inventory["article_count"] == 2 and inventory["invalid_count"] == 2
    run = runner.run_pipeline(["cna"], store=store)
    assert run["status"] == "completed_with_warnings"
    result = run["source_results"]["cna"]
    assert result["fetched"] == 4 and result["documents_inserted"] == 1
    assert result["filtered"] == 3 and result["invalid_records"] == 2
    assert len(run["warnings"]) == 1
    assert "2 cached CNA record(s) skipped" in run["warnings"][0]["message"]
    assert counts(db)["aspect_sentiment"] == 1
    assert len(run["stages"][1]["files"]) == 2
    network.assert_not_called()


def test_last_record_for_an_article_replaces_old_cached_failure(small_pipeline, cache):
    _, store, _ = small_pipeline
    path, _ = cache
    write(path, [{"id": "a", "error": "old timeout"}, article()])
    run = runner.run_pipeline(["cna"], store=store)
    assert run["status"] == "completed"
    result = run["source_results"]["cna"]
    assert result["fetched"] == 2 and result["documents_inserted"] == 1
    assert result["superseded_records"] == result["duplicates"] == 1
    assert result["invalid_records"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"published": "not-a-date"},
        {"url": "https://other.example/article"},
        {"text": []},
        {"title": " "},
        {"id": None},
    ],
)
def test_unusable_cache_records_fail_with_an_explanation(
    small_pipeline, cache, changes
):
    db, store, _ = small_pipeline
    path, _ = cache
    write(path, [article(**changes)])
    run = runner.run_pipeline(["cna"], store=store)
    assert run["status"] == "failed" and run["current_stage"] == "import"
    assert (
        run["source_results"]["cna"]["error"]
        == "No usable CNA articles in articles.jsonl."
    )
    assert counts(db)["documents"] == 0


def test_missing_cache_is_unavailable_and_empty_cache_is_valid(cache):
    path, network = cache
    inventory = cna_cache.inventory()
    assert not inventory["exists"] and "articles.jsonl" in inventory["error"]
    path.write_text("")
    inventory = stages.describe_sources(["cna"])[0]
    assert inventory["exists"] and inventory["article_count"] == 0
    assert inventory["kind"] == "local_cache" and inventory["pdf_count"] == 0
    network.assert_not_called()


def test_cna_keeps_full_text_when_google_already_has_its_headline(
    small_pipeline, cache
):
    from ingest.cna_archive import to_document

    db, store, _ = small_pipeline
    path, _ = cache
    row = article()
    headline = to_document(row)
    db.upsert_documents(
        [
            {
                **headline,
                "doc_id": "google-copy",
                "source": "google_news",
                "bank": "DBS",
                "body": row["title"],
            }
        ]
    )
    write(path, [row])
    run = runner.run_pipeline(["cna"], store=store)
    assert run["status"] == "completed"
    result = run["source_results"]["cna"]
    assert result["documents_inserted"] == 1
    assert result["filter_stats"]["kept_full_text_over_headline"] == 1


def test_cna_cache_is_not_limited_by_an_online_collection_window(
    small_pipeline, cache, monkeypatch
):
    from ingest import google_news

    db, store, _ = small_pipeline
    path, _ = cache
    write(path, [article()])
    monkeypatch.setattr(google_news, "iter_batches", lambda *args: iter([]))
    run = runner.run_pipeline(
        ["google_news", "cna"], store=store, since="2024-05-01", until="2024-05-02"
    )
    assert run["status"] == "completed"
    assert run["source_results"]["cna"]["documents_inserted"] == 1
    assert counts(db)["documents"] == 1


def test_committed_cna_import_survives_a_failure_and_next_run_finishes_analysis(
    small_pipeline, cache, monkeypatch
):
    db, store, _ = small_pipeline
    path, _ = cache
    write(path, [article()])
    original = db.upsert_documents

    def commit_then_fail(docs):
        original(docs)
        raise RuntimeError("Worker stopped just after commit")

    monkeypatch.setattr(db, "upsert_documents", commit_then_fail)
    failed = runner.run_pipeline(["cna"], store=store)
    assert failed["status"] == "failed"
    assert failed["source_results"]["cna"]["documents_inserted"] == 1
    assert failed["source_results"]["cna"]["status"] == "failed"
    assert len(failed["imported_documents"]) == 1
    assert counts(db)["aspect_sentiment"] == 0
    monkeypatch.setattr(db, "upsert_documents", original)
    resumed = runner.run_pipeline(["cna"], store=store)
    assert resumed["status"] == "completed"
    assert resumed["source_results"]["cna"]["duplicates"] == 1
    assert resumed["imported_documents"] == []
    assert counts(db)["aspect_sentiment"] == 1


def test_empty_cna_cache_can_run_pending_analysis(small_pipeline, cache):
    db, store, _ = small_pipeline
    path, _ = cache
    path.write_text("")
    run = runner.run_pipeline(["cna"], store=store)
    assert run["status"] == "completed"
    assert run["source_results"]["cna"]["fetched"] == 0
    assert counts(db)["documents"] == 0


@pytest.mark.parametrize(
    "published,expected",
    [
        ("2012-06-01T12:00:00+08:00", 0),
        ("2120-01-01T00:00:00+08:00", 0),
        ("2022-12-31T15:59:59Z", 0),
        ("2022-12-31T16:00:00Z", 1),
    ],
)
def test_cna_coverage_starts_in_2023_and_uses_singapore_publication_dates(
    small_pipeline, cache, published, expected
):
    db, store, _ = small_pipeline
    path, _ = cache
    write(path, [article(published=published)])
    inventory = cna_cache.inventory()
    assert inventory["article_count"] == expected
    assert inventory["excluded_date_count"] == 1 - expected
    run = runner.run_pipeline(["cna"], store=store)
    assert run["status"] == "completed"
    assert run["source_results"]["cna"]["excluded_date_records"] == 1 - expected
    assert counts(db)["documents"] == expected
