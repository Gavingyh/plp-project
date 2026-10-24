"""First-install, interrupted-install and restart guarantees for Docker setup."""

import hashlib
import io
import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import numpy as np
import pytest

from docker import bootstrap

VERSION = "docker-test-v1"


@pytest.fixture(autouse=True)
def isolated_setup_configuration(monkeypatch):
    for name in ("HF_TOKEN", "PLP_DATA_URL", "PLP_DATA_TOKEN", "PLP_DATA_SHA256"):
        monkeypatch.delenv(name, raising=False)


def database_bytes(tmp_path, version=VERSION, ids=("one", "two")):
    path = tmp_path / "source.db"
    with sqlite3.connect(path) as conn:
        for table in ("documents", "sentence_aspects", "analyst_consensus"):
            conn.execute(f"CREATE TABLE {table} (id TEXT)")
        conn.execute("CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO sentences VALUES (?)", [(i,) for i in ids])
        for table in ("aspect_sentiment", "sentiment_index"):
            conn.execute(f"CREATE TABLE {table} (model_version TEXT)")
            conn.execute(f"INSERT INTO {table} VALUES (?)", (version,))
    return path.read_bytes()


def embeddings(ids=("one", "two")):
    stream = io.BytesIO()
    np.savez_compressed(stream, sentence_ids=np.array(ids), vectors=np.zeros((len(ids), 768), dtype=np.float32))
    return stream.getvalue()


def bundle(tmp_path, prefix="data/", version=VERSION, cache_ids=("one", "two"), extras=None):
    data = tmp_path / "target"
    data.mkdir()
    with ZipFile(data / "data.zip", "w") as archive:
        archive.writestr(prefix + "plp.db", database_bytes(tmp_path, version))
        archive.writestr(prefix + "sentence_embeddings.npz", embeddings(cache_ids))
        archive.writestr(prefix + "cna/articles.jsonl", '{"title":"test"}\n')
        archive.writestr(prefix + "aspect_llm/test.jsonl", '{}\n')
        archive.writestr(prefix + "archive/old.db", "not a runtime file")
        archive.writestr(prefix + "preview/scores.jsonl", "not a runtime file")
        for name, content in (extras or {}).items():
            archive.writestr(name, content)
    return data


@pytest.mark.parametrize("prefix", ["data/", ""])
def test_restores_only_valid_runtime_files(tmp_path, prefix):
    data = bundle(tmp_path, prefix)
    result = bootstrap.prepare_data(data, VERSION)
    assert result["sentences"] == result["embeddings"] == 2
    assert (data / "plp.db").is_file()
    assert (data / "cna/articles.jsonl").is_file()
    assert (data / "aspect_llm/test.jsonl").is_file()
    assert not (data / "data").exists()
    assert not (data / "archive").exists()
    assert not (data / "preview/scores.jsonl").exists()


def test_restart_preserves_modified_database_and_cache_files(tmp_path):
    data = bundle(tmp_path)
    bootstrap.prepare_data(data, VERSION)
    with sqlite3.connect(data / "plp.db") as conn:
        conn.execute("INSERT INTO sentences VALUES ('new-sentence')")
    (data / "cna/articles.jsonl").write_text("new local data")
    before = (data / "plp.db").read_bytes()
    result = bootstrap.prepare_data(data, VERSION)
    assert result["restored"] == []
    assert result["sentences"] == 3
    assert (data / "plp.db").read_bytes() == before
    assert (data / "cna/articles.jsonl").read_text() == "new local data"


@pytest.mark.parametrize("extra", ["../outside", "/absolute", "data/../outside", "data\\outside"])
def test_unsafe_archive_does_not_publish_any_data(tmp_path, extra):
    data = bundle(tmp_path, extras={extra: "bad"})
    with pytest.raises(bootstrap.SetupError, match="unsafe"):
        bootstrap.prepare_data(data, VERSION)
    assert not (data / "plp.db").exists()
    assert not list(data.glob(".setup-*"))


def test_duplicate_flat_and_prefixed_names_are_rejected(tmp_path):
    data = bundle(tmp_path, extras={"plp.db": "ambiguous"})
    with pytest.raises(bootstrap.SetupError, match="duplicate"):
        bootstrap.prepare_data(data, VERSION)


def test_old_model_version_is_not_published(tmp_path):
    data = bundle(tmp_path, version="wrong-version")
    with pytest.raises(bootstrap.SetupError, match="matching team dataset"):
        bootstrap.prepare_data(data, VERSION)
    assert not (data / "plp.db").exists()


def test_cache_from_other_database_is_not_published(tmp_path):
    data = bundle(tmp_path, cache_ids=("different",))
    with pytest.raises(bootstrap.SetupError, match="another database"):
        bootstrap.prepare_data(data, VERSION)
    assert not (data / "plp.db").exists()


def test_existing_database_is_not_replaced_to_match_zip(tmp_path):
    data = bundle(tmp_path)
    bootstrap.prepare_data(data, VERSION)
    with sqlite3.connect(data / "plp.db") as conn:
        conn.execute("DELETE FROM sentences WHERE sentence_id='one'")
    (data / "sentence_embeddings.npz").unlink()
    before = (data / "plp.db").read_bytes()
    with pytest.raises(bootstrap.SetupError, match="another database"):
        bootstrap.prepare_data(data, VERSION)
    assert (data / "plp.db").read_bytes() == before
    assert not (data / "sentence_embeddings.npz").exists()


def test_missing_zip_explains_location(tmp_path, monkeypatch):
    monkeypatch.delenv("PLP_DATA_URL", raising=False)
    with pytest.raises(bootstrap.SetupError, match="data/data.zip"):
        bootstrap.prepare_data(tmp_path, VERSION)


