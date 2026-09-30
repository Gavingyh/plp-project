"""Tests for aspects/assignment_eval.py's metrics on a hand-built similarity matrix."""

import numpy as np
import pytest

from aspects.assignment_eval import assign_at, corpus_metrics, cosine_matrix, label_metrics

ASPECTS = ["dividend_policy", "asset_quality"]
# rows: sentences; columns: similarity to each centroid
SIMS = np.array([[0.90, 0.70],    # both clear 0.65, top-1 dividend
                 [0.60, 0.80],    # asset only
                 [0.50, 0.55]])   # nothing clears 0.65 -> other


def test_assign_at_matches_assign_py_rules():
    matched, top1 = assign_at(SIMS, ASPECTS, 0.65)
    assert matched.tolist() == [[True, True], [False, True], [False, False]]
    assert top1 == ["dividend_policy", "asset_quality", "other"]


def test_label_metrics():
    human = ["asset_quality", "asset_quality", "other"]
    m = label_metrics(SIMS, ASPECTS, human, 0.65)
    assert m["top1_accuracy"] == pytest.approx(2 / 3)     # row 0 wrong at top-1
    assert m["recall"] == pytest.approx(1.0)              # row 0's human aspect is among its matches
    assert m["mean_matched"] == pytest.approx(1.0)        # (2 + 1 + 0) / 3
    assert m["pct_other"] == pytest.approx(1 / 3)


def test_corpus_metrics_and_cosine():
    assert corpus_metrics(SIMS, 0.65) == {"floor": 0.65, "mean_matched": 1.0, "pct_other": pytest.approx(1 / 3)}
    v = np.array([[1.0, 0.0], [0.0, 2.0]])
    assert cosine_matrix(v, np.array([[1.0, 0.0]])).ravel() == pytest.approx([1.0, 0.0])
