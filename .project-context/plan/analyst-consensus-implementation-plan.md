# Implementation Plan: Analyst Consensus Ingestion (Yahoo Finance)

**Audience:** an AI coding agent executing this plan step by step.
**Scope:** add analyst-consensus data (ratings + price targets for DBS/OCBC/UOB) as a new data source, wire it into the daily batch, expose it to the chatbot and dashboard, and test it.
**Estimated size:** 6 tasks, ~350 lines of new code including tests.

Execute tasks **in order**. Each task has a verification step. **Do not start a task until the previous task's verification passes.**

---

## 0. Before you start — read this section fully

### What already exists (do not rebuild these)

- `ingest/db.py` — SQLite connection + schema. Tables: `documents`, `sentences`, `sentence_aspects`, `aspect_sentiment`, `sentiment_index`.
- `ingest/base.py` — `BANKS` dict, `detect_banks()`, `resolve_bank()`, `request_with_retries()`.
- `ingest/newsapi.py`, `ingest/arctic_shift.py`, `ingest/earnings_extract.py`, `ingest/analyst_tag.py` — existing ingest adapters.
- `run_daily_batch.py` — the batch entrypoint.
- `chatbot/tools.py` — chatbot tool functions + `TOOL_SCHEMAS` + `TOOL_FUNCTIONS`.
- `dashboard/app.py` — Streamlit dashboard.
- `tests/` — 52 passing tests. `tests/conftest.py` has a `temp_db` fixture.

### Hard rules

1. **Always use this exact Python interpreter** — never plain `python3`, never `pip`:
   ```
   /Users/gavin/Projects/plp-project/.venv-plp/bin/python3
   ```
   A conda/miniforge Python 3.9 is on this machine's PATH and **will** shadow the project venv and fail with `TypeError: unsupported operand type(s) for |`. This has already caused one wasted overnight run.

2. **Always set `HF_HUB_OFFLINE=1`** when running anything that loads FinBERT (`aspects.*`, `sentiment.*`, the test suite). Without it, model loading intermittently hangs on a rate-limited HuggingFace call.

3. **Run all commands from** `/Users/gavin/Projects/plp-project`.

4. **Do not modify** any of these — they are working and tested, and are out of scope:
   - `config/aspects.yaml` (the aspect taxonomy is a pending human decision)
   - `aspects/`, `sentiment/`, `aggregate/`, `preprocess/` modules
   - the `documents` / `sentences` / `aspect_sentiment` / `sentiment_index` table schemas
   - any existing test file

5. **Do not run** `preprocess.pipeline`, `aspects.assign`, `sentiment.score`, or `aggregate.index`. This feature does not touch the sentence pipeline.

6. If a verification step fails, **fix it before continuing**. Do not proceed with a failing test.

### Key design decision (already made — implement it, do not redesign)

Analyst consensus is **structured numeric data**, not text. It does **not** go into the `documents` table (whose rows flow into sentence-splitting and FinBERT sentiment scoring — meaningless for a price target).

It goes into a **new `analyst_consensus` table**, one row per (bank, date). Daily rows accumulate into a time series so consensus drift becomes visible over time.

---

## Task 1 — Create the `analyst_consensus` table

**File to edit:** `ingest/db.py`

Find the `SCHEMA` string. It currently ends with the `sentences` table's `CREATE INDEX` lines, followed by `"""`. Append the following **inside** the same `SCHEMA` string, immediately before the closing `"""`:

```sql

-- Analyst consensus (ratings + price targets), one row per bank per day.
-- Structured numeric data, NOT text — deliberately separate from `documents`,
-- which feeds sentence-splitting and FinBERT sentiment scoring.
CREATE TABLE IF NOT EXISTS analyst_consensus (
    bank                TEXT NOT NULL,
    as_of_date          TEXT NOT NULL,   -- YYYY-MM-DD, one snapshot per day
    ticker              TEXT NOT NULL,
    n_analysts          INTEGER,
    recommendation_key  TEXT,            -- e.g. 'buy', 'hold'
    recommendation_mean REAL,            -- 1.0=strong buy .. 5.0=strong sell
    target_mean         REAL,
    target_median       REAL,
    target_high         REAL,
    target_low          REAL,
    current_price       REAL,
    strong_buy          INTEGER,
    buy                 INTEGER,
    hold                INTEGER,
    sell                INTEGER,
    strong_sell         INTEGER,
    fetched_at          TEXT NOT NULL,
    PRIMARY KEY (bank, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_analyst_consensus_bank ON analyst_consensus(bank);
```

