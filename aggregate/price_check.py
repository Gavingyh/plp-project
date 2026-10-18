"""
Does the sentiment index track anything outside itself?

The Practice Module's sentiment-mining course ends a system's design with
business measures (its financial-prediction application relates sentiment to
markets). So far nothing shows the index relates to what happened to the banks.
This compares it with the banks' share prices in two ways, and reports what it
finds as exploratory, never as a trading signal:

  1. Monthly: the index for each month against that month's share-price return
     and the next month's (does sentiment move with the price, or ahead of it?),
     per bank and pooled. Spearman rank correlation with a bootstrap interval
     and a permutation p-value.
  2. Earnings events: the tone of a bank's results documents against the share
     price's reaction on the release day, relative to the other two banks. Needs
     the real release dates in data/prices/earnings_dates.csv (columns: bank,
     date). The database's dates for earnings documents are the first of the
     month, not the release day, so they cannot be used for this.

Read the result with its limits in mind. There are few months (the news sources
start in 2023) and a handful of earnings releases per bank, so only a large
relationship would show; the three banks' prices move together; and a
correlation in 20 tests would turn up by chance about once. A result of "no
clear relationship" is an honest finding and the report should say that.

Share prices: data/prices/<BANK>.csv with columns Date and Close (adjusted close
is best). `--fetch` downloads them with yfinance (already a dependency; the tickers
are those in the analyst_consensus table) for banks whose file is missing.
The database is read only (set PLP_DB_PATH to use a copy).

USAGE:
  python -m aggregate.price_check --fetch
  python -m aggregate.price_check --min-n 30 --out data/eval/price_check
Output goes to data/eval/price_check/ (price_check.md and price_check.json).
"""

import argparse
import json
import os
import sqlite3

import numpy as np
import pandas as pd

from aggregate import index as ix
from aggregate import uncertainty as unc

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES_DIR = os.path.join(BASE_DIR, "data", "prices")
DEFAULT_OUT = os.path.join(BASE_DIR, "data", "eval", "price_check")
BANKS = unc.BANKS
SEED = 2026


# --- prices --------------------------------------------------------------------------

def fetch_prices(prices_dir: str, tickers: dict[str, str]) -> list[str]:
    """Download daily closes with yfinance for every bank without a file."""
    import yfinance as yf
    os.makedirs(prices_dir, exist_ok=True)
    got = []
    for bank, ticker in tickers.items():
        path = os.path.join(prices_dir, f"{bank}.csv")
        if os.path.exists(path):
            continue
        hist = yf.Ticker(ticker).history(period="max", auto_adjust=True)
        if hist.empty:
            raise RuntimeError(f"yfinance returned no prices for {ticker}")
        out = hist[["Close"]].copy()
        out.index = pd.to_datetime(out.index).tz_localize(None).strftime("%Y-%m-%d")
        out.index.name = "Date"
        out.to_csv(path)
        got.append(bank)
    return got


def load_prices(prices_dir: str) -> dict[str, pd.Series]:
    out = {}
    for bank in BANKS:
        path = os.path.join(prices_dir, f"{bank}.csv")
        if os.path.exists(path):
            df = pd.read_csv(path)
            df["Date"] = pd.to_datetime(df["Date"])
            out[bank] = df.set_index("Date")["Close"].astype(float).sort_index()
    return out


def monthly_returns(close: pd.Series) -> pd.Series:
    """Month-end close to month-end close, indexed by 'YYYY-MM'."""
    month_end = close.groupby(close.index.to_period("M")).last()
    ret = month_end.pct_change().dropna()
    ret.index = ret.index.astype(str)
    return ret


def daily_returns(close: pd.Series) -> pd.Series:
    return close.pct_change().dropna()


# --- statistics (pure, tested) ---------------------------------------------------------

def spearman(x, y) -> float:
    x, y = pd.Series(list(x)), pd.Series(list(y))
    if len(x) < 3 or x.nunique() < 2 or y.nunique() < 2:
        return float("nan")
    return float(x.rank().corr(y.rank()))


def permutation_p(x, y, rounds: int = 5000, seed: int = SEED) -> float:
    """Two-sided p-value: how often a shuffled pairing correlates at least as strongly."""
    rng = np.random.default_rng(seed)
    x = np.asarray(list(x), float); y = np.asarray(list(y), float)
    observed = abs(spearman(x, y))
    if np.isnan(observed):
        return float("nan")
    hits = sum(abs(spearman(x, rng.permutation(y))) >= observed - 1e-12 for _ in range(rounds))
    return float((hits + 1) / (rounds + 1))


