"""
News data pull for SG bank sentiment project (DBS / OCBC / UOB).

Pulls from two sources:
  1. NewsAPI.org        (free tier: 100 req/day, ~1 month lookback only)
  2. Alpha Vantage News  (free tier: 25 req/day, NEWS_SENTIMENT endpoint)

SETUP:
  pip install requests pandas python-dotenv
  Get free keys:
    NewsAPI:      https://newsapi.org/register
    AlphaVantage: https://www.alphavantage.co/support/#api-key
  Set them as environment variables before running:
    export NEWSAPI_KEY="your_key_here"
    export ALPHAVANTAGE_KEY="your_key_here"

USAGE:
  python news_pull.py

OUTPUT:
  ./data/news_newsapi_raw.csv
  ./data/news_alphavantage_raw.csv
  Prints a volume summary per bank per source at the end — this is your
  go/no-go signal on whether news data is thick enough for Option 2a.
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))  # load .env from project root regardless of cwd

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5  # doubled each retry: 5s, 10s, 20s

BANKS = {
    "DBS": ["DBS Bank", "DBS Group", "D05.SI"],
    "OCBC": ["OCBC Bank", "Oversea-Chinese Banking", "O39.SI"],
    "UOB": ["United Overseas Bank", "UOB Bank", "U11.SI"],
}

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")
AV_KEY = os.environ.get("ALPHAVANTAGE_KEY")


def request_with_retries(url, params, timeout=15):
    """GET with a few retries on transient failures (timeouts, 429, 5xx).
    Does NOT retry on 4xx auth errors (401/403) — a bad key won't fix itself."""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code in (401, 403):
                resp.raise_for_status()  # fail fast, no point retrying a bad key
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.exceptions.HTTPError(
                    f"{resp.status_code} — retryable", response=resp
                )
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt == MAX_RETRIES:
                break
            wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"    -> request failed ({e}); retrying in {wait}s "
                  f"(attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)
    raise last_exc


def pull_newsapi():
    if not NEWSAPI_KEY:
        print("[NewsAPI] Skipped — set NEWSAPI_KEY env var to run this.")
        return pd.DataFrame()

    rows = []
    for bank, queries in BANKS.items():
        query = " OR ".join(f'"{q}"' for q in queries)
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 100,
            "apiKey": NEWSAPI_KEY,
        }
        try:
            resp = request_with_retries(url, params)
            data = resp.json()
            articles = data.get("articles", [])
            print(f"[NewsAPI] {bank}: {len(articles)} articles "
                  f"(totalResults reported: {data.get('totalResults', '?')})")
            for a in articles:
                rows.append({
                    "bank": bank,
                    "source": a.get("source", {}).get("name"),
                    "title": a.get("title"),
                    "description": a.get("description"),
                    "content": a.get("content"),
                    "published_at": a.get("publishedAt"),
                    "url": a.get("url"),
                })
        except Exception as e:
            print(f"[NewsAPI] {bank}: ERROR — {e}")
        time.sleep(1)  # be polite to free tier

    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_csv(os.path.join(DATA_DIR, "news_newsapi_raw.csv"), index=False)
    return df


def pull_alphavantage():
    if not AV_KEY:
        print("[AlphaVantage] Skipped — set ALPHAVANTAGE_KEY env var to run this.")
        return pd.DataFrame()

    rows = []
    for bank, queries in BANKS.items():
        # Alpha Vantage NEWS_SENTIMENT uses tickers param; SG tickers may not be indexed —
        # this call itself is your test of whether AV covers these names at all.
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": queries[-1],  # e.g. "D05.SI" — test ticker-based lookup
            "apikey": AV_KEY,
            "limit": 50,
        }
        try:
            resp = request_with_retries(url, params)
            data = resp.json()
            feed = data.get("feed", [])
            print(f"[AlphaVantage] {bank}: {len(feed)} articles "
                  f"(raw response keys: {list(data.keys())})")
            if "Note" in data or "Information" in data:
                # rate limit or invalid ticker message from AV
                print(f"    -> AV message: {data.get('Note') or data.get('Information')}")
            for a in feed:
                rows.append({
                    "bank": bank,
                    "title": a.get("title"),
                    "summary": a.get("summary"),
                    "source": a.get("source"),
                    "time_published": a.get("time_published"),
                    "url": a.get("url"),
                    # Note: AV also returns overall_sentiment_score — do NOT use this as
                    # your DNN's training label, only use the raw title/summary text.
                })
        except Exception as e:
            print(f"[AlphaVantage] {bank}: ERROR — {e}")
        time.sleep(15)  # free tier is 25 req/day — space calls out, avoid burning quota fast

    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_csv(os.path.join(DATA_DIR, "news_alphavantage_raw.csv"), index=False)
    return df


def summarize(df_newsapi, df_av):
    print("\n" + "=" * 50)
    print("VOLUME SUMMARY — use this to decide go/no-go on news source")
    print("=" * 50)
    if not df_newsapi.empty:
        print("\nNewsAPI counts per bank:")
        print(df_newsapi.groupby("bank").size())
    if not df_av.empty:
        print("\nAlphaVantage counts per bank:")
        print(df_av.groupby("bank").size())
    if df_newsapi.empty and df_av.empty:
        print("\nNo data pulled — check your API keys are set correctly.")


if __name__ == "__main__":
    print(f"Run started: {datetime.now().isoformat()}\n")
    df_newsapi = pull_newsapi()
    df_av = pull_alphavantage()
    summarize(df_newsapi, df_av)
