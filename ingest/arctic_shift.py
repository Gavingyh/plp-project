"""
Reddit ingestion via Arctic Shift (https://github.com/ArthurHeitmann/arctic_shift),
replacing reddit_pull.py / PRAW because Reddit has not approved this project's API
application.

Design decisions here are backed by live testing against the real API
(see .project-context/plan/mvp-implementation-plan.md, Phase 1c), not assumption:

  - Keyword search (`&query=...`) times out (HTTP 422) on active subreddits.
    So: harvest whole subreddits by date window, filter for bank mentions locally.
  - No page token exists — paginate by moving `after` to `last_row.created_utc + 1`,
    which requires `sort=asc`.
  - r/SingaporeInvestments has had no posts since 2023-10-01 (effectively dead) —
    kept only for pre-2023-10 historical pulls, not the daily batch.
  - r/singapore returned 0/100 bank-mentioning posts in testing — general-interest
    noise, dropped entirely.
  - r/singaporefi is the primary source: measured 775 bank-mentioning posts +
    662+ bank-mentioning comments over 12 months (comments undercounted — see plan).

USAGE:
  python -m ingest.arctic_shift                 # backfill + upsert into data/plp.db
  python -m ingest.arctic_shift --since 2025-09-01
"""

import argparse
import json
import time
from datetime import datetime, timedelta, timezone

import requests

from ingest.base import BANKS, resolve_bank
from ingest.db import make_doc_id, now_iso, upsert_documents

BASE_URL = "https://arctic-shift.photon-reddit.com/api"

# r/SingaporeInvestments is included for historical (pre-2023-10) pulls only —
# see module docstring. r/singapore and r/investing were both tested and
# dropped: 0 bank-mentioning items out of 7,000+ fetched across two separate
# samples (90-day and 12-day) — pure noise for this project, and r/investing's
# comment volume in particular is large enough that fetching it for zero
# payoff would dominate ingestion time.
SUBREDDITS = ["singaporefi", "SingaporeInvestments"]

PAGE_LIMIT = 100          # Arctic Shift's max per page
MAX_PAGES_PER_WINDOW = 500  # safety cap so a runaway window can't loop forever
REQUEST_TIMEOUT = 60
POLITE_DELAY_SECONDS = 0.3


def _get(endpoint: str, **params) -> list[dict]:
    """GET one page from Arctic Shift. On the documented 422 "timeout" response,
    return [] rather than raising — callers narrow the window and move on."""
    url = f"{BASE_URL}/{endpoint}/search"
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        print(f"    -> request error: {e}")
        return []
    if resp.status_code == 429:
        wait = int(resp.headers.get("Retry-After", 5))
        print(f"    -> rate limited, waiting {wait}s")
        time.sleep(wait)
        return _get(endpoint, **params)
    if resp.status_code != 200:
        # Includes the documented 422 timeout case for keyword search / heavy queries.
        print(f"    -> {endpoint} search returned {resp.status_code}: {resp.text[:120]}")
        return []
    try:
        return resp.json().get("data") or []
    except json.JSONDecodeError:
        return []


def _harvest_window(endpoint: str, subreddit: str, after: str, before: str, fields: str) -> list[dict]:
    """Page through one subreddit/date-window via the after-cursor method
    (no page token exists in this API)."""
    rows, cursor = [], after
    for _ in range(MAX_PAGES_PER_WINDOW):
        page = _get(endpoint, subreddit=subreddit, after=cursor, before=before,
                    limit=PAGE_LIMIT, sort="asc", fields=f"{fields},created_utc")
        if not page:
            break
        rows.extend(page)
        cursor = str(page[-1]["created_utc"] + 1)
        time.sleep(POLITE_DELAY_SECONDS)
        if len(page) < PAGE_LIMIT:
            break
    return rows


def _to_documents(rows: list[dict], subreddit: str, doc_type: str, text_field: str) -> list[dict]:
    docs = []
    for r in rows:
        if doc_type == "submission":
            # Link-only posts have an empty selftext but a bank can still be
            # named in the title — build full_text from both rather than
            # requiring selftext, which would silently drop those posts.
            title = r.get("title") or ""
            selftext = (r.get("selftext") or "").strip()
            full_text = f"{title}. {selftext}" if selftext else title
        else:
            title = None
            full_text = (r.get(text_field) or "").strip()
        if not full_text.strip():
            continue
        bank = resolve_bank(full_text)
        if bank is None:
            continue  # no bank mentioned at all — not useful for this project
        native_id = r.get("id") or str(r.get("created_utc"))
        published_at = datetime.fromtimestamp(r["created_utc"], tz=timezone.utc).isoformat()
        if doc_type == "submission":
            url = r.get("url") or f"https://www.reddit.com/r/{subreddit}/comments/{native_id}/"
        else:
            # Comments carry no direct URL field from the API; build one from
            # the parent submission id (link_id, e.g. "t3_1w2lszc") + comment id.
            link_id = (r.get("link_id") or "").removeprefix("t3_")
            url = (f"https://www.reddit.com/r/{subreddit}/comments/{link_id}/comment/{native_id}/"
                   if link_id else f"https://www.reddit.com/r/{subreddit}/")
        docs.append({
            "doc_id": make_doc_id("arctic_shift", f"{doc_type}:{native_id}"),
            "source": "arctic_shift",
            "source_detail": subreddit,
            "bank": bank,
            "doc_type": doc_type,
            "title": title,
            "body": full_text,
            "published_at": published_at,
            "url": url,
            "ingested_at": now_iso(),
            "raw": r,
        })
    return docs


def pull(since: str | None = None, until: str | None = None) -> list[dict]:
    """Backfill (or incremental pull with `since`) across SUBREDDITS.

    Note per Arctic Shift's own docs: scores/comment counts are incomplete for
    ~36h after posting — treat very recent engagement metrics as provisional.
    """
    until = until or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    since = since or "2020-01-01"  # effectively "all history the archive has"

    all_docs = []
    for sub in SUBREDDITS:
        print(f"[ArcticShift] r/{sub}: pulling posts {since} .. {until}")
        posts = _harvest_window("posts", sub, since, until, "title,selftext,url,id")
        post_docs = _to_documents(posts, sub, "submission", "selftext")
        print(f"    {len(posts)} posts fetched, {len(post_docs)} bank-mentioning")

        print(f"[ArcticShift] r/{sub}: pulling comments {since} .. {until}")
        comments = _harvest_window("comments", sub, since, until, "body,link_id,id")
        comment_docs = _to_documents(comments, sub, "comment", "body")
        print(f"    {len(comments)} comments fetched, {len(comment_docs)} bank-mentioning")

        all_docs.extend(post_docs)
        all_docs.extend(comment_docs)

    return all_docs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Reddit data via Arctic Shift")
    parser.add_argument("--since", default=None, help="YYYY-MM-DD, default = full backfill")
    parser.add_argument("--until", default=None, help="YYYY-MM-DD, default = today")
    args = parser.parse_args()

    print(f"Run started: {datetime.now().isoformat()}\n")
    docs = pull(since=args.since, until=args.until)
    attempted, inserted = upsert_documents(docs)
    print(f"\n{'=' * 50}\nDocuments attempted: {attempted}  |  newly inserted: {inserted}  "
          f"|  already-seen (skipped): {attempted - inserted}\n{'=' * 50}")
