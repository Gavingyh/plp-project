"""Tests for preprocess/fragments.py's debris rules."""

import pytest

from preprocess.fragments import fragment_reason


@pytest.mark.parametrize("text, reason", [
    ("N e t p ro fit (in c lu d in g o n e -o ff e x p e n s e s )", "garbled"),
    ("Profit before tax 2,113 1,888 +12 2,412 -12 1,745 1,687 +3", "table"),
    ("-1% CASA ratio 47.4% 47.1% 48.7% +0.3ppt -1.3ppt CET1 16.2% 15.9%", "table"),
    # prose, kept even with numbers or few words
    ("UOB Evol is nerfing the cashback from 40/600 (6.7%) to 30/800 (3.75%) for online payments.", None),
    ("Cards were strong at 17%.", None),
    ("I thought my $2m+ in DBS is a problem.", None),
    ("DBS raised its quarterly dividend to 60 cents a share after record profit.", None),
])
def test_fragment_reason(text, reason):
    assert fragment_reason(text) == reason


def test_only_pdf_text_is_checked_when_the_source_is_known():
    row = "SSB 3.3% $200k = $6.6k, UOB 4% $150k = $6k, $150k T-bills 3.74% = $5,610."
    assert fragment_reason(row) == "table"
    assert fragment_reason(row, "arctic_shift") is None
    assert fragment_reason(row, "earnings") == "table"
