"""Tests for chatbot/settings.py: config/chatbot.yaml defaults, environment overrides."""

import os

import pytest
import yaml

from chatbot import settings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _paths(node, prefix=""):
    for k, v in node.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict) and "value" in v:
            yield path
        elif isinstance(v, dict):
            yield from _paths(v, path + ".")


def test_every_setting_in_the_file_can_be_read():
    with open(settings.CONFIG_PATH) as f:
        paths = list(_paths(yaml.safe_load(f)))
    assert len(paths) > 20
    for p in paths:
        settings.get(p)


def test_the_default_is_used_unless_the_environment_sets_one(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert settings.get("models.ollama") == "llama3.1:8b"            # the demo model
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
    assert settings.get("models.ollama") == "qwen3:4b"


def test_environment_values_take_the_default_type(monkeypatch):
    monkeypatch.setenv("CHATBOT_TEMPERATURE", "0.5")
    monkeypatch.setenv("CHATBOT_ASPECT_QUERY", "yes")
    monkeypatch.setenv("OLLAMA_THINK", "false")
    assert settings.get("temperature") == 0.5 and settings.get("aspect_query") is True
    assert settings.get("ollama_think") is False


def test_a_bad_environment_value_falls_back(monkeypatch):
    monkeypatch.setenv("CHATBOT_TEMPERATURE", "warm")
    assert settings.get("temperature") == 0.2


def test_an_unknown_setting_is_an_error():
    with pytest.raises(KeyError):
        settings.get("models")          # a group, not a setting


def test_the_embeddings_are_read_once_until_the_file_changes(tmp_path, monkeypatch):
    import os
    import numpy as np
    import aspects.embed_store as es
    path = tmp_path / "emb.npz"
    np.savez_compressed(path, sentence_ids=np.array(["a"]), vectors=np.ones((1, 768), dtype=np.float32))
    monkeypatch.setattr(es, "STORE_PATH", str(path))
    monkeypatch.setattr(es, "_search_cache", {})
    first = es.load_for_search()
    assert es.load_for_search() is first                     # no second read
    np.savez_compressed(path, sentence_ids=np.array(["a", "b"]), vectors=np.ones((2, 768), dtype=np.float32))
    os.utime(path, (os.path.getmtime(path) + 5,) * 2)
    assert es.load_for_search()[0] == ["a", "b"]             # a changed file is read again


def test_the_prompt_names_every_tool_that_returns_figures_and_the_floor():
    from chatbot.prompts import SYSTEM_PROMPT
    from chatbot.tools import MIN_VOLUME_FOR_SCORE, TOOL_SCHEMAS
    for t in TOOL_SCHEMAS:
        if t["name"] != "search_evidence":
            assert t["name"] in SYSTEM_PROMPT.split("2. Every")[0]
    assert f"n is below {MIN_VOLUME_FOR_SCORE}" in SYSTEM_PROMPT


def test_database_and_embeddings_paths_can_be_overridden(tmp_path):
    # PLP_DB_PATH / PLP_EMBEDDINGS_PATH let the API serve a copy (a rescored one,
    # say) without touching data/plp.db. Checked in a fresh interpreter, so
    # this process's modules keep their paths.
    import subprocess
    import sys
    env = {**os.environ, "PLP_DB_PATH": str(tmp_path / "copy.db"), "PLP_EMBEDDINGS_PATH": str(tmp_path / "e.npz")}
    out = subprocess.run([sys.executable, "-c", "import ingest.db, aspects.embed_store as e; "
                          "print(ingest.db.DB_PATH); print(ingest.db.DEFAULT_DB_PATH); print(e.STORE_PATH)"],
                         env=env, capture_output=True, text=True, check=True, cwd=ROOT).stdout.split("\n")
    assert out[0] == str(tmp_path / "copy.db")
    assert out[1].endswith(os.path.join("data", "plp.db"))
    assert out[2] == str(tmp_path / "e.npz")



def test_a_bare_database_file_name_is_taken_from_the_working_directory(tmp_path):
    # PLP_DB_PATH=copy.db once made os.makedirs('') fail on every connection.
    import subprocess
    import sys
    env = {**os.environ, "PLP_DB_PATH": "copy.db"}
    out = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {ROOT!r}); import ingest.db; "
                          "c = ingest.db.get_connection(); c.close(); print(ingest.db.DB_PATH)"],
                         env=env, capture_output=True, text=True, check=True, cwd=tmp_path).stdout.strip()
    assert out == os.path.realpath(tmp_path / "copy.db") or out == str(tmp_path / "copy.db")