**Verify:**
```bash
cd /Users/gavin/Projects/plp-project
/Users/gavin/Projects/plp-project/.venv-plp/bin/python3 -c "
from ingest.db import init_db, get_connection
init_db()
cols = [r[1] for r in get_connection().execute('PRAGMA table_info(analyst_consensus)')]
print(cols)
assert 'target_mean' in cols and 'n_analysts' in cols, 'table not created correctly'
print('TASK 1 OK')
"
```
**Expected:** prints the column list, then `TASK 1 OK`.

---

## Task 2 — Write the Yahoo Finance adapter

**File to create:** `ingest/yahoo_analyst.py`

Write exactly this file:

```python
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
        print(f"[YahooAnalyst] {bank} ({ticker}): HTTP {resp.status_code} — {resp.text[:150]}")
        return None

    result = (resp.json().get("quoteSummary") or {}).get("result")
    if not result:
        print(f"[YahooAnalyst] {bank} ({ticker}): no result payload")
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
        print(f"[YahooAnalyst] Skipped — could not establish a Yahoo session: {e}")
        return []

    rows = []
    for bank, ticker in TICKERS.items():
        try:
            row = fetch_bank(session, crumb, bank, ticker)
        except Exception as e:
            print(f"[YahooAnalyst] {bank} ({ticker}): ERROR — {e}")
            row = None
        if row:
            print(f"[YahooAnalyst] {bank}: {row['n_analysts']} analysts, "
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
    print(f"Run started: {datetime.now().isoformat()}\n")
    rows = pull()
    n = upsert(rows)
    print(f"\nAnalyst consensus rows written: {n}")
```

**Verify (this makes a real network call):**
```bash
cd /Users/gavin/Projects/plp-project
/Users/gavin/Projects/plp-project/.venv-plp/bin/python3 -m ingest.yahoo_analyst
```
**Expected:** three `[YahooAnalyst] <BANK>: N analysts, target_mean=..., rating=...` lines (N should be roughly 15-16 for each bank), then `Analyst consensus rows written: 3`.

**If it prints `HTTP 401` or a crumb error:** Yahoo changed the handshake. Do not work around it by disabling verification or scraping HTML. Stop and report that the endpoint's auth flow has changed.

---

## Task 3 — Wire into the daily batch

**File to edit:** `run_daily_batch.py`

1. Add to the imports at the top, alongside the existing `from ingest import ...` line:
   ```python
   from ingest import yahoo_analyst
   ```

2. Immediately **before** the `print(f"{'=' * 60}\nBATCH SUMMARY..."` line, insert:
   ```python
       print("--- Yahoo analyst consensus ---")
       consensus_rows = yahoo_analyst.pull()
       n_consensus = yahoo_analyst.upsert(consensus_rows)
       print(f"Analyst consensus: {n_consensus} bank snapshots\n")
   ```

**Verify:**
```bash
cd /Users/gavin/Projects/plp-project
/Users/gavin/Projects/plp-project/.venv-plp/bin/python3 -c "
import ast, sys
src = open('run_daily_batch.py').read()
ast.parse(src)
assert 'yahoo_analyst' in src, 'import/call not added'
print('TASK 3 OK — run_daily_batch.py parses and references yahoo_analyst')
"
```
**Expected:** `TASK 3 OK ...`

Do **not** run the full `run_daily_batch.py` to verify — it does a long Reddit pull. The syntax check above is sufficient.

---

## Task 4 — Add a chatbot tool

**File to edit:** `chatbot/tools.py`

1. Add this function after the existing `get_coverage` function:

