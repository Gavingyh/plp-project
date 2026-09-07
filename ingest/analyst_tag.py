"""
Analyst-consensus tagging over the news stream (docs/DESIGN.md — labeled
1c/1d in the plan text, "open decision, flag to mentor").

A genuine fourth ingestion source for analyst consensus reports isn't
practically buildable for this MVP: full analyst PDFs sit behind brokerage
entitlements, and the obvious free alternatives are bot-protected against
scraping —

  - sgx.com serves a static "unsupported browser" shell to any non-browser
    HTTP client regardless of User-Agent (confirmed: HTTP 200, but the
    body is the compatibility-warning shell, not the article).
  - sginvestors.io (an analyst-report aggregator) returns an empty HTTP 202
    Cloudflare challenge response to a plain request.

Both would require a full headless browser (Playwright) to scrape, which is
fragile, heavy for this MVP, and sits in much greyer ToS territory than
reading a public feed. So: financial media routinely reports analyst actions
verbatim ("Maintains BUY, raises TP to S$X on NIM resilience"), and this
module tags those mentions inside documents already ingested from NewsAPI /
Alpha Vantage rather than adding a new source.

THIS IS A PROXY, NOT A REPLACEMENT for full analyst reports — say so plainly
in the report/dashboard, per the plan's disclosure requirement. It only
flags documents/sentences that quote or describe an analyst action; it does
not have access to full report reasoning.

USAGE:
  python -m ingest.analyst_tag   # backfills has_analyst_view for existing docs
"""

import re
from datetime import datetime

from ingest.db import get_connection, init_db

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

# Common SG/regional brokerage and research-house names that show up when
# local media reports an analyst call. Not exhaustive — extend as false
# negatives turn up during Phase 4 labeling review.
_BROKERS = [
    "DBS Group Research", "UOB Kay Hian", "OCBC Investment Research",
    "CGS International", "CGS-CIMB", "Maybank", "RHB", "Phillip Securities",
    "PhillipCapital", "Citi", "Citigroup", "Goldman Sachs", "Morgan Stanley",
    "JPMorgan", "J.P. Morgan", "Jefferies", "Macquarie", "CLSA", "HSBC",
    "Nomura", "UBS", "Barclays", "Bank of America", "BofA",
]

_ACTION_PATTERN = re.compile(
    r"\b(BUY|HOLD|SELL|ADD|REDUCE|OVERWEIGHT|UNDERWEIGHT|NEUTRAL|OUTPERFORM|"
    r"UNDERPERFORM|target price|TP of|raises? TP|cuts? TP|upgrades?|downgrades?|"
    r"maintains? (?:its |a )?(?:BUY|HOLD|SELL)|price target)\b",
    re.IGNORECASE,
)
_BROKER_PATTERN = re.compile("|".join(re.escape(b) for b in _BROKERS), re.IGNORECASE)


def is_analyst_view(text: str) -> bool:
    """A document counts as carrying an analyst view if it names a broker/research
    house AND uses rating/action language — either alone is too weak a signal
    (e.g. a broker named only as the article's own source attribution)."""
    if not text:
        return False
    return bool(_BROKER_PATTERN.search(text) and _ACTION_PATTERN.search(text))


def backfill() -> int:
    """Adds/updates a has_analyst_view flag on existing documents. Idempotent —
    safe to re-run after new documents are ingested."""
    init_db()
    conn = get_connection()
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN has_analyst_view INTEGER DEFAULT 0")
    except Exception:
        pass  # column already exists — fine, this is meant to be re-run
    try:
        rows = conn.execute(
            "SELECT doc_id, title, body FROM documents WHERE source IN ('newsapi','alphavantage')"
        ).fetchall()
        flagged = 0
        for doc_id, title, body in rows:
            text = f"{title or ''}. {body or ''}"
            if is_analyst_view(text):
                conn.execute("UPDATE documents SET has_analyst_view = 1 WHERE doc_id = ?", (doc_id,))
                flagged += 1
        conn.commit()
        return flagged
    finally:
        conn.close()


if __name__ == "__main__":
    setup_logging()
    logger.info(f"Run started: {datetime.now().isoformat()}")
    n = backfill()
    logger.info(f"Flagged {n} documents as carrying an analyst view (proxy tag, see module docstring).")
