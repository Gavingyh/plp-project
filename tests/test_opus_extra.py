"""Tests for train/opus_extra.py: batches, answer validation and the NER merge (no raters)."""

import json

import pandas as pd
import pytest

import train.opus_extra as ox


@pytest.fixture
def sheets(tmp_path, monkeypatch):
    ner = tmp_path / "gold_sheet.csv"
    pd.DataFrame({"sentence_id": [f"n{i}" for i in range(5)], "case": ["vickers"] * 5, "source": ["cna"] * 5,
                  "text": [f"t{i}" for i in range(5)], "gold_banks": [""] * 5, "annotator": [""] * 5}).to_csv(ner, index=False)
    monkeypatch.setitem(ox.SHEETS, "ner", {**ox.SHEETS["ner"], "sheet": str(ner), "batches": 2})
    monkeypatch.setattr(ox, "CLAUDE_DIR", str(tmp_path / "claude"))
    (tmp_path / "claude").mkdir()
    return tmp_path


def _answer_path(inp):
    import os
    return os.path.join(os.path.dirname(inp), "opus_" + os.path.basename(inp)[:-4] + ".jsonl")


def _answer(path, rows):
    with open(path, "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")


def test_ner_batches_hide_the_stratum_and_merge_validates(sheets):
    paths = ox.write_batches("ner")
    assert len(paths) == 2 and "case" not in pd.read_csv(paths[0]).columns
    for p in paths:
        ids = pd.read_csv(p)["sentence_id"]
        _answer(_answer_path(p),
                [{"sentence_id": s, "banks": ["UOB", "DBS"]} for s in ids])
    merged = ox.merge("ner")
    assert len(merged) == 5 and set(merged["opus_banks"]) == {"DBS;UOB"}      # canonical order


def test_merge_refuses_wrong_order_or_unknown_banks(sheets):
    paths = ox.write_batches("ner")
    for p in paths:
        ids = list(pd.read_csv(p)["sentence_id"])
        _answer(_answer_path(p),
                [{"sentence_id": s, "banks": ["HSBC"]} for s in ids])
    with pytest.raises(ValueError, match="invalid answer"):
        ox.merge("ner")
    ids = list(pd.read_csv(paths[0])["sentence_id"])[::-1]
    _answer(_answer_path(paths[0]), [{"sentence_id": s, "banks": []} for s in ids])
    with pytest.raises(ValueError, match="order differ"):
        ox.merge("ner")