```python
def get_analyst_consensus(bank: str) -> dict:
    """Latest analyst consensus (ratings + price targets) for one bank.

    This is consensus *aggregate* data from Yahoo Finance, NOT the contents of
    any analyst report — say so when reporting it. Returns has_data=False when
    no snapshot exists yet.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT as_of_date, n_analysts, recommendation_key, recommendation_mean, "
            "target_mean, target_high, target_low, current_price, "
            "strong_buy, buy, hold, sell, strong_sell "
            "FROM analyst_consensus WHERE bank = ? ORDER BY as_of_date DESC LIMIT 1",
            (bank,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {"bank": bank, "has_data": False,
                "reason": "no analyst consensus snapshot stored yet — "
                          "run `python -m ingest.yahoo_analyst`"}

    (as_of, n, key, mean, t_mean, t_high, t_low, price,
     s_buy, buy_, hold, sell_, s_sell) = row
    upside = None
    if t_mean is not None and price:
        upside = round(100 * (t_mean - price) / price, 1)
    return {
        "bank": bank, "has_data": True, "as_of_date": as_of,
        "n_analysts": n, "consensus_rating": key, "rating_mean_1best_5worst": mean,
        "target_mean": t_mean, "target_high": t_high, "target_low": t_low,
        "current_price": price, "implied_upside_pct": upside,
        "rating_breakdown": {"strong_buy": s_buy, "buy": buy_, "hold": hold,
                              "sell": sell_, "strong_sell": s_sell},
        "source_note": "Yahoo Finance consensus aggregate, not analyst report text",
    }
```

2. Add this entry to the `TOOL_SCHEMAS` list (append as the last element):

```python
    {
        "name": "get_analyst_consensus",
        "description": "Get professional analyst consensus for one bank: number of analysts, "
                        "consensus rating, average/high/low price targets, and implied upside. "
                        "This is consensus aggregate data, NOT the text or reasoning of any "
                        "analyst report — do not claim to know why analysts hold that view.",
        "input_schema": {
            "type": "object",
            "properties": {"bank": {"type": "string", "enum": ["DBS", "OCBC", "UOB"]}},
            "required": ["bank"],
        },
    },
```

3. Add this entry to the `TOOL_FUNCTIONS` dict:
```python
    "get_analyst_consensus": lambda **kw: get_analyst_consensus(**kw),
```

