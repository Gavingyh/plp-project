"""
Central logging setup for the project.

Purpose:

1. Suppress third-party noise. transformers and huggingface_hub emit
   weight-loading progress bars, model load reports and hub warnings that
   bury pipeline output. quiet_noisy_libraries() silences these at the
   source; DEBUG mode restores them.

2. Preserve a record of unattended runs. The overnight Reddit backfill and
   the multi-minute embedding and scoring steps write to a rotating file
   (data/logs/plp.log) at DEBUG level regardless of console level, so a
   failure that happens overnight remains diagnosable afterwards.

3. Allow verbosity changes without code edits, via LOG_LEVEL or DEBUG.

Logs are written to stderr so that stdout carries only a program's real
output: `python -m chatbot.agent "..."` writes its answer to stdout and its
tool-call trace to stderr, allowing the answer to be piped on its own.

CONFIG (env vars, all optional; .env is loaded automatically):
  LOG_LEVEL   DEBUG | INFO | WARNING | ERROR   (default INFO)
  DEBUG       "true"/"1"/"yes" - shorthand for LOG_LEVEL=DEBUG, and also
              stops third-party libraries being silenced
  LOG_FILE    path to the log file (default data/logs/plp.log);
              set to "" or "none" to disable file logging entirely

USAGE:
  # once, at an entry point (a __main__ block, the API, the dashboard):
  from config.logging_config import setup_logging
  setup_logging()

  # in every module:
  from config.logging_config import get_logger
  logger = get_logger(__name__)
  logger.info("...")
"""

import logging
import logging.handlers
import os
import sys
import warnings

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DEFAULT_LOG_FILE = os.path.join(BASE_DIR, "data", "logs", "plp.log")
_MAX_BYTES = 5 * 1024 * 1024  # 5MB per file
_BACKUP_COUNT = 3

# Chatty libraries pinned to WARNING unless DEBUG is on. transformers and
# huggingface_hub need their own APIs on top of this (see
# quiet_noisy_libraries) because they don't route everything through the
# stdlib logging module.
_NOISY_LIBRARIES = [
    "transformers", "huggingface_hub", "urllib3", "requests", "httpx", "httpcore",
    "numba", "matplotlib", "asyncio", "filelock", "PIL", "pdfminer", "fsspec",
]

_CONSOLE_FORMAT = "%(levelname)-7s %(name)-28s %(message)s"
_FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)-28s %(message)s"

_configured = False


def is_debug() -> bool:
    if os.environ.get("DEBUG", "").strip().lower() in ("true", "1", "yes"):
        return True
    return os.environ.get("LOG_LEVEL", "").strip().upper() == "DEBUG"


def resolve_level(level: str | int | None = None) -> int:
    """Explicit argument wins, then DEBUG=true, then LOG_LEVEL, else INFO."""
    if level is not None:
        if isinstance(level, int):
            return level
        return getattr(logging, str(level).strip().upper(), logging.INFO)
    if is_debug():
        return logging.DEBUG
    return getattr(logging, os.environ.get("LOG_LEVEL", "INFO").strip().upper(), logging.INFO)


def quiet_noisy_libraries(debug: bool = False) -> None:
    """Silences the third-party output that otherwise buries real messages.

    Skipped entirely when debug=True - if you've turned on DEBUG you probably
    want transformers' loading details and urllib3's connection chatter too.
    """
    if debug:
        return

    for name in _NOISY_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)

    # transformers and huggingface_hub print progress bars and load reports
    # outside the stdlib logging module, so setting a logger level isn't
    # enough - they need their own verbosity APIs.
    try:
        from transformers.utils import logging as hf_logging
        hf_logging.set_verbosity_error()
        hf_logging.disable_progress_bar()
    except Exception:  # transformers not installed / API moved - not fatal
        pass
    try:
        from huggingface_hub.utils import logging as hub_logging
        hub_logging.set_verbosity_error()
    except Exception:
        pass

    # Known-harmless warnings seen on every run: MPS doesn't support
    # pin_memory (torch), and vaderSentiment still uses codecs.open.
    warnings.filterwarnings("ignore", message=".*pin_memory.*")
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="vaderSentiment")


def setup_logging(level: str | int | None = None, log_file: str | None = None,
                   force: bool = False) -> logging.Logger:
    """Configures root logging. Idempotent - safe to call from several entry
    points; pass force=True to reconfigure (used by tests)."""
    global _configured
    root = logging.getLogger()
    if _configured and not force:
        return root
    if force:
        for handler in list(root.handlers):
            root.removeHandler(handler)

    resolved = resolve_level(level)
    debug = resolved <= logging.DEBUG
    root.setLevel(logging.DEBUG)  # handlers filter; root must pass everything through

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(resolved)
    console.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    root.addHandler(console)

    # File logging always captures DEBUG regardless of console level, so an
    # unattended run that failed can still be diagnosed afterwards.
    path = DEFAULT_LOG_FILE if log_file is None else log_file
    if os.environ.get("LOG_FILE") is not None and log_file is None:
        path = os.environ["LOG_FILE"]
    if path and path.strip().lower() not in ("", "none", "off"):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
            root.addHandler(file_handler)
        except OSError as e:
            # A read-only or missing directory must not stop the program -
            # console logging still works.
            root.warning("Could not open log file %s (%s); console logging only", path, e)

    quiet_noisy_libraries(debug=debug)
    _configured = True
    if debug:
        root.debug("Logging configured at DEBUG; third-party libraries left verbose.")
    return root


def get_logger(name: str) -> logging.Logger:
    """Module-level logger. Deliberately does NOT call setup_logging() - no
    import side effects; entry points configure logging explicitly."""
    return logging.getLogger(name)
