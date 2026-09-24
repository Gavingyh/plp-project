# News dataset

How the news part of `data/plp.db` was collected, what it covers, and where it
falls short. Written for the report's datasets section. Numbers are as of
2026-09-24, after the pull (`python run_news_pull.py`) and the cleanup
described below; re-run `python run_news_pull.py --report` for the current
table.

## Sources

| source (`documents.source`) | endpoint | text stored | coverage | rows |
|---|---|---|---|---|
| `google_news` | Google News RSS search, en-SG edition, free, no key | headline only | 2023-01-01 to 2026-09-24, every month | 3,492 |
| `yahoo_news` | Yahoo Finance news via `yfinance` `Ticker.get_news`, free, no key | headline + Yahoo summary | 2025-09-29 to 2026-09-23 | 114 |
| `newsapi` | NewsAPI.org `/v2/everything`, free developer key | headline + description | 2026-08-06 to 2026-09-11 | 13 |
| `alphavantage` | Alpha Vantage `NEWS_SENTIMENT`, free key | title + summary | none | 0 |

Per bank, all news sources together (a `MULTI` row names more than one bank):

| bank | articles | first | last | months with news |
|---|---|---|---|---|
| DBS | 1,447 | 2023-01-02 | 2026-09-24 | 45 of 45 |
| OCBC | 1,012 | 2023-01-01 | 2026-09-24 | 45 of 45 |
| UOB | 910 | 2023-01-03 | 2026-09-23 | 45 of 45 |
| MULTI | 250 | 2023-03-10 | 2026-09-24 | 40 of 45 |

Before this pull, news was 20 NewsAPI rows spanning 2026-08-06 to 2026-09-05.
12 of those 20 named none of the three banks (the old NewsAPI adapter fell
back to the bank it had searched for) and were removed in the cleanup.

How each source was queried:

- **Google News** has no API. The RSS search accepts `after:YYYY-MM-DD
  before:YYYY-MM-DD`, so history is reachable one calendar month at a time.
  Two queries per bank: the quoted name from the team brief (`"DBS Group"
  Singapore`, `"OCBC Bank" Singapore`, `"UOB bank" Singapore`) and a looser
  unquoted one (`DBS bank Singapore`, `OCBC Singapore`, `UOB Singapore`). The
  loose query returned 4-7x as many items in a March 2024 probe. A response is
  capped at 100 items, so a month that returns 90 or more is split in half
  and re-queried. Requests are 2 s apart with retry and backoff.
- **Yahoo** has no date parameter and no paging: it returns the most recent
  stream per ticker, 10 items by default. Asked for 200, it returned 35-71
  unique items per bank across all tabs, reaching back about 12 months. All six listings are
  queried (SGX `D05.SI`, `O39.SI`, `U11.SI` and the US OTC ADRs `DBSDY`,
  `OVCHY`, `UOVEY`) on the `news`, `all` and `press releases` tabs. The ADR
  streams were near-copies of the SGX ones (DBS: 1 extra article out of 35).
  Yahoo is in `run_daily_batch.py`, so its coverage grows from here on.
- **NewsAPI**'s free tier only reaches back about a month.
- **Alpha Vantage** does not index SGX tickers; that was established earlier
  (docs/DESIGN.md) and it returned 0 rows again. Its vendor sentiment score
  is never stored. GDELT was not tried: Google and Yahoo already cleared the
  target of 300+ articles per bank over 6+ months.

No article pages are fetched and nothing behind a paywall is read. Straits
Times and Business Times items are headlines only.

## Filtering and dedup rules

All four sources go through `ingest/news_filter.py` before insert.

