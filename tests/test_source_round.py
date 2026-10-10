"""
Tests for the per-source labelling round: suggestions into the sheet, the
annotators' filled sheets back out, and the combined file the fine-tuning reads.

The rules pinned here are the ones the project's labelling design depends on:
test rows never get model output, a suggestion is never promoted to a label,
and the combined file passes the same leakage check as the original.
"""

import pandas as pd
import pytest

from preprocess.export_source_round import CANDIDATE_COLUMNS, junk_reason
from train.labels import check_splits
from train.source_round import RESOLVED_COLUMNS, combine, merge, parse_suggestions, prelabel


def _sheet(tmp_path, n_train=4, n_test=2):
    rows = []
    for i in range(n_train):
        rows.append({"sentence_id": f"t{i}", "text": f"train sentence {i}", "bank": "DBS", "source": "sgx_research",
                     "url": "u", "published_at": "2026-01-01", "split": "train_dev", "sampling_method": "stratified",
                     "aspect": "other", "original_aspect": "other", "base_finbert_label": "neutral",
                     "base_finbert_confidence": "0.9"})
    for i in range(n_test):
        rows.append({"sentence_id": f"x{i}", "text": f"test sentence {i}", "bank": "UOB", "source": "sgx_research",
                     "url": "u", "published_at": "2026-01-01", "split": "test", "sampling_method": "random"})
    df = pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)
    (tmp_path / "llm_prelabels").mkdir()
    df.to_csv(tmp_path / "candidates.csv", index=False)
    pd.DataFrame({"sentence_id": [f"t{i}" for i in range(n_train)]}).to_csv(
        tmp_path / "llm_prelabels" / "order.csv", index=False)
    return tmp_path


def _suggest(tmp_path, lines):
    (tmp_path / "llm_prelabels" / "labels_1_4.txt").write_text("\n".join(lines), encoding="utf-8")


def test_parse_suggestions_maps_compact_keys_and_the_flag(tmp_path):
    _sheet(tmp_path)
    _suggest(tmp_path, ["1 AQ -", "2 NIM 0", "3 DP + x", "4 ISS +"])
    s = parse_suggestions(str(tmp_path / "llm_prelabels")).set_index("sentence_id")
    assert s.loc["t0", "claude_aspect"] == "asset_quality" and s.loc["t0", "claude_label"] == "negative"
    assert s.loc["t2", "claude_not_about_bank"] and not s.loc["t1", "claude_not_about_bank"]


@pytest.mark.parametrize("lines", [["1 AQ -", "2 NIM 0", "3 DP +"],                        # row 4 missing
                                   ["1 AQ -", "2 NIM 0", "3 DP +", "4 ZZ +"],              # unknown aspect
                                   ["1 AQ -", "1 AQ -", "3 DP +", "4 ISS +"]])             # row 1 twice
def test_parse_suggestions_rejects_incomplete_or_unreadable_files(tmp_path, lines):
    _sheet(tmp_path)
    _suggest(tmp_path, lines)
    with pytest.raises(ValueError):
        parse_suggestions(str(tmp_path / "llm_prelabels"))


def test_prelabel_fills_train_rows_and_leaves_test_rows_blind(tmp_path):
    _sheet(tmp_path)
    _suggest(tmp_path, ["1 AQ -", "2 NIM 0", "3 DP + x", "4 ISS +"])
    report = prelabel(str(tmp_path), "claude-sonnet-5-5", "2026-10-04")
    sheet = pd.read_csv(tmp_path / "candidates.csv", dtype=str)
    train, test = sheet[sheet.split == "train_dev"], sheet[sheet.split == "test"]
    assert report["rows_prelabelled"] == 4 and report["flagged_not_about_bank"] == 1
    assert train.set_index("sentence_id").loc["t0", ["aspect", "llm_prelabel"]].tolist() == ["asset_quality", "negative"]
    assert train.set_index("sentence_id").loc["t2", "llm_not_about_bank"] == "true"
    assert train["label"].isna().all(), "a suggestion must never fill the label column"
    assert test[["aspect", "llm_prelabel", "base_finbert_label"]].isna().all().all()


