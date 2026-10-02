"""
Downloads UOB's quarterly earnings PDFs from the Wayback Machine.

Stage one of three, for one bank. Its sibling ingest/earnings_fetch_ir.py does
the same job for DBS and OCBC, and ingest/earnings_extract.py then turns
whatever landed in data/earnings_pdfs/<BANK>/ into `documents`.

WHY A SEPARATE FETCHER: DBS and OCBC publish their IR PDFs over plain HTTP and
ingest/earnings_fetch_ir.py downloads them directly. UOB sits behind an F5 WAF
that answers any scripted request with a redirect to a challenge page
("Request Redirected" / TS.request.ID), so the same approach returns a
199-byte stub instead of a listing. That left UOB with 4 earnings sentences
against DBS's 9,093, which invalidated every cross-bank comparison in the
project.

The Wayback Machine holds captures of the same PDFs at their original UOB
URLs, and archive.org is not behind that WAF. So this reads the CDX index
for UOB's IR PDF paths, picks the prose-rich documents, and downloads each
capture. The bytes are UOB's own published PDF; only the transport differs.
The archived URL is recorded so provenance stays traceable.

LIMITS worth knowing before relying on this:
  - Coverage thins out for recent quarters - the archive lags publication, so
    the last quarter or two is usually missing. Check the per-year counts the
    dry run prints.
  - A capture can be a WAF stub rather than a PDF. Downloads are verified by
    magic bytes and anything that is not a real PDF is discarded.

USAGE:
  python -m ingest.earnings_fetch_uob --dry-run      # list what would be fetched
  python -m ingest.earnings_fetch_uob                # download into data/earnings_pdfs/UOB/
"""

import argparse
import os
import re
import time

import requests

from config.logging_config import get_logger, setup_logging
from ingest.base import request_with_retries

logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "earnings_pdfs", "UOB")

CDX_URL = "http://web.archive.org/cdx/search/cdx"
UOB_PDF_PREFIX = "uobgroup.com/investor-relations/assets/pdfs/investor/financial*"

# Prose-rich documents, using UOB's own naming. Deliberately mirrors the
# intent of _KEEP_PATTERNS in earnings_fetch_ir.py: management commentary and
# press releases, not statement tables.
_KEEP = re.compile(r"ceo-presentation|cfo-presentation|ceo-slides|cfo-slides|"
                   r"newsrelease|news-release|performance-highlights|financial-updates",
                   re.IGNORECASE)

# Numeric or regulatory documents. ingest/earnings_extract.py drops lines that are
# >40% digits, so these would survive download only to be stripped to nothing.
_SKIP = re.compile(r"pillar-?3|regulatory-disclosures|selected-f|corp-factsheet|"
                   r"condensed-financial|interim-financial|key-fea|gp-financial|"
                   r"-malay|-tamil|-zh|-chinese",
                   re.IGNORECASE)

_PDF_MAGIC = b"%PDF"
_REQUEST_DELAY = 1.0  # archive.org is a donated public service; don't hammer it


def discover(from_year: int = 2020, to_year: int = 2026) -> list[dict]:
    """CDX lookup for archived UOB IR PDFs worth ingesting."""
    params = {
        "url": UOB_PDF_PREFIX,
        "output": "text",
        "fl": "original,timestamp,statuscode",
        "collapse": "urlkey",
        "filter": "statuscode:200",
        "from": str(from_year),
        "to": str(to_year),
        "limit": "5000",
    }
    # CDX rate-limits and returns 503 under load; request_with_retries backs
    # off rather than failing the whole run on a transient refusal.
    resp = request_with_retries(CDX_URL, params, timeout=90)

    seen, entries = set(), []
    for line in resp.text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        url, timestamp = parts[0], parts[1]
        # Some captures carry tracking parameters ("...pdf?utm_campaign=..."),
        # which would otherwise become part of the saved filename and produce a
        # second copy of a document already collected.
        name = url.rsplit("/", 1)[-1].split("?", 1)[0]

        year_match = re.search(r"/financial/(\d{4})/", url)
        if not year_match or not (from_year <= int(year_match.group(1)) <= to_year):
            continue
        if _SKIP.search(name) or not _KEEP.search(name):
            continue
        if name in seen:          # same document captured many times
            continue
        seen.add(name)
        entries.append({"url": url, "timestamp": timestamp, "filename": name,
                        "year": int(year_match.group(1))})

    entries.sort(key=lambda e: (e["year"], e["filename"]))
    return entries


def download(entries: list[dict], out_dir: str = OUT_DIR) -> dict:
    """Download each capture, skipping any that is not really a PDF."""
    os.makedirs(out_dir, exist_ok=True)
    saved = skipped = failed = 0

    for entry in entries:
        dest = os.path.join(out_dir, entry["filename"])
        if os.path.exists(dest):
            skipped += 1
            continue

        # The id_ suffix asks for the original bytes without archive.org's
        # navigation wrapper injected into them.
        wayback_url = f"https://web.archive.org/web/{entry['timestamp']}id_/{entry['url']}"
        try:
            resp = requests.get(wayback_url, timeout=120)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("%s: download failed — %s", entry["filename"], e)
            failed += 1
            continue

        if not resp.content.startswith(_PDF_MAGIC):
            # Usually a WAF stub or an archive error page captured as if it
            # were the document. Writing it would produce a file that fails
            # extraction much later, with a confusing message.
            logger.warning("%s: not a PDF (%d bytes) — discarded",
                           entry["filename"], len(resp.content))
            failed += 1
            continue

        with open(dest, "wb") as f:
            f.write(resp.content)
        logger.info("%s (%.0f KB)", entry["filename"], len(resp.content) / 1024)
        saved += 1
        time.sleep(_REQUEST_DELAY)

    return {"saved": saved, "already_present": skipped, "failed": failed,
            "out_dir": out_dir}


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-year", type=int, default=2020)
    parser.add_argument("--to-year", type=int, default=2026)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    found = discover(args.from_year, args.to_year)
    if args.limit:
        found = found[:args.limit]

    by_year: dict[int, int] = {}
    for e in found:
        by_year[e["year"]] = by_year.get(e["year"], 0) + 1
    logger.info("%d document(s) to fetch; per year: %s", len(found), dict(sorted(by_year.items())))

    if args.dry_run:
        for e in found:
            print(f"  {e['year']}  {e['filename']}")
    else:
        print(download(found))
