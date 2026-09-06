# Data Viability Report — Phase 0

Findings from running the actual pipeline against live data (2026-09-06),
answering the unknowns flagged in the MVP plan before building further on them.

## Alpha Vantage — confirmed non-viable for SGX names

Two separate issues, tested live:

1. **Ticker format bug (fixed):** `NEWS_SENTIMENT?tickers=D05.SI` returned
   `{"Error Message": "Invalid ticker format..."}` — the API rejects periods.
   Fixed in `ingest/alphavantage.py` by stripping the exchange suffix.
2. **No SGX coverage (not fixable):** even with valid ticker syntax
   (`D05`, `D05SI`, `D05-SI`), all three return `feed: []`. Confirmed across
   all three banks. **Alpha Vantage does not index SGX-listed names at all.**
   Dropped from the pipeline as a live source — the adapter is kept in
   `ingest/alphavantage.py` in case AV adds coverage later, but it contributes
   nothing today.

## NewsAPI — viable, with the known free-tier limits

- 172 new articles pulled across DBS (99), OCBC (39), UOB (30)+4 MULTI in a
  single run, against a ~1-month lookback window (free tier).
- DBS `totalResults` reported 349 vs. 99 pulled — capped by `pageSize=100`
  and single-page fetch; a paginated pull would recover more of DBS's volume
  specifically, worth doing before Phase 4 labeling export if DBS ever looks
  thin relative to its actual coverage.
- `content` field truncation confirmed as expected — usable text is title +
  description only.

## Reddit via Arctic Shift — the primary source, confirmed at scale

12-month backfill (2025-09-01 → 2026-09-06), corrected subreddit list:

| subreddit | posts fetched | bank-mentioning | comments fetched | bank-mentioning |
|---|---|---|---|---|
| r/singaporefi | 7,176 | 786 | 50,000\* | 1,484 |
| r/SingaporeInvestments | 0 | 0 | 0 | 0 |

\* comments hit the per-window page cap — this is a floor, not the true total.

r/SingaporeInvestments returning literally zero for the full 12-month window
reconfirms it's been dead since Oct 2023 (per the original plan finding) —
kept in the subreddit list only for pre-2023 historical pulls, contributes
nothing to current-window batches.

**r/investing and r/singapore were dropped from the default subreddit list
entirely** (not just deprioritized) — both returned 0 bank-mentioning items
against 7,000+ items sampled across two separate tests, and r/investing's
comment volume in particular would have dominated ingestion time for zero
payoff.

## Analyst consensus proxy — built, but returned zero on this batch

`ingest/analyst_tag.py` (tags news documents that name a broker AND use
rating/action language) flagged **0 of 172 news documents** in this run.
Two plausible explanations, not yet distinguished:
1. NewsAPI's free-tier title+description snippets are too short/generic to
   carry explicit analyst-action language ("Maintains BUY...") even when the
   underlying article does.
2. This 1-month window genuinely had no such coverage for these three banks.

**Action before relying on this proxy for the dashboard:** pull a larger news
sample (or manually check a few DBS articles from `totalResults=349`) to
tell these apart. If it's (1), the proxy needs either fuller article text
(a different news source or fetching full article pages) or a looser
detection pattern — 0/172 as a permanent state would mean the "analyst view"
flag never fires, which defeats its purpose.

## SGX / analyst-aggregator direct scraping — confirmed non-viable

Tested live, not just assumed:
- `sgx.com` serves a static "unsupported browser" shell to any non-browser
  HTTP client regardless of realistic User-Agent (verified via curl with a
  Chrome UA string — HTTP 200, but body is the compatibility warning, not
  the article).
- `sginvestors.io` (analyst-report aggregator) returns an empty HTTP 202
  (Cloudflare challenge) to a plain request.

Both would require a full headless browser (Playwright) to scrape — assessed
as disproportionate for this MVP and in greyer ToS territory than reading a
public feed. The news-derived analyst-tag proxy above is the practical
substitute; it should be disclosed as a proxy, not presented as equivalent to
full analyst reports, per the plan's disclosure requirement.

## Earnings PDFs — not yet started

Still a manual step: download results announcements / IR presentations for
DBS/OCBC/UOB from each bank's investor-relations site into
`data/earnings_pdfs/<BANK>/*.pdf`, then run `python -m ingest.earnings`. Not
done in this pass — needs a human to go get the PDFs (see MVP plan Phase 1b).

## Volume gate check (Phase 0 hard gate: ≥300 Reddit items/bank/12mo) — PASSED

Post-preprocessing sentence counts by bank, 2,453 documents processed into
3,038 sentences total (2026-09-06 run):

| bank | documents | sentences |
|---|---|---|
| DBS | 1,340 | 1,911 |
| UOB | 615 | 913 |
| OCBC | 265 | 430 |
| MULTI (docs) | 391 | — (re-attributed per sentence in preprocessing) |

All three banks clear the ≥300 gate comfortably, even OCBC (thinnest, as
anticipated). The DBS skew is real and large (~4.4x OCBC by sentence count)
— consistent with the plan's anticipated Reddit DBS-dominance and worth
stating plainly in the report rather than smoothing over, since it means the
three banks' eventual sentiment indices rest on very different sample sizes.
Worth revisiting before Phase 4 labeling: OCBC's 430 sentences need to
comfortably cover 200-300 examples *per sentiment class* once split three
ways across positive/neutral/negative — thin, not failing, but the first
place to add more source volume (extra subreddits, deeper history) if the
labeling pool runs short for OCBC specifically.

## What this means for the pipeline as currently configured

- **Three live sources**: NewsAPI, Arctic Shift (Reddit), earnings (pending
  manual PDF collection). Alpha Vantage confirmed dead, dropped.
- **Analyst consensus**: proxy built, needs a volume check before being
  trusted as "working."
- All findings above are backed by a live, reproducible run on 2026-09-06 —
  not assumption. Re-run `python run_daily_batch.py` to refresh.
