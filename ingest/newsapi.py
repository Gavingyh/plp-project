"""
NewsAPI ingestion (free tier: 100 req/day, ~1 month lookback only).

Refactored from the original news_pull.py to write into the shared `documents`
table (ingest/db.py) instead of an overwrite-CSV, so repeated runs accumulate
history instead of replacing it.

Known free-tier limitation (see MVP plan, finding (c)): the `content` field is
truncated to ~200 chars with a "[+N chars]" suffix. We therefore only rely on
title + description as usable text — do not expect long-form content here.

USAGE:
  python -m ingest.newsapi
"""

import os
import time
from datetime import datetime

from dotenv import load_dotenv

from ingest.base import BANKS, request_with_retries, resolve_bank
from ingest.db import make_doc_id, now_iso, upsert_documents

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")

# Free tier is 100 req/day. 4 pages x 3 banks = 12 requests per run — cheap
# relative to quota, but paginating fully (DBS alone reported 349 totalResults
# on a single-page pull) recovers volume the original single-page pull missed.
MAX_PAGES = 4


def pull() -> list[dict]:
    if not NEWSAPI_KEY:
        logger.warning("Skipped — set NEWSAPI_KEY in .env to run this.")
        return []

    docs = []
    for bank, queries in BANKS.items():
        # Exclude the bare short alias (e.g. plain "DBS") from the query terms —
        # confirmed live to pull in unrelated global news (US college football
        # articles) that happen to contain the substring "DBS" with no
        # Singapore/banking context at all. The bare alias is kept in BANKS for
        # in-text detection on already-relevant text (Reddit etc.), just not
        # for driving an unscoped global search. Also AND-gate on Singapore
        # context to keep the query genuinely selective.
        specific_terms = [q for q in queries if " " in q or "." in q]  # drops bare "DBS"/"OCBC"/"UOB"
        bank_query = " OR ".join(f'"{q}"' for q in specific_terms)
        query = f'({bank_query}) AND (Singapore OR SGX)'
        url = "https://newsapi.org/v2/everything"

        total_this_bank = 0
        for page in range(1, MAX_PAGES + 1):
            params = {
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 100,
                "page": page,
                "apiKey": NEWSAPI_KEY,
            }
            try:
                resp = request_with_retries(url, params)
                data = resp.json()
                articles = data.get("articles", [])
                total_results = data.get("totalResults", "?")
                logger.info(f"{bank} page {page}: {len(articles)} articles "
                      f"(totalResults reported: {total_results})")
                for a in articles:
                    title = a.get("title") or ""
                    description = a.get("description") or ""
                    body = f"{title}. {description}".strip(". ")
                    if not body:
                        continue
                    resolved_bank = resolve_bank(body, fallback=bank)
                    docs.append({
                        "doc_id": make_doc_id("newsapi", a.get("url") or title),
                        "source": "newsapi",
                        "source_detail": a.get("source", {}).get("name"),
                        "bank": resolved_bank,
                        "doc_type": "article",
                        "title": title,
                        "body": body,
                        "published_at": a.get("publishedAt") or now_iso(),
                        "url": a.get("url") or "",
                        "ingested_at": now_iso(),
                        "raw": a,
                    })
                total_this_bank += len(articles)
                # Stop paginating once we've covered totalResults, or the page
                # came back short (no more results), or a free-tier page-depth
                # limit kicks in (NewsAPI's developer plan restricts how far
                # back `page` can go regardless of pageSize).
                if len(articles) < 100 or (isinstance(total_results, int) and total_this_bank >= total_results):
                    break
            except Exception as e:
                logger.error(f"{bank} page {page}: ERROR — {e}")
                break  # free-tier page-depth limits surface as errors here — stop, don't retry deeper pages
            time.sleep(1)  # be polite to free tier
        time.sleep(1)

    return docs


if __name__ == "__main__":
    setup_logging()
    logger.info(f"Run started: {datetime.now().isoformat()}")
    docs = pull()
    attempted, inserted = upsert_documents(docs)
    logger.info(f"Documents attempted: {attempted}  |  newly inserted: {inserted}  "
          f"|  already-seen (skipped): {attempted - inserted}")
