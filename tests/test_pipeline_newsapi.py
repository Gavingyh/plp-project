"""NewsAPI credentials, bounded collection and real SQLite pipeline behaviour."""

import json
from unittest.mock import Mock

import pytest
import requests

from config import newsapi as settings
from ingest import newsapi
from pipeline import runner
from pipeline.collection import collect
from test_pipeline_runner import small_pipeline, counts  # noqa: F401

KEY = "synthetic-newsapi-test-key"
WINDOW = {"since": "2024-05-01", "until": "2024-05-03"}


def article(identity="one", **changes):
    return {
        "source": {"id": None, "name": "Example publisher"},
        "title": "DBS reports higher quarterly profit",
        "description": "DBS reported strong growth in fee income from its wealth management business.",
        "content": "Truncated content [+1000 chars]",
        "url": f"https://example.test/news/{identity}",
        "publishedAt": "2024-05-02T08:00:00Z",
        **changes,
    }


def response(articles=None, *, total=None, status=200, error=None):
    payload = (
        {"status": "error", "code": error, "message": "Provider echoed " + KEY}
        if error
        else {
            "status": "ok",
            "totalResults": total if total is not None else len(articles or []),
            "articles": articles or [],
        }
    )
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    return result


@pytest.fixture
def setup(temp_db, tmp_path, monkeypatch):
    from ingest import news_filter

    monkeypatch.setenv("NEWSAPI_KEY", KEY)
    monkeypatch.setattr(settings, "ROOT", tmp_path)
    monkeypatch.setattr(newsapi.time, "sleep", lambda _: None)
    monkeypatch.setattr(newsapi, "FAILED_WINDOWS", [])
    monkeypatch.setattr(news_filter, "FLAGGED_PATH", str(tmp_path / "flagged.csv"))
    get = Mock(return_value=response())
    monkeypatch.setattr(newsapi.requests, "get", get)
    return temp_db, get


def collect_news():
    return collect(
        "newsapi", WINDOW, report=lambda event: None, before_insert=lambda docs: None
    )


def test_key_can_come_from_local_env_file_without_being_exposed(tmp_path, monkeypatch):
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    monkeypatch.setattr(settings, "ROOT", tmp_path)
    (tmp_path / ".env").write_text("NEWSAPI_KEY=" + KEY + "\n")
    assert settings.api_key() == KEY
    monkeypatch.setenv("NEWSAPI_KEY", "override")
    assert settings.api_key() == "override"


@pytest.mark.parametrize("value", ["", " ", "your_newsapi_key_here"])
def test_blank_and_example_keys_are_unavailable(setup, monkeypatch, value):
    _, get = setup
    monkeypatch.setenv("NEWSAPI_KEY", value)
    result = collect_news()
    assert result["status"] == "failed" and "NEWSAPI_KEY" in result["error"]
    get.assert_not_called()


def test_mapping_keeps_title_and_description_not_truncated_content():
    item = article()
    doc = newsapi.to_document(item, "DBS")
    assert doc["body"] == item["title"] + ". " + item["description"]
    assert "Truncated" not in doc["body"]
    assert doc["source"] == "newsapi" and doc["source_detail"] == "Example publisher"
    assert doc["published_at"] == "2024-05-02T08:00:00+00:00"
    assert doc["doc_id"] == newsapi.to_document(item, "UOB")["doc_id"]
    assert (
        newsapi.to_document(article(publishedAt="2024-05-02T16:00:00+08:00"), "DBS")[
            "published_at"
        ]
        == doc["published_at"]
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "[Removed]"},
        {"title": None},
        {"publishedAt": None},
        {"url": "javascript:alert(1)"},
    ],
)
def test_invalid_article_fields_are_not_given_fake_publication_dates(changes):
    assert newsapi.to_document(article(**changes), "DBS") is None


def test_request_uses_header_auth_dates_and_a_fixed_page_budget(setup, monkeypatch):
    _, get = setup
    newsapi.FAILED_WINDOWS.append("stale failure")
    monkeypatch.setattr(newsapi, "PAGE_SIZE", 2)
    monkeypatch.setattr(newsapi, "MAX_PAGES", 2)
    get.return_value = response([article(), article("two")], total=100)
    result = collect_news()
    assert result["status"] == "partial" and len(get.call_args_list) == 6
    assert len(result["incomplete_windows"]) == 3
    assert "stale failure" not in result["incomplete_windows"]
    assert "shorter date range" in result["error"]
    for call in get.call_args_list:
        params = call.kwargs["params"]
        assert call.args[0] == newsapi.URL
        assert call.kwargs["allow_redirects"] is False
        assert "apiKey" not in params and call.kwargs["headers"] == {"X-Api-Key": KEY}
        assert (
            params["from"] == "2024-05-01T00:00:00Z"
            and params["to"] == "2024-05-03T00:00:00Z"
        )
        assert params["page"] in {1, 2} and params["pageSize"] == 2


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "apiKeyInvalid"),
        (403, "apiKeyDisabled"),
        (429, "apiKeyExhausted"),
        (200, "rateLimited"),
        (400, "parameterInvalid"),
    ],
)
def test_auth_quota_and_plan_errors_stop_without_retry_or_leaking_key(
    setup, status, code
):
    _, get = setup
    get.return_value = response(status=status, error=code)
    result = collect_news()
    assert result["status"] == "failed" and result["fetched"] == 0
    assert newsapi.ERROR_MESSAGES[code] in result["error"]
    assert KEY not in json.dumps(result)
    assert get.call_count == 1


