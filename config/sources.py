"""
The sources in config/sources.yaml: each one's weight in the index,
whether members of the public wrote its text, and whether its text must stay
within the team. Read once per process.
"""

import functools
import os

import yaml

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources.yaml")


@functools.cache
def _load() -> dict:
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    for name, spec in cfg["sources"].items():
        if (not isinstance(spec.get("weight"), (int, float)) or not isinstance(spec.get("personal_text"), bool)
                or not isinstance(spec.get("team_only"), bool)):
            raise ValueError(f"config/sources.yaml: {name} needs a numeric weight and true/false "
                             f"personal_text and team_only")
    return cfg


def weights() -> dict[str, float]:
    return {name: float(spec["weight"]) for name, spec in _load()["sources"].items()}


def default_weight() -> float:
    return float(_load()["default_weight"])


def personal_text_sources() -> frozenset[str]:
    return frozenset(name for name, spec in _load()["sources"].items() if spec["personal_text"])


def team_only_sources() -> frozenset[str]:
    return frozenset(name for name, spec in _load()["sources"].items() if spec["team_only"])


def label(source: str | None) -> str:
    """What the chatbot calls a source when citing it; the stored name if none is set."""
    spec = _load()["sources"].get(source) or {}
    return spec.get("label") or (source or "unknown source")
