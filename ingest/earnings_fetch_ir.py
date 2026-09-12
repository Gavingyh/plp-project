"""
Downloads DBS's and OCBC's quarterly earnings PDFs from their own
investor-relations sites into data/earnings_pdfs/<BANK>/.

Stage one of three. Its sibling ingest/earnings_fetch_uob.py does the same job
for UOB, and ingest/earnings_extract.py then turns whatever landed in those
directories into `documents`.

WHY THESE SOURCES, NOT SGX: SGX doesn't host what this project needs. SGXNet
carries company announcements (which is what "earnings from SGX" would
actually mean) and SGX's own commentary — third-party analyst reports are
brokerage IP behind client entitlements and aren't on SGX at all. Meanwhile
SGX's own API sits behind a WAF returning 403, while DBS and OCBC publish the
exact same earnings material openly on their IR sites with no bot protection
at all (confirmed: plain requests, HTTP 200, real content). So this
fetcher needs no browser automation, no stealth/anti-detection tooling, and
no ToS grey area — it reads openly published pages the way any reader would.

UOB IS NOT HERE, IT HAS ITS OWN FETCHER: uobgroup.com redirects non-browser
clients to a WAF challenge page (confirmed against the live site). Rather than
escalate to fingerprint-spoofing to defeat that, UOB's PDFs come from the
Wayback Machine instead — see ingest/earnings_fetch_uob.py. Same documents,
different transport. run() says so explicitly rather than failing silently.

BONUS FIND — the analyst transcripts: DBS publishes `*_analyst_transcript.pdf`
every quarter: the edited transcript of its analyst call, with named
brokerage analysts (Citi, etc.) asking management about NIM, asset quality,
dividends and guidance, and the CEO/CFO answering. That is genuine analyst
voice on exactly the aspects this project's taxonomy targets, openly
published — much closer to the original "analyst reports" goal than anything
scraping SGX would have produced, and it fills the gap Reddit can't
(r/singaporefi discusses banking products, not net interest margin).

USAGE:
  python -m ingest.earnings_fetch_ir                 # 2023+ (default)
  python -m ingest.earnings_fetch_ir --since-year 2020
  python -m ingest.earnings_fetch_ir --dry-run       # list what it would fetch
"""

import argparse
import os
import re
import time
from urllib.parse import quote, urljoin

import requests

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(BASE_DIR, "data", "earnings_pdfs")

_USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
_TIMEOUT = 60
_POLITE_DELAY_SECONDS = 1.0

# Listing page + a regex matching that bank's PDF hrefs on it.
SOURCES = {
    "DBS": {
        "listing_url": "https://www.dbs.com/investors/financials/quarterly-financials",
        "href_pattern": re.compile(
            r'/iwov-resources/images/investors/quarterly-financials/(\d{4})/([^"\']+?\.pdf)'),
        "root": "https://www.dbs.com",
    },
    "OCBC": {
        "listing_url": "https://www.ocbc.com/group/investors/financials",
        "href_pattern": re.compile(
            r'/iwov-resources/sg/ocbc/gbc/pdf/investors/quarterly-results/(\d{4})/([^"\']+?\.pdf)'),
        "root": "https://www.ocbc.com",
    },
}

# Prose-rich documents worth ingesting. Everything else is dropped — see
# _SKIP_PATTERNS below for what and why.
_KEEP_PATTERNS = re.compile(
    r"analyst_transcript|CEO_presentation|CFO_presentation|press_statement|"
    r"performance_summary|trading_update|media_transcript|media_briefing_transcript|"
    r"CEO Presentation|Results Presentation|Results Press Release|Results Highlights|"
    r"Media Release",
    re.IGNORECASE,
)

