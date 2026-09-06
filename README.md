# plp-data

Data-volume survey for the Practice Module project (DBS / OCBC / UOB sentiment dashboard).

## What this does
Pulls a test sample from three sources — NewsAPI, Alpha Vantage, Reddit — for each of
the three banks, and produces one report telling you which bank/source combinations
have enough volume to build on, and which are too thin.

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env
```
Fill in `.env` with your own keys. See **[API_KEYS.md](API_KEYS.md)** for
step-by-step instructions on getting each one:
- NewsAPI: https://newsapi.org/register
- Alpha Vantage: https://www.alphavantage.co/support/#api-key
- Reddit: https://www.reddit.com/prefs/apps (create app, type: script)

## Run
```bash
python run_data_survey.py
```

This runs both pulls and writes `data/survey_report.txt` — read that file first.
Raw pulled data is also saved to `data/*.csv` for inspection.

## Files
- `news_pull.py` — NewsAPI + Alpha Vantage pull, can be run standalone
- `reddit_pull.py` — Reddit pull via PRAW, can be run standalone
- `run_data_survey.py` — runs both, produces the combined go/no-go report
- `.env.example` — copy to `.env` and fill in keys (never commit `.env`)
- `API_KEYS.md` — how to get each API key and where to put it

## Notes
- NewsAPI free tier only covers ~1 month lookback. If the project needs a longer
  historical window, that's a paid-tier or alternative-source decision — this script
  will not silently work around it.
- Alpha Vantage pull only keeps raw article title/summary text, not its built-in
  sentiment score — that score must not be used as your DNN's training label.
- Reddit free tier: 100 queries/minute, non-commercial/research use only.
- Thresholds for "OK" vs "THIN" in the report (15 news articles/bank, 10 Reddit
  submissions/bank/subreddit) are a starting point, not a hard rule — adjust in
  `run_data_survey.py` if the team agrees on different numbers.
