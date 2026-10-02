"""
Earnings PDFs -> documents. The second stage of earnings ingestion.

The earnings pipeline is three modules, and this is the last of them:

    earnings_fetch_ir.py    downloads DBS's and OCBC's PDFs from their own
                            investor-relations sites
    earnings_fetch_uob.py   downloads UOB's from the Wayback Machine, because
                            UOB's IR site is WAF-blocked
    earnings_extract.py     THIS FILE - reads whatever is in
                            data/earnings_pdfs/<BANK>/, extracts prose,
                            discards numeric tables (FinBERT scores them as
                            noise), and upserts into `documents`

It does not care which fetcher produced a PDF, or whether a human put it there
by hand. Run it after either fetcher, or after dropping files in yourself.

Not part of the daily batch: the corpus only changes when a bank publishes,
which is twice a year plus business updates.

REQUIRES: pip install pdfplumber

USAGE:
  python -m ingest.earnings_extract
"""

import os
import re
from datetime import datetime

from ingest.base import BANKS
from ingest.db import make_doc_id, now_iso, upsert_documents

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE_DIR, "data", "earnings_pdfs")

# A line that's mostly digits/punctuation is almost certainly a financial-
# statement table row, not prose - drop it (see docs/DESIGN.md).
_NUMERIC_LINE = re.compile(r"^[\d\s.,()%$SGDsgd/-]{10,}$")
_MIN_PROSE_LEN = 40


# Filename -> announcement date. Lives here, with extraction, because that is
# the only place it is used and because it parses BOTH fetchers' naming
# conventions. It previously sat in the DBS/OCBC fetcher, which never called
# it, while handling UOB's format.
def _quarter_to_announcement_date(filename: str) -> str | None:
    """Maps a reporting period in the filename to the approximate date those
    results were announced, e.g. "2Q26_analyst_transcript.pdf" -> 2026-08-01.

    WHY THIS MATTERS: without it every earnings document gets stamped with
    ingestion time, which would drop the entire back-catalogue into the
    dashboard's 7d/30d rolling windows at once and badly distort recent
    sentiment. Approximate-but-right beats precise-and-wrong here; the day of
    month is nominal, the quarter is what actually matters for windowing.
    """
    # UOB's IR naming: "ceo-presentation-2q-2021.pdf" - lowercase q, four-digit
    # year. Checked BEFORE the two-digit form below, which would otherwise read
    # the "20" of "2021" as the year.
    m = re.search(r"([1-4])[qQ][-_ ]?(\d{4})", filename)
    if m:
        quarter, year = int(m.group(1)), int(m.group(2))
        month, year = {1: (5, year), 2: (8, year), 3: (11, year), 4: (2, year + 1)}[quarter]
        return f"{year:04d}-{month:02d}-01T00:00:00+00:00"
    # 1Q26 / 2Q26 / 3Q26 / 4Q26
    m = re.search(r"([1-4])Q(\d{2})", filename)
    if m:
        quarter, yy = int(m.group(1)), int(m.group(2))
        year = 2000 + yy
        month, year = {1: (5, year), 2: (8, year), 3: (11, year), 4: (2, year + 1)}[quarter]
        return f"{year:04d}-{month:02d}-01T00:00:00+00:00"
    # 1H26 (half-year, reported with Q2) / 2H26 (reported with Q4)
    m = re.search(r"([12])H(\d{2})", filename)
    if m:
        half, yy = int(m.group(1)), int(m.group(2))
        year = 2000 + yy
        return (f"{year:04d}-08-01T00:00:00+00:00" if half == 1
                else f"{year + 1:04d}-02-01T00:00:00+00:00")
    # FY25 - full-year results, announced early the following year
    m = re.search(r"FY(\d{2})", filename)
    if m:
        return f"{2000 + int(m.group(1)) + 1:04d}-02-01T00:00:00+00:00"
    return None


def _is_prose(line: str) -> bool:
    line = line.strip()
    if len(line) < _MIN_PROSE_LEN:
        return False
    digit_ratio = sum(c.isdigit() for c in line) / max(len(line), 1)
    if digit_ratio > 0.4:
        return False
    if _NUMERIC_LINE.match(line):
        return False
    return True


def extract_prose(pdf_path: str) -> list[str]:
    import pdfplumber  # imported here so a missing dependency doesn't block other ingest modules

    paragraphs = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                if _is_prose(line):
                    paragraphs.append(line.strip())
    return paragraphs


def pull() -> list[dict]:
    if not os.path.isdir(PDF_DIR):
        logger.warning(f"No {PDF_DIR} directory found.")
        logger.info("Create data/earnings_pdfs/<BANK>/*.pdf and re-run — "
              "see docs/DESIGN.md for where to source these (bank IR sites).")
        return []

    docs = []
    for bank in BANKS:
        bank_dir = os.path.join(PDF_DIR, bank)
        if not os.path.isdir(bank_dir):
            continue
        pdfs = [f for f in os.listdir(bank_dir) if f.lower().endswith(".pdf")]
        if not pdfs:
            continue
        logger.info(f"{bank}: {len(pdfs)} PDF(s) found")
        for fname in pdfs:
            path = os.path.join(bank_dir, fname)
            try:
                paragraphs = extract_prose(path)
            except Exception as e:
                logger.error(f"{fname}: ERROR extracting text — {e}")
                continue
            body = "\n".join(paragraphs)
            if not body.strip():
                logger.info(f"{fname}: no prose extracted (table-only or scanned PDF?)")
                continue
            logger.info(f"{fname}: {len(paragraphs)} prose lines extracted")
            docs.append({
                "doc_id": make_doc_id("earnings", f"{bank}:{fname}"),
                "source": "earnings",
                "source_detail": fname,
                "bank": bank,
                "doc_type": "earnings_release",
                "title": fname,
                "body": body,
                # Real reporting date parsed from the period in the filename
                # ("2Q26_..." -> 2026-08-01), NOT ingestion time. This matters:
                # stamping the whole back-catalogue with now() would drop every
                # historical earnings document into the dashboard's 7d/30d
                # rolling windows at once and badly distort recent sentiment.
                # Falls back to ingestion time only for files whose name carries
                # no recognisable period.
                "published_at": _quarter_to_announcement_date(fname) or now_iso(),
                "url": f"file://{path}",
                "ingested_at": now_iso(),
                "raw": {"filename": fname, "n_prose_lines": len(paragraphs)},
            })
    return docs


if __name__ == "__main__":
    setup_logging()
    logger.info(f"Run started: {datetime.now().isoformat()}")
    docs = pull()
    attempted, inserted = upsert_documents(docs)
    logger.info(f"Documents attempted: {attempted}  |  newly inserted: {inserted}  "
          f"|  already-seen (skipped): {attempted - inserted}")
