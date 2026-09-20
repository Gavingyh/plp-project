"""
Extract full-length articles from a CNA (Channel News Asia) RSS feed.

For each item in the feed, fetches the linked article page and extracts the
full article text (not just the RSS summary) using trafilatura, falling back
to a generic BeautifulSoup heuristic if that fails.

Usage:
    python cna_scraper.py --feed "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936
    python cna_scraper.py --feed "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936" --limit 20 --delay 2 --output cna_articles.json
    python cna_scraper.py --feed "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936" --format csv --output cna_articles.csv

Note: This only fetches what CNA already publishes in its public RSS feed.
Respect CNA's Terms of Service and copyright if you plan to store, redistribute,
or publish the scraped content -- this tool is meant for personal use,
research, or archiving, not republishing.
"""

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

try:
    import trafilatura
except ImportError:
    trafilatura = None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_FEED = "https://www.channelnewsasia.com/rssfeeds/8395986"


@dataclass
class Article:
    title: str
    link: str
    published: Optional[str]
    feed_summary: Optional[str]
    full_text: Optional[str]
    author: Optional[str]
    extraction_method: str
    error: Optional[str] = None


def fetch_feed(feed_url: str) -> list:
    parsed = feedparser.parse(feed_url)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"Could not parse feed at {feed_url}: {parsed.bozo_exception}")
    return parsed.entries


def fetch_page_html(url: str, session: requests.Session, timeout: int = 15) -> str:
    resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def extract_with_trafilatura(html: str, url: str) -> Optional[dict]:
    if trafilatura is None:
        return None
    result = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        with_metadata=True,
        output_format="json",
    )
    if not result:
        return None
    data = json.loads(result)
    return {
        "text": data.get("text"),
        "author": data.get("author"),
    }


def extract_with_bs4_fallback(html: str) -> Optional[str]:
    """Generic fallback: grab <article> or the largest cluster of <p> tags."""
    soup = BeautifulSoup(html, "html.parser")

    article_tag = soup.find("article")
    container = article_tag if article_tag else soup

    paragraphs = [
        p.get_text(" ", strip=True)
        for p in container.find_all("p")
        if len(p.get_text(strip=True)) > 40
    ]
    if not paragraphs:
        return None
    return "\n\n".join(paragraphs)


def extract_full_article(url: str, session: requests.Session) -> tuple:
    """Returns (full_text, author, method, error)."""
    try:
        html = fetch_page_html(url, session)
    except requests.RequestException as exc:
        return None, None, "none", f"fetch failed: {exc}"

    trafilatura_result = extract_with_trafilatura(html, url)
    if trafilatura_result and trafilatura_result.get("text"):
        return trafilatura_result["text"], trafilatura_result.get("author"), "trafilatura", None

    fallback_text = extract_with_bs4_fallback(html)
    if fallback_text:
        return fallback_text, None, "bs4_fallback", None

    return None, None, "none", "no extractable article body found"


def scrape(feed_url: str, limit: Optional[int], delay: float) -> list:
    entries = fetch_feed(feed_url)
    if limit:
        entries = entries[:limit]

    session = requests.Session()
    articles = []

    for i, entry in enumerate(entries, start=1):
        link = entry.get("link")
        title = entry.get("title", "")
        print(f"[{i}/{len(entries)}] Fetching: {title}", file=sys.stderr)

        full_text, author, method, error = (None, None, "none", "missing link")
        if link:
            full_text, author, method, error = extract_full_article(link, session)

        articles.append(
            Article(
                title=title,
                link=link or "",
                published=entry.get("published"),
                feed_summary=entry.get("summary"),
                full_text=full_text,
                author=author,
                extraction_method=method,
                error=error,
            )
        )

        if i < len(entries):
            time.sleep(delay)

    return articles


def save_json(articles: list, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(a) for a in articles], f, ensure_ascii=False, indent=2)


def save_csv(articles: list, path: str):
    fieldnames = list(asdict(articles[0]).keys()) if articles else []
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for a in articles:
            writer.writerow(asdict(a))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--feed", default=DEFAULT_FEED, help="CNA RSS feed URL")
    parser.add_argument("--limit", type=int, default=None, help="Max number of articles to fetch")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds to wait between article requests")
    parser.add_argument("--output", default="articles.json", help="Output file path")
    parser.add_argument("--format", choices=["json", "csv"], default=None, help="Output format (inferred from --output extension if omitted)")
    args = parser.parse_args()

    output_format = args.format or ("csv" if args.output.lower().endswith(".csv") else "json")

    articles = scrape(args.feed, args.limit, args.delay)

    if output_format == "csv":
        save_csv(articles, args.output)
    else:
        save_json(articles, args.output)

    ok = sum(1 for a in articles if a.full_text)
    print(f"\nDone. {ok}/{len(articles)} articles extracted successfully -> {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
