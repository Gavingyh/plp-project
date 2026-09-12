"""
Tests for ingest/earnings_extract.py prose extraction.

These exist because of a real, total-breakage bug that shipped unnoticed:
`extract_prose` called `text.split("")` - an empty separator, which raises
ValueError on every page of every PDF. `pull()` catches per-file exceptions
and continues, so the whole earnings source degraded to zero documents while
still exiting successfully. The corpus already held earnings sentences from
an earlier working run, so nothing downstream looked wrong either.

The lesson driving these tests: a function whose failure mode is "silently
returns nothing" needs a test that asserts it returns something.
"""

import pytest
from unittest.mock import MagicMock, patch

from ingest.earnings_extract import (_is_prose, _quarter_to_announcement_date,
                                     extract_prose)


def _pdf_with_pages(*page_texts):
    """A stand-in pdfplumber document yielding the given page text."""
    pages = []
    for text in page_texts:
        page = MagicMock()
        page.extract_text.return_value = text
        pages.append(page)
    pdf = MagicMock()
    pdf.pages = pages
    pdf.__enter__ = lambda self: self
    pdf.__exit__ = lambda self, *a: False
    return pdf


def test_extract_prose_returns_lines_and_does_not_raise():
    """The regression itself: this raised ValueError for every input."""
    text = ("Net interest income rose on the back of higher margins this quarter\n"
            "Fee income grew across wealth management and card products\n")
    with patch("pdfplumber.open", return_value=_pdf_with_pages(text)):
        lines = extract_prose("ignored.pdf")
    assert len(lines) == 2
    assert lines[0].startswith("Net interest income rose")


def test_extract_prose_splits_on_newlines_not_characters():
    """Guards the exact defect: an empty separator would explode the text into
    one entry per character, so assert whole lines come back."""
    with patch("pdfplumber.open", return_value=_pdf_with_pages(
            "Allowances were set aside in view of the uncertain macro outlook\n")):
        lines = extract_prose("ignored.pdf")
    assert lines == ["Allowances were set aside in view of the uncertain macro outlook"]


def test_extract_prose_spans_multiple_pages():
    page1 = "The group delivered a record operating profit for the full year\n"
    page2 = "Loan growth was broad based across the core markets of the group\n"
    with patch("pdfplumber.open", return_value=_pdf_with_pages(page1, page2)):
        assert len(extract_prose("ignored.pdf")) == 2


def test_extract_prose_handles_a_page_with_no_text():
    with patch("pdfplumber.open", return_value=_pdf_with_pages(None, "")):
        assert extract_prose("ignored.pdf") == []


def test_extract_prose_drops_table_rows():
    text = ("Net interest income increased on stronger loan volumes this year\n"
            "1,234.5 6,789.0 (12.3) 45.6% 1,000.0 2,000.0 3,000.0\n")
    with patch("pdfplumber.open", return_value=_pdf_with_pages(text)):
        lines = extract_prose("ignored.pdf")
    assert len(lines) == 1
    assert "Net interest income" in lines[0]


def test_is_prose_rejects_short_lines():
    assert _is_prose("Too short") is False


def test_is_prose_rejects_number_heavy_lines():
    assert _is_prose("2020 2021 2022 1,234 5,678 9,012 3,456 7,890 1,234") is False


def test_is_prose_accepts_a_real_sentence():
    assert _is_prose(
        "Net interest margin improved to 1.58% on the back of higher rates") is True


# ---------------------------------------------------------------------------
# Period -> announcement date
#
# Lives here because the function does, and it does because extraction is its
# only caller. It parses BOTH fetchers' naming conventions: DBS and OCBC use
# "2Q26"/"1H26"/"FY25", UOB uses "2q-2021".
#
# Without it every earnings document would be stamped with ingestion time,
# dropping the whole back-catalogue into the dashboard's 7d/30d rolling
# windows at once.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename,expected_prefix", [
    ("2Q26_analyst_transcript.pdf", "2026-08"),
    ("1Q23_CEO_presentation.pdf", "2023-05"),
    ("3Q24_media_transcript.pdf", "2024-11"),
    ("4Q25_press_statement.pdf", "2026-02"),      # Q4 reported early the NEXT year
    ("OCBC 1H26 CEO Presentation.pdf", "2026-08"),
    ("OCBC FY25 Results Presentation.pdf", "2026-02"),  # FY reported the next year
    ("ceo-presentation-2q-2021.pdf", "2021-08"),  # UOB's lowercase, four-digit form
    ("cfo-presentation-1q-2023.pdf", "2023-05"),
])
def test_period_parsed_to_announcement_date(filename, expected_prefix):
    assert _quarter_to_announcement_date(filename).startswith(expected_prefix)


def test_unrecognised_filename_returns_none():
    # Caller falls back to ingestion time only in this case.
    assert _quarter_to_announcement_date("some_random_document.pdf") is None
