"""Offline MiniLM preparation, repair, incremental reuse and atomic persistence."""

import json
from pathlib import Path
import sqlite3
from unittest.mock import Mock

import numpy as np
import pytest

from aspects import embed_store
from chatbot import search_vectors
from config.search_model import DOWNLOAD_PATTERNS, MODEL_NAME, MODEL_REVISION, WIDTH
from docker import bootstrap, search_cache
from pipeline import stages


def database(data, rows=(("one", "DBS earnings rose."), ("two", "DBS service improved."))):
    data.mkdir(exist_ok=True)
    with sqlite3.connect(data / "plp.db") as conn:
        conn.execute("CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, text TEXT)")
        conn.executemany("INSERT INTO sentences VALUES (?, ?)", rows)


@pytest.fixture
def embed_calls(monkeypatch):
    calls = []
    def embed(texts):
        calls.append(list(texts))
        return np.ones((len(texts), WIDTH), dtype=np.float32) / np.sqrt(WIDTH)
    monkeypatch.setattr(search_vectors, "embed_sentences", embed)
    return calls


def test_old_bundle_needs_no_precomputed_search_cache(tmp_path, embed_calls):
    database(tmp_path)
    before = (tmp_path / "plp.db").read_bytes()
    result = search_cache.prepare(tmp_path)
    assert result["newly_embedded"] == 2
    assert (tmp_path / "plp.db").read_bytes() == before
    with np.load(tmp_path / "search_embeddings.npz", allow_pickle=False) as cache:
        assert cache["vectors"].shape == (2, WIDTH)
        assert set(cache["sentence_ids"]) == {"one", "two"}


def test_restart_reuses_complete_cache_without_model_loading(tmp_path, embed_calls, monkeypatch):
    database(tmp_path)
    search_cache.prepare(tmp_path)
    target = tmp_path / "search_embeddings.npz"
    before = target.read_bytes(), target.stat().st_mtime_ns
    monkeypatch.setattr(search_vectors, "update", Mock(side_effect=AssertionError("must reuse cache")))
    assert search_cache.prepare(tmp_path)["newly_embedded"] == 0
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before
    assert len(embed_calls) == 1


def test_changed_database_embeds_only_new_sentences_and_prunes_removed_ones(tmp_path, embed_calls):
    database(tmp_path)
    search_cache.prepare(tmp_path)
    with sqlite3.connect(tmp_path / "plp.db") as conn:
        conn.execute("DELETE FROM sentences WHERE sentence_id='one'")
        conn.execute("INSERT INTO sentences VALUES ('three', 'DBS expanded its services.')")
    result = search_cache.prepare(tmp_path)
    assert result == {"already_cached": 1, "newly_embedded": 1, "pruned_stale": 1, "total": 2}
    assert embed_calls[-1] == ["DBS expanded its services."]
    with np.load(tmp_path / "search_embeddings.npz") as cache:
        assert set(cache["sentence_ids"]) == {"two", "three"}


@pytest.mark.parametrize("damage", ["bad_zip", "wrong_width", "nan", "duplicate_ids"])
def test_invalid_search_cache_is_rebuilt_without_changing_database(tmp_path, embed_calls, damage):
    database(tmp_path)
    target = tmp_path / "search_embeddings.npz"
    if damage == "bad_zip":
        target.write_bytes(b"interrupted file")
    else:
        vectors = np.ones((2, 768 if damage == "wrong_width" else WIDTH), dtype=np.float32)
        if damage == "nan":
            vectors[0, 0] = np.nan
        ids = ["one", "one"] if damage == "duplicate_ids" else ["one", "two"]
        np.savez_compressed(target, sentence_ids=np.array(ids), vectors=vectors)
    before = (tmp_path / "plp.db").read_bytes()
    assert search_cache.prepare(tmp_path)["newly_embedded"] == 2
    assert (tmp_path / "plp.db").read_bytes() == before
    assert bootstrap.validate_embeddings(target, {"one", "two"}, width=WIDTH) == 2