1. **Must name a bank.** The headline (plus snippet, where there is one) must
   contain DBS, OCBC or UOB, a full name, the SGX or ADR ticker, or POSB
   (DBS's own retail brand). 38% of Google's raw results (2,451 of 6,471)
   failed this: general Singapore news that the loose queries also match.
2. **Names that aren't the bank are masked first**, so they neither count as
   a mention nor cause a rejection of an article that also names a real bank:
   - brokers: UOB Kay Hian / UOB-Kay Hian / UOBKH, DBS Vickers, OCBC
     Securities
   - venues and events: OCBC Arena, OCBC Square, OCBC Cycle, DBS Marina
     Regatta, UOB Plaza, UOB Painting of the Year
   - the bank's research desk: "DBS analysts", "OCBC economist", "UOB
     Global Research"
   - a headline opening with a rating call on another company: "DBS
     maintains 'buy' on IHH", "OCBC's Lim raises fair value for SingPost".
     This rule is skipped when the headline also mentions profit, guidance,
     loan growth, NIM or dividends ("UOB CEO lowers loan growth forecast as
     profit leaps" is UOB's own news).

   "UOB Kay Hian upgrades DBS to buy" therefore counts as a DBS article, and
   "UOB Kay Hian names top picks" is rejected.
3. **Cross-source dedup.** An article is a duplicate if its normalised URL
   (scheme, `www.` and tracking parameters removed) matches a stored news
   article, or its normalised headline is at least 90% similar
   (`difflib` ratio) to one published within 3 days. The first copy stored
   wins; Yahoo runs first because it carries a summary. 173 duplicates were
   caught across and within sources.
4. **Bank attribution** comes from the text, not the query: a Google result
   for "DBS bank Singapore" that only names OCBC is stored as OCBC.

Nothing is dropped silently. `data/news_flagged.csv` lists every rejected
article once with its reason (unique-article counts) (`no_bank_mention` 2,445, `false_positive_only` 164,
`duplicate` 173), every kept article that had a phrase masked (15), and
every kept headline that credits the bank as speaker at the end, such as
"Vietnam currency to strengthen: UOB" (`kept_possible_bank_commentary`, 199).
The last group is kept because a real minority are about the bank ("Review:
OCBC Rewards Card", "Citibank consumer banking acquisition to be complete by
Nov: UOB"). Annotators may want to look at them.

`python run_news_pull.py --audit` re-checks stored articles against the
current rules and flags (never deletes) those that now fail.

**Cleanup on 2026-09-24.** An audit after the pull found 75 stored articles
failing the rules. 63 were Google headlines of bank analysts' calls on other
companies ("DBS raises Singtel target price"). They slipped through a bug,
since fixed, that ran the rules on the headline twice. The other 12 were the
old NewsAPI rows above. All 75 were deleted, with their 26 sentences, 38
aspect assignments and 38 aspect-sentiment rows. So was one unlabelled
labelling candidate derived from them (a Sensex sentence tagged DBS;
`data/labeled/candidates.csv` went from 998 to 997 rows). They remain listed
in `news_flagged.csv` as `removed_from_db_2026-09-24`. `sentiment_index` was
not recomputed and still includes those 38 scores until the next
`python -m aggregate.index`.

## Known gaps

- **Google volume is a sample, not a census, and it rises towards the
  present**: about 50 articles a month in 2023, 55 in 2024, 83 in 2025 and
  152 in 2026. Google ranks recent articles higher, so more of them survive
  the per-query cap. Do not read news volume over time as a trend in news
  coverage. Normalise per month before comparing periods.
- **Google items are headlines only.** The RSS description repeats the
  headline, so each Google article is one sentence. Stored URLs are
  `news.google.com` redirect links. Resolving them to the publisher URL needs
  a request per article to Google, so the publisher's homepage is kept in
  `raw.source_href` instead.
- **Yahoo has no history before about 12 months ago**, and none will appear
  retroactively. It only grows through the daily batch.
- **Self-published news**: 80 Google items come from DBS's own newsroom
  (`source_detail = 'DBS Bank Ltd'`) and about 36 are PR Newswire, Business
  Wire or GlobeNewswire releases. Like earnings material, these are the
  bank describing itself. Filter on `source_detail` if that matters.
- **Bank commentary still gets through**: headlines where the bank's
  economists or strategists comment on markets without a rating word
  ("STI eyes 5,040 peak: DBS"). In a hand-read random sample of 50 stored
  headlines, 8 were of this kind. Most are flagged
  `kept_possible_bank_commentary`.
- **Subsidiaries with their own brand are not aliased**: Bank of Singapore
  and Great Eastern (OCBC), UOB Asset Management headlines that don't say
  "UOB". They are in `news_flagged.csv` as `no_bank_mention`.
- **Near-duplicates more than 3 days apart are kept**: 11 identical
  headlines appear twice or three times, mostly recurring card promotions and
  UOB's daily FX notes, which reuse titles on different days.
- **Sentence-level attribution in `preprocess/`** uses `ingest/base.py`,
  which does not mask broker names. A single-sentence headline like "UOB Kay
  Hian upgrades DBS" reads there as naming two banks, and the sentence is
  dropped. That is lost data, not mislabelled data. The masking wasn't
  applied to preprocessing because 662 existing sentences, mostly Reddit,
  mention DBS Vickers / UOB Kay Hian / OCBC Securities, and complaints about
  a DBS Vickers account are plausibly about DBS.
- **CNA overlap**: 98 Google headlines are from CNA. When the CNA feed is
  loaded into `documents`, run it through `news_filter.filter_and_dedup` so
  those headlines are recognised as duplicates.

## Commands

```bash
python run_news_pull.py                     # all sources; Google backfill from 2023-01-01 (~20 min)
python run_news_pull.py --source google --since 2022-01-01 --until 2023-01-01
python run_news_pull.py --report            # the table below
python run_news_pull.py --audit             # flag stored articles the current rules reject
python run_daily_batch.py                   # daily: Yahoo, last 45 days of Google, NewsAPI, AV, Reddit
```

None of these create `sentences`. Run `python -m preprocess.pipeline` for
that, before aspect discovery.

## Counts: source × bank × month

Before (2026-09-24, prior to the pull):

| month | newsapi DBS | newsapi OCBC | newsapi UOB | newsapi MULTI | total |
|---|---|---|---|---|---|
| 2026-08 | 12 | 2 | 4 | 1 | 19 |
| 2026-09 | 0 | 1 | 0 | 0 | 1 |
| **total** | 12 | 3 | 4 | 1 | 20 |

After (post-cleanup):

| month | newsapi DBS | newsapi OCBC | newsapi UOB | newsapi MULTI | yahoo_news DBS | yahoo_news OCBC | yahoo_news UOB | yahoo_news MULTI | google_news DBS | google_news OCBC | google_news UOB | google_news MULTI | total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023-01 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 8 | 7 | 0 | 28 |
| 2023-02 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 20 | 15 | 4 | 0 | 39 |
| 2023-03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 23 | 9 | 10 | 4 | 46 |
| 2023-04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 18 | 7 | 15 | 1 | 41 |
| 2023-05 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 16 | 18 | 1 | 63 |
| 2023-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 19 | 8 | 12 | 7 | 46 |
| 2023-07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 20 | 17 | 21 | 3 | 61 |
| 2023-08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 35 | 28 | 6 | 1 | 70 |
| 2023-09 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 15 | 11 | 11 | 3 | 40 |
| 2023-10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 25 | 18 | 20 | 3 | 66 |
| 2023-11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 27 | 19 | 12 | 6 | 64 |
| 2023-12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 12 | 15 | 4 | 1 | 32 |
| 2024-01 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 17 | 10 | 9 | 2 | 38 |
| 2024-02 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 19 | 15 | 25 | 0 | 59 |
| 2024-03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 11 | 7 | 15 | 6 | 39 |
| 2024-04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 15 | 15 | 16 | 5 | 51 |
| 2024-05 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 32 | 15 | 11 | 5 | 63 |
| 2024-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 18 | 21 | 8 | 2 | 49 |
| 2024-07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 23 | 17 | 17 | 3 | 60 |
| 2024-08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 31 | 10 | 17 | 3 | 61 |
| 2024-09 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 26 | 24 | 15 | 0 | 65 |
| 2024-10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 14 | 21 | 9 | 0 | 44 |
| 2024-11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 30 | 23 | 25 | 1 | 79 |
| 2024-12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 20 | 17 | 16 | 4 | 57 |
| 2025-01 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 21 | 8 | 7 | 4 | 40 |
| 2025-02 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 32 | 9 | 20 | 7 | 68 |
| 2025-03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 33 | 16 | 23 | 4 | 76 |
| 2025-04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 24 | 17 | 23 | 6 | 70 |
| 2025-05 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 29 | 18 | 18 | 4 | 69 |
| 2025-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 26 | 11 | 9 | 74 |
| 2025-07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 29 | 49 | 22 | 5 | 105 |
| 2025-08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 36 | 29 | 17 | 6 | 88 |
| 2025-09 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 39 | 12 | 18 | 3 | 73 |
| 2025-10 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 34 | 19 | 25 | 12 | 94 |
| 2025-11 | 0 | 0 | 0 | 0 | 4 | 6 | 3 | 0 | 54 | 40 | 40 | 18 | 165 |
| 2025-12 | 0 | 0 | 0 | 0 | 1 | 4 | 1 | 0 | 31 | 15 | 14 | 6 | 72 |
| 2026-01 | 0 | 0 | 0 | 0 | 2 | 2 | 3 | 0 | 30 | 30 | 31 | 13 | 111 |
| 2026-02 | 0 | 0 | 0 | 0 | 4 | 2 | 3 | 1 | 69 | 50 | 33 | 10 | 172 |
| 2026-03 | 0 | 0 | 0 | 0 | 1 | 4 | 11 | 0 | 48 | 32 | 34 | 13 | 143 |
| 2026-04 | 0 | 0 | 0 | 0 | 0 | 5 | 1 | 0 | 64 | 56 | 16 | 9 | 151 |
| 2026-05 | 0 | 0 | 0 | 0 | 1 | 4 | 2 | 0 | 48 | 56 | 40 | 13 | 164 |
| 2026-06 | 0 | 0 | 0 | 0 | 2 | 2 | 5 | 0 | 78 | 25 | 41 | 8 | 161 |
| 2026-07 | 0 | 0 | 0 | 0 | 2 | 9 | 6 | 0 | 68 | 43 | 43 | 9 | 180 |
| 2026-08 | 4 | 2 | 1 | 1 | 4 | 1 | 4 | 0 | 52 | 27 | 34 | 17 | 147 |
| 2026-09 | 4 | 0 | 1 | 0 | 2 | 3 | 4 | 0 | 57 | 24 | 30 | 10 | 135 |
| **total** | 8 | 2 | 2 | 1 | 24 | 43 | 45 | 2 | 1415 | 967 | 863 | 247 | 3619 |
