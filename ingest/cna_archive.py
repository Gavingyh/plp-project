"""
CNA (Channel News Asia) articles about DBS, OCBC and UOB, backfilled from 2023.

ingest/cna_scraper.py reads CNA's RSS feed, which only ever holds the latest
items and is not about the banks, and it writes a file rather than the
database. This module fills both gaps: it finds bank articles back to 2023,
fetches their full text, and loads them through the same filter and dedup as
every other news source (ingest/news_filter.py).

DISCOVERY. CNA offers no usable archive: its news sitemap holds only the
latest 50 articles, and robots.txt disallows /search and /api/*. The Wayback
Machine's CDX index lists every CNA URL it has captured, and CNA URLs carry
the headline as a slug (/business/dbs-sued-1-billion-1mdb-6373296). So this
asks the CDX index for URLs in the news sections whose slug names a bank, a
bank's product (PayLah) or a bank's chief executive. Headlines that name no
bank in the slug are missed; a probe that also took any slug containing
"bank" returned ~2,900 business URLs, almost all about other banks, so it
isn't used.

FETCHING. Each article is fetched from CNA itself, at robots.txt's
Crawl-delay of 10 seconds, and falls back to the archived capture when the
live page is gone. Text is extracted with trafilatura (the same extractor
cna_scraper.py uses); the publish time comes from the page's metadata.
Fetching runs newest first, so an interrupted run has the most recent
articles. It can't stop early at the first old article: CNA gave migrated
archive stories new ids (id 5820966 is a 2015 obituary), so ids aren't in
publish order. Every candidate is fetched, and its publish date, read from
the page, decides whether it is kept. The candidate list is cached in data/cna/candidates.json and fetched articles
in data/cna/articles.jsonl, so an interrupted run resumes where it stopped
(--rediscover refreshes the list) and a re-load needs no network. data/cna/ is
gitignored: the text is CNA's, used here for research and not redistributed.

USAGE:
  python -m ingest.cna_archive --since 2023-01-01 --until 2026-09-26 --dry-run
  python -m ingest.cna_archive --since 2023-01-01 --until 2026-09-26
  python -m ingest.cna_archive --fetch-only ...                # discover and fetch, don't load
  python -m ingest.cna_archive --load-only ...                 # cache -> DB, no network
  python -m ingest.cna_archive --from-json ingest/cna_articles.json   # load cna_scraper.py output
"""

import argparse
import json
import os
import re
import time
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

from config.logging_config import get_logger, setup_logging
from ingest.db import make_doc_id, now_iso, upsert_documents
from ingest.news_filter import filter_and_dedup, load_index

try:
    import trafilatura
except ImportError:  # declared in requirements.txt; checked at fetch time
    trafilatura = None

logger = get_logger(__name__)

SOURCE = "cna"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "data", "cna")
CACHE_PATH = os.path.join(CACHE_DIR, "articles.jsonl")
CANDIDATES_PATH = os.path.join(CACHE_DIR, "candidates.json")

CDX_URL = "https://web.archive.org/cdx/search/cdx"
SITE = "www.channelnewsasia.com"
# Sections that carried bank articles in a 2023-2026 probe; others had none.
SECTIONS = ("business", "singapore", "commentary", "asia", "today")
# Server-side CDX filter (loose, one regex), then SLUG_RE below decides.
CDX_FILTER = (r"original:.*(dbs|ocbc|uob|posb|paylah|piyush-gupta|tan-su-shan|"
              r"wee-ee-cheong|helen-wong|singapore-banks|local-banks).*")
SLUG_RE = re.compile(r"(^|-)(dbs|ocbc|uob|posb|paylah|piyush-gupta|tan-su-shan|"
                     r"wee-ee-cheong|helen-wong|singapore-banks|local-banks)(-|$)")
ARTICLE_URL = re.compile(r"^https?://www\.channelnewsasia\.com/"
                         r"(?P<section>[a-z-]+(?:/[a-z-]+)?)/(?P<slug>[a-z0-9-]+)-(?P<id>\d{5,8})"
                         r"(?:[/?#].*)?$")

CRAWL_DELAY = 10.0      # robots.txt: Crawl-delay: 10
CDX_DELAY = 3.0
USER_AGENT = "Mozilla/5.0 (compatible; plp-research/1.0; academic project)"


# --- discovery -------------------------------------------------------------

def parse_article_url(url: str) -> dict | None:
    """Section, slug and CNA article id from a CNA article URL, or None."""
    m = ARTICLE_URL.match(url.strip())
    if not m:
        return None
    return {"section": m["section"], "slug": m["slug"], "id": m["id"],
            "url": f"https://{SITE}/{m['section']}/{m['slug']}-{m['id']}"}