**Verify:**
```bash
cd /Users/gavin/Projects/plp-project
HF_HUB_OFFLINE=1 /Users/gavin/Projects/plp-project/.venv-plp/bin/python3 -c "
from chatbot.tools import get_analyst_consensus, TOOL_SCHEMAS, TOOL_FUNCTIONS
import json
names = [t['name'] for t in TOOL_SCHEMAS]
assert 'get_analyst_consensus' in names, 'schema not registered'
assert 'get_analyst_consensus' in TOOL_FUNCTIONS, 'function not registered'
print(json.dumps(get_analyst_consensus('DBS'), indent=2))
print('TASK 4 OK')
" 2>&1 | grep -v "Loading weights\|UNEXPECTED\|Notes:\|classifier\|^-----\|^Key \|Warning:"
```
**Expected:** a JSON block with `"has_data": true`, an `n_analysts` around 15-16, and a numeric `implied_upside_pct`, then `TASK 4 OK`.
(If Task 2's run was skipped, `has_data` will be `false` — go back and run Task 2 first.)

---

## Task 5 — Add tests

**File to create:** `tests/test_yahoo_analyst.py`

These tests must **not** make network calls. Write exactly this:

```python
"""
Tests for ingest/yahoo_analyst.py and the get_analyst_consensus chatbot tool.
No network calls — Yahoo's payload shape is pinned as a fixture so a change in
their API surfaces as a real ingestion failure, not a silently-passing test.
"""

import pytest

from chatbot.tools import get_analyst_consensus
from ingest.yahoo_analyst import _raw, fetch_bank, upsert

# Trimmed copy of a real Yahoo quoteSummary response (verified live 2026-09-07).
_FAKE_PAYLOAD = {
    "quoteSummary": {
        "result": [{
            "financialData": {
                "numberOfAnalystOpinions": {"raw": 16},
                "recommendationKey": "buy",
                "recommendationMean": {"raw": 2.1875},
                "targetMeanPrice": {"raw": 76.72708},
                "targetMedianPrice": {"raw": 79.5},
                "targetHighPrice": {"raw": 85.86},
                "targetLowPrice": {"raw": 63.0},
                "currentPrice": {"raw": 78.65},
                "ebitda": {},  # Yahoo returns absent numerics as empty dicts
            },
            "recommendationTrend": {"trend": [
                {"period": "0m", "strongBuy": 1, "buy": 7, "hold": 7, "sell": 1, "strongSell": 0},
                {"period": "-1m", "strongBuy": 1, "buy": 8, "hold": 7, "sell": 0, "strongSell": 0},
            ]},
        }]
    }
}


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "fake"

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self._status_code = status_code

    def get(self, url, params=None, timeout=None):
        return _FakeResponse(self._payload, self._status_code)


def test_raw_handles_empty_dict_fields():
    # Yahoo sends absent numerics as {} — a naive ['raw'] read would KeyError.
    assert _raw({"ebitda": {}}, "ebitda") is None
    assert _raw({"targetMeanPrice": {"raw": 76.7}}, "targetMeanPrice") == 76.7
    assert _raw({}, "missing") is None


def test_fetch_bank_parses_real_payload_shape():
    row = fetch_bank(_FakeSession(_FAKE_PAYLOAD), "crumb", "DBS", "D05.SI")
    assert row["bank"] == "DBS"
    assert row["ticker"] == "D05.SI"
    assert row["n_analysts"] == 16
    assert row["recommendation_key"] == "buy"
    assert row["target_mean"] == pytest.approx(76.72708)
    # must take the '0m' (current month) trend entry, not just the first one
    assert row["buy"] == 7 and row["hold"] == 7


def test_fetch_bank_returns_none_on_http_error():
    assert fetch_bank(_FakeSession({}, status_code=401), "c", "DBS", "D05.SI") is None


def test_fetch_bank_returns_none_on_empty_result():
    empty = {"quoteSummary": {"result": None}}
    assert fetch_bank(_FakeSession(empty), "c", "DBS", "D05.SI") is None


def test_upsert_and_read_back(temp_db):
    row = fetch_bank(_FakeSession(_FAKE_PAYLOAD), "crumb", "DBS", "D05.SI")
    assert upsert([row]) == 1
    result = get_analyst_consensus("DBS")
    assert result["has_data"] is True
    assert result["n_analysts"] == 16
    assert result["consensus_rating"] == "buy"
    # implied upside: (76.72708 - 78.65) / 78.65 * 100 = -2.4%
    assert result["implied_upside_pct"] == pytest.approx(-2.4, abs=0.1)


def test_upsert_same_day_replaces_not_duplicates(temp_db):
    row = fetch_bank(_FakeSession(_FAKE_PAYLOAD), "crumb", "DBS", "D05.SI")
    upsert([row])
    upsert([row])
    conn = temp_db.get_connection()
    count = conn.execute("SELECT COUNT(*) FROM analyst_consensus WHERE bank='DBS'").fetchone()[0]
    conn.close()
    assert count == 1


def test_get_analyst_consensus_no_data(temp_db):
    result = get_analyst_consensus("OCBC")
    assert result["has_data"] is False
```

**Verify:**
```bash
cd /Users/gavin/Projects/plp-project
HF_HUB_OFFLINE=1 /Users/gavin/Projects/plp-project/.venv-plp/bin/python3 -m pytest tests/ 2>&1 | tail -5
```
**Expected:** `59 passed` (52 existing + 7 new). **All previously passing tests must still pass** — if any existing test broke, you changed something out of scope; revert that change.

---

## Task 6 — Show it on the dashboard

**File to edit:** `dashboard/app.py`

1. Add this loader function after the existing `load_evidence` function:

```python
@st.cache_data(ttl=300)
def load_analyst_consensus() -> pd.DataFrame:
    conn = get_connection()
    try:
        return pd.read_sql_query(
            "SELECT bank, as_of_date, n_analysts, recommendation_key, target_mean, "
            "current_price FROM analyst_consensus WHERE as_of_date = "
            "(SELECT MAX(as_of_date) FROM analyst_consensus)", conn)
    except Exception:
        return pd.DataFrame()  # table may not exist yet on a fresh install
    finally:
        conn.close()
```

2. Inside `with tab1:`, immediately **before** the `disclosure_footer()` call, insert:

```python
    st.divider()
    st.subheader("Professional analyst consensus")
    st.caption(
        "Consensus aggregates from Yahoo Finance (unofficial API) — the number of "
        "analysts covering each bank and their average price target. This is NOT "
        "the content of any analyst report, and is separate from the social/news "
        "sentiment scores above."
    )
    consensus_df = load_analyst_consensus()
    if consensus_df.empty:
        st.info("No analyst consensus data yet — run `python -m ingest.yahoo_analyst`.")
    else:
        acols = st.columns(3)
        for acol, bank in zip(acols, BANKS):
            brow = consensus_df[consensus_df.bank == bank]
            with acol:
                if brow.empty:
                    st.metric(f"{bank} consensus", "No data")
                else:
                    b = brow.iloc[0]
                    upside = None
                    if pd.notna(b["target_mean"]) and b["current_price"]:
                        upside = 100 * (b["target_mean"] - b["current_price"]) / b["current_price"]
                    st.metric(
                        f"{bank} — {b['recommendation_key'] or 'n/a'}",
                        f"S${b['target_mean']:.2f}" if pd.notna(b["target_mean"]) else "n/a",
                        delta=f"{upside:+.1f}% vs spot" if upside is not None else None,
                    )
                    st.caption(f"{int(b['n_analysts'])} analysts · as of {b['as_of_date']}"
                               if pd.notna(b["n_analysts"]) else f"as of {b['as_of_date']}")
```

**Verify:**
```bash
cd /Users/gavin/Projects/plp-project
HF_HUB_OFFLINE=1 /Users/gavin/Projects/plp-project/.venv-plp/bin/python3 -m streamlit run dashboard/app.py \
  --server.headless true --server.port 8510 > /tmp/dash_check.log 2>&1 &
sleep 8
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://localhost:8510
pkill -f "streamlit run dashboard/app.py"
grep -iE "traceback|exception|error" /tmp/dash_check.log | head -5 || echo "no errors logged"
rm -f /tmp/dash_check.log
```
**Expected:** `HTTP:200` and no traceback/exception lines.

---

## Final acceptance checklist

Run all of these. Every one must pass before declaring the work done.

```bash
cd /Users/gavin/Projects/plp-project

# 1. Full test suite — 59 passing, zero failures
HF_HUB_OFFLINE=1 /Users/gavin/Projects/plp-project/.venv-plp/bin/python3 -m pytest tests/ 2>&1 | tail -3

# 2. Live ingestion works and writes 3 rows
/Users/gavin/Projects/plp-project/.venv-plp/bin/python3 -m ingest.yahoo_analyst

# 3. Data is queryable for all three banks
/Users/gavin/Projects/plp-project/.venv-plp/bin/python3 -c "
from ingest.db import get_connection
rows = get_connection().execute(
    'SELECT bank, as_of_date, n_analysts, recommendation_key, target_mean FROM analyst_consensus'
).fetchall()
for r in rows: print(r)
assert len(rows) >= 3, f'expected >=3 rows, got {len(rows)}'
print('ACCEPTANCE OK')
"
```

Then commit:
```bash
git add -A
git commit -m "Add analyst consensus ingestion via Yahoo Finance

Adds analyst ratings and price targets for DBS/OCBC/UOB as a new structured
data source, filling the gap left by ingest/analyst_tag.py's news-derived
proxy (which matched 0 documents). Direct SGX and sginvestors.io scraping
were both tested and are bot-protected.

New analyst_consensus table (one snapshot per bank per day, so consensus
drift accumulates as a time series), ingest/yahoo_analyst.py adapter with
Yahoo's required cookie+crumb handshake, a get_analyst_consensus chatbot
tool, a dashboard panel, and 7 tests using a pinned copy of Yahoo's real
payload shape so an API change surfaces as a failure rather than passing
silently.

Yahoo's quoteSummary is an unofficial API (the endpoint yfinance wraps) and
provides consensus aggregates, not analyst report text — both caveats are
documented in the module docstring and surfaced in the dashboard caption.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Things that are explicitly NOT in scope

Do not attempt these, even if they seem related:

- Scraping sgx.com, sginvestors.io, straitstimes.com, or channelnewsasia.com — all four were tested and block non-browser clients. Do not try to defeat their bot protection.
- Feeding analyst consensus into `sentiment_index` or the FinBERT scoring pipeline. Consensus is numeric; that pipeline expects text sentences.
- Changing the aspect taxonomy or `similarity_floor` in `config/aspects.yaml`.
- Removing or "fixing" `ingest/analyst_tag.py`. It stays as-is; its 0-match result is a documented finding, not a bug to hide.
- Adding a `yfinance` library dependency. The direct `requests` call above is verified working and avoids a heavyweight dependency for three HTTP calls.
