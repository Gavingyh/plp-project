"""Tests for preprocess/segment.py: sentence splits in bank text."""

from preprocess.segment import segment


def _texts(text):
    return [s for s, _, _ in segment(text)]


def test_offsets_point_at_the_sentence():
    text = "Net profit rose 5% vs. a year ago on fee income. Margins held steady in the quarter."
    out = segment(text)
    assert len(out) == 2
    assert all(text[a:b].strip() == s for s, a, b in out)


def test_a_capitalised_abbreviation_does_not_end_the_sentence():
    # a stored headline was cut here: "OCBC Declares Interim Dividend per Share of S$0.47 Vs."
    assert _texts("OCBC Declares Interim Dividend per Share of S$0.47 Vs. S$0.40 a Year Earlier") == \
        ["OCBC Declares Interim Dividend per Share of S$0.47 Vs. S$0.40 a Year Earlier"]


def test_slide_bullets_become_separate_sentences():
    text = ("Fee income up 7% YoY on wealth management demand ▪ Treasury Markets trading income "
            "declines 34% YoY on weaker flows • Allowances lower than a year ago")
    out = segment(text)
    assert [s for s, _, _ in out] == ["Fee income up 7% YoY on wealth management demand",
                                      "Treasury Markets trading income declines 34% YoY on weaker flows",
                                      "Allowances lower than a year ago"]
    assert all(text[a:b] == s for s, a, b in out)


def test_a_quarter_at_the_end_of_a_sentence_still_ends_it():
    assert len(segment("Profit rose strongly in Q3. Margins held steady over the period.")) == 2