def test_prelabel_refuses_a_sheet_whose_test_rows_carry_model_output(tmp_path):
    _sheet(tmp_path)
    _suggest(tmp_path, ["1 AQ -", "2 NIM 0", "3 DP +", "4 ISS +"])
    sheet = pd.read_csv(tmp_path / "candidates.csv", dtype=str)
    sheet.loc[sheet.split == "test", "llm_prelabel"] = "positive"
    sheet.to_csv(tmp_path / "candidates.csv", index=False)
    with pytest.raises(ValueError, match="blind"):
        prelabel(str(tmp_path), "r", "d")


def _filled(tmp_path):
    """Annotators' sheets: t0 corrected, t1 flagged, t2 left blank, t3 kept; both test rows labelled."""
    _sheet(tmp_path)
    _suggest(tmp_path, ["1 AQ -", "2 NIM 0", "3 DP +", "4 ISS +"])
    prelabel(str(tmp_path), "r", "d")
    sheet = pd.read_csv(tmp_path / "candidates.csv", dtype=str).set_index("sentence_id")
    sheet.loc["t0", ["aspect", "label", "annotator"]] = ["net_interest_margin", "negative", "A"]
    sheet.loc["t1", ["not_about_bank", "annotator"]] = ["true", "A"]
    sheet.loc["t3", ["label", "annotator"]] = ["positive", "A"]
    sheet.reset_index().to_csv(tmp_path / "filled_candidates.csv", index=False)
    blind = pd.DataFrame({"sentence_id": ["x0", "x1"], "aspect": ["asset_quality", "other"],
                          "label": ["Neutral", "positive"], "not_about_bank": ["", ""], "annotator": ["A", "A"]})
    blind.to_csv(tmp_path / "filled_blind.csv", index=False)
    return str(tmp_path / "filled_candidates.csv"), str(tmp_path / "filled_blind.csv")


def test_merge_keeps_only_what_a_person_filled_in(tmp_path):
    cand, blind = _filled(tmp_path)
    report = merge(str(tmp_path), cand, blind)
    resolved = pd.read_csv(tmp_path / "resolved_candidates.csv")
    assert report["train_dev"] == 2 and report["test"] == 2
    assert list(resolved.columns) == RESOLVED_COLUMNS
    assert set(resolved[resolved.split == "train_dev"].sentence_id) == {"t0", "t3"}, \
        "a flagged row and an unfilled row must not become labels, whatever the model suggested"
    t0 = resolved.set_index("sentence_id").loc["t0"]
    assert t0["aspect"] == "net_interest_margin" and t0["was_corrected"] in (True, "True"), \
        "the annotator changed the LLM's suggested aspect"
    t3 = resolved.set_index("sentence_id").loc["t3"]
    assert t3["was_corrected"] in (False, "False"), "the annotator kept the LLM's suggestion"
    assert set(resolved[resolved.split == "test"].label) == {"neutral", "positive"}   # lower-cased


def test_merge_rejects_an_invalid_label(tmp_path):
    cand, blind = _filled(tmp_path)
    pd.DataFrame({"sentence_id": ["x0", "x1"], "aspect": ["other", "other"], "label": ["great", "positive"],
                  "not_about_bank": ["", ""], "annotator": ["A", "A"]}).to_csv(blind, index=False)
    with pytest.raises(ValueError, match="invalid"):
        merge(str(tmp_path), cand, blind)


def test_combine_adds_a_round_to_the_existing_files_without_leaking(tmp_path):
    cand, blind = _filled(tmp_path)
    merge(str(tmp_path), cand, blind)
    out = tmp_path / "combined"
    report = combine([str(tmp_path)], str(out))
    combined = pd.read_csv(out / "candidates.csv")
    check_splits(combined)
    original = pd.read_csv("data/labeled/candidates.csv")
    assert report["train_dev"] == int((original.split == "train_dev").sum()) + 2
    assert report["test"] == int((original.split == "test").sum()) + 2
    assert "sgx_research" in set(combined.source)


