"""NewsAPI headlines/descriptions, collected in bounded, recoverable pages.

The manual pipeline commits each page separately and applies the shared news
filter. pull() remains available to the existing batch ingestion script.
No article pages are scraped and the truncated content is not analysed.
"""

from datetime import datetime, timedelta, timezone
import time
from urllib.parse import urlsplit

import requests

from config.newsapi import api_key
from config.logging_config import get_logger, setup_logging
from ingest.base import BANKS, resolve_bank
from ingest.db import make_doc_id, now_iso, upsert_documents

logger = get_logger(__name__)
URL = "https://newsapi.org/v2/everything"
PAGE_SIZE = 100
MAX_PAGES = 4  # At most 12 successful page requests across the three banks.
MAX_ATTEMPTS = 3
FAILED_WINDOWS: list[str] = []

ERROR_MESSAGES = {
    "apiKeyMissing": "Set NEWSAPI_KEY in .env on the API machine.",
    "apiKeyInvalid": "The NewsAPI key is invalid. Check NEWSAPI_KEY on the API machine.",
    "apiKeyDisabled": "The NewsAPI key is disabled. Check your NewsAPI account.",
    "apiKeyExhausted": "The NewsAPI request quota is exhausted. Retry after your quota resets.",
    "rateLimited": "NewsAPI rate-limited this update. Wait before starting another update.",
    "maximumResultsReached": "NewsAPI's plan result limit was reached. Try a shorter date range.",
    "parameterInvalid": "NewsAPI rejected the dates or query. Check your plan's available history.",
    "parametersMissing": "NewsAPI rejected the request parameters.",
}
STOP_CODES = {
    "apiKeyMissing",
    "apiKeyInvalid",
    "apiKeyDisabled",
    "apiKeyExhausted",
    "rateLimited",
    "parameterInvalid",
    "parametersMissing",
}


class NewsAPIError(RuntimeError):
    """An actionable provider failure without credentials or raw responses."""

    def __init__(self, code, message=None):
        self.code = code
        super().__init__(
            message
            or ERROR_MESSAGES.get(code, "NewsAPI could not complete the request.")
        )


def _fetch(params, key):
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requests.get(
                URL,
                params=params,
                headers={"X-Api-Key": key},
                timeout=(5, 20),
                allow_redirects=False,
            )
        except requests.RequestException:
            if attempt + 1 == MAX_ATTEMPTS:
                raise NewsAPIError(
                    "connection", "NewsAPI could not be reached after retries."
                ) from None
        else:
            if response.status_code >= 500:
                if attempt + 1 == MAX_ATTEMPTS:
                    raise NewsAPIError(
                        "server", "NewsAPI is temporarily unavailable after retries."
                    )
            else:
                try:
                    data = response.json()
                except ValueError:
                    if response.status_code in {401, 403, 429}:
                        data = {}
                    else:
                        raise NewsAPIError(
                            "response", "NewsAPI returned an invalid response."
                        ) from None
                if not isinstance(data, dict):
                    if response.status_code in {401, 403, 429}:
                        data = {}
                    else:
                        raise NewsAPIError(
                            "response", "NewsAPI returned an invalid response."
                        )
                if response.status_code != 200 or data.get("status") == "error":
                    code = data.get("code")
                    if not isinstance(code, str) or code not in ERROR_MESSAGES:
                        code = {
                            401: "apiKeyInvalid",
                            403: "apiKeyDisabled",
                            429: "rateLimited",
                        }.get(response.status_code, "request")
                    # Never persist raw messages: a provider/proxy can echo credentials.
                    raise NewsAPIError(code)
                if (
                    data.get("status") != "ok"
                    or type(data.get("totalResults")) is not int
                    or data["totalResults"] < 0
                    or not isinstance(data.get("articles"), list)
                ):
                    raise NewsAPIError(
                        "response", "NewsAPI returned an invalid response."
                    )
                return data
        time.sleep(2**attempt)


def to_document(article, bank):
    if not isinstance(article, dict):
        return None
    title, description = article.get("title"), article.get("description") or ""
    if not isinstance(title, str) or not title.strip() or title.strip() == "[Removed]":
        return None
    if not isinstance(description, str):
        return None
    url = article.get("url")
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
        if (
            not parsed
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return None
        published = datetime.fromisoformat(
            article["publishedAt"].replace("Z", "+00:00")
        )
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    title = title.strip()
    description = description.strip()
    separator = " " if title.endswith((".", "!", "?")) else ". "
    body = title + separator + description if description else title
    source = article.get("source")
    return {
        "doc_id": make_doc_id("newsapi", url),
        "source": "newsapi",
        "source_detail": source.get("name") if isinstance(source, dict) else None,
        "bank": resolve_bank(body, fallback=bank),
        "doc_type": "article",
        "title": title,
        "body": body,
        "published_at": published.astimezone(timezone.utc).isoformat(),
        "url": url,
        "ingested_at": now_iso(),
        "raw": article,
    }


def iter_batches(since, until):
    """Yield each bank/page for [since, until); record incomplete coverage."""
    FAILED_WINDOWS.clear()
    key = api_key()
    if not key:
        raise NewsAPIError("apiKeyMissing")
    for bank, queries in BANKS.items():
        specific = [query for query in queries if " " in query or "." in query]
        bank_query = " OR ".join(f'"{query}"' for query in specific)
        seen = 0
        for page in range(1, MAX_PAGES + 1):
            label = f"{bank} page {page}"
            params = {
                "q": f"({bank_query}) AND (Singapore OR SGX)",
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": PAGE_SIZE,
                "page": page,
                "from": f"{since}T00:00:00Z",
                "to": f"{until}T00:00:00Z",
            }
            try:
                data = _fetch(params, key)
            except NewsAPIError as exc:
                FAILED_WINDOWS.append(f"{label} ({since} to {until}): {exc}")
                if exc.code in STOP_CODES:
                    raise
                yield label, []
                break
            articles = data["articles"]
            docs = [doc for item in articles if (doc := to_document(item, bank))]
            if len(docs) < len(articles):
                FAILED_WINDOWS.append(
                    f"{label}: {len(articles) - len(docs)} article(s) had unusable fields."
                )
            seen += len(articles)
            logger.info(
                "%s: %d article candidates (totalResults: %d)",
                label,
                len(articles),
                data["totalResults"],
            )
            yield label, docs
            if seen >= data["totalResults"]:
                break
            if len(articles) < PAGE_SIZE or page == MAX_PAGES:
                FAILED_WINDOWS.append(
                    f"{label} ({since} to {until}): result/page limit reached before totalResults. Try a shorter date range."
                )
                break
            time.sleep(1)


def pull():
    """Compatibility entry point: recent 30 UTC days, without database writes."""
    if not api_key():
        logger.warning("Skipped - set NEWSAPI_KEY in .env to run this.")
        return []
    end = datetime.now(timezone.utc).date() + timedelta(days=1)
    docs = []
    try:
        for _, batch in iter_batches(
            (end - timedelta(days=30)).isoformat(), end.isoformat()
        ):
            docs.extend(batch)
    except NewsAPIError as exc:
        logger.warning("%s", exc)
    return docs


if __name__ == "__main__":
    setup_logging()
    docs = pull()
    attempted, inserted = upsert_documents(docs)
    logger.info(
        "Documents attempted: %d | newly inserted: %d | skipped: %d",
        attempted,
        inserted,
        attempted - inserted,
    )
    if FAILED_WINDOWS or not api_key():
        raise SystemExit(1)
