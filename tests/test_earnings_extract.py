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

import os

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


def test_extract_prose_keeps_the_short_last_line_of_a_wrapped_sentence():
    """A wrapped sentence's last line is often under the length floor. Dropping
    it spliced the kept part into the next sentence, as in the stored corpus:
    "Markets trading income rose to Expenses increased 10%, ..."."""
    text = ("Markets trading income for the quarter rose 12% from a year ago to\n"
            "S$1.23 billion.\n"
            "Expenses increased 10%, driven by higher staff and technology costs,\n"
            "and fell in the quarter\n"
            "Net profit was a record for the group in the first half of the year.\n")
    with patch("pdfplumber.open", return_value=_pdf_with_pages(text)):
        lines = extract_prose("ignored.pdf")
    joined = " ".join(lines)
    assert "rose 12% from a year ago to S$1.23 billion. Expenses increased 10%" in joined
    assert "technology costs, and fell in the quarter" in joined   # a lowercase continuation


def test_extract_prose_still_drops_headers_page_numbers_and_table_fragments():
    unfinished = "Net interest income rose on the back of higher loan volumes in"
    finished = "Fee income grew across wealth management and card products."
    text = "\n".join([unfinished, "Financial Highlights", "12", "1,234.5 6,789.0",
                      unfinished, "Key drivers:", unfinished, "bps",
                      finished, "Outlook", "for the year ahead.", ""])
    with patch("pdfplumber.open", return_value=_pdf_with_pages(text)):
        lines = extract_prose("ignored.pdf")
    assert lines == [unfinished, unfinished, unfinished, finished]


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
    ("ceo-slides-q1-2024.pdf", "2024-05"),         # UOB's 2024 naming, q first
    ("cfo-slides-q2-2024.pdf", "2024-08"),
    ("performance-highlights-q1-2024.pdf", "2024-05"),
    ("cfo-presentation-2023-results.pdf", "2024-02"),     # full year, no quarter
    ("ceo-presentation-2q-2023-results.pdf", "2023-08"),  # the quarter wins over "results"
])
def test_period_parsed_to_announcement_date(filename, expected_prefix):
    assert _quarter_to_announcement_date(filename).startswith(expected_prefix)


def test_unrecognised_filename_returns_none():
    # Caller falls back to ingestion time only in this case.
    assert _quarter_to_announcement_date("some_random_document.pdf") is None


def test_fix_earnings_dates_finds_and_redates_only_misdated_documents(tmp_path):
    import sqlite3
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fix_earnings_dates", os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "fix_earnings_dates.py"))
    fix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fix)
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.execute("CREATE TABLE documents (doc_id TEXT, source TEXT, title TEXT, published_at TEXT)")
    conn.execute("CREATE TABLE sentences (sentence_id TEXT, doc_id TEXT, published_at TEXT)")
    conn.executemany("INSERT INTO documents VALUES (?,?,?,?)", [
        ("a", "earnings", "cfo-slides-q1-2024.pdf", "2026-09-10T09:54:27+00:00"),     # misdated
        ("b", "earnings", "cfo-presentation-1q-2023.pdf", "2023-05-01T00:00:00+00:00"),  # already right
        ("c", "cna", "cfo-slides-q1-2024.pdf", "2026-09-10T09:54:27+00:00"),          # not earnings
    ])
    conn.executemany("INSERT INTO sentences VALUES (?,?,?)", [
        ("s1", "a", "2026-09-10T09:54:27+00:00"), ("s2", "a", "2026-09-10T09:54:27+00:00"),
        ("s3", "b", "2023-05-01T00:00:00+00:00")])
    rows = fix.misdated(conn)
    assert [(r[0], r[3], r[4]) for r in rows] == [("a", "2024-05-01T00:00:00+00:00", 2)]
    fix.apply(conn, rows)
    assert conn.execute("SELECT published_at FROM documents WHERE doc_id='a'").fetchone()[0].startswith("2024-05")
    assert {r[0] for r in conn.execute("SELECT published_at FROM sentences WHERE doc_id='a'")} == {"2024-05-01T00:00:00+00:00"}
    assert fix.misdated(conn) == []


def test_fix_earnings_dates_refuses_a_database_that_does_not_exist(tmp_path, monkeypatch, capsys):
    """--apply opens the database read-write, which creates a missing file: a
    mistyped --db left an empty database behind before failing."""
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location(
        "fix_earnings_dates", os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "fix_earnings_dates.py"))
    fix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fix)
    typo = tmp_path / "pl.db"
    monkeypatch.setattr(sys, "argv", ["fix_earnings_dates.py", "--apply", "--db", str(typo)])
    with pytest.raises(SystemExit) as exit_info:
        fix.main()
    assert exit_info.value.code != 0
    assert not typo.exists()
    assert "pl.db" in capsys.readouterr().err


def test_pdf_links_are_relative_to_the_repository(tmp_path, monkeypatch):
    # No absolute path (and so no home folder) in the URL.
    import ingest.earnings_extract as ee
    pdf_dir = tmp_path / "data" / "earnings_pdfs"
    (pdf_dir / "DBS").mkdir(parents=True)
    (pdf_dir / "DBS" / "2Q26_results.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(ee, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(ee, "PDF_DIR", str(pdf_dir))
    monkeypatch.setattr(ee, "extract_prose", lambda path: ["DBS reported record net profit for the quarter."])
    docs = ee.pull()
    assert [d["url"] for d in docs] == ["data/earnings_pdfs/DBS/2Q26_results.pdf"]
    assert docs[0]["doc_id"] == ee.make_doc_id("earnings", "DBS:2Q26_results.pdf")   # ids don't depend on the path
