"""Tests for train/opus_labels.py: merging, the blindness audit rule, review queues."""

import json

import pandas as pd
import pytest

import train.opus_labels as ol

KEYS = ["dividend_policy", "other"]


def _write(tmp_path, name, ids, rows, task):
    inp = tmp_path / f"{name}.csv"
    pd.DataFrame({"sentence_id": ids, "text": ["t"] * len(ids)}).to_csv(inp, index=False)
    out = tmp_path / f"opus_{name}.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return str(inp), str(out), task


def test_merge_joins_both_passes(tmp_path):
    pairs = [_write(tmp_path, "aspect_01", ["s1", "s2"], [
                {"sentence_id": "s1", "aspect": "other", "not_about_bank": False},
                {"sentence_id": "s2", "aspect": "dividend_policy", "not_about_bank": True}], "aspect"),
             _write(tmp_path, "sentiment_01", ["s1", "s2"], [
                {"sentence_id": "s1", "label": "neutral"}, {"sentence_id": "s2", "label": "negative"}], "sentiment")]
    out = ol.merge(pairs, KEYS)
    assert out.columns.tolist() == ["sentence_id", "rater", "opus_aspect", "opus_not_about_bank", "opus_label"]
    assert out.set_index("sentence_id").loc["s2", "opus_label"] == "negative"


def test_merge_rejects_reordered_or_invalid_answers(tmp_path):
    reordered = [_write(tmp_path, "aspect_01", ["s1", "s2"], [
        {"sentence_id": "s2", "aspect": "other", "not_about_bank": False},
        {"sentence_id": "s1", "aspect": "other", "not_about_bank": False}], "aspect")]
    with pytest.raises(ValueError, match="order"):
        ol.merge(reordered, KEYS)
    bad_key = [_write(tmp_path, "aspect_02", ["s1"], [
        {"sentence_id": "s1", "aspect": "wealth", "not_about_bank": False}], "aspect")]
    with pytest.raises(ValueError, match="invalid aspect"):
        ol.merge(bad_key, KEYS)


def test_audit_allows_only_the_raters_own_files():
    root = ol.CLAUDE_DIR
    assert ol.audit_call("Read", {"file_path": f"{root}/batches/aspect_03.csv"})
    assert ol.audit_call("Write", {"file_path": f"{root}/batches/opus_aspect_03.jsonl"})
    assert ol.audit_call("Read", {"file_path": f"{root}/instructions_sentiment.md"})
    assert ol.audit_call("Bash", {"command": f"wc -l {root}/batches/opus_aspect_03.jsonl"})
    assert not ol.audit_call("Read", {"file_path": ol.CANDIDATES_PATH})
    assert not ol.audit_call("Read", {"file_path": f"{root}/review_aspect.csv"})
    assert not ol.audit_call("Bash", {"command": f"ls {root}"})
    assert not ol.audit_call("Bash", {"command": "cat ../candidates.csv"})
    assert not ol.audit_call("Grep", {"pattern": "dividend"})


def test_review_queues_hold_only_disagreements():
    d = pd.DataFrame({"sentence_id": ["a", "b"], "split": ["test", "train_dev"], "source": ["x", "y"],
                      "bank": ["DBS", "UOB"], "text": ["t1", "t2"],
                      "aspect": ["other", "other"], "opus_aspect": ["other", "dividend_policy"],
                      "opus_not_about_bank": [False, False],
                      "label": ["neutral", "positive"], "opus_label": ["negative", "positive"],
                      "llm_prelabel": ["neutral", "positive"]})
    qa, qs = ol.review_queues(d)
    assert qa["sentence_id"].tolist() == ["b"] and qa["decision"].eq("").all()
    assert qs["sentence_id"].tolist() == ["a"] and qs.loc[qs.index[0], "human_label"] == "neutral"


# --- the later rounds: top-up and NER sheets ---------------------------------------


@pytest.fixture
def sheets(tmp_path, monkeypatch):
    ner = tmp_path / "gold_sheet.csv"
    pd.DataFrame({"sentence_id": [f"n{i}" for i in range(5)], "case": ["vickers"] * 5, "source": ["cna"] * 5,
                  "text": [f"t{i}" for i in range(5)], "gold_banks": [""] * 5, "annotator": [""] * 5}).to_csv(ner, index=False)
    monkeypatch.setitem(ol.SHEETS, "ner", {**ol.SHEETS["ner"], "sheet": str(ner), "batches": 2})
    monkeypatch.setattr(ol, "CLAUDE_DIR", str(tmp_path / "claude"))
    (tmp_path / "claude").mkdir()
    return tmp_path


def _answer_path(inp):
    import os
    return os.path.join(os.path.dirname(inp), "opus_" + os.path.basename(inp)[:-4] + ".jsonl")


def _answer(path, rows):
    with open(path, "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")


def test_ner_batches_hide_the_stratum_and_merge_validates(sheets):
    paths = ol.extra_batches("ner")
    assert len(paths) == 2 and "case" not in pd.read_csv(paths[0]).columns
    for p in paths:
        ids = pd.read_csv(p)["sentence_id"]
        _answer(_answer_path(p),
                [{"sentence_id": s, "banks": ["UOB", "DBS"]} for s in ids])
    merged = ol.merge_extra("ner")
    assert len(merged) == 5 and set(merged["opus_banks"]) == {"DBS;UOB"}      # canonical order


def test_merge_refuses_wrong_order_or_unknown_banks(sheets):
    paths = ol.extra_batches("ner")
    for p in paths:
        ids = list(pd.read_csv(p)["sentence_id"])
        _answer(_answer_path(p),
                [{"sentence_id": s, "banks": ["HSBC"]} for s in ids])
    with pytest.raises(ValueError, match="invalid answer"):
        ol.merge_extra("ner")
    ids = list(pd.read_csv(paths[0])["sentence_id"])[::-1]
    _answer(_answer_path(paths[0]), [{"sentence_id": s, "banks": []} for s in ids])
    with pytest.raises(ValueError, match="order differ"):
        ol.merge_extra("ner")
