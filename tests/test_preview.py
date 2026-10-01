"""Tests for aggregate/preview.py: scoring like the index, and refusing garbage probabilities."""

import numpy as np
import pandas as pd
import pytest

import aggregate.preview as pv


def test_headline_counts_each_sentence_once_with_its_most_confident_pair():
    meta = pd.DataFrame({"sentence_id": ["s1", "s2"], "bank": ["DBS", "DBS"], "source": ["arctic_shift"] * 2})
    pairs = pd.DataFrame({"sentence_id": ["s1", "s1", "s2"], "aspect": ["a", "b", "a"],
                          "label": ["positive", "negative", "neutral"], "confidence": [0.9, 0.6, 0.8]})
    out = pv.summarize(pairs, meta).set_index("aspect")
    assert out.loc["ALL", "n"] == 2 and out.loc["ALL", "pos"] == 1 and out.loc["ALL", "neg"] == 0
    assert out.loc["a", "n"] == 2 and out.loc["b", "n"] == 1


def test_garbage_probabilities_are_refused(monkeypatch):
    import train.evaluate
    monkeypatch.setattr(train.evaluate, "finetuned_probs", lambda d, df: np.zeros((len(df), 3)))
    with pytest.raises(RuntimeError, match="sum to 1"):
        pv.finetuned_labels(pd.DataFrame({"sentence_id": ["s1"], "aspect": ["a"], "text": ["t"]}), ["m"])
