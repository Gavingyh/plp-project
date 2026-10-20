"""Server-side NewsAPI configuration, shared by inventory and the collector."""

import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def api_key() -> str | None:
    value = os.environ.get("NEWSAPI_KEY")
    if value is None:
        value = dotenv_values(ROOT / ".env").get("NEWSAPI_KEY")
    value = (value or "").strip()
    if not value or value.lower() == "your_newsapi_key_here":
        return None
    return value