def test_non_json_rate_limit_is_still_reported_as_rate_limit(setup):
    _, get = setup
    payload = response(status=429)
    payload._content = b"<html>Too many requests</html>"
    get.return_value = payload
    result = collect_news()
    assert "rate-limited" in result["error"] and get.call_count == 1


def test_partial_page_results_survive_a_later_plan_limit(setup, monkeypatch):
    db, get = setup
    monkeypatch.setattr(newsapi, "BANKS", {"DBS": ["DBS Bank"]})
    monkeypatch.setattr(newsapi, "PAGE_SIZE", 1)
    get.side_effect = [
        response([article()], total=2),
        response(status=426, error="maximumResultsReached"),
    ]
    result = collect_news()
    assert result["status"] == "partial" and result["documents_inserted"] == 1
    assert "plan result limit" in result["error"]
    with db.get_connection() as conn:
        assert conn.execute("SELECT source FROM documents").fetchone()[0] == "newsapi"


def test_network_failures_are_retried_boundedly_and_sanitised(setup, monkeypatch):
    _, get = setup
    monkeypatch.setattr(newsapi, "BANKS", {"DBS": ["DBS Bank"]})
    get.side_effect = requests.ConnectionError("Proxy echoed " + KEY)
    result = collect_news()
    assert result["status"] == "failed" and get.call_count == newsapi.MAX_ATTEMPTS
    assert KEY not in json.dumps(result) and "after retries" in result["error"]


def test_transient_server_failure_can_recover(setup):
    _, get = setup
    get.side_effect = [response(status=503), response(), response(), response()]
    assert collect_news()["status"] == "completed" and get.call_count == 4


def test_true_empty_success_and_malformed_success_are_distinct(setup):
    _, get = setup
    assert collect_news()["status"] == "completed"
    malformed = response()
    malformed._content = b'{"status":"ok"}'
    get.return_value = malformed
    result = collect_news()
    assert result["status"] == "failed" and "invalid response" in result["error"]


def test_newsapi_uses_shared_relevance_cross_source_dedup_and_exclusive_dates(
    setup, monkeypatch
):
    db, get = setup
    existing = newsapi.to_document(article(), "DBS")
    db.upsert_documents([{**existing, "source": "cna", "doc_id": "existing-cna"}])
    monkeypatch.setattr(newsapi, "BANKS", {"DBS": ["DBS Bank"]})
    get.return_value = response(
        [
            article(),
            article("noise", title="Warm weather report", description="A fine day."),
            article("old", publishedAt="2024-04-30T23:59:59Z"),
            article("upper", publishedAt="2024-05-03T00:00:00Z"),
        ]
    )
    result = collect_news()
    assert result["status"] == "completed" and result["documents_inserted"] == 0
    assert result["duplicates"] == 1 and result["filtered"] == 3


def test_newsapi_full_pipeline_then_incremental_rerun(small_pipeline, setup):
    db, store, _ = small_pipeline
    _, get = setup
    get.return_value = response([article()])
    first = runner.run_pipeline(["newsapi"], store=store, **WINDOW)
    assert first["status"] == "completed", first["error"]
    assert first["source_results"]["newsapi"]["documents_inserted"] == 1
    baseline = counts(db)
    assert baseline["documents"] == 1 and baseline["aspect_sentiment"] > 0
    assert baseline["sentiment_index"] > 0
    second = runner.run_pipeline(["newsapi"], store=store, **WINDOW)
    assert second["status"] == "completed" and not second["imported_documents"]
    assert counts(db) == baseline


def test_newsapi_failure_does_not_hide_another_sources_success(
    small_pipeline, setup, monkeypatch
):
    from ingest import google_news

    db, store, _ = small_pipeline
    _, get = setup
    get.return_value = response(status=401, error="apiKeyInvalid")
    doc = {
        **newsapi.to_document(article(), "DBS"),
        "source": "google_news",
        "doc_id": "google-one",
    }
    monkeypatch.setattr(
        google_news, "iter_batches", lambda *args: iter([("first", [doc])])
    )
    run = runner.run_pipeline(["google_news", "newsapi"], store=store, **WINDOW)
    assert run["status"] == "completed_with_warnings"
    assert run["source_results"]["newsapi"]["status"] == "failed"
    assert run["source_results"]["google_news"]["status"] == "completed"
    assert counts(db)["aspect_sentiment"] > 0 and KEY not in json.dumps(run)


def test_committed_page_is_reconciled_after_storage_failure(
    small_pipeline, setup, monkeypatch
):
    db, store, _ = small_pipeline
    _, get = setup
    get.return_value = response([article()])
    original = db.upsert_documents

    def committed_then_failed(docs):
        original(docs)
        raise RuntimeError("Disk failure after commit")

    monkeypatch.setattr(db, "upsert_documents", committed_then_failed)
    run = runner.run_pipeline(["newsapi"], store=store, **WINDOW)
    assert run["status"] == "failed" and run["current_stage"] == "import"
    assert run["source_results"]["newsapi"]["documents_inserted"] == 1
    assert len(run["imported_documents"]) == 1
    assert counts(db)["aspect_sentiment"] == 0
