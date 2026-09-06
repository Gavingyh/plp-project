"""
Single entry point for the Option 2a data-volume survey (DBS / OCBC / UOB).

Runs news_pull.py and reddit_pull.py in sequence, then writes one combined
report so the team can decide, in one sitting, whether the data is thick
enough to proceed — instead of eyeballing two separate console outputs.

USAGE:
  1. cp .env.example .env   (then fill in your API keys)
  2. pip install -r requirements.txt
  3. python run_data_survey.py

OUTPUT:
  ./data/news_newsapi_raw.csv
  ./data/news_alphavantage_raw.csv
  ./data/reddit_raw.csv
  ./data/survey_report.txt   <- read this one first
"""

import os
import sys
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))  # explicit — don't rely on news_pull's import side effect

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Reasonable minimum thresholds for "is this usable" — adjust based on team judgement,
# but these give a concrete first cut instead of a vague impression.
MIN_NEWS_PER_BANK = 15
MIN_REDDIT_PER_BANK = 10


def run_news():
    print("\n" + "#" * 60)
    print("# STEP 1/2: News pull")
    print("#" * 60)
    import news_pull
    df_newsapi = news_pull.pull_newsapi()
    df_av = news_pull.pull_alphavantage()
    return df_newsapi, df_av


def run_reddit():
    print("\n" + "#" * 60)
    print("# STEP 2/2: Reddit pull")
    print("#" * 60)
    import reddit_pull
    reddit_pull.main()
    path = os.path.join(DATA_DIR, "reddit_raw.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


def build_report(df_newsapi, df_av, df_reddit):
    lines = []
    lines.append(f"Data survey report — generated {datetime.now().isoformat()}")
    lines.append("=" * 60)

    verdicts = {}

    lines.append("\nNEWS — NewsAPI")
    if df_newsapi.empty:
        lines.append("  No data (key missing or zero results).")
    else:
        counts = df_newsapi.groupby("bank").size()
        for bank, n in counts.items():
            ok = n >= MIN_NEWS_PER_BANK
            verdicts[f"news_newsapi_{bank}"] = ok
            lines.append(f"  {bank:5s}: {n:4d} articles  [{'OK' if ok else 'THIN'}]")

    lines.append("\nNEWS — Alpha Vantage")
    if df_av.empty:
        lines.append("  No data (key missing, zero results, or tickers not indexed).")
    else:
        counts = df_av.groupby("bank").size()
        for bank, n in counts.items():
            ok = n >= MIN_NEWS_PER_BANK
            verdicts[f"news_av_{bank}"] = ok
            lines.append(f"  {bank:5s}: {n:4d} articles  [{'OK' if ok else 'THIN'}]")

    lines.append("\nREDDIT")
    if df_reddit.empty:
        lines.append("  No data (credentials missing or zero results).")
    else:
        counts = df_reddit[df_reddit["type"] == "submission"].groupby(["subreddit", "bank"]).size()
        for (sub, bank), n in counts.items():
            ok = n >= MIN_REDDIT_PER_BANK
            verdicts[f"reddit_{sub}_{bank}"] = ok
            lines.append(f"  {sub:22s} | {bank:5s}: {n:4d} submissions  [{'OK' if ok else 'THIN'}]")

    lines.append("\n" + "=" * 60)
    lines.append("VERDICT")
    lines.append("=" * 60)
    if not verdicts:
        lines.append("No sources returned data — set API keys in .env and re-run before "
                      "making any go/no-go call.")
    else:
        thin = [k for k, ok in verdicts.items() if not ok]
        if not thin:
            lines.append("All checked sources meet the minimum volume threshold. "
                          "Proceed with Option 2a as scoped.")
        else:
            lines.append(f"{len(thin)} of {len(verdicts)} checks came back THIN:")
            for k in thin:
                lines.append(f"  - {k}")
            lines.append("\nThin does not automatically mean abandon the option — it means "
                          "decide explicitly: widen the time window, add a data source, or "
                          "accept a smaller training set for that bank/source combination. "
                          "Don't proceed silently assuming it'll be fine.")

    report = "\n".join(lines)
    report_path = os.path.join(DATA_DIR, "survey_report.txt")
    with open(report_path, "w") as f:
        f.write(report)
    print("\n" + report)


if __name__ == "__main__":
    df_newsapi, df_av = run_news()
    df_reddit = run_reddit()
    build_report(df_newsapi, df_av, df_reddit)
    print(f"\nFull report written to: {os.path.join(DATA_DIR, 'survey_report.txt')}")
