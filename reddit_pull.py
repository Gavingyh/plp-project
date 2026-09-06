"""
Reddit data pull for SG bank sentiment project (DBS / OCBC / UOB).

SETUP:
  pip install praw pandas

  1. Register an app at https://www.reddit.com/prefs/apps
     - Click "create another app..."
     - Type: script
     - redirect uri: http://localhost:8080 (unused but required)
  2. Note your client_id (under the app name) and client_secret.
  3. Set env vars before running:
       export REDDIT_CLIENT_ID="your_id"
       export REDDIT_CLIENT_SECRET="your_secret"
       export REDDIT_USER_AGENT="plp-practice-module/0.1 by u/your_username"

USAGE:
  python reddit_pull.py

OUTPUT:
  ./data/reddit_raw.csv
  Prints a volume summary per bank per subreddit — this is your go/no-go
  signal on whether Reddit has enough SG-bank discussion to support a
  second sentiment DNN.
"""

import os
import time
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))  # load .env from project root regardless of cwd

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "plp-practice-module/0.1")

SUBREDDITS = ["SingaporeInvestments", "singapore", "investing"]

BANKS = {
    "DBS": ["DBS", "DBS Bank", "DBS Group"],
    "OCBC": ["OCBC"],
    "UOB": ["UOB"],
}

SEARCH_LIMIT_PER_QUERY = 100  # PRAW search cap per call; adjust if needed


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Missing REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET env vars. "
              "Register an app at https://www.reddit.com/prefs/apps first.")
        return

    import praw  # imported here so the missing-key message above shows even without praw installed

    reddit = praw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT,
    )
    reddit.read_only = True

    rows = []
    volume_counts = {}

    for sub_name in SUBREDDITS:
        subreddit = reddit.subreddit(sub_name)
        for bank, terms in BANKS.items():
            query = " OR ".join(terms)
            count = 0
            try:
                for submission in subreddit.search(query, sort="new", limit=SEARCH_LIMIT_PER_QUERY, time_filter="year"):
                    rows.append({
                        "bank": bank,
                        "subreddit": sub_name,
                        "type": "submission",
                        "id": submission.id,
                        "title": submission.title,
                        "selftext": submission.selftext,
                        "score": submission.score,
                        "num_comments": submission.num_comments,
                        "created_utc": submission.created_utc,
                        "url": f"https://reddit.com{submission.permalink}",
                    })
                    count += 1

                    # Pull top-level comments too — often where actual sentiment/discussion lives
                    submission.comments.replace_more(limit=0)
                    for comment in submission.comments.list()[:20]:
                        rows.append({
                            "bank": bank,
                            "subreddit": sub_name,
                            "type": "comment",
                            "id": comment.id,
                            "title": None,
                            "selftext": comment.body,
                            "score": comment.score,
                            "num_comments": None,
                            "created_utc": comment.created_utc,
                            "url": f"https://reddit.com{comment.permalink}",
                        })

            except Exception as e:
                print(f"[{sub_name} / {bank}] ERROR — {e}")

            volume_counts[(sub_name, bank)] = count
            print(f"[{sub_name}] {bank}: {count} submissions found")
            time.sleep(1)  # stay well under 100 QPM

    df = pd.DataFrame(rows)
    if not df.empty:
        df.to_csv(os.path.join(DATA_DIR, "reddit_raw.csv"), index=False)

    print("\n" + "=" * 50)
    print("VOLUME SUMMARY — use this to decide go/no-go on Reddit source")
    print("=" * 50)
    for (sub_name, bank), count in volume_counts.items():
        print(f"  {sub_name:22s} | {bank:5s} | {count} submissions (last 12 months)")

    if df.empty:
        print("\nNo data pulled — check your API credentials.")
    else:
        print(f"\nTotal rows collected (submissions + comments): {len(df)}")
        print("If any bank shows single-digit submission counts, that bank/subreddit "
              "combo is too thin to rely on for training data — note this now, not in week 2.")


if __name__ == "__main__":
    print(f"Run started: {datetime.now().isoformat()}\n")
    main()