# Financial-statement PDFs are almost entirely numeric tables; ingest/earnings_extract.py
# would strip them to nearly nothing anyway (it drops lines >40% digits), so
# downloading them is wasted bandwidth and wasted extraction time. Basel Pillar 3
# "other regulatory disclosures" are the same. Annual reports are 200+ pages of
# mostly boilerplate and tables — excluded from the MVP scope deliberately.
_SKIP_PATTERNS = re.compile(
    r"Condensed|Interim FS|Bank Group FS|other_regulatory_disclosures|"
    r"Annual Report|notice-of-agm|letter-to-shareholders",
    re.IGNORECASE,
)


def discover(bank: str, since_year: int) -> list[tuple[str, str]]:
    """Returns [(absolute_pdf_url, local_filename), ...] for one bank.

    Scrapes the bank's own listing page rather than hardcoding URLs, so new
    quarters are picked up automatically as they're published.
    """
    cfg = SOURCES[bank]
    resp = requests.get(cfg["listing_url"], headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT)
    resp.raise_for_status()

    found = {}
    for match in cfg["href_pattern"].finditer(resp.text):
        year, filename = int(match.group(1)), match.group(2)
        if year < since_year:
            continue
        if _SKIP_PATTERNS.search(filename) or not _KEEP_PATTERNS.search(filename):
            continue
        # Filenames contain spaces on OCBC's site — quote the path, not the whole URL.
        url = urljoin(cfg["root"], quote(match.group(0)))
        local_name = f"{year}_{filename.replace('/', '_')}"
        found[local_name] = url
    return sorted((url, name) for name, url in found.items())


def fetch(bank: str, since_year: int = 2023, dry_run: bool = False) -> dict:
    stats = {"discovered": 0, "downloaded": 0, "already_present": 0, "failed": 0}
    try:
        targets = discover(bank, since_year)
    except Exception as e:
        logger.error(f"{bank}: could not read listing page — {e}")
        stats["failed"] += 1
        return stats

    stats["discovered"] = len(targets)
    bank_dir = os.path.join(PDF_DIR, bank)
    os.makedirs(bank_dir, exist_ok=True)

    for url, local_name in targets:
        dest = os.path.join(bank_dir, local_name)
        if os.path.exists(dest):
            stats["already_present"] += 1
            continue
        if dry_run:
            logger.info(f"{bank}: WOULD FETCH {local_name}")
            continue
        try:
            resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT)
            resp.raise_for_status()
            if not resp.content.startswith(b"%PDF"):
                logger.warning(f"{bank}: {local_name} is not a PDF (got "
                      f"{resp.content[:20]!r}) — skipping")
                stats["failed"] += 1
                continue
            with open(dest, "wb") as f:
                f.write(resp.content)
            logger.info(f"{bank}: {local_name} ({len(resp.content) // 1024}KB)")
            stats["downloaded"] += 1
        except Exception as e:
            logger.error(f"{bank}: FAILED {local_name} — {e}")
            stats["failed"] += 1
        time.sleep(_POLITE_DELAY_SECONDS)
    return stats


def run(since_year: int = 2023, dry_run: bool = False) -> dict:
    all_stats = {}
    for bank in SOURCES:
        logger.info(f"--- {bank} ---")
        all_stats[bank] = fetch(bank, since_year=since_year, dry_run=dry_run)

    logger.info("--- UOB ---")
    logger.info("UOB: not handled here — uobgroup.com sits behind a WAF that "
                "rejects non-browser clients. Run "
                "`python -m ingest.earnings_fetch_uob` instead; it fetches the "
                "same PDFs from the Wayback Machine into "
                f"{os.path.join(PDF_DIR, 'UOB')}/.")
    return all_stats


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Fetch earnings PDFs from bank IR sites")
    parser.add_argument("--since-year", type=int, default=2023)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stats = run(since_year=args.since_year, dry_run=args.dry_run)
    logger.info(f"{'=' * 50}")
    for bank, s in stats.items():
        logger.info(f"  {bank:6s} discovered={s['discovered']:3d} downloaded={s['downloaded']:3d} "
              f"already_present={s['already_present']:3d} failed={s['failed']:3d}")
    logger.info(f"{'=' * 50}")
    logger.info("Next: python -m ingest.earnings_extract   (extracts prose and ingests into documents)")