def _cdx(section: str, start: str, end: str) -> list[str] | None:
    """One CDX query; None when the archive times out (the caller splits)."""
    params = {"url": f"{SITE}/{section}/", "matchType": "prefix", "filter": CDX_FILTER,
              "collapse": "urlkey", "fl": "original,timestamp", "from": start, "to": end}
    try:
        resp = requests.get(CDX_URL, params=params, timeout=180,
                            headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        logger.warning("CDX %s %s-%s failed: %s", section, start, end, exc)
        return None
    if resp.status_code != 200 or resp.text.lstrip().startswith("<"):
        logger.warning("CDX %s %s-%s returned %s", section, start, end, resp.status_code)
        return None
    return [l for l in resp.text.splitlines() if l.startswith("http")]


def _months(start: date, end: date) -> list[str]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _query_range(section: str, months: list[str]) -> list[str]:
    """CDX lines for a run of months, halving the range whenever the archive
    times out on it (busy sections time out on a whole year)."""
    lines = _cdx(section, months[0], months[-1])
    time.sleep(CDX_DELAY)
    if lines is not None:
        return lines
    if len(months) == 1:
        logger.warning("CDX %s %s failed at one month; skipped", section, months[0])
        return []
    mid = len(months) // 2
    return _query_range(section, months[:mid]) + _query_range(section, months[mid:])


def discover(since: str, until: str) -> dict[str, dict]:
    """Candidate articles keyed by CNA article id, with the earliest capture.

    CDX dates are capture dates, not publish dates, so the range starts a
    year early to catch articles captured late; the publish date read from
    each page decides what is kept.
    """
    start = date.fromisoformat(since).replace(month=1, day=1)
    start = start.replace(year=start.year - 1)
    months = _months(start, date.fromisoformat(until))
    found: dict[str, dict] = {}
    for section in SECTIONS:
        for year in sorted({m[:4] for m in months}):
            year_months = [m for m in months if m.startswith(year)]
            for line in _query_range(section, year_months):
                original, _, timestamp = line.partition(" ")
                art = parse_article_url(original)
                if not art or not SLUG_RE.search(art["slug"]):
                    continue
                prev = found.get(art["id"])
                if prev is None or timestamp < prev["timestamp"]:
                    found[art["id"]] = {**art, "timestamp": timestamp.strip()}
        logger.info("discovered %d candidates after section %s", len(found), section)
    return found


# --- fetching --------------------------------------------------------------

def published_from_html(html: str) -> str | None:
    """Publish time from CNA's page metadata, as an ISO string."""
    soup = BeautifulSoup(html, "html.parser")
    for key in ("cXenseParse:recs:publishtime", "article:published_time"):
        tag = soup.find("meta", attrs={"name": key}) or soup.find("meta", attrs={"property": key})
        if tag and tag.get("content"):
            try:
                return datetime.fromisoformat(tag["content"]).isoformat()
            except ValueError:
                continue
    return None


def extract(html: str, url: str) -> dict | None:
    """Title, text and publish time, or None when no article body is found."""
    if trafilatura is None:
        raise RuntimeError("trafilatura is not installed: pip install -r requirements.txt")
    result = trafilatura.extract(html, url=url, include_comments=False, include_tables=False,
                                 with_metadata=True, output_format="json")
    if not result:
        return None
    data = json.loads(result)
    if not data.get("text"):
        return None
    published = published_from_html(html)
    if not published and data.get("date"):
        published = f"{data['date']}T00:00:00+08:00"   # CNA dates are Singapore time
    return {"title": data.get("title"), "text": data["text"], "published": published,
            "author": data.get("author")}


def _get(url: str) -> requests.Response | None:
    try:
        return requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        logger.warning("fetch failed %s: %s", url, exc)
        return None


def fetch_article(cand: dict) -> dict:
    """Fetch one candidate: live page first, the archived capture if the live
    page is gone or yields no text. Always returns a cache record."""
    record = {"id": cand["id"], "url": cand["url"], "section": cand["section"],
              "slug": cand["slug"], "fetched_at": now_iso()}
    resp = _get(cand["url"])
    if resp is not None and resp.status_code == 200:
        art = extract(resp.text, cand["url"])
        if art:
            return {**record, **art, "fetched_from": "live"}
    live_status = resp.status_code if resp is not None else None
    if cand.get("timestamp"):
        archived = f"https://web.archive.org/web/{cand['timestamp']}id_/{cand['url']}"
        resp = _get(archived)
        if resp is not None and resp.status_code == 200:
            art = extract(resp.text, cand["url"])
            if art:
                return {**record, **art, "fetched_from": "wayback", "archived_url": archived}
    return {**record, "error": f"no text (live status {live_status})"}


def load_cache(path: str = CACHE_PATH) -> dict[str, dict]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["id"]: r for r in (json.loads(l) for l in f if l.strip())}


# Statuses that mean the page is gone for good. Any other failure (a network
# error, a 5xx, a page that yielded no text) may be a blip, so it is fetched
# again on the next run rather than kept as final.
_GONE_STATUSES = {"404", "410"}
_LIVE_STATUS = re.compile(r"live status (\w+)")