def bootstrap_interval(x, y, rounds: int = 2000, seed: int = SEED) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    x = np.asarray(list(x), float); y = np.asarray(list(y), float)
    n = len(x)
    vals = []
    for _ in range(rounds):
        idx = rng.integers(0, n, n)
        r = spearman(x[idx], y[idx])
        if not np.isnan(r):
            vals.append(r)
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if vals else (float("nan"),) * 2


def relation(x, y, rounds: int = 3000) -> dict:
    x, y = list(x), list(y)
    lo, hi = bootstrap_interval(x, y)
    return {"n": len(x), "rho": round(spearman(x, y), 3), "low": round(lo, 3), "high": round(hi, 3),
            "p_permutation": round(permutation_p(x, y, rounds), 4)}


def align(index_by_month: pd.Series, returns: pd.Series, lag: int) -> pd.DataFrame:
    """Pairs the index of month t with the return of month t+lag (lag 0 = the same
    month; 1 = the next month; -1 = the month before, i.e. sentiment following price)."""
    months = sorted(set(index_by_month.index))
    pos = {m: i for i, m in enumerate(sorted(set(index_by_month.index) | set(returns.index)))}
    ordered = sorted(pos, key=pos.get)
    rows = []
    for m in months:
        i = ordered.index(m) + lag
        if 0 <= i < len(ordered) and ordered[i] in returns.index:
            rows.append((m, index_by_month[m], returns[ordered[i]]))
    return pd.DataFrame(rows, columns=["month", "index", "return"])


# --- index per month and per release ---------------------------------------------------

def monthly_index(records, bank: str, min_n: int) -> pd.Series:
    """The bank's headline score for each month with at least min_n sentences, by
    the index's own formula."""
    by_month: dict[str, list] = {}
    best: dict = {}
    for b, aspect, src, published_at, sid, doc_id, label, conf in records:
        if b != bank:
            continue
        if sid not in best or conf > best[sid][0]:
            best[sid] = (conf, published_at, (ix._LABEL_SCORE[label], conf,
                                              ix._SOURCE_WEIGHT.get(src, ix._DEFAULT_WEIGHT)))
    for conf, published_at, item in best.values():
        period = ix._period(published_at, "month")
        if period:
            by_month.setdefault(period, []).append((_label_name(item[0]), item[1], item[2]))
    out = {}
    for period, items in by_month.items():
        if len(items) >= min_n:
            out[period] = ix._summarize(items)[0]
    return pd.Series(out).sort_index()


def _label_name(score: float) -> str:
    return {1.0: "positive", 0.0: "neutral", -1.0: "negative"}[score]


def earnings_tone(records, bank: str, month: str) -> tuple[float | None, int]:
    """Score of the bank's own earnings sentences in the release's month."""
    items = []
    best: dict = {}
    for b, aspect, src, published_at, sid, doc_id, label, conf in records:
        if b == bank and src == "earnings" and ix._period(published_at, "month") == month:
            if sid not in best or conf > best[sid][0]:
                best[sid] = (conf, (_label_name(ix._LABEL_SCORE[label]), conf,
                                    ix._SOURCE_WEIGHT.get(src, ix._DEFAULT_WEIGHT)))
    items = [v[1] for v in best.values()]
    return (ix._summarize(items)[0], len(items)) if len(items) >= ix.MIN_N else (None, len(items))


def event_study(records, prices: dict[str, pd.Series], dates: pd.DataFrame) -> dict:
    """Tone of each release against the share price's reaction on the release day,
    relative to the other banks, and the tone's change from the bank's previous release."""
    daily = {b: daily_returns(c) for b, c in prices.items()}
    rows = []
    for bank in BANKS:
        if bank not in daily:
            continue
        mine = dates[dates["bank"] == bank].sort_values("date")
        previous = None
        for date in pd.to_datetime(mine["date"]):
            if date not in daily[bank].index:
                continue   # a non-trading day: the reaction is not defined
            others = [daily[o].get(date) for o in BANKS if o != bank and o in daily]
            others = [v for v in others if v is not None and not np.isnan(v)]
            if not others:
                continue
            tone, n = earnings_tone(records, bank, date.strftime("%Y-%m"))
            if tone is None:
                continue
            rows.append({"bank": bank, "date": date.strftime("%Y-%m-%d"), "tone": tone, "n": n,
                         "tone_change": None if previous is None else round(tone - previous, 4),
                         "abnormal_return": float(daily[bank][date] - np.mean(others))})
            previous = tone
    df = pd.DataFrame(rows)
    out = {"events": rows}
    if len(df) >= 6:
        out["tone_vs_reaction"] = relation(df["tone"], df["abnormal_return"])
        sub = df.dropna(subset=["tone_change"])
        if len(sub) >= 6:
            out["tone_change_vs_reaction"] = relation(sub["tone_change"], sub["abnormal_return"])
    return out


