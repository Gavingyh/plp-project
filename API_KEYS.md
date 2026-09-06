# API Keys — how to get them, where to put them

This project needs four credentials: NewsAPI key, Alpha Vantage key, Reddit
client ID, Reddit client secret. All four go in one file: `.env`, in this
project's root folder (same folder as `run_data_survey.py`).

```bash
cp .env.example .env
```

Then open `.env` and fill in the blanks. Nothing else needs to change —
every script calls `load_dotenv()` and reads the values from there.

Never commit `.env`. It's already listed in `.gitignore`. If you ever paste
a real key into a chat, issue, or commit by mistake, treat it as burned and
regenerate it.

## 1. NewsAPI

1. Go to https://newsapi.org/register
2. Sign up with an email (no card required for the free "Developer" tier).
3. Your key is shown immediately on the dashboard after signup, and also
   emailed to you — https://newsapi.org/account
4. Copy it into `.env`:
   ```
   NEWSAPI_KEY=paste_your_key_here
   ```

Free tier limits: 100 requests/day, and article search only covers roughly
the last month. Fine for the volume survey; not enough for a longer
historical pull.

## 2. Alpha Vantage

1. Go to https://www.alphavantage.co/support/#api-key
2. Enter your email and click "GET FREE API KEY" — no signup form, no
   password, the key is generated and displayed on the same page.
3. Copy it into `.env`:
   ```
   ALPHAVANTAGE_KEY=paste_your_key_here
   ```

Free tier limits: 25 requests/day total (not per-endpoint). The demo key
(`demo`) only works for a handful of hardcoded example tickers — it will
not return anything for DBS/OCBC/UOB, so you do need your own key.

## 3. Reddit

Reddit requires an actual "app" registration, not just an API key — three
values come out of this step.

1. Log into Reddit, go to https://www.reddit.com/prefs/apps
2. Click "create another app..." (bottom of the page).
3. Fill in:
   - name: anything, e.g. `plp-practice-module`
   - type: select **script**
   - redirect uri: `http://localhost:8080` (required by the form, unused
     by this project since it's read-only)
4. Click "create app".
5. Read the values off the app tile that appears:
   - **client_id** — the string directly under the app name / under
     "personal use script", NOT labeled explicitly
   - **client_secret** — labeled "secret"
6. Copy both into `.env`, and set a descriptive user agent (Reddit will
   throttle or block generic/default user agents):
   ```
   REDDIT_CLIENT_ID=paste_client_id_here
   REDDIT_CLIENT_SECRET=paste_secret_here
   REDDIT_USER_AGENT=plp-practice-module/0.1 by u/your_actual_username
   ```

Free tier: 100 queries/minute, non-commercial/research use only per
Reddit's API terms.

## Verifying it worked

Run one script standalone before running the full survey, so a bad key
fails fast and cheap:

```bash
python news_pull.py
```

If a key is missing, the script prints a `Skipped — set <VAR> env var`
message for that source instead of crashing — that's expected, not a bug.
If a key is present but wrong, you'll see an `ERROR —` line with the
underlying HTTP error (401/403 usually means a bad or not-yet-active key).
