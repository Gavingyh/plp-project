# API keys: how to get them, where to put them

**One key matters: `OPENAI_API_KEY`, for the chatbot's answers.** The
chatbot answers with OpenAI's `gpt-6-luna` by default (`backend` in
`config/chatbot.yaml`). Without the key, the dashboard and the API still
work and the chat explains the missing setting; a missing key never makes
the chatbot switch to another provider (`chatbot/backends/__init__.py`).
For answers with no key at all, set `CHATBOT_BACKEND=ollama`: a local
`llama3.1:8b` through Ollama answers instead. The question classifier runs
locally on `llama3.1:8b` with either choice.

Everything else runs without a key: Reddit comes from Arctic Shift, the
earnings PDFs from the banks' sites and the Wayback Machine, analyst
consensus from Yahoo Finance.

| key | what it adds | needed? |
|---|---|---|
| `OPENAI_API_KEY` | the chatbot's default answer model, `gpt-6-luna` | for chatbot answers, unless `CHATBOT_BACKEND=ollama` |
| `ANTHROPIC_API_KEY` | Claude as the answer model, with `CHATBOT_BACKEND=claude` | optional |
| `NEWSAPI_KEY` | news articles, about one month of lookback on the free tier | optional |
| `ALPHAVANTAGE_KEY` | nothing, see below | no |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | nothing, see below | no |

A hosted model receives the question, the tools' figures, and quoted
sentences from CNA, broker research, news and the banks' reports. It never
receives Reddit text (`hosted_model` in `config/sources.yaml`,
`chatbot/backends/base.py`). The Gemini backend has been removed.

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
> They are still in the git history and should be treated as compromised:
> regenerate both. See [docs/HANDOFF.md](docs/HANDOFF.md).

## 1. OpenAI

1. Sign in at https://platform.openai.com and open the API keys page.
2. Create a key and copy it into `.env`:
   ```
   OPENAI_API_KEY=paste_your_key_here
   ```
3. Restart the API (`scripts/stop.sh api`, then `scripts/start.sh api`; in
   Docker, `docker compose up -d api`). The key stays on the API machine and
   is never sent to the dashboard.

`OPENAI_MODEL` and `OPENAI_BASE_URL` in `.env.example` change the model or
point at another OpenAI-compatible provider.

## Two keys you can skip

**Alpha Vantage** is retained in the codebase but contributes nothing. It
does not index SGX-listed tickers at all: tested live across `D05`, `D05SI`
and `D05-SI` for all three banks, every response an empty feed. The adapter
stays in case coverage is added later. Details in
[docs/data-viability.md](docs/data-viability.md).

**Reddit credentials are no longer used.** Reddit declined this project's API
application, so PRAW was unavailable and ingestion moved to Arctic Shift, a
public archive with no key and several years more history. The section below
is kept for the record; `ingest/arctic_shift.py` is what actually runs.

## 2. NewsAPI

1. Go to https://newsapi.org/register
2. Sign up with an email (no card required for the free "Developer" tier).
3. Your key is shown immediately on the dashboard after signup, and also
   emailed to you: https://newsapi.org/account
4. Copy it into `.env`:
   ```
   NEWSAPI_KEY=paste_your_key_here
   ```

Free tier limits: 100 requests/day, and article search only covers roughly
the last month, with a 24-hour delay ([current plans](https://newsapi.org/pricing)).
Fine for local development/testing; today's articles may not be available yet.
The dashboard's **Data Management → NewsAPI** option uses this key on the API
machine. Restart the API after changing it, then refresh the dashboard. Missing
keys disable this source and exclude it from **All available sources**.

## 3. Alpha Vantage *(historical: contributes nothing, see above)*

1. Go to https://www.alphavantage.co/support/#api-key
2. Enter your email and click "GET FREE API KEY": no signup form, no
   password, the key is generated and displayed on the same page.
3. Copy it into `.env`:
   ```
   ALPHAVANTAGE_KEY=paste_your_key_here
   ```

Free tier limits: 25 requests/day total (not per-endpoint). The demo key
(`demo`) only works for a handful of hardcoded example tickers; it will
not return anything for DBS/OCBC/UOB, so you do need your own key.

## 4. Reddit *(historical: not used; Arctic Shift replaced it)*

Reddit requires an actual "app" registration, not just an API key; three
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
   - **client_id**: the string directly under the app name / under
     "personal use script", NOT labeled explicitly
   - **client_secret**: labeled "secret"
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

Run NewsAPI on its own through **Data Management**, or use the manual runner
(**this collects, analyses and writes to the configured database**):

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pipeline.runner --sources newsapi
```

A missing key fails prerequisite checks before import. Invalid/disabled keys,
exhausted quota and plan/date limits are reported in the run without exposing
the key. The API and worker never send the key to the dashboard.
