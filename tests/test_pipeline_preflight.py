"""Prerequisites fail before imports; PDF reporting preserves the existing API."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from pipeline import runner, stages
from pipeline.jobs import RunStore


@pytest.fixture
def prerequisites(temp_db, tmp_path, monkeypatch):
    from config import aspect_taxonomy
    from ingest import earnings_extract, sgx_research_extract
    from pipeline import cna_cache

    monkeypatch.setattr(cna_cache, "CACHE_PATH", tmp_path / "cna/articles.jsonl")

    for source, module in (
        ("earnings", earnings_extract),
        ("sgx_research", sgx_research_extract),
    ):
        folder = tmp_path / source
        folder.mkdir()
        monkeypatch.setattr(module, "PDF_DIR", str(folder))
    monkeypatch.setattr(stages.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(stages, "_cached_finbert", lambda: tmp_path / "cached-finbert")
    monkeypatch.setattr(stages, "_cached_search_model", lambda: tmp_path / "cached-search")
    monkeypatch.setattr(
        aspect_taxonomy, "load", lambda: {"assignment_method": "centroid"}
    )
    return temp_db, RunStore(tmp_path / "jobs")


def test_preflight_rejects_missing_folder_before_any_import(prerequisites, monkeypatch):
    from ingest import earnings_extract

    db, store = prerequisites
    monkeypatch.setattr(earnings_extract, "PDF_DIR", "/a/nonexistent/source")
    import_call = Mock(side_effect=AssertionError("import must not start"))
    monkeypatch.setattr(stages, "import_sources", import_call)
    before = Path(db.DB_PATH).read_bytes()
    result = runner.run_pipeline(["earnings"], store=store)
    assert result["status"] == "failed" and result["current_stage"] == "preflight"
    assert "Source folder is missing" in result["error"]
    import_call.assert_not_called()
    assert Path(db.DB_PATH).read_bytes() == before


def test_missing_database_is_not_silently_created(prerequisites, monkeypatch, tmp_path):
    db, store = prerequisites
    missing = tmp_path / "typo.db"
    monkeypatch.setattr(db, "DB_PATH", str(missing))
    result = runner.run_pipeline(["earnings"], store=store)
    assert result["status"] == "failed" and result["current_stage"] == "preflight"
    assert not missing.exists()


def test_missing_cna_cache_fails_preflight_before_import(prerequisites, monkeypatch):
    _, store = prerequisites
    importer = Mock(side_effect=AssertionError("must not import"))
    monkeypatch.setattr(stages, "import_sources", importer)
    run = runner.run_pipeline(["cna"], store=store)
    assert run["current_stage"] == "preflight" and run["status"] == "failed"
    assert "articles.jsonl" in run["error"]
    importer.assert_not_called()


@pytest.mark.parametrize("key", ["", "your_newsapi_key_here"])
def test_missing_newsapi_key_fails_before_import_without_affecting_other_sources(
    prerequisites, monkeypatch, key
):
    _, store = prerequisites
    monkeypatch.setenv("NEWSAPI_KEY", key)
    importer = Mock(side_effect=AssertionError("must not import"))
    monkeypatch.setattr(stages, "import_sources", importer)
    option = stages.describe_sources(["newsapi"])[0]
    assert not option["exists"] and "NEWSAPI_KEY" in option["error"]
    assert stages.describe_sources(["google_news"])[0]["exists"]
    run = runner.run_pipeline(["newsapi"], store=store)
    assert run["status"] == "failed" and run["current_stage"] == "preflight"
    assert "NewsAPI unavailable" in run["error"]
    importer.assert_not_called()


def test_cna_cache_does_not_require_pdf_or_article_extraction_dependencies(
    prerequisites, monkeypatch
):
    from pipeline import cna_cache

    cna_cache.CACHE_PATH.parent.mkdir()
    cna_cache.CACHE_PATH.write_text("")
    monkeypatch.setattr(
        stages.importlib.util,
        "find_spec",
        lambda name: (
            None if name in {"pdfplumber", "trafilatura", "feedparser"} else object()
        ),
    )
    assert stages.preflight(["cna"])["sources"][0]["kind"] == "local_cache"


def test_missing_spacy_model_is_reported_before_import(prerequisites, monkeypatch):
    _, store = prerequisites
    monkeypatch.setattr(
        stages.importlib.util,
        "find_spec",
        lambda name: None if name == "en_core_web_sm" else object(),
    )
    result = runner.run_pipeline(["earnings"], store=store)
    assert result["status"] == "failed"
    assert "Missing dependencies: en_core_web_sm" in result["error"]
    assert ".venv-plp/bin/python3 -m spacy download en_core_web_sm" in result["error"]
    assert result["import_candidates"] == []


def test_selected_finetuned_models_are_required_before_import(
    prerequisites, monkeypatch, tmp_path
):
    from config import model_version

    _, store = prerequisites
    monkeypatch.setattr(model_version, "MODEL_VERSION", "test-finetuned")
    monkeypatch.setattr(
        model_version,
        "FINETUNED",
        {"test-finetuned": {"models": [str(tmp_path / "missing-seed")]}},
    )
    result = runner.run_pipeline(["earnings"], store=store)
    assert result["status"] == "failed"
    assert (
        "Missing model files" in result["error"]
        and "model.safetensors" in result["error"]
    )
    assert result["import_candidates"] == []


def test_preflight_uses_configured_topic_model(prerequisites, monkeypatch):
    from config import aspect_taxonomy

    _, _ = prerequisites
    monkeypatch.setattr(
        aspect_taxonomy,
        "load",
        lambda: {"assignment_method": "llm", "llm_model": "topic-model:8b"},
    )
    checker = Mock()
    monkeypatch.setattr(stages, "_check_ollama", checker)
    result = stages.preflight(["earnings"])
    checker.assert_called_once_with("topic-model:8b")
    assert result["assignment_method"] == "llm"


def test_preflight_only_inspects_the_selected_source_folder(prerequisites, monkeypatch):
    original = stages.source_module

    def selected_only(source):
        assert source == "earnings", "An unselected source was inspected"
        return original(source)

    monkeypatch.setattr(stages, "source_module", selected_only)
    assert stages.preflight(["earnings"])["sources"][0]["key"] == "earnings"


def test_missing_ollama_stops_the_job_before_import(prerequisites, monkeypatch):
    from config import aspect_taxonomy
    import requests

    _, store = prerequisites
    monkeypatch.setattr(
        aspect_taxonomy,
        "load",
        lambda: {"assignment_method": "llm", "llm_model": "topic-model:8b"},
    )
    monkeypatch.setattr(requests, "get", Mock(side_effect=requests.ConnectionError()))
    result = runner.run_pipeline(["earnings"], store=store)
    assert "Start Ollama" in result["error"] and result["status"] == "failed"
    assert result["import_candidates"] == []


@pytest.mark.parametrize(
    "names,ok", [(["topic-model:8b"], True), (["other:8b"], False)]
)
def test_ollama_reachable_but_wrong_model_is_not_enough(monkeypatch, names, ok):
    import requests

    response = Mock()
    response.json.return_value = {"models": [{"name": name} for name in names]}
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434/")
    if ok:
        stages._check_ollama("topic-model:8b")
    else:
        with pytest.raises(RuntimeError, match="topic model"):
            stages._check_ollama("topic-model:8b")
    get.assert_called_once_with("http://ollama:11434/api/tags", timeout=(3, 5))


def test_base_model_cache_check_never_downloads(monkeypatch, tmp_path):
    import huggingface_hub

    snapshot = Mock(return_value=str(tmp_path))
    monkeypatch.setattr(huggingface_hub, "snapshot_download", snapshot)
    with pytest.raises(RuntimeError, match="incomplete"):
        stages._cached_finbert()
    for name in ("config.json", "model.safetensors", "vocab.txt"):
        (tmp_path / name).write_text("fixture")
    assert stages._cached_finbert() == tmp_path
    from config.model_version import BASE_MODEL_DOWNLOAD_PATTERNS
    snapshot.assert_called_with("ProsusAI/finbert", local_files_only=True,
                                allow_patterns=BASE_MODEL_DOWNLOAD_PATTERNS)


def test_inventory_counts_supported_pdf_locations(prerequisites):
    from ingest import earnings_extract, sgx_research_extract

    earnings = Path(earnings_extract.PDF_DIR)
    (earnings / "DBS").mkdir()
    (earnings / "DBS" / "report.PDF").touch()
    (earnings / "misplaced-at-root.pdf").touch()
    (earnings / "DBS" / "not-a-pdf.txt").touch()
    (Path(sgx_research_extract.PDF_DIR) / "report.pdf").touch()
    assert {item["key"]: item["pdf_count"] for item in stages.describe_sources()} == {
        "earnings": 1,
        "sgx_research": 1,
        "google_news": 0,
        "arctic_shift": 0,
        "cna": 0,
        "newsapi": 0,
    }


def test_broker_pull_skips_known_files_and_reports_failure_skip_and_success(
    prerequisites, monkeypatch
):
    from ingest import sgx_research_extract as module
    from ingest.db import make_doc_id

    folder = Path(module.PDF_DIR)
    for name in ("known.pdf", "broken.pdf", "empty.pdf", "good.pdf"):
        (folder / name).touch()
    calls = []

    def build(path):
        name = Path(path).name
        calls.append(name)
        if name == "broken.pdf":
            raise ValueError("Corrupt PDF")
        if name == "empty.pdf":
            return None
        return {
            "doc_id": make_doc_id("sgx_research", name),
            "bank": "DBS",
            "body": "Fixture prose",
            "published_at": "2026-01-01",
            "raw": {"read_by": "text"},
        }

    monkeypatch.setattr(module, "build_document", build)
    events = []
    docs = module.pull(
        skip_doc_ids={make_doc_id("sgx_research", "known.pdf")}, report=events.append
    )
    assert len(docs) == 1 and "known.pdf" not in calls
    assert {event["file"]: event["status"] for event in events} == {
        "known.pdf": "already_stored",
        "broken.pdf": "failed",
        "empty.pdf": "skipped",
        "good.pdf": "extracted",
    }
    # The pre-existing no-argument contract still returns document dictionaries.
    assert isinstance(module.pull(), list)


def test_cli_exit_status_and_json_do_not_require_real_pipeline(monkeypatch, capsys):
    import config.logging_config

    monkeypatch.setattr(config.logging_config, "setup_logging", lambda: None)
    for status, code in (
        ("completed", 0),
        ("completed_with_warnings", 0),
        ("failed", 1),
    ):
        monkeypatch.setattr(
            runner, "run_pipeline", lambda *a, _status=status, **k: {"status": _status}
        )
        assert runner.main(["--sources", "earnings"]) == code
        assert '"status"' in capsys.readouterr().out
    from pipeline.jobs import PipelineBusy

    monkeypatch.setattr(
        runner, "run_pipeline", Mock(side_effect=PipelineBusy("Already running"))
    )
    assert runner.main(["--sources", "earnings"]) == 3


def test_online_only_preflight_does_not_require_pdf_folders_or_pdf_dependencies(
    prerequisites, monkeypatch
):
    from ingest import earnings_extract, sgx_research_extract

    monkeypatch.setattr(earnings_extract, "PDF_DIR", "/missing/earnings")
    monkeypatch.setattr(sgx_research_extract, "PDF_DIR", "/missing/research")
    monkeypatch.setattr(
        stages.importlib.util,
        "find_spec",
        lambda name: (
            None
            if name in {"pdfplumber", "pypdfium2", "rapidocr_onnxruntime", "wordninja"}
            else object()
        ),
    )
    result = stages.preflight(["google_news", "arctic_shift"])
    assert {row["kind"] for row in result["sources"]} == {"online"}


def test_missing_search_model_fails_before_import(prerequisites, monkeypatch):
    _, store = prerequisites
    def missing():
        raise RuntimeError("MiniLM search model is not cached locally")
    monkeypatch.setattr(stages, "_cached_search_model", missing)
    importer = Mock(side_effect=AssertionError("must not import"))
    monkeypatch.setattr(stages, "import_sources", importer)
    result = runner.run_pipeline(["earnings"], store=store)
    assert result["status"] == "failed" and result["current_stage"] == "preflight"
    assert "MiniLM" in result["error"]
    importer.assert_not_called()
