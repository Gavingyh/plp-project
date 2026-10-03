"""Tests for chatbot/settings.py: config/chatbot.yaml defaults, environment overrides."""

import pytest
import yaml

from chatbot import settings


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
    assert settings.get("models.ollama") == "llama3.2:3b"
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
    assert settings.get("models.ollama") == "qwen3:4b"


def test_environment_values_take_the_default_type(monkeypatch):
    monkeypatch.setenv("CHATBOT_TEMPERATURE", "0.5")
    monkeypatch.setenv("CHATBOT_ASPECT_QUERY", "yes")
    monkeypatch.setenv("OLLAMA_THINK", "false")
    assert settings.get("temperature") == 0.5 and settings.get("aspect_query") is True
    assert settings.get("ollama_think") is False


def test_a_second_variable_name_is_read_and_a_bad_value_falls_back(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_CHAT_MODEL", "gemini-x")
    assert settings.get("models.gemini") == "gemini-x"
    monkeypatch.setenv("CHATBOT_TEMPERATURE", "warm")
    assert settings.get("temperature") == 0.2


def test_an_unknown_setting_is_an_error():
    with pytest.raises(KeyError):
        settings.get("models")          # a group, not a setting