def test_valid_existing_install_does_not_require_the_zip(tmp_path):
    data = bundle(tmp_path)
    bootstrap.prepare_data(data, VERSION)
    (data / "data.zip").unlink()
    assert bootstrap.prepare_data(data, VERSION)["restored"] == []


def test_bad_zip_and_hash_have_actionable_errors(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "data.zip").write_text("a download login page")
    with pytest.raises(bootstrap.SetupError, match="damaged or is not a ZIP"):
        bootstrap.prepare_data(data, VERSION)
    monkeypatch.setenv("PLP_DATA_SHA256", "0" * 64)
    with pytest.raises(bootstrap.SetupError, match="SHA-256"):
        bootstrap.prepare_data(data, VERSION)


def test_successful_download_is_atomic_and_does_not_log_credentials(tmp_path, monkeypatch, capsys):
    import requests

    data = bundle(tmp_path)
    payload = (data / "data.zip").read_bytes()
    response = Mock()
    response.iter_content.return_value = [payload]
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)
    target = tmp_path / "download/data.zip"
    bootstrap.download_archive(target, "https://example.test/data?private=hidden", hashlib.sha256(payload).hexdigest(), "secret-token")
    assert target.read_bytes() == payload
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer secret-token"}
    assert "secret-token" not in capsys.readouterr().out
    assert not list(target.parent.glob(".bundle-*"))


def test_failed_download_does_not_leave_archive_or_partial_file(tmp_path, monkeypatch):
    import requests

    monkeypatch.setattr(requests, "get", Mock(side_effect=requests.ConnectionError("private URL")))
    target = tmp_path / "data.zip"
    with pytest.raises(bootstrap.SetupError, match="Dataset download failed"):
        bootstrap.download_archive(target, "https://example.test/data")
    assert not target.exists()
    assert not list(tmp_path.glob(".bundle-*"))


def test_checkpoint_checks_all_files_and_weight_hash(tmp_path):
    for name in bootstrap.MODEL_FILES:
        (tmp_path / name).write_text("{}" if name.endswith(".json") else "weights")
    expected = bootstrap.sha256(tmp_path / "model.safetensors")
    assert bootstrap.valid_checkpoint(tmp_path, expected)
    (tmp_path / "model.safetensors").write_text("damaged")
    assert not bootstrap.valid_checkpoint(tmp_path, expected)


def test_verified_model_cache_is_reused_without_network(tmp_path, monkeypatch, served_version):
    import huggingface_hub
    from pipeline import stages
    from config.model_version import BASE_MODEL_DOWNLOAD_PATTERNS

    for name in ("config.json", "pytorch_model.bin", "vocab.txt"):
        (tmp_path / name).write_text("cached")
    snapshot = Mock(return_value=str(tmp_path))
    monkeypatch.setattr(huggingface_hub, "snapshot_download", snapshot)
    monkeypatch.setattr(bootstrap, "valid_checkpoint", lambda *_: True)
    monkeypatch.setattr(stages, "_cached_finbert", lambda: tmp_path)
    monkeypatch.setenv("FINBERT_REVISION", "pinned-revision")
    bootstrap.prepare_models(tmp_path)
    snapshot.assert_called_once_with(
        "ProsusAI/finbert", revision="pinned-revision", local_files_only=True,
        allow_patterns=BASE_MODEL_DOWNLOAD_PATTERNS, token=False,
    )


def test_model_manifest_must_match_the_served_version(tmp_path):
    # conftest serves the base-model fixture; the Docker manifest is fine-tuned.
    with pytest.raises(bootstrap.SetupError, match="does not match the served"):
        bootstrap.prepare_models(tmp_path)


def test_shared_ollama_model_is_pulled_once(tmp_path, monkeypatch):
    import requests

    monkeypatch.setattr(bootstrap, "ollama_models", lambda: ["same:8b", "same:8b"])
    listing = Mock()
    listing.json.return_value = {"models": []}
    stream = Mock()
    stream.__enter__ = Mock(return_value=stream)
    stream.__exit__ = Mock(return_value=False)
    stream.iter_lines.return_value = [json.dumps({"status": "success"}).encode()]
    monkeypatch.setattr(requests, "get", Mock(return_value=listing))
    post = Mock(return_value=stream)
    monkeypatch.setattr(requests, "post", post)
    bootstrap.prepare_ollama("http://ollama:11434")
    assert post.call_count == 1


def test_ollama_incomplete_download_fails_setup(monkeypatch):
    import requests

    monkeypatch.setattr(bootstrap, "ollama_models", lambda: ["model:8b"])
    listing = Mock()
    listing.json.return_value = {"models": []}
    stream = Mock()
    stream.__enter__ = Mock(return_value=stream)
    stream.__exit__ = Mock(return_value=False)
    stream.iter_lines.return_value = [json.dumps({"status": "pulling manifest"}).encode()]
    monkeypatch.setattr(requests, "get", Mock(return_value=listing))
    monkeypatch.setattr(requests, "post", Mock(return_value=stream))
    with pytest.raises(bootstrap.SetupError, match="before completion"):
        bootstrap.prepare_ollama("http://ollama:11434")


def test_intent_warmup_uses_only_the_local_classifier(monkeypatch):
    from chatbot import intent

    classify = Mock(return_value="in_scope")
    monkeypatch.setattr(intent, "classify_intent", classify)
    bootstrap.warm_intent()
    classify.assert_called_once_with("What is the overall sentiment on DBS?")


def test_failed_intent_warmup_does_not_advertise_readiness(monkeypatch):
    from chatbot import intent

    monkeypatch.setattr(intent, "classify_intent", lambda *_: None)
    with pytest.raises(bootstrap.SetupError, match="warm-up failed"):
        bootstrap.warm_intent()