def test_failed_rebuild_preserves_old_cache(tmp_path, monkeypatch):
    database(tmp_path)
    target = tmp_path / "search_embeddings.npz"
    target.write_bytes(b"old invalid cache")
    def fail(_):
        raise OSError("simulated interruption")
    monkeypatch.setattr(search_vectors, "embed_sentences", fail)
    with pytest.raises(OSError, match="interruption"):
        search_cache.prepare(tmp_path)
    assert target.read_bytes() == b"old invalid cache"
    assert not list(tmp_path.glob(".search-*"))


def test_cache_save_is_atomic_if_compression_fails(tmp_path, monkeypatch):
    path = tmp_path / "search.npz"
    path.write_bytes(b"previous complete cache")
    def fail(stream, **_):
        stream.write(b"incomplete output")
        raise OSError("disk full")
    monkeypatch.setattr(embed_store.np, "savez_compressed", fail)
    with pytest.raises(OSError, match="disk full"):
        embed_store._save_store(["one"], np.ones((1, WIDTH)), str(path))
    assert path.read_bytes() == b"previous complete cache"
    assert not list(tmp_path.glob(".vectors-*"))


def test_optional_search_cache_can_be_restored_from_zip(tmp_path):
    from zipfile import ZipFile
    path = tmp_path / "data.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("data/search_embeddings.npz", b"cached")
    with ZipFile(path) as archive:
        assert bootstrap.archive_members(archive) == {"search_embeddings.npz": "data/search_embeddings.npz"}


def test_search_cache_dimensions_are_independent_of_finbert(tmp_path):
    path = tmp_path / "search.npz"
    np.savez_compressed(path, sentence_ids=np.array(["one"]), vectors=np.ones((1, WIDTH)))
    assert bootstrap.validate_embeddings(path, {"one"}, width=WIDTH) == 1
    with pytest.raises(bootstrap.SetupError, match="embedding cache"):
        bootstrap.validate_embeddings(path, {"one"})


def test_search_preflight_only_checks_pinned_local_files(tmp_path, monkeypatch):
    import huggingface_hub
    for name in ("config.json", "model.safetensors", "vocab.txt"):
        (tmp_path / name).write_text("cached")
    download = Mock(return_value=str(tmp_path))
    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    assert stages._cached_search_model() == tmp_path
    download.assert_called_once_with(MODEL_NAME, revision=MODEL_REVISION,
                                     local_files_only=True, allow_patterns=DOWNLOAD_PATTERNS)


def test_search_setup_reuses_downloaded_model(monkeypatch, tmp_path):
    import huggingface_hub
    monkeypatch.setattr(stages, "_cached_search_model", lambda: tmp_path)
    download = Mock(side_effect=AssertionError("must not download"))
    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    bootstrap.prepare_search_model()
    download.assert_not_called()


def test_search_setup_downloads_missing_model_at_pinned_revision(monkeypatch, tmp_path):
    import huggingface_hub
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(stages, "_cached_search_model", Mock(side_effect=[RuntimeError("missing"), tmp_path]))
    download = Mock()
    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    bootstrap.prepare_search_model()
    download.assert_called_once_with(MODEL_NAME, revision=MODEL_REVISION,
                                    allow_patterns=DOWNLOAD_PATTERNS, token=False)


def test_search_manifest_must_match_runtime(monkeypatch, tmp_path):
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker/models.json").write_text(json.dumps({"search": {"repo": MODEL_NAME, "revision": "wrong", "width": WIDTH}}))
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    with pytest.raises(bootstrap.SetupError, match="search model manifest"):
        bootstrap.prepare_search_model()


def test_search_cache_child_runs_offline_and_propagates_failure(monkeypatch, tmp_path):
    run = Mock(return_value=Mock(returncode=1))
    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    with pytest.raises(bootstrap.SetupError, match="Search cache preparation failed"):
        bootstrap.prepare_search_cache(tmp_path)
    environment = run.call_args.kwargs["env"]
    assert environment["HF_HUB_OFFLINE"] == environment["TRANSFORMERS_OFFLINE"] == "1"
    assert environment["PLP_SEARCH_EMBEDDINGS_PATH"] == str((tmp_path / "search_embeddings.npz").resolve())
