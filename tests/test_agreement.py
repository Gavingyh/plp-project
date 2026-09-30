"""
Tests for train/agreement.py.

The property worth protecting is that kappa behaves differently from raw
agreement on a skewed corpus. Two annotators who both label almost everything
`neutral` agree most of the time while sharing no judgement about the hard
cases, and this project's corpus is 87% neutral under base FinBERT, so that
scenario is the expected one rather than a corner case. A test that only
checked "kappa is high when labels match" would not catch a regression that
silently reported raw agreement.
"""

import pandas as pd
import pytest

from train.agreement import LABELS, interpret, load_pair, run, score


def _pairs(a, b):
    return pd.DataFrame({
        "sentence_id": [f"s{i}" for i in range(len(a))],
        "aspect": ["dividend_policy"] * len(a),
        "rater_a": a,
        "rater_b": b,
    })


def test_perfect_agreement_is_kappa_one():
    labels = ["positive", "negative", "neutral"] * 5
    result = score(_pairs(labels, labels))
    assert result["cohen_kappa"] == 1.0
    assert result["observed_agreement"] == 1.0
    assert result["meets_target"]


def test_skewed_corpus_inflates_raw_agreement_far_above_kappa():
    """The reason kappa is used at all.

    Both raters say `neutral` 18 times in 20 and swap their answers on the two
    remaining rows. Raw agreement is 90%, which reads as excellent; kappa is
    0.46, below this project's 0.6 target. Hand-check: chance agreement is
    0.9*0.9 + 0.05*0.05 + 0.05*0.05 = 0.815, so kappa is
    (0.90 - 0.815) / (1 - 0.815) = 0.459.
    """
    a = ["neutral"] * 18 + ["positive", "negative"]
    b = ["neutral"] * 18 + ["negative", "positive"]
    result = score(_pairs(a, b))

    assert result["observed_agreement"] == 0.9
    assert result["cohen_kappa"] == pytest.approx(0.4595, abs=1e-3)
    assert result["observed_agreement"] - result["cohen_kappa"] > 0.4
    assert not result["meets_target"], "0.46 is below the 0.6 target"


def test_agreement_at_exactly_chance_level_is_kappa_zero():
    """The limiting case: 90% raw agreement worth nothing at all.

    Each rater uses one non-neutral label once, on different rows. Chance
    agreement (0.905) slightly exceeds observed (0.90), so kappa goes just
    negative — the correct answer, and the one raw agreement cannot express.
    """
    a = ["neutral"] * 19 + ["positive"]
    b = ["positive"] + ["neutral"] * 19
    result = score(_pairs(a, b))

    assert result["observed_agreement"] == 0.9
    assert result["cohen_kappa"] < 0.0
    assert not result["meets_target"]


def test_rows_are_skipped_when_either_rater_left_it_blank():
    a = ["positive", "negative", "", "neutral"]
    b = ["positive", "negative", "neutral", ""]
    result = score(_pairs(a, b))
    assert result["n_compared"] == 2
    assert result["n_skipped"] == 2


def test_labels_are_matched_case_and_whitespace_insensitively():
    """A hand-filled spreadsheet will contain " Positive" sooner or later."""
    result = score(_pairs([" Positive", "NEGATIVE"], ["positive", "negative"]))
    assert result["n_compared"] == 2
    assert result["cohen_kappa"] == 1.0


def test_no_usable_rows_raises_a_useful_message():
    with pytest.raises(ValueError, match="is the label column filled in"):
        score(_pairs(["", ""], ["", ""]))


def test_two_annotator_files_are_joined_on_sentence_and_aspect(tmp_path):
    """Rows only one annotator labelled must not count as disagreement."""
    a = pd.DataFrame({"sentence_id": ["s1", "s2", "s3"],
                      "aspect": ["dividend_policy"] * 3,
                      "label": ["positive", "negative", "neutral"]})
    # s3 absent, s4 extra: only s1 and s2 are comparable.
    b = pd.DataFrame({"sentence_id": ["s1", "s2", "s4"],
                      "aspect": ["dividend_policy"] * 3,
                      "label": ["positive", "negative", "positive"]})
    pa, pb = tmp_path / "a.csv", tmp_path / "b.csv"
    a.to_csv(pa, index=False)
    b.to_csv(pb, index=False)

    merged = load_pair(str(pa), str(pb))
    assert len(merged) == 2
    assert set(merged["sentence_id"]) == {"s1", "s2"}


