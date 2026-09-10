"""
Tests for preprocess/export_blind_test.py.

The property under test is the one the held-out evaluation depends on: an
annotator working from the blind sheet must not be able to see any label a
model produced. Every test writes to tmp_path - none of them may touch the
real data/labeled/candidates.csv, which holds irreplaceable human work.
"""

import pandas as pd
import pytest

from preprocess.export_blind_test import (WITHHELD_COLUMNS, export_blind,
                                          find_split_leakage, merge_labels,
                                          repair_split_leakage)


def _candidates_frame():
    rows = []
    for i in range(4):
        rows.append({
            "sentence_id": f"s{i}", "aspect": "dividend_policy", "text": f"text {i}",
            "bank": "DBS", "source": "arctic_shift", "url": "http://x", 
            "published_at": "2026-01-01", "split": "test", "sampling_method": "random",
            "base_finbert_label": "positive", "base_finbert_confidence": 0.9,
            "label": None, "annotator": None, "labeled_at": None,
            "llm_prelabel": "negative", "was_corrected": None,
            "llm_rationale": "the model's reasoning",
        })
    for i in range(4, 8):
        rows.append({**rows[0], "sentence_id": f"s{i}", "text": f"text {i}",
                     "split": "train_dev", "sampling_method": "stratified"})
    return pd.DataFrame(rows)


@pytest.fixture
def candidates_csv(tmp_path):
    path = tmp_path / "candidates.csv"
    _candidates_frame().to_csv(path, index=False)
    return str(path)


def test_blind_sheet_withholds_every_model_produced_column(candidates_csv, tmp_path):
    out = str(tmp_path / "test_blind.csv")
    export_blind(candidates_csv, out)
    blind = pd.read_csv(out)
    for col in WITHHELD_COLUMNS:
        assert col not in blind.columns, f"{col} leaked into the blind sheet"


def test_blind_sheet_withholds_base_finbert_specifically(candidates_csv, tmp_path):
    # Called out separately because it is the easiest one to forget and the
    # most damaging: base FinBERT is one of the two models the test set exists
    # to compare, so anchoring on its label biases that comparison directly.
    out = str(tmp_path / "test_blind.csv")
    export_blind(candidates_csv, out)
    text = open(out).read()
    assert "base_finbert" not in text


def test_blind_sheet_contains_only_test_rows(candidates_csv, tmp_path):
    out = str(tmp_path / "test_blind.csv")
    result = export_blind(candidates_csv, out)
    assert result["rows"] == 4
    blind = pd.read_csv(out)
    assert set(blind.sentence_id) == {"s0", "s1", "s2", "s3"}


def test_blind_sheet_label_column_starts_empty(candidates_csv, tmp_path):
    out = str(tmp_path / "test_blind.csv")
    export_blind(candidates_csv, out)
    blind = pd.read_csv(out)
    assert blind["label"].isna().all()


# ---------------------------------------------------------------------------
# Split leakage
# ---------------------------------------------------------------------------

def test_find_split_leakage_detects_a_shared_sentence(tmp_path):
    df = _candidates_frame()
    # Same sentence sampled again under a different aspect, on the other side.
    df.loc[len(df)] = {**df.iloc[0].to_dict(), "aspect": "asset_quality",
                       "split": "train_dev"}
    assert find_split_leakage(df) == ["s0"]


def test_find_split_leakage_clean_frame(tmp_path):
    assert find_split_leakage(_candidates_frame()) == []


def test_repair_drops_the_train_side_not_the_test_side(tmp_path):
    df = _candidates_frame()
    df.loc[len(df)] = {**df.iloc[0].to_dict(), "aspect": "asset_quality",
                       "split": "train_dev"}
    path = str(tmp_path / "candidates.csv")
    df.to_csv(path, index=False)

    result = repair_split_leakage(path)
    assert result["rows_dropped"] == 1

    after = pd.read_csv(path)
    # The precious test row survives; the cheap train row is the one removed.
    assert len(after[(after.sentence_id == "s0") & (after.split == "test")]) == 1
    assert len(after[(after.sentence_id == "s0") & (after.split == "train_dev")]) == 0
    assert find_split_leakage(after) == []


def test_repair_refuses_once_human_labels_exist(tmp_path):
    df = _candidates_frame()
    df.loc[len(df)] = {**df.iloc[0].to_dict(), "aspect": "asset_quality",
                       "split": "train_dev"}
    df.loc[0, "label"] = "positive"   # a human has started work
    path = str(tmp_path / "candidates.csv")
    df.to_csv(path, index=False)

    with pytest.raises(RuntimeError, match="already contains human labels"):
        repair_split_leakage(path)


# ---------------------------------------------------------------------------
# Merging back
# ---------------------------------------------------------------------------

def test_merge_writes_labels_back(candidates_csv, tmp_path):
    blind_path = str(tmp_path / "test_blind.csv")
    export_blind(candidates_csv, blind_path)

    blind = pd.read_csv(blind_path)
    blind["label"] = ["positive", "negative", "neutral", "positive"]
    blind["annotator"] = "gavin"
    blind.to_csv(blind_path, index=False)

    result = merge_labels(blind_path, candidates_csv)
    assert result["merged"] == 4

    after = pd.read_csv(candidates_csv)
    test_rows = after[after.split == "test"].set_index("sentence_id")
    assert test_rows.loc["s0", "label"] == "positive"
    assert test_rows.loc["s1", "label"] == "negative"
    assert after[after.split == "train_dev"]["label"].isna().all()


def test_merge_keys_on_sentence_id_and_aspect_together(tmp_path):
    """The same sentence can be sampled under two aspects. Merging on
    sentence_id alone would write one aspect's label onto both rows."""
    df = _candidates_frame()
    df.loc[len(df)] = {**df.iloc[0].to_dict(), "aspect": "asset_quality"}
    path = str(tmp_path / "candidates.csv")
    df.to_csv(path, index=False)

    blind_path = str(tmp_path / "test_blind.csv")
    export_blind(path, blind_path)
    blind = pd.read_csv(blind_path)
    blind["label"] = blind["label"].astype(object)

    # Label the two s0 rows differently - a sentence_id-only merge collapses them.
    blind.loc[(blind.sentence_id == "s0") & (blind.aspect == "dividend_policy"), "label"] = "positive"
    blind.loc[(blind.sentence_id == "s0") & (blind.aspect == "asset_quality"), "label"] = "negative"
    blind.to_csv(blind_path, index=False)

    merge_labels(blind_path, path)
    after = pd.read_csv(path)
    s0 = after[after.sentence_id == "s0"].set_index("aspect")
    assert s0.loc["dividend_policy", "label"] == "positive"
    assert s0.loc["asset_quality", "label"] == "negative"


def test_merge_rejects_an_invalid_label(candidates_csv, tmp_path):
    blind_path = str(tmp_path / "test_blind.csv")
    export_blind(candidates_csv, blind_path)
    blind = pd.read_csv(blind_path)
    blind["label"] = blind["label"].astype(object)
    blind.loc[0, "label"] = "very positive"     # not in the guideline's label set
    blind.to_csv(blind_path, index=False)

    with pytest.raises(ValueError, match="invalid label"):
        merge_labels(blind_path, candidates_csv)


def test_merge_with_nothing_filled_in_raises(candidates_csv, tmp_path):
    blind_path = str(tmp_path / "test_blind.csv")
    export_blind(candidates_csv, blind_path)
    with pytest.raises(RuntimeError, match="no labels filled"):
        merge_labels(blind_path, candidates_csv)
