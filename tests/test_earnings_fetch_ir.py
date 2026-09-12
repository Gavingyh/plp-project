"""
Tests for ingest/earnings_fetch_ir.py — discovering and downloading earnings
PDFs from DBS's and OCBC's investor-relations sites.

The listing-page HTML fixtures below are trimmed copies of real markup
(captured from the live page), so a change in either bank's URL structure
surfaces as a failing discovery test rather than a silent "0 documents
found" in production.

No network calls — requests.get is mocked throughout.
"""

import pytest

from ingest.earnings_fetch_ir import SOURCES, discover, fetch

# Trimmed from the real DBS quarterly-financials page.
_DBS_LISTING_HTML = """
<a href="/iwov-resources/images/investors/quarterly-financials/2026/2Q26_analyst_transcript.pdf">x</a>
<a href="/iwov-resources/images/investors/quarterly-financials/2026/2Q26_CEO_presentation.pdf">x</a>
<a href="/iwov-resources/images/investors/quarterly-financials/2026/2Q26_P3_other_regulatory_disclosures.pdf">x</a>
<a href="/iwov-resources/images/investors/quarterly-financials/2022/1Q22_analyst_transcript.pdf">x</a>
<a href="/iwov-resources/images/investors/quarterly-financials/2025/Bank Group FS FY25.pdf">x</a>
<a href="/iwov-resources/images/investors/quarterly-financials/2025/DBS Annual Report 2025.pdf">x</a>
"""

# Trimmed from the real OCBC financials page — note the spaces in filenames.
_OCBC_LISTING_HTML = """
<a href="/iwov-resources/sg/ocbc/gbc/pdf/investors/quarterly-results/2026/OCBC 1H26 CEO Presentation.pdf">x</a>
<a href="/iwov-resources/sg/ocbc/gbc/pdf/investors/quarterly-results/2026/1H26 Unaudited Condensed Interim FS.pdf">x</a>
<a href="/iwov-resources/sg/ocbc/gbc/pdf/investors/quarterly-results/2022/OCBC 1Q22 CEO Presentation.pdf">x</a>
"""


class _FakeResponse:
    def __init__(self, text="", content=b"", status_code=200):
        self.text = text
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# ---------------------------------------------------------------------------
# Discovery + filtering
# ---------------------------------------------------------------------------

def test_discover_dbs_keeps_prose_docs_and_drops_tables(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **kw: _FakeResponse(text=_DBS_LISTING_HTML))
    results = discover("DBS", since_year=2023)
    names = [name for _url, name in results]

    assert any("analyst_transcript" in n for n in names)
    assert any("CEO_presentation" in n for n in names)
    # Basel Pillar 3 disclosures, financial statements and annual reports are
    # near-pure tables/boilerplate — ingest/earnings_extract.py would strip them to
    # nothing, so they must not be downloaded at all.
    assert not any("other_regulatory_disclosures" in n for n in names)
    assert not any("Bank Group FS" in n for n in names)
    assert not any("Annual Report" in n for n in names)


def test_discover_respects_since_year(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **kw: _FakeResponse(text=_DBS_LISTING_HTML))
    names_2023 = [n for _u, n in discover("DBS", since_year=2023)]
    names_2020 = [n for _u, n in discover("DBS", since_year=2020)]
    assert not any("1Q22" in n for n in names_2023)
    assert any("1Q22" in n for n in names_2020)


def test_discover_ocbc_url_encodes_spaces(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **kw: _FakeResponse(text=_OCBC_LISTING_HTML))
    results = discover("OCBC", since_year=2023)
    urls = [url for url, _name in results]
    assert urls, "expected at least one OCBC document"
    # Spaces must be percent-encoded or the request 404s.
    assert all(" " not in u for u in urls)
    assert any("%20" in u for u in urls)


def test_discover_ocbc_drops_financial_statements(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **kw: _FakeResponse(text=_OCBC_LISTING_HTML))
    names = [n for _u, n in discover("OCBC", since_year=2023)]
    assert not any("Condensed" in n for n in names)


def test_all_configured_sources_have_required_keys():
    for bank, cfg in SOURCES.items():
        assert {"listing_url", "href_pattern", "root"} <= set(cfg), f"{bank} config incomplete"


# ---------------------------------------------------------------------------
# Download behaviour
# ---------------------------------------------------------------------------

def test_fetch_skips_already_downloaded_files(monkeypatch, tmp_path):
    monkeypatch.setattr("ingest.earnings_fetch_ir.PDF_DIR", str(tmp_path))
    monkeypatch.setattr("requests.get", lambda *a, **kw: _FakeResponse(text=_DBS_LISTING_HTML))

    targets = discover("DBS", since_year=2023)
    bank_dir = tmp_path / "DBS"
    bank_dir.mkdir()
    for _url, name in targets:
        (bank_dir / name).write_bytes(b"%PDF-fake")

    stats = fetch("DBS", since_year=2023)
    assert stats["already_present"] == len(targets)
    assert stats["downloaded"] == 0


def test_fetch_rejects_non_pdf_response(monkeypatch, tmp_path):
    monkeypatch.setattr("ingest.earnings_fetch_ir.PDF_DIR", str(tmp_path))
    monkeypatch.setattr("ingest.earnings_fetch_ir._POLITE_DELAY_SECONDS", 0)

    def fake_get(url, **kw):
        if url.endswith(".pdf"):
            # An HTML error page served with a 200 — must not be saved as a PDF.
            return _FakeResponse(content=b"<html>error</html>")
        return _FakeResponse(text=_DBS_LISTING_HTML)

    monkeypatch.setattr("requests.get", fake_get)
    stats = fetch("DBS", since_year=2023)
    assert stats["downloaded"] == 0
    assert stats["failed"] > 0
    assert not list((tmp_path / "DBS").glob("*.pdf"))


def test_fetch_saves_valid_pdfs(monkeypatch, tmp_path):
    monkeypatch.setattr("ingest.earnings_fetch_ir.PDF_DIR", str(tmp_path))
    monkeypatch.setattr("ingest.earnings_fetch_ir._POLITE_DELAY_SECONDS", 0)

    def fake_get(url, **kw):
        if url.endswith(".pdf"):
            return _FakeResponse(content=b"%PDF-1.7 fake content")
        return _FakeResponse(text=_DBS_LISTING_HTML)

    monkeypatch.setattr("requests.get", fake_get)
    stats = fetch("DBS", since_year=2023)
    assert stats["downloaded"] > 0
    assert stats["failed"] == 0
    saved = list((tmp_path / "DBS").glob("*.pdf"))
    assert len(saved) == stats["downloaded"]


def test_fetch_listing_page_failure_is_reported_not_raised(monkeypatch, tmp_path):
    monkeypatch.setattr("ingest.earnings_fetch_ir.PDF_DIR", str(tmp_path))

    def boom(*a, **kw):
        raise ConnectionError("network down")

    monkeypatch.setattr("requests.get", boom)
    stats = fetch("DBS", since_year=2023)  # must not raise
    assert stats["failed"] == 1
    assert stats["discovered"] == 0
