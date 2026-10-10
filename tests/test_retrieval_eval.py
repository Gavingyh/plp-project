"""Tests for chatbot/retrieval_eval.py: metrics and the random baseline."""

import numpy as np
import pandas as pd
import pytest

import chatbot.retrieval_eval as re_


def test_metrics_for_one_ranked_list():
    m = re_.metrics([False, True, False, True, False, False, False, False, False, False])
    assert m["rr"] == 0.5 and m["hit@1"] == 0.0 and m["hit@5"] == 1.0 and m["p@5"] == 0.4


def test_random_baseline_matches_known_values():
    b = re_.random_baseline(10, 1)
    assert b["hit@1"] == pytest.approx(0.1) and b["hit@5"] == pytest.approx(0.5)
    assert b["rr"] == pytest.approx(sum(1 / i for i in range(1, 11)) / 10)   # H(10) / 10
    assert re_.random_baseline(10, 10)["rr"] == pytest.approx(1.0)


def test_evaluate_ranks_each_banks_pool_and_skips_thin_aspects():
    labels = pd.DataFrame({"sentence_id": [f"s{i}" for i in range(8)], "bank": ["DBS"] * 8,
                           "aspect": ["dividend_policy"] * 3 + ["asset_quality"] * 3 + ["other", "wealth_business"],
                           "text": ["dividend paid"] * 3 + ["bad loans"] * 3 + ["misc", "aum"]})
    vecs = {f"s{i}": np.array([1.0, 0.0]) if i < 3 else np.array([0.0, 1.0]) for i in range(8)}
    embed = lambda q: np.array([1.0, 0.0]) if "dividend" in q.lower() else np.array([0.0, 1.0])
    res = re_.evaluate(labels, vecs, embed, {"dividend_policy": "Dividend Policy", "asset_quality": "Asset Quality"})
    assert set(res["aspect"]) == {"dividend_policy", "asset_quality"}        # other and the 1-row aspect skipped
    assert res.set_index("aspect").loc["dividend_policy", "rr"] == 1.0


def test_aspect_query_is_on_by_default_and_names_the_aspect(monkeypatch):
    from chatbot.retrieval import aspect_query_enabled, ranking_query
    monkeypatch.delenv("CHATBOT_ASPECT_QUERY", raising=False)
    assert aspect_query_enabled() is True                             # on by default, as decided
    monkeypatch.setenv("CHATBOT_ASPECT_QUERY", "0")
    assert aspect_query_enabled() is False
    q = ranking_query("What do people say about DBS's dividend policy?", "dividend_policy")
    assert q == "Dividend Policy"                                   # bank and label words dropped
    assert ranking_query("Is there evidence of a DBS dividend cut?", "dividend_policy") == "Dividend Policy cut"
    assert ranking_query("anything at all", None) == "anything at all"
