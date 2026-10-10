"""train/evaluate.py's finetuned_probs, with a fake model: outputs come back
in the project's label order whatever the head's order, and probabilities
that don't sum to 1 (a GPU fault seen once) stop the run."""

import numpy as np
import pandas as pd
import pytest
import torch

import train.evaluate as ev
from train.finetune import write_input_format


class _Batch(dict):
    def to(self, device):
        return self


class _Tokenizer:
    def __call__(self, texts, *rest, **kw):
        return _Batch(n=len(texts))


class _Model:
    def __init__(self, logits):
        self.logits_row = logits
        self.config = type("C", (), {"id2label": {0: "positive", 1: "negative", 2: "neutral"}})()

    def eval(self):
        return self

    def to(self, device):
        return self

    def __call__(self, n, **kw):
        return type("O", (), {"logits": torch.tensor([self.logits_row] * n, dtype=torch.float32)})()


def _probs(monkeypatch, tmp_path, logits, softmax=None):
    write_input_format(str(tmp_path), with_aspect=False)
    monkeypatch.setattr(ev, "AutoTokenizer", type("T", (), {"from_pretrained": staticmethod(lambda d: _Tokenizer())}))
    monkeypatch.setattr(ev, "AutoModelForSequenceClassification",
                        type("M", (), {"from_pretrained": staticmethod(lambda d: _Model(logits))}))
    monkeypatch.setattr(ev, "best_device", lambda: "cpu")
    if softmax:
        monkeypatch.setattr(torch, "softmax", softmax)
    return ev.finetuned_probs(str(tmp_path), pd.DataFrame({"text": ["a", "b", "c"], "aspect": ["other"] * 3}))


def test_probabilities_come_back_in_the_project_label_order(monkeypatch, tmp_path):
    # Head order positive 0, negative 1, neutral 2; LABELS is negative, neutral, positive.
    probs = _probs(monkeypatch, tmp_path, [3.0, 1.0, 0.0])
    assert list(ev.LABELS) == ["negative", "neutral", "positive"]
    assert probs.shape == (3, 3) and np.allclose(probs.sum(axis=1), 1.0)
    assert (probs.argmax(axis=1) == 2).all()              # the head's "positive" is the project's positive


def test_probabilities_that_do_not_sum_to_one_stop_the_run(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match="--cpu"):
        _probs(monkeypatch, tmp_path, [3.0, 1.0, 0.0], softmax=lambda x, dim: torch.zeros_like(x))
