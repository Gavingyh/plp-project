"""
Tests for the broker-research extractor's text and metadata helpers.

The PDFs themselves are not in the repository, so these pin the decisions the
extractor made after reading all 25 of them: which filename dates to trust, how
a report's subject bank is decided (the broker "UOB Kay Hian" is not UOB, and a
leading "DBS - " in a DBS Group Research filename is the publisher), and the
text repairs for doubled capitals, OCR run-together words and web furniture.
"""

from datetime import datetime, timezone

import pytest

from ingest.sgx_research_extract import (
    _END_OF_REPORT, _SGI_END, _SGI_URL, _SGI_TITLE, collapse_doubled_letters, filename_date,
    find_gutter, metadata_date, publication_date, split_run_together, subject_bank)

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def test_filename_date_reads_both_prefix_forms():
    assert filename_date("300426 CGSI - DBS Group Update.pdf", NOW).date().isoformat() == "2026-04-30"
    assert filename_date("08052026 DBS - OCBC - 1Q26 results.pdf", NOW).date().isoformat() == "2026-05-08"


def test_filename_date_rejects_a_future_date():
    # SGX's own "070827 DBS - United Overseas Bank ..." decodes to 2027-08-07
    assert filename_date("070827 DBS - United Overseas Bank Ltd Update.pdf", NOW) is None


def test_filename_date_none_without_a_prefix():
    assert filename_date("A Mixed Set Of 3Q25 Results From SG Banks.pdf", NOW) is None


def test_metadata_date():
    assert metadata_date("D:20260807172933+08'00'").date().isoformat() == "2026-08-07"
    assert metadata_date(None) is None and metadata_date("garbage") is None


def test_publication_date_falls_back_to_creation_date_for_a_mistyped_filename():
    assert publication_date("070827 DBS - UOB.pdf", "D:20260807172933+08'00'").startswith("2026-08-07")


def test_publication_date_keeps_the_filename_when_both_agree():
    # created six days after the filename date: the filename wins
    assert publication_date("081124 DBS - UOB.pdf", "D:20241114033613Z").startswith("2024-11-08")


def test_publication_date_prefers_the_title_date_of_a_web_page():
    assert publication_date("x.pdf", "D:20261004083736+00'00'", "2025-11-20").startswith("2025-11-20")


@pytest.mark.parametrize("text, expected", [
    ("040825 DBS - OCBC Update - Bracing for impact", "OCBC"),          # publisher DBS is skipped
    ("260226 DBS - Oversea-Chinese Banking Corporation Update", "OCBC"),
    ("070827 DBS - United Overseas Bank Ltd Update", "UOB"),
    ("300426 CGSI - DBS Group Update - Clarity", "DBS"),
    ("310826 DBS - Singapore Market Focus - Market Strategy", "MULTI"),
    ("Singapore Banks - UOB Kay Hian", "MULTI"),                        # the broker, not the bank
    ("DBS", "DBS"),
    ("SG Banks", "MULTI"),
])
def test_subject_bank(text, expected):
    assert subject_bank(text) == expected


def test_collapse_doubled_letters_only_touches_fully_doubled_tokens():
    assert collapse_doubled_letters("SSIINNGGAAPPOORREE EEQQUUIITTYY RREESSEEAARRCCHH") == "SINGAPORE EQUITY RESEARCH"
    assert collapse_doubled_letters("Moody's rating, a good book keeper, 1,000 less") == "Moody's rating, a good book keeper, 1,000 less"


def test_split_run_together_leaves_figures_alone():
    pytest.importorskip("wordninja")
    out = split_run_together("2Q25 saw lower credit; 3Q24revenueandprofitbeatconsensus; Refertoimportantdisclosuresattheendofthisreport")
    assert "2Q25 saw lower credit" in out
    assert "3Q24 revenue and profit beat consensus" in out
    assert "Refer to important disclosures at the end of this report" in out


def test_find_gutter_splits_two_columns_and_not_one():
    left = [(40 + (i % 5) * 50, 80 + (i % 5) * 50) for i in range(60)]     # x 40..330
    right = [(380 + (i % 3) * 60, 430 + (i % 3) * 60) for i in range(60)]  # x 380..550
    gutter = find_gutter(left + right, 595)
    assert 330 < gutter < 380
    assert find_gutter(left, 595) is None          # one column: nothing to split
    assert find_gutter(left[:10] + right[:10], 595) is None   # too few words to trust


def test_end_of_report_cuts_at_the_disclaimer_but_not_the_page_footer():
    text = "Real analysis.\nDisclaimer: The information contained in this document\nMore analysis.\nGENERAL DISCLOSURE/DISCLAIMER\nlegal"
    assert text[:_END_OF_REPORT.search(text).start()] == "Real analysis.\nDisclaimer: The information contained in this document\nMore analysis.\n"
    cgsi = "Analysis.\nDISCLAIMER\nlegal"
    assert cgsi[:_END_OF_REPORT.search(cgsi).start()] == "Analysis.\n"


def test_sginvestors_url_and_end_markers():
    body = "DBS (https://sginvestors.io/sgx/stock/d05-\ndbs/stock-info) raised its target. Above is an excerpt from RHB"
    stripped = _SGI_URL.sub("", body.replace("\n", " "))
    assert "https" not in stripped
    assert _SGI_END.search(stripped).group(0) == "Above is an excerpt"
    assert _SGI_END.search("text 2026-07-14DBS - Expecting Resiliency").group(0) == "2026-07-14"


def test_sginvestors_title_gives_subject_broker_and_date():
    m = _SGI_TITLE.match("DBS - RHB Research 2026-07-14: Expecting Resiliency For Upcoming 2Q26 Results; BUY")
    assert (m["subject"], m["broker"], m["date"]) == ("DBS", "RHB Research", "2026-07-14")
