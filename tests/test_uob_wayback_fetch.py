"""
Tests for ingest/uob_wayback_fetch.py.

UOB's IR site is behind a WAF that answers scripted requests with a
challenge-page stub, so its PDFs are fetched from the Wayback Machine
instead. Two behaviours carry the risk and are tested here:

  - selecting the prose-rich documents, since downloading statement tables
    wastes bandwidth on text ingest/earnings.py will strip to nothing;
  - refusing anything that is not really a PDF, because a captured WAF stub
    saved as a .pdf fails much later with a confusing error.

No test touches the network.
"""

from unittest.mock import Mock, patch

import pytest

from ingest.uob_wayback_fetch import discover, download

CDX_SAMPLE = """https://www.uobgroup.com/investor-relations/assets/pdfs/investor/financial/2021/ceo-presentation-2q-2021.pdf 20211028181913 200
https://www.uobgroup.com/investor-relations/assets/pdfs/investor/financial/2021/cfo-presentation-2q-2021.pdf 20211025180305 200
https://www.uobgroup.com/investor-relations/assets/pdfs/investor/financial/2021/newsrelease-2q-2021-results.pdf 20211028181914 200
https://www.uobgroup.com/investor-relations/assets/pdfs/investor/financial/2021/performance-highlights-1q-2021.pdf 20210723174458 200
https://www.uobgroup.com/investor-relations/assets/pdfs/investor/financial/2021/pillar3-disclosures-2q-2021.pdf 20211028181915 200
https://www.uobgroup.com/investor-relations/assets/pdfs/investor/financial/2021/corp-factsheet-2q-2021.pdf 20211017094134 200
https://www.uobgroup.com/investor-relations/assets/pdfs/investor/financial/2021/selected-fs-fy2021-tamil.pdf 20211017094135 200
https://www.uobgroup.com/investor-relations/assets/pdfs/investor/financial/2021/condensed-financial-statement-4q-2021.pdf 20220420024904 200
https://www.uobgroup.com/investor-relations/assets/pdfs/investor/financial/2015/ceo-presentation-2q-2015.pdf 20150801000000 200
"""


def _mock_cdx(text=CDX_SAMPLE):
    resp = Mock()
    resp.text = text
    resp.raise_for_status = Mock()
    return resp


def test_discover_keeps_only_prose_rich_documents():
    with patch("ingest.uob_wayback_fetch.request_with_retries", return_value=_mock_cdx()):
        names = {e["filename"] for e in discover(2020, 2026)}
    assert names == {
        "ceo-presentation-2q-2021.pdf",
        "cfo-presentation-2q-2021.pdf",
        "newsrelease-2q-2021-results.pdf",
        "performance-highlights-1q-2021.pdf",
    }


@pytest.mark.parametrize("excluded", [
    "pillar3-disclosures-2q-2021.pdf",      # regulatory, numeric
    "corp-factsheet-2q-2021.pdf",           # numeric summary
    "selected-fs-fy2021-tamil.pdf",         # statement tables, and not English
    "condensed-financial-statement-4q-2021.pdf",
])
def test_discover_excludes_numeric_documents(excluded):
    with patch("ingest.uob_wayback_fetch.request_with_retries", return_value=_mock_cdx()):
        assert excluded not in {e["filename"] for e in discover(2020, 2026)}


def test_discover_respects_the_year_range():
    with patch("ingest.uob_wayback_fetch.request_with_retries", return_value=_mock_cdx()):
        assert "ceo-presentation-2q-2015.pdf" not in {e["filename"] for e in discover(2020, 2026)}
        assert "ceo-presentation-2q-2015.pdf" in {e["filename"] for e in discover(2015, 2026)}


def test_discover_strips_tracking_parameters_from_the_filename():
    """A capture carrying ?utm_campaign=... would otherwise be saved as a
    second copy of a document already collected, under an unusable name."""
    line = ("https://www.uobgroup.com/investor-relations/assets/pdfs/investor/financial/"
            "2020/performance-highlights-3q-2020.pdf?utm_campaign=x&utm_medium=email 20201103233008 200\n")
    with patch("ingest.uob_wayback_fetch.request_with_retries",
               return_value=_mock_cdx(line)):
        entries = discover(2020, 2026)
    assert [e["filename"] for e in entries] == ["performance-highlights-3q-2020.pdf"]


def test_discover_deduplicates_repeat_captures():
    doubled = CDX_SAMPLE + CDX_SAMPLE
    with patch("ingest.uob_wayback_fetch.request_with_retries", return_value=_mock_cdx(doubled)):
        entries = discover(2020, 2026)
    assert len(entries) == len({e["filename"] for e in entries})


# ---------------------------------------------------------------------------
# download()
# ---------------------------------------------------------------------------

def _entry(name="ceo-presentation-2q-2021.pdf"):
    return [{"url": f"https://www.uobgroup.com/x/{name}", "timestamp": "20211028181913",
             "filename": name, "year": 2021}]


def test_download_writes_a_real_pdf(tmp_path):
    resp = Mock(content=b"%PDF-1.5 real content here", raise_for_status=Mock())
    with patch("ingest.uob_wayback_fetch.requests.get", return_value=resp):
        result = download(_entry(), out_dir=str(tmp_path))
    assert result["saved"] == 1
    assert (tmp_path / "ceo-presentation-2q-2021.pdf").read_bytes().startswith(b"%PDF")


def test_download_discards_a_waf_stub(tmp_path):
    """The exact failure this guards against: the archive captured the WAF's
    challenge page instead of the document. Saving it produces a .pdf that
    only fails later, during extraction, with an unrelated-looking error."""
    stub = b"<html><head><title>Request Redirected</title></head></html>"
    resp = Mock(content=stub, raise_for_status=Mock())
    with patch("ingest.uob_wayback_fetch.requests.get", return_value=resp):
        result = download(_entry(), out_dir=str(tmp_path))
    assert result["saved"] == 0
    assert result["failed"] == 1
    assert list(tmp_path.iterdir()) == []


def test_download_skips_files_already_present(tmp_path):
    (tmp_path / "ceo-presentation-2q-2021.pdf").write_bytes(b"%PDF already here")
    with patch("ingest.uob_wayback_fetch.requests.get") as get:
        result = download(_entry(), out_dir=str(tmp_path))
    get.assert_not_called()
    assert result["already_present"] == 1


def test_download_survives_a_network_error(tmp_path):
    with patch("ingest.uob_wayback_fetch.requests.get", side_effect=OSError("boom")):
        result = download(_entry(), out_dir=str(tmp_path))
    assert result == {"saved": 0, "already_present": 0, "failed": 1, "out_dir": str(tmp_path)}
