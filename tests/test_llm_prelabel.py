"""
Tests for train/llm_prelabel.py.

The behaviour worth locking down is the one the whole design exists for:
resumability. A prior unattended run in this project was lost entirely
because nothing was checkpointed - these tests exist so that can't happen
again silently.

No real network calls - requests.post is mocked throughout.
"""

import json

import pandas as pd
import pytest

from train.llm_prelabel import classify, merge_into_csv, run


def _fake_ollama_response(label="positive", rationale="test rationale"):
    payload = {"message": {"content": json.dumps({"label": label, "rationale": rationale})}}

    class _Resp:
        status_code = 200

        def json(self):
            return payload

        def raise_for_status(self):
            pass

    return _Resp()


def _write_candidates(path, rows):
    cols = ["sentence_id", "aspect", "text", "bank", "source", "url", "published_at",
            "split", "sampling_method", "base_finbert_label", "base_finbert_confidence",
            "label", "annotator", "labeled_at", "llm_prelabel", "was_corrected"]
    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(path, index=False)


def test_classify_parses_valid_response(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_ollama_response("negative", "NPL rose"))
    row = pd.Series({"bank": "UOB", "aspect": "asset_quality", "text": "NPL ratio rose to 1.4%"})
    result = classify("llama3.2:3b", row)
    assert result == {"label": "negative", "rationale": "NPL rose"}


def test_classify_rejects_invalid_label(monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_ollama_response("very_positive", "x"))
    row = pd.Series({"bank": "DBS", "aspect": "dividend_policy", "text": "x"})
    with pytest.raises(ValueError, match="invalid label"):
        classify("llama3.2:3b", row)


def test_full_run_processes_all_rows(tmp_path, monkeypatch):
    candidates = tmp_path / "candidates.csv"
    progress = tmp_path / "progress.jsonl"
    _write_candidates(candidates, [
        {"sentence_id": "s1", "aspect": "dividend_policy", "text": "t1", "bank": "DBS",
         "source": "x", "url": "", "published_at": "", "split": "test", "sampling_method": "random",
         "base_finbert_label": "", "base_finbert_confidence": "", "label": "", "annotator": "",
         "labeled_at": "", "llm_prelabel": "", "was_corrected": ""},
        {"sentence_id": "s2", "aspect": "asset_quality", "text": "t2", "bank": "UOB",
         "source": "x", "url": "", "published_at": "", "split": "train_dev", "sampling_method": "stratified",
         "base_finbert_label": "", "base_finbert_confidence": "", "label": "", "annotator": "",
         "labeled_at": "", "llm_prelabel": "", "was_corrected": ""},
    ])
    monkeypatch.setattr("train.llm_prelabel.CANDIDATES_PATH", str(candidates))
    monkeypatch.setattr("train.llm_prelabel.PROGRESS_PATH", str(progress))
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_ollama_response())

    stats = run(model="llama3.2:3b")
    assert stats == {"processed": 2, "ok": 2, "failed": 0}

    result = pd.read_csv(candidates, keep_default_na=False)
    assert (result["llm_prelabel"] == "positive").all()
    assert (result["llm_rationale"] == "test rationale").all()


def test_resumes_and_skips_already_done_rows(tmp_path, monkeypatch):
    """The core guarantee: a killed and restarted run must not re-query
    anything already recorded in the progress file."""
    candidates = tmp_path / "candidates.csv"
    progress = tmp_path / "progress.jsonl"
    _write_candidates(candidates, [
        {"sentence_id": "s1", "aspect": "dividend_policy", "text": "t1", "bank": "DBS",
         "source": "x", "url": "", "published_at": "", "split": "test", "sampling_method": "random",
         "base_finbert_label": "", "base_finbert_confidence": "", "label": "", "annotator": "",
         "labeled_at": "", "llm_prelabel": "", "was_corrected": ""},
        {"sentence_id": "s2", "aspect": "asset_quality", "text": "t2", "bank": "UOB",
         "source": "x", "url": "", "published_at": "", "split": "train_dev", "sampling_method": "stratified",
         "base_finbert_label": "", "base_finbert_confidence": "", "label": "", "annotator": "",
         "labeled_at": "", "llm_prelabel": "", "was_corrected": ""},
    ])
    # s1 already has a recorded result from a prior (interrupted) run.
    progress.write_text(json.dumps({"sentence_id": "s1", "aspect": "dividend_policy",
                                     "status": "ok", "label": "neutral", "rationale": "prior run",
                                     "model": "llama3.2:3b"}) + "\n")

    monkeypatch.setattr("train.llm_prelabel.CANDIDATES_PATH", str(candidates))
    monkeypatch.setattr("train.llm_prelabel.PROGRESS_PATH", str(progress))

    calls = []

    def fake_post(*a, **kw):
        calls.append(kw["json"]["messages"][-1]["content"])
        return _fake_ollama_response("positive", "new run")

    monkeypatch.setattr("requests.post", fake_post)
    stats = run(model="llama3.2:3b")

    assert stats == {"processed": 1, "ok": 1, "failed": 0}  # only s2 queried
    assert len(calls) == 1
    assert "t2" in calls[0]

    result = pd.read_csv(candidates, keep_default_na=False)
    s1_row = result[result.sentence_id == "s1"].iloc[0]
    s2_row = result[result.sentence_id == "s2"].iloc[0]
    assert s1_row["llm_prelabel"] == "neutral"   # preserved from the prior run
    assert s2_row["llm_prelabel"] == "positive"  # newly processed