@pytest.mark.parametrize("text, expected", [
    ("Too short to be useful here.", "too short"),
    ("Please refer to Disclaimer for the ratings and target price history shown on the last page.", "legal text, chart legend or page furniture"),
    ("NIM held up at 2% while credit costs stayed within the guided range of 25 to 30 bps this quarter.", None),
])
def test_junk_reason(text, expected):
    assert junk_reason(text, "sgx_research") == expected


def test_jaccard_catches_a_reworded_copy_and_not_a_different_sentence():
    from preprocess.export_source_round import NEAR_DUP_VS_TEST, jaccard
    a = "We believe there are downside risks to earnings in an escalating trade war environment given the huge and broad US tariffs."
    b = "We believe there are downside risks to earnings in an escalating trade war environment given the extensive and broad US tariffs."
    assert jaccard(a, b) >= NEAR_DUP_VS_TEST
    assert jaccard(a, "Capital ratios remained strong with CET1 at 16.9% in 4Q25.") < 0.2


def _llm_labelled_round(tmp_path):
    _sheet(tmp_path)
    _suggest(tmp_path, ["1 AQ -", "2 NIM 0", "3 DP + x", "4 ISS +"])
    prelabel(str(tmp_path), "claude-sonnet-5-5", "2026-10-04")
    pd.DataFrame({"sentence_id": ["x0", "x1"], "text": ["a", "b"]}).to_csv(tmp_path / "test_blind.csv", index=False)
    (tmp_path / "llm_test_labels").mkdir()
    pd.DataFrame({"sentence_id": ["x0", "x1"]}).to_csv(tmp_path / "llm_test_labels" / "order.csv", index=False)
    (tmp_path / "llm_test_labels" / "labels_test.txt").write_text("1 AQ -\n2 MG + x\n", encoding="utf-8")
    return str(tmp_path)


def test_label_test_writes_a_separate_file_and_leaves_the_blind_sheet_alone(tmp_path):
    from train.source_round import label_test
    round_dir = _llm_labelled_round(tmp_path)
    before = (tmp_path / "test_blind.csv").read_bytes()
    report = label_test(round_dir, "claude-sonnet-5-5", "2026-10-04")
    assert report["test_rows_labelled"] == 2 and report["flagged_not_about_bank"] == 1
    assert (tmp_path / "llm_test_labels.csv").exists()
    assert (tmp_path / "test_blind.csv").read_bytes() == before, "the blind sheet must stay blind"


def test_silver_files_say_the_llm_labelled_them_and_drop_flagged_rows(tmp_path):
    from train.source_round import label_test, silver
    round_dir = _llm_labelled_round(tmp_path)
    label_test(round_dir, "claude-sonnet-5-5", "2026-10-04")
    report = silver(round_dir, "claude-sonnet-5-5")
    resolved = pd.read_csv(tmp_path / "silver_candidates.csv")
    assert set(resolved["annotator"]) == {"claude-sonnet-5-5"}, "silver labels must never pass as a person's"
    assert report["train_dev"] == 3 and report["test"] == 1          # one flagged row of each dropped
    assert "t2" not in set(resolved["sentence_id"]) and "x1" not in set(resolved["sentence_id"])
    assert not (tmp_path / "resolved_candidates.csv").exists(), "silver must not pose as the human files"


@pytest.mark.parametrize("sheet", ["candidates", "blind"])
def test_merge_refuses_labelled_rows_without_an_annotator(tmp_path, sheet):
    cand, blind = _filled(tmp_path)
    path = cand if sheet == "candidates" else blind
    df = pd.read_csv(path, dtype=str)
    df.loc[df["label"].notna(), "annotator"] = ""
    df.to_csv(path, index=False)
    with pytest.raises(ValueError, match="without an annotator"):
        merge(str(tmp_path), cand, blind)
