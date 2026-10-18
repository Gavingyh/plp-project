"""
config/aspects.yaml, read once per process: the aspect keys in file order
and their readable labels. A missing or broken file is an error, never a
built-in fallback list.
"""

import functools
import os

import yaml

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aspects.yaml")


@functools.cache
def load() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def keys() -> list[str]:
    return list(load()["aspects"])


def labels() -> dict[str, str]:
    """Aspect key -> readable label ("dividend_policy" -> "Dividend Policy")."""
    return {k: (v or {}).get("label", k) for k, v in load()["aspects"].items()}