def _settled(record: dict) -> bool:
    """True when a cached record needs no further fetch: it has the article,
    or its failure was a page that no longer exists."""
    if not record.get("error"):
        return True
    m = _LIVE_STATUS.search(record["error"])
    return bool(m) and m.group(1) in _GONE_STATUSES


def fetch_all(candidates: dict[str, dict], path: str = CACHE_PATH,
              delay: float = CRAWL_DELAY) -> dict[str, dict]:
    """Fetch every candidate not already cached, newest first, appending each
    as it lands. A cached failure other than a missing page is fetched again;
    the new record is appended and, read later, replaces the old one."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cache = load_cache(path)
    todo = [c for k, c in sorted(candidates.items(), key=lambda kv: -int(kv[0]))
            if k not in cache or not _settled(cache[k])]
    logger.info("%d candidates, %d cached, %d to fetch (~%.0f min at %.0fs each)",
                len(candidates), len(cache), len(todo), len(todo) * delay / 60, delay)
    with open(path, "a", encoding="utf-8") as f:
        for i, cand in enumerate(todo, 1):
            record = fetch_article(cand)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            cache[cand["id"]] = record
            if i % 25 == 0:
                logger.info("fetched %d/%d", i, len(todo))
            if i < len(todo):
                time.sleep(delay)
    return cache


def candidates_for(since: str, until: str, rediscover: bool = False,
                   path: str = CANDIDATES_PATH) -> dict[str, dict]:
    """The cached candidate list, or a fresh discovery (which is then cached)."""
    if not rediscover and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    found = discover(since, until)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(found, f)
    return found


# --- documents -------------------------------------------------------------

def to_document(record: dict) -> dict | None:
    """A cache record as a `documents` row, or None if it has no usable text."""
    if record.get("error") or not record.get("text") or not record.get("published"):
        return None
    title = (record.get("title") or "").strip()
    if not title:
        return None
    return {
        "doc_id": make_doc_id(SOURCE, record["id"]),
        "source": SOURCE,
        "source_detail": f"CNA/{record['section']}",
        "bank": "",                      # set by filter_and_dedup from the text
        "doc_type": "article",
        "title": title,
        "body": record["text"],
        "published_at": record["published"],
        "url": record["url"],
        "ingested_at": now_iso(),
        "raw": {"cna_id": record["id"], "section": record["section"],
                "fetched_from": record.get("fetched_from"),
                "archived_url": record.get("archived_url"),
                "author": record.get("author")},
    }


def in_window(published: str, since: str, until: str) -> bool:
    """since inclusive, until exclusive, compared on the Singapore date."""
    day = datetime.fromisoformat(published).date().isoformat()
    return since <= day < until


def load(records: list[dict], since: str, until: str) -> dict:
    docs = [d for d in (to_document(r) for r in records)
            if d and in_window(d["published_at"], since, until)]
    kept, stats = filter_and_dedup(docs, load_index())
    attempted, inserted = upsert_documents(kept)
    stats.update({"records": len(records), "in_window": len(docs), "inserted": inserted})
    return stats


def records_from_scraper_json(path: str) -> list[dict]:
    """ingest/cna_scraper.py output as cache records, so RSS pulls load the same way."""
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    out = []
    for it in items:
        art = parse_article_url(it.get("link") or "")
        if not art or not it.get("full_text"):
            continue
        published = None
        if it.get("published"):
            try:
                published = datetime.strptime(it["published"], "%a, %d %b %Y %H:%M:%S %z").isoformat()
            except ValueError:
                pass
        out.append({**art, "title": it.get("title"), "text": it["full_text"],
                    "published": published, "author": it.get("author"), "fetched_from": "rss"})
    return out


def main():
    setup_logging()
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--since", default="2023-01-01")
    p.add_argument("--until", default=date.today().isoformat(), help="exclusive")
    p.add_argument("--dry-run", action="store_true", help="discover and report only")
    p.add_argument("--fetch-only", action="store_true", help="discover and fetch, don't load")
    p.add_argument("--rediscover", action="store_true", help="refresh the cached candidate list")
    p.add_argument("--load-only", action="store_true", help="load the cache, no network")
    p.add_argument("--from-json", help="load a cna_scraper.py JSON file instead")
    args = p.parse_args()

    if args.from_json:
        print(load(records_from_scraper_json(args.from_json), args.since, args.until))
        return
    if not args.load_only:
        candidates = candidates_for(args.since, args.until, args.rediscover)
        cached = load_cache()
        print(f"{len(candidates)} candidates; {len(set(candidates) - set(cached))} not yet fetched")
        if args.dry_run:
            return
        fetch_all(candidates)
        if args.fetch_only:
            return
    print(load(list(load_cache().values()), args.since, args.until))


if __name__ == "__main__":
    main()
