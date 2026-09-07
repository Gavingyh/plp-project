"""
Analyst consensus ingestion via Yahoo Finance's quoteSummary endpoint.

WHY THIS SOURCE: full analyst report PDFs sit behind brokerage entitlements,
and the free alternatives were tested and are bot-protected — sgx.com serves
an "unsupported browser" shell to any non-browser client, and sginvestors.io
returns an empty Cloudflare challenge. The news-derived proxy in
ingest/analyst_tag.py found 0 matches across the news corpus. This endpoint
returns real, structured consensus for all three banks (verified live:
D05.SI 16 analysts, O39.SI 16, U11.SI 15).

IMPORTANT CAVEAT — DISCLOSE THIS IN THE REPORT: this is an *unofficial* API.
It is the same endpoint the widely-used `yfinance` library wraps, but Yahoo
publishes no public API terms blessing it, and it requires a cookie+crumb
handshake that Yahoo added specifically to slow automated access. It may
change or break without notice. It provides consensus *aggregates* (how many
analysts, what average target), NOT the reasoning inside any analyst report.
Do not describe this as "analyst reports" in the writeup — it is analyst
consensus data.

USAGE:
  python -m ingest.yahoo_analyst
"""

import time
from datetime import datetime, timezone

import requests

from ingest.db import get_connection, init_db, now_iso

from config.logging_config import get_logger, setup_logging


logger = get_logger(__name__)

# Yahoo tickers for the three banks. Keys must match ingest/base.py BANKS keys.
TICKERS = {"DBS": "D05.SI", "OCBC": "O39.SI", "UOB": "U11.SI"}

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
_MODULES = "recommendationTrend,financialData"
_TIMEOUT = 20
_POLITE_DELAY_SECONDS = 1.0


def _make_session() -> tuple[requests.Session, str]:
    """Yahoo requires a cookie + crumb handshake before quoteSummary will answer.
    Without it every request returns HTTP 401 'Invalid Crumb'."""
    session = requests.Session()
    session.headers.update({"User-Agent": _USER_AGENT})
    session.get("https://fc.yahoo.com", timeout=_TIMEOUT)
    crumb = session.get(
        "https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=_TIMEOUT
    ).text.strip()
    if not crumb or len(crumb) > 32:
        raise RuntimeError(f"Did not get a usable crumb from Yahoo (got {crumb!r})")
    return session, crumb


def _raw(container: dict, key: str):
    """Yahoo returns absent numeric fields as an empty dict rather than null,
    so a plain .get(key)['raw'] will KeyError. Always read through this."""
    value = container.get(key)
    if isinstance(value, dict):
        return value.get("raw")
    return value


def fetch_bank(session: requests.Session, crumb: str, bank: str, ticker: str) -> dict | None:
    """Returns one consensus row for a bank, or None if Yahoo has no data for it."""
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
    resp = session.get(url, params={"modules": _MODULES, "crumb": crumb}, timeout=_TIMEOUT)
    if resp.status_code != 200:
        logger.info(f"{bank} ({ticker}): HTTP {resp.status_code} — {resp.text[:150]}")
        return None

    result = (resp.json().get("quoteSummary") or {}).get("result")
    if not result:
        logger.warning(f"{bank} ({ticker}): no result payload")
        return None

    data = result[0]
    financial = data.get("financialData") or {}
    trend_list = (data.get("recommendationTrend") or {}).get("trend") or []
    # trend entries are relative periods; '0m' is the current month.
    current = next((t for t in trend_list if t.get("period") == "0m"), {})

    return {
        "bank": bank,
        "as_of_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "ticker": ticker,
        "n_analysts": _raw(financial, "numberOfAnalystOpinions"),
        "recommendation_key": financial.get("recommendationKey"),
        "recommendation_mean": _raw(financial, "recommendationMean"),
        "target_mean": _raw(financial, "targetMeanPrice"),
        "target_median": _raw(financial, "targetMedianPrice"),
        "target_high": _raw(financial, "targetHighPrice"),
        "target_low": _raw(financial, "targetLowPrice"),
        "current_price": _raw(financial, "currentPrice"),
        "strong_buy": current.get("strongBuy"),
        "buy": current.get("buy"),
        "hold": current.get("hold"),
        "sell": current.get("sell"),
        "strong_sell": current.get("strongSell"),
        "fetched_at": now_iso(),
    }


def pull() -> list[dict]:
    try:
        session, crumb = _make_session()
    except Exception as e:
        logger.warning(f"Skipped — could not establish a Yahoo session: {e}")
        return []

    rows = []
    for bank, ticker in TICKERS.items():
        try:
            row = fetch_bank(session, crumb, bank, ticker)
        except Exception as e:
            logger.error(f"{bank} ({ticker}): ERROR — {e}")
            row = None
        if row:
            logger.info(f"{bank}: {row['n_analysts']} analysts, "
                  f"target_mean={row['target_mean']}, rating={row['recommendation_key']}")
            rows.append(row)
        time.sleep(_POLITE_DELAY_SECONDS)
    return rows


def upsert(rows: list[dict]) -> int:
    """One snapshot per (bank, date). Re-running on the same day REPLACES that
    day's row rather than creating a duplicate, so the batch stays idempotent
    while still refreshing intraday if run twice."""
    if not rows:
        return 0
    init_db()
    conn = get_connection()
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO analyst_consensus
               (bank, as_of_date, ticker, n_analysts, recommendation_key,
                recommendation_mean, target_mean, target_median, target_high,
                target_low, current_price, strong_buy, buy, hold, sell,
                strong_sell, fetched_at)
               VALUES (:bank, :as_of_date, :ticker, :n_analysts, :recommendation_key,
                       :recommendation_mean, :target_mean, :target_median, :target_high,
                       :target_low, :current_price, :strong_buy, :buy, :hold, :sell,
                       :strong_sell, :fetched_at)""",
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


if __name__ == "__main__":
    setup_logging()
    logger.info(f"Run started: {datetime.now().isoformat()}")
    rows = pull()
    n = upsert(rows)
    logger.info(f"Analyst consensus rows written: {n}")