# --- run -----------------------------------------------------------------------------

def run(model_version: str, prices_dir: str, min_n: int, out_dir: str, fetch: bool) -> dict:
    from ingest.db import DB_PATH
    os.makedirs(out_dir, exist_ok=True)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        records = unc.collect(conn, model_version)
        tickers = dict(conn.execute("SELECT DISTINCT bank, ticker FROM analyst_consensus").fetchall())
    finally:
        conn.close()
    if fetch:
        fetch_prices(prices_dir, tickers)
    prices = load_prices(prices_dir)
    if not prices:
        raise SystemExit(f"No price files in {prices_dir}. Add <BANK>.csv (Date, Close) or run with --fetch.")

    results = {"model_version": model_version, "min_sentences_per_month": min_n, "monthly": {}, "pooled": {}}
    pooled = {lag: [] for lag in (-1, 0, 1)}
    for bank in BANKS:
        if bank not in prices:
            continue
        idx = monthly_index(records, bank, min_n)
        ret = monthly_returns(prices[bank])
        results["monthly"][bank] = {"months_with_index": len(idx)}
        for lag in (-1, 0, 1):
            pairs = align(idx, ret, lag)
            pooled[lag].append(pairs)
            if len(pairs) >= 8:
                results["monthly"][bank][f"lag_{lag}"] = relation(pairs["index"], pairs["return"])
    for lag, frames in pooled.items():
        if frames:
            both = pd.concat(frames)
            if len(both) >= 8:
                results["pooled"][f"lag_{lag}"] = relation(both["index"], both["return"])
    dates_path = os.path.join(prices_dir, "earnings_dates.csv")
    if os.path.exists(dates_path):
        results["events"] = event_study(records, prices, pd.read_csv(dates_path))
    else:
        results["events"] = {"skipped": f"{dates_path} not found (columns: bank, date)"}
    with open(os.path.join(out_dir, "price_check.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    with open(os.path.join(out_dir, "price_check.md"), "w", encoding="utf-8") as f:
        f.write(render(results))
    return results


def render(results: dict) -> str:
    L = ["# The index against share prices", "",
         f"Model `{results['model_version']}`; months with at least {results['min_sentences_per_month']} sentences. "
         "Spearman rank correlation; the interval is a bootstrap 95% interval and p a permutation test. "
         "Exploratory: see the limits in the module's header before quoting any line.", "",
         "Lag 0 pairs a month's index with that month's return, lag 1 with the next month's (sentiment ahead of "
         "the price), lag -1 with the previous month's (sentiment following the price).", "",
         "| group | lag | months | rho | 95% interval | p |", "|---|---|---|---|---|---|"]
    for bank, d in results["monthly"].items():
        for lag in (-1, 0, 1):
            r = d.get(f"lag_{lag}")
            if r:
                L.append(f"| {bank} | {lag} | {r['n']} | {r['rho']:+.2f} | {r['low']:+.2f} to {r['high']:+.2f} | {r['p_permutation']:.3f} |")
    for key, r in results["pooled"].items():
        L.append(f"| all banks pooled | {key.split('_')[1]} | {r['n']} | {r['rho']:+.2f} | {r['low']:+.2f} to {r['high']:+.2f} | {r['p_permutation']:.3f} |")
    L += ["", "## Earnings releases", ""]
    ev = results["events"]
    if "skipped" in ev:
        L.append(f"Skipped: {ev['skipped']}.")
    else:
        L.append(f"{len(ev['events'])} releases with a trading-day reaction and enough earnings sentences.")
        for key, title in (("tone_vs_reaction", "tone against abnormal return"),
                           ("tone_change_vs_reaction", "change in tone against abnormal return")):
            r = ev.get(key)
            L.append(f"- {title}: n={r['n']}, rho {r['rho']:+.2f} ({r['low']:+.2f} to {r['high']:+.2f}), p {r['p_permutation']:.3f}"
                     if r else f"- {title}: too few releases to test.")
    return "\n".join(L) + "\n"


def main():
    from config import model_version as mv
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--model-version", default=mv.MODEL_VERSION)
    p.add_argument("--prices-dir", default=PRICES_DIR)
    p.add_argument("--min-n", type=int, default=30, help="sentences a month needs to count")
    p.add_argument("--fetch", action="store_true", help="download missing prices with yfinance")
    p.add_argument("--out", default=DEFAULT_OUT)
    args = p.parse_args()
    results = run(args.model_version, args.prices_dir, args.min_n, args.out, args.fetch)
    print(render(results))
    print(f"Full output in {args.out}")


if __name__ == "__main__":
    main()
