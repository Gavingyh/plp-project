"""
Tests for config/logging_config.py.

The behaviours worth guarding are the ones that made this module necessary:
third-party noise gets silenced by default (transformers' progress bars and
load reports used to bury every pipeline run's real output), DEBUG turns it
back on, and file logging captures DEBUG regardless of console level so an
unattended overnight run can still be diagnosed the next morning.
"""

import logging

import pytest

from config.logging_config import (get_logger, is_debug, quiet_noisy_libraries,
                                    resolve_level, setup_logging)


@pytest.fixture(autouse=True)
def _reset_logging():
    """Each test reconfigures from scratch; restore afterwards so test order
    can't leak handler state between cases."""
    root = logging.getLogger()
    saved = list(root.handlers), root.level
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in saved[0]:
        root.addHandler(h)
    root.setLevel(saved[1])


# ---------------------------------------------------------------------------
# Level resolution
# ---------------------------------------------------------------------------

def test_default_level_is_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    assert resolve_level() == logging.INFO


def test_log_level_env_var_respected(monkeypatch):
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    assert resolve_level() == logging.WARNING


def test_debug_env_var_shorthand(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("DEBUG", "true")
    assert resolve_level() == logging.DEBUG
    assert is_debug() is True


@pytest.mark.parametrize("value,expected", [
    ("true", True), ("TRUE", True), ("1", True), ("yes", True),
    ("false", False), ("0", False), ("", False),
])
def test_debug_flag_parsing(monkeypatch, value, expected):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("DEBUG", value)
    assert is_debug() is expected


def test_explicit_argument_beats_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    assert resolve_level("DEBUG") == logging.DEBUG


def test_unknown_level_string_falls_back_to_info(monkeypatch):
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_REAL_LEVEL")
    assert resolve_level() == logging.INFO


# ---------------------------------------------------------------------------
# Handler setup
# ---------------------------------------------------------------------------

def test_setup_creates_console_and_file_handlers(tmp_path, monkeypatch):
    monkeypatch.delenv("LOG_FILE", raising=False)
    log_file = tmp_path / "test.log"
    root = setup_logging(level="INFO", log_file=str(log_file), force=True)
    kinds = [type(h).__name__ for h in root.handlers]
    assert "StreamHandler" in kinds
    assert "RotatingFileHandler" in kinds


def test_file_captures_debug_even_when_console_is_info(tmp_path, monkeypatch):
    """The point of file logging here: a 3am failure is still diagnosable at
    9am, even though the console was only showing INFO at the time."""
    monkeypatch.delenv("LOG_FILE", raising=False)
    log_file = tmp_path / "test.log"
    setup_logging(level="INFO", log_file=str(log_file), force=True)
    get_logger("test.module").debug("a debug detail")
    logging.shutdown()
    assert "a debug detail" in log_file.read_text()


def test_file_logging_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("LOG_FILE", raising=False)
    root = setup_logging(level="INFO", log_file="none", force=True)
    assert not any(type(h).__name__ == "RotatingFileHandler" for h in root.handlers)


def test_setup_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.delenv("LOG_FILE", raising=False)
    log_file = tmp_path / "test.log"
    root = setup_logging(level="INFO", log_file=str(log_file), force=True)
    before = len(root.handlers)
    setup_logging(level="INFO", log_file=str(log_file))  # no force - should no-op
    assert len(root.handlers) == before


def test_unwritable_log_path_does_not_raise(monkeypatch):
    """A bad log path must degrade to console-only, never take down the run."""
    monkeypatch.delenv("LOG_FILE", raising=False)
    root = setup_logging(level="INFO", log_file="/nonexistent-root-dir/x/y.log", force=True)
    assert any(type(h).__name__ == "StreamHandler" for h in root.handlers)


# ---------------------------------------------------------------------------
# Third-party noise suppression - the original motivation
# ---------------------------------------------------------------------------

def test_noisy_libraries_pinned_to_warning_or_quieter():
    quiet_noisy_libraries(debug=False)
    # transformers ends up at ERROR rather than WARNING: the generic loop sets
    # WARNING, then set_verbosity_error() pushes it further,
    # because its INFO/WARNING output (weight-loading reports) is exactly the
    # noise this module exists to remove. So assert "at least WARNING", not
    # an exact level.
    assert logging.getLogger("transformers").level >= logging.WARNING
    assert logging.getLogger("urllib3").level >= logging.WARNING
    assert logging.getLogger("httpx").level >= logging.WARNING


def test_debug_mode_leaves_third_party_alone():
    """If you've asked for DEBUG you want the library chatter too - that's the
    whole point of turning it on."""
    for name in ("transformers", "urllib3"):
        logging.getLogger(name).setLevel(logging.NOTSET)
    quiet_noisy_libraries(debug=True)
    assert logging.getLogger("transformers").level == logging.NOTSET
    assert logging.getLogger("urllib3").level == logging.NOTSET


def test_get_logger_has_no_import_side_effects():
    """get_logger must not configure logging - entry points do that
    explicitly, so importing a library module stays inert."""
    logger = get_logger("some.module.name")
    assert logger.name == "some.module.name"
    assert not logger.handlers
