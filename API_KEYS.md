# API Keys — how to get them, where to put them

**The project runs with no API key at all.** Reddit comes from Arctic Shift
(no key), earnings PDFs from the banks' IR sites and the Wayback Machine, and
the chatbot from a local model via Ollama. Keys only add optional sources.

| key | what it adds | needed? |
|---|---|---|
| *(none)* | Reddit, earnings PDFs, Yahoo consensus, local chatbot | — |
| `NEWSAPI_KEY` | news articles, ~1 month lookback on the free tier | optional |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | a hosted chatbot model instead of the local one | optional |
| `ALPHAVANTAGE_KEY` | nothing — see below | no |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | nothing — see below | no |

Keys go in `.env` in the project root:

```bash
cp .env.example .env
```

Then open `.env` and fill in whichever you want. Every script calls
`load_dotenv()` and reads the values from there.

Never commit `.env`. It's in `.gitignore`. `.env.example` **is** tracked, so
every value in it must stay a placeholder.

> **This has already gone wrong once.** Real NewsAPI and Alpha Vantage keys
> were committed in `.env.example` from the first commit until 2026-09-11.
> They are still in the git history and should be treated as compromised —
> regenerate both. See [docs/HANDOFF.md](docs/HANDOFF.md).

## Two keys you can skip

**Alpha Vantage** is retained in the codebase but contributes nothing. It
does not index SGX-listed tickers at all — tested live across `D05`, `D05SI`
and `D05-SI` for all three banks, every response an empty feed. The adapter
stays in case coverage is added later. Details in
[docs/data-viability.md](docs/data-viability.md).

**Reddit credentials are no longer used.** Reddit declined this project's API
application, so PRAW was unavailable and ingestion moved to Arctic Shift, a
public archive with no key and several years more history. The section below
is kept for the record; `ingest/arctic_shift.py` is what actually runs.

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

## 2. Alpha Vantage *(historical — contributes nothing, see above)*

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

## 3. Reddit *(historical — not used; Arctic Shift replaced it)*

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