def test_a_failed_row_does_not_stop_the_run(tmp_path, monkeypatch):
    candidates = tmp_path / "candidates.csv"
    progress = tmp_path / "progress.jsonl"
    _write_candidates(candidates, [
        {"sentence_id": "bad", "aspect": "dividend_policy", "text": "t1", "bank": "DBS",
         "source": "x", "url": "", "published_at": "", "split": "test", "sampling_method": "random",
         "base_finbert_label": "", "base_finbert_confidence": "", "label": "", "annotator": "",
         "labeled_at": "", "llm_prelabel": "", "was_corrected": ""},
        {"sentence_id": "good", "aspect": "asset_quality", "text": "t2", "bank": "UOB",
         "source": "x", "url": "", "published_at": "", "split": "train_dev", "sampling_method": "stratified",
         "base_finbert_label": "", "base_finbert_confidence": "", "label": "", "annotator": "",
         "labeled_at": "", "llm_prelabel": "", "was_corrected": ""},
    ])
    monkeypatch.setattr("train.llm_prelabel.CANDIDATES_PATH", str(candidates))
    monkeypatch.setattr("train.llm_prelabel.PROGRESS_PATH", str(progress))

    def flaky_post(*a, **kw):
        text = kw["json"]["messages"][-1]["content"]
        if "t1" in text:
            raise ConnectionError("simulated network failure")
        return _fake_ollama_response("negative", "ok")

    monkeypatch.setattr("requests.post", flaky_post)
    stats = run(model="llama3.2:3b")

    assert stats == {"processed": 2, "ok": 1, "failed": 1}
    lines = [json.loads(l) for l in progress.read_text().splitlines()]
    assert any(r["status"] == "failed" and r["sentence_id"] == "bad" for r in lines)
    assert any(r["status"] == "ok" and r["sentence_id"] == "good" for r in lines)


def test_limit_caps_new_rows_processed(tmp_path, monkeypatch):
    candidates = tmp_path / "candidates.csv"
    progress = tmp_path / "progress.jsonl"
    rows = [{"sentence_id": f"s{i}", "aspect": "dividend_policy", "text": f"t{i}", "bank": "DBS",
             "source": "x", "url": "", "published_at": "", "split": "test", "sampling_method": "random",
             "base_finbert_label": "", "base_finbert_confidence": "", "label": "", "annotator": "",
             "labeled_at": "", "llm_prelabel": "", "was_corrected": ""} for i in range(5)]
    _write_candidates(candidates, rows)
    monkeypatch.setattr("train.llm_prelabel.CANDIDATES_PATH", str(candidates))
    monkeypatch.setattr("train.llm_prelabel.PROGRESS_PATH", str(progress))
    monkeypatch.setattr("requests.post", lambda *a, **kw: _fake_ollama_response())

    stats = run(model="llama3.2:3b", limit=2)
    assert stats["processed"] == 2


def test_merge_into_csv_only_touches_successful_rows(tmp_path, monkeypatch):
    # merge_into_csv writes to the module-level CANDIDATES_PATH as a side
    # effect - this MUST be patched, or the test writes over the real
    # candidates.csv (a mistake made once while writing this file).
    monkeypatch.setattr("train.llm_prelabel.CANDIDATES_PATH", str(tmp_path / "out.csv"))
    df = pd.DataFrame({
        "sentence_id": ["a", "b"], "aspect": ["x", "y"],
        "llm_prelabel": ["", ""],
    })
    progress = {
        ("a", "x"): {"status": "ok", "label": "positive", "rationale": "r1"},
        ("b", "y"): {"status": "failed", "error": "boom"},
    }
    result = merge_into_csv(df, progress)
    assert result.loc[0, "llm_prelabel"] == "positive"
    assert result.loc[1, "llm_prelabel"] == ""  # failed row left untouched, not blanked-with-garbage