def test_same_aspect_different_sentence_does_not_collide(tmp_path):
    """The join key is (sentence_id, aspect), not either one alone."""
    a = pd.DataFrame({"sentence_id": ["s1", "s1"],
                      "aspect": ["dividend_policy", "asset_quality"],
                      "label": ["positive", "negative"]})
    b = pd.DataFrame({"sentence_id": ["s1", "s1"],
                      "aspect": ["dividend_policy", "asset_quality"],
                      "label": ["positive", "negative"]})
    pa, pb = tmp_path / "a.csv", tmp_path / "b.csv"
    a.to_csv(pa, index=False)
    b.to_csv(pb, index=False)
    assert len(load_pair(str(pa), str(pb))) == 2


def test_missing_column_names_the_file_and_the_column(tmp_path):
    good = pd.DataFrame({"sentence_id": ["s1"], "aspect": ["x"], "label": ["positive"]})
    bad = pd.DataFrame({"sentence_id": ["s1"], "aspect": ["x"]})
    pa, pb = tmp_path / "a.csv", tmp_path / "b.csv"
    good.to_csv(pa, index=False)
    bad.to_csv(pb, index=False)
    with pytest.raises(ValueError, match=r"--b is missing column\(s\): label"):
        load_pair(str(pa), str(pb))


@pytest.mark.parametrize("kappa,expected", [
    (-0.1, "poor"), (0.15, "slight"), (0.35, "fair"),
    (0.55, "moderate"), (0.75, "substantial"), (0.95, "almost perfect"),
])
def test_landis_koch_bands(kappa, expected):
    assert interpret(kappa).startswith(expected)


def test_run_against_two_columns_in_one_file(tmp_path, capsys):
    df = pd.DataFrame({
        "sentence_id": [f"s{i}" for i in range(6)],
        "aspect": ["dividend_policy"] * 6,
        "label": ["positive", "negative", "neutral", "positive", "negative", "neutral"],
        "llm_prelabel": ["positive", "negative", "neutral", "negative", "negative", "neutral"],
    })
    path = tmp_path / "c.csv"
    df.to_csv(path, index=False)

    result = run(path=str(path), col_a="label", col_b="llm_prelabel",
                 show_disagreements=5)
    assert result["n_compared"] == 6
    out = capsys.readouterr().out
    assert "Cohen's kappa" in out
    assert "Disagreements" in out
    assert "s3" in out, "the one disagreeing row should be listed"


def test_all_three_labels_appear_in_the_confusion_matrix():
    """Shape must stay 3x3 even when a rater never used one of the labels,
    or the printed matrix silently stops lining up with its header."""
    result = score(_pairs(["positive", "positive"], ["positive", "negative"]))
    assert result["confusion"].shape == (len(LABELS), len(LABELS))


def test_a_pair_listed_twice_in_a_sheet_counts_once(tmp_path):
    rows = [{"sentence_id": "s1", "aspect": "a", "label": "positive"},
            {"sentence_id": "s1", "aspect": "a", "label": "positive"},
            {"sentence_id": "s2", "aspect": "a", "label": "neutral"}]
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    pd.DataFrame(rows).to_csv(a, index=False)
    pd.DataFrame(rows).to_csv(b, index=False)
    assert len(load_pair(str(a), str(b))) == 2


def test_a_pair_listed_twice_with_different_labels_is_refused(tmp_path):
    rows = [{"sentence_id": "s1", "aspect": "a", "label": "positive"},
            {"sentence_id": "s1", "aspect": "a", "label": "negative"}]
    a = tmp_path / "a.csv"
    pd.DataFrame(rows).to_csv(a, index=False)
    with pytest.raises(ValueError, match="more than once"):
        load_pair(str(a), str(a))
