"""
Quarterly earnings release ingestion, per MVP plan Phase 1b.

There is no free API for SGX company announcements worth building against.
This is a ONE-TIME MANUAL CORPUS: a team member downloads results announcements
/ investor presentations from each bank's investor-relations site and drops the
PDFs into data/earnings_pdfs/<BANK>/*.pdf. This script extracts text, discards
numeric tables (FinBERT scores them as noise), and ingests the prose sections.

This corpus is static — run it once after PDFs are added, not part of the
daily batch.

REQUIRES: pip install pdfplumber

USAGE:
  python -m ingest.earnings
"""

import os
import re
from datetime import datetime

from ingest.base import BANKS
from ingest.db import make_doc_id, now_iso, upsert_documents

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE_DIR, "data", "earnings_pdfs")

# A line that's mostly digits/punctuation is almost certainly a financial-
# statement table row, not prose — drop it (see plan Phase 1b).
_NUMERIC_LINE = re.compile(r"^[\d\s.,()%$SGDsgd/-]{10,}$")
_MIN_PROSE_LEN = 40


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
        print(f"[Earnings] No {PDF_DIR} directory found.")
        print("           Create data/earnings_pdfs/<BANK>/*.pdf and re-run — "
              "see plan Phase 1b for where to source these (bank IR sites).")
        return []

    docs = []
    for bank in BANKS:
        bank_dir = os.path.join(PDF_DIR, bank)
        if not os.path.isdir(bank_dir):
            continue
        pdfs = [f for f in os.listdir(bank_dir) if f.lower().endswith(".pdf")]
        if not pdfs:
            continue
        print(f"[Earnings] {bank}: {len(pdfs)} PDF(s) found")
        for fname in pdfs:
            path = os.path.join(bank_dir, fname)
            try:
                paragraphs = extract_prose(path)
            except Exception as e:
                print(f"    -> {fname}: ERROR extracting text — {e}")
                continue
            body = "\n".join(paragraphs)
            if not body.strip():
                print(f"    -> {fname}: no prose extracted (table-only or scanned PDF?)")
                continue
            print(f"    -> {fname}: {len(paragraphs)} prose lines extracted")
            docs.append({
                "doc_id": make_doc_id("earnings", f"{bank}:{fname}"),
                "source": "earnings",
                "source_detail": fname,
                "bank": bank,
                "doc_type": "earnings_release",
                "title": fname,
                "body": body,
                # Earnings PDFs don't carry a reliable machine-readable date in
                # the file itself; the team should rename files with the
                # quarter (e.g. DBS_2025Q3.pdf) and this date is a placeholder
                # until Phase 2 preprocessing parses it from the filename/text.
                "published_at": now_iso(),
                "url": f"file://{path}",
                "ingested_at": now_iso(),
                "raw": {"filename": fname, "n_prose_lines": len(paragraphs)},
            })
    return docs


if __name__ == "__main__":
    print(f"Run started: {datetime.now().isoformat()}\n")
    docs = pull()
    attempted, inserted = upsert_documents(docs)
    print(f"\nDocuments attempted: {attempted}  |  newly inserted: {inserted}  "
          f"|  already-seen (skipped): {attempted - inserted}")
