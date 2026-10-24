"""config/sources.yaml: source weights and which sources hold text written by
the public (before, the weights were a dict in aggregate/index.py and
the Reddit check a literal in the OpenAI backend)."""

import re
from pathlib import Path

import pytest

from config import sources

ROOT = Path(__file__).resolve().parent.parent


def test_weights_are_the_ones_the_stored_index_was_built_with():
    # sgx_research (broker reports, added later) is not in the stored index; it counts like earnings
    assert sources.weights() == {"earnings": 1.0, "newsapi": 1.5, "alphavantage": 1.5, "arctic_shift": 1.0,
                                 "yahoo_news": 1.5, "google_news": 1.5, "cna": 1.5, "sgx_research": 1.0}
    assert sources.default_weight() == 1.0


def test_only_reddit_is_text_written_by_the_public():
    assert sources.personal_text_sources() == {"arctic_shift"}


def test_only_cna_and_the_broker_reports_must_stay_within_the_team():
    # third-party articles and research: CNA's, and the brokers' (sgx_research)
    assert sources.team_only_sources() == {"cna", "sgx_research"}


def test_the_team_cleared_cna_and_the_broker_reports_for_a_hosted_model():
    assert sources.withheld_team_only_sources() == frozenset()
    assert "arctic_shift" in sources.personal_text_sources()     # Reddit is never cleared this way


def test_every_source_the_ingesters_write_is_configured():
    named = set()
    for f in (ROOT / "ingest").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        named |= set(re.findall(r'^SOURCE = "(\w+)"', text, re.M))
        named |= set(re.findall(r'"source": "(\w+)"', text))
        named |= set(re.findall(r'make_doc_id\("(\w+)"', text))
    assert {"arctic_shift", "earnings", "cna", "google_news", "yahoo_news"} <= named   # the scan finds them
    assert named <= set(sources.weights())


def test_a_source_without_a_weight_is_rejected(tmp_path, monkeypatch):
    bad = tmp_path / "sources.yaml"
    bad.write_text("default_weight: 1.0\nsources:\n  cna: {personal_text: false}\n")
    monkeypatch.setattr(sources, "CONFIG_PATH", str(bad))
    sources._load.cache_clear()
    try:
        with pytest.raises(ValueError, match="cna"):
            sources.weights()
    finally:
        sources._load.cache_clear()


def test_the_index_uses_the_configured_weights():
    from aggregate import index
    assert index._SOURCE_WEIGHT == sources.weights()
    assert index._DEFAULT_WEIGHT == sources.default_weight()
