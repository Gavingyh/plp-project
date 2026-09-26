# News dataset

How the news part of `data/plp.db` was collected, what it covers, and where it
falls short. Written for the report's datasets section. Numbers are as of
2026-09-26, after both Google backfills, both cleanups and the CNA load
described below; the month tables at the end show each stage.
Re-run `python run_news_pull.py --report` for the current table.

## Sources

| source (`documents.source`) | endpoint | text stored | coverage | rows |
|---|---|---|---|---|
| `google_news` | Google News RSS search, en-SG edition, free, no key | headline only | 2023-01-01 to 2026-09-25, every month | 5,685 |
| `cna` | CNA article pages, found through the Wayback Machine's URL index, free, no key | full article text | 2023-01-04 to 2026-09-09, 44 of 45 months | 207 |
| `yahoo_news` | Yahoo Finance news via `yfinance` `Ticker.get_news`, free, no key | headline + Yahoo summary | 2025-09-29 to 2026-09-23 | 114 |
| `newsapi` | NewsAPI.org `/v2/everything`, free developer key | headline + description | 2026-08-06 to 2026-09-11 | 13 |
| `alphavantage` | Alpha Vantage `NEWS_SENTIMENT`, free key | title + summary | none | 0 |

Per bank, all news sources together (a `MULTI` row names more than one bank):

| bank | articles | first | last | months with news |
|---|---|---|---|---|
| DBS | 2,602 | 2023-01-02 | 2026-09-25 | 45 of 45 |
| OCBC | 1,505 | 2023-01-01 | 2026-09-25 | 45 of 45 |
| UOB | 1,546 | 2023-01-03 | 2026-09-24 | 45 of 45 |
| MULTI | 366 | 2023-01-06 | 2026-09-25 | 45 of 45 |

Counts as of 2026-09-26, after CNA was loaded; the Google News row count
includes the daily pulls made after the backfill.

Before this pull, news was 20 NewsAPI rows spanning 2026-08-06 to 2026-09-05.
12 of those 20 named none of the three banks (the old NewsAPI adapter fell
back to the bank it had searched for) and were removed in the cleanup.

How each source was queried:

- **Google News** has no API. The RSS search accepts `after:YYYY-MM-DD
  before:YYYY-MM-DD`, so history is reachable one calendar month at a time.
  Three queries per bank: the quoted name from the team brief (`"DBS Group"
  Singapore`, `"OCBC Bank" Singapore`, `"UOB bank" Singapore`), a looser
  unquoted one (`DBS bank Singapore`, `OCBC Singapore`, `UOB Singapore`),
  which returned 4-7x as many items in a March 2024 probe, and an `intitle:`
  query requiring the bank in the headline (chosen by the pilot below). A response is
  capped at 100 items, so a month that returns 90 or more is split in half
  and re-queried. Requests are 2 s apart with retry and backoff.
- **Yahoo** has no date parameter and no paging: it returns the most recent
  stream per ticker, 10 items by default. Asked for 200, it returned 35-71
  unique items per bank across all tabs, reaching back about 12 months. All six listings are
  queried (SGX `D05.SI`, `O39.SI`, `U11.SI` and the US OTC ADRs `DBSDY`,
  `OVCHY`, `UOVEY`) on the `news`, `all` and `press releases` tabs. The ADR
  streams were near-copies of the SGX ones (DBS: 1 extra article out of 35).
  Yahoo is in `run_daily_batch.py`, so its coverage grows from here on.
- **CNA** (`ingest/cna_archive.py`) is the only news source stored as full
  article text. CNA has no usable archive: its news sitemap lists only the
  latest 50 articles, its RSS feed only recent items, and robots.txt
  disallows `/search` and `/api/*`. The Wayback Machine's CDX index lists the
  CNA URLs it has captured, and a CNA URL carries the headline as a slug, so
  the index is queried for URLs in the business, Singapore, commentary, Asia
  and TODAY sections whose slug names a bank, PayLah or one of the three chief
  executives. That found 446 candidates. Each was fetched from CNA at
  robots.txt's 10-second crawl delay (from the archived copy when CNA no
  longer serves it): 308 live, 112 archived, 27 with no text anywhere. The
  publish date on the page decides what is kept, because the archive also
  holds older stories captured later: 218 fell in 2023-01-01 to 2026-09-25,
  and 207 passed the filter. A wider query taking any slug with "bank" in it
  returned about 2,900 business URLs, almost all about other banks, so it
  was not used.
- **NewsAPI**'s free tier only reaches back about a month.
- **Alpha Vantage** does not index SGX tickers; that was established earlier
  (docs/DESIGN.md) and it returned 0 rows again. Its vendor sentiment score
  is never stored. GDELT was not tried: Google and Yahoo already cleared the
  target of 300+ articles per bank over 6+ months.

### Choosing the Google queries

Before the second backfill, seven pull techniques were piloted on three
sample months (June 2023, October 2024, December 2025, about 330 requests).
Each was measured by how many articles it added that passed the filter and
were not already stored or duplicates. Counts below are new articles per
month, cumulative, so each technique is credited only for what the ones
above it missed.

| technique | requests / month | Jun 2023 | Oct 2024 | Dec 2025 | used? |
|---|---|---|---|---|---|
| re-run of the original two queries | 6 | 0 | 0 | 0 | yes (results were stable over hours) |
| `intitle:` bank in headline, banking context for DBS | 3 | +29 | +32 | +27 | **yes** |
| `intitle:` without context | 3 | +44 | +55 | +57 | no: about a third of "DBS" hits were Aston Martin DBS, Dragon Ball Super, American-football "DBs", deep brain stimulation |
| full-name variants ("United Overseas Bank") | 3 | +3 | 0 | +2 | no |
| weekly instead of monthly windows | 30 | +1 | 0 | +1 | no: monthly windows weren't hitting the cap |
| other editions (en-MY, en-GB, en-US) | 18 | 0 | +1 | 0 | no: same stories |
| per-outlet `site:` queries, 8 outlets | 24 | 0 | +1 | +3 | no: about 90% of results didn't name the bank |

The final query set is three per bank: the quoted name, the loose query and
the `intitle:` query (see `QUERIES` in `ingest/google_news.py`).

No article pages are fetched and nothing behind a paywall is read. Straits
Times and Business Times items are headlines only.

## Filtering and dedup rules

All four sources go through `ingest/news_filter.py` before insert.

1. **Must name a bank.** The headline (plus snippet, where there is one) must
   contain DBS, OCBC or UOB, a full name, the SGX or ADR ticker, or POSB
   (DBS's own retail brand). In the first backfill 38% of Google's raw
   results (2,451 of 6,471) failed this: general Singapore news that the
   loose queries also match. The `intitle:` backfill rarely did (77 of
   6,153).
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
   - a bank's market note: a currency, rates, commodity or macro headline
     that credits the bank at the end ("Australian Dollar: Gradual upside
     within capped range – UOB"). FX sites have syndicated these in bulk
     since 2026. Awards, launches and own results are exempt ("Singapore's
     best FX bank: DBS").

   "UOB Kay Hian upgrades DBS to buy" therefore counts as a DBS article, and
   "UOB Kay Hian names top picks" is rejected.
3. **Cross-source dedup.** An article is a duplicate if its normalised URL
   (scheme, `www.` and tracking parameters removed) matches a stored news
   article, or its normalised headline is at least 90% similar
   (`difflib` ratio) to one published within 3 days. The first copy stored
   wins; Yahoo runs first because it carries a summary. 405 duplicates were
   caught across and within sources.
4. **Bank attribution** comes from the text, not the query: a Google result
   for "DBS bank Singapore" that only names OCBC is stored as OCBC.

Nothing is dropped silently. `data/news_flagged.csv` lists every rejected
article once with its reason (`no_bank_mention` 2,479, `false_positive_only`
288, `duplicate` 405), every kept article that had a phrase masked (19), and
every kept headline that credits the bank as speaker at the end but isn't a
market note, such as "Platform workers are spending more than they earn: DBS
study" (`kept_possible_bank_commentary`, 258).
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

**Second cleanup, same day.** The `intitle:` backfill added 2,331 articles.
It also surfaced the banks' syndicated market notes, which led to the
market-note rule above. The 195 stored notes it caught (all Google, none
preprocessed yet) were deleted and are listed as `removed_from_db_2026-09-24`.

## Known gaps

- **Google volume is a sample, not a census, and it rises towards the
  present**: about 77 articles a month in 2023, 90 in 2024, 131 in 2025 and
  244 in 2026. Google ranks recent articles higher, so more of them survive
  the per-query cap. The `intitle:` queries widened the gap: they added
  12-52 articles a month in 2023-24 and 119-204 a month from May 2026. Do
  not read news volume over time as a trend in news coverage. Normalise
  per month before comparing periods.
- **Google items are headlines only.** The RSS description repeats the
  headline, so each Google article is one sentence. Stored URLs are
  `news.google.com` redirect links. Resolving them to the publisher URL needs
  a request per article to Google, so the publisher's homepage is kept in
  `raw.source_href` instead.
- **Yahoo has no history before about 12 months ago**, and none will appear
  retroactively. It only grows through the daily batch.
- **Self-published news**: 90 Google items come from DBS's own newsroom
  (`source_detail = 'DBS Bank Ltd'`) and 41 are PR Newswire, Business Wire
  or GlobeNewswire releases. Like earnings material, these are the
  bank describing itself. Filter on `source_detail` if that matters.
- **Bank commentary still gets through**: headlines where the bank's
  economists or strategists comment on markets without a rating word
  and without a market topic the rule recognises ("Frasers Property is an
  'attractive privatisation candidate': DBS"). In a hand-read random sample
  of 50 stored headlines after the first backfill, 8 were of this kind. The
  market-note rule has since removed the commonest form. The rest are mostly
  flagged `kept_possible_bank_commentary`.
- **Subsidiaries with their own brand are not aliased**: Bank of Singapore
  and Great Eastern (OCBC), UOB Asset Management headlines that don't say
  "UOB". They are in `news_flagged.csv` as `no_bank_mention`.
- **Near-duplicates more than 3 days apart are kept**: 29 identical
  headlines appear more than once, mostly recurring card promotions and
  UOB's daily FX notes, which reuse titles on different days.
- **Sentence-level attribution in `preprocess/`** uses `ingest/base.py`,
  which does not mask broker names. A single-sentence headline like "UOB Kay
  Hian upgrades DBS" reads there as naming two banks, and the sentence is
  dropped. That is lost data, not mislabelled data. The masking wasn't
  applied to preprocessing because 662 existing sentences, mostly Reddit,
  mention DBS Vickers / UOB Kay Hian / OCBC Securities, and complaints about
  a DBS Vickers account are plausibly about DBS.
- **CNA overlap with Google News**: Google News had already stored 117 of
  the 207 CNA stories as bare headlines. Under the first-copy-wins rule the
  CNA full text would have been dropped, so the filter now keeps a full-text
  article over a headline-only copy (flagged `kept_full_text_over_headline`),
  and preprocessing's sentence hash stops the headline being counted twice.
  Two CNA stories were still dropped, because NewsAPI had stored them first
  with a one-line description.
- **CNA coverage is what the archive happened to capture**, and only
  headlines whose URL names a bank are found. Months hold 0 to 13 CNA
  articles (none in September 2025), so CNA volume says nothing about news
  flow. Two discovery runs on the same day returned 461 and 446 candidates,
  because the archive's index answers vary under load.

## Commands

```bash
python run_news_pull.py                     # all sources; Google backfill from 2023-01-01 (~25 min)
python run_news_pull.py --source google --since 2022-01-01 --until 2023-01-01
python run_news_pull.py --report            # the table below
python run_news_pull.py --audit             # flag stored articles the current rules reject
python run_daily_batch.py                   # daily: Yahoo, last 45 days of Google, NewsAPI, AV, Reddit
```

None of these create `sentences`. Run `python -m preprocess.pipeline` for
that, before aspect discovery. It was run on 2026-09-24 after the cleanups
and produced 5,764 news sentences (DBS 2,563, OCBC 1,577, UOB 1,624). 347
news articles gave no sentence, mostly headlines naming two banks, which
the pipeline drops as ambiguous at sentence level.

## Counts: source × bank × month

Before (2026-09-24, prior to the pull):

| month | newsapi DBS | newsapi OCBC | newsapi UOB | newsapi MULTI | total |
|---|---|---|---|---|---|
| 2026-08 | 12 | 2 | 4 | 1 | 19 |
| 2026-09 | 0 | 1 | 0 | 0 | 1 |
| **total** | 12 | 3 | 4 | 1 | 20 |

After (both backfills and cleanups, 2026-09-24):

| month | newsapi DBS | newsapi OCBC | newsapi UOB | newsapi MULTI | yahoo_news DBS | yahoo_news OCBC | yahoo_news UOB | yahoo_news MULTI | google_news DBS | google_news OCBC | google_news UOB | google_news MULTI | total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023-01 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 20 | 14 | 11 | 0 | 45 |
| 2023-02 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 18 | 4 | 0 | 50 |
| 2023-03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 31 | 17 | 20 | 4 | 72 |
| 2023-04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 32 | 9 | 19 | 1 | 61 |
| 2023-05 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 26 | 32 | 2 | 97 |
| 2023-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 14 | 25 | 8 | 75 |
| 2023-07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 29 | 26 | 28 | 3 | 86 |
| 2023-08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 | 38 | 13 | 1 | 111 |
| 2023-09 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 16 | 17 | 5 | 66 |
| 2023-10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 41 | 26 | 24 | 3 | 94 |
| 2023-11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 38 | 32 | 23 | 9 | 102 |
| 2023-12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 17 | 13 | 1 | 59 |
| 2024-01 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 24 | 17 | 17 | 3 | 61 |
| 2024-02 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 39 | 19 | 44 | 1 | 103 |
| 2024-03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 22 | 9 | 31 | 7 | 69 |
| 2024-04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 22 | 19 | 30 | 5 | 76 |
| 2024-05 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 46 | 31 | 16 | 5 | 98 |
| 2024-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 29 | 25 | 13 | 2 | 69 |
| 2024-07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 44 | 27 | 26 | 3 | 100 |
| 2024-08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 72 | 13 | 26 | 3 | 114 |
| 2024-09 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 40 | 30 | 24 | 0 | 94 |
| 2024-10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 22 | 29 | 23 | 0 | 74 |
| 2024-11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 51 | 29 | 40 | 1 | 121 |
| 2024-12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 24 | 30 | 4 | 95 |
| 2025-01 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 35 | 13 | 14 | 4 | 66 |
| 2025-02 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 69 | 19 | 28 | 7 | 123 |
| 2025-03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 63 | 26 | 32 | 5 | 126 |
| 2025-04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 38 | 19 | 41 | 7 | 105 |
| 2025-05 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 47 | 23 | 32 | 4 | 106 |
| 2025-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 49 | 43 | 19 | 9 | 120 |
| 2025-07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 | 63 | 35 | 6 | 163 |
| 2025-08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 39 | 40 | 7 | 146 |
| 2025-09 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 59 | 18 | 28 | 3 | 109 |
| 2025-10 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 61 | 27 | 41 | 12 | 145 |
| 2025-11 | 0 | 0 | 0 | 0 | 4 | 6 | 3 | 0 | 114 | 53 | 62 | 19 | 261 |
| 2025-12 | 0 | 0 | 0 | 0 | 1 | 4 | 1 | 0 | 44 | 19 | 21 | 7 | 97 |
| 2026-01 | 0 | 0 | 0 | 0 | 2 | 2 | 3 | 0 | 51 | 42 | 40 | 13 | 153 |
| 2026-02 | 0 | 0 | 0 | 0 | 4 | 2 | 3 | 1 | 107 | 57 | 49 | 10 | 233 |
| 2026-03 | 0 | 0 | 0 | 0 | 1 | 4 | 11 | 0 | 87 | 39 | 59 | 14 | 215 |
| 2026-04 | 0 | 0 | 0 | 0 | 0 | 5 | 1 | 0 | 124 | 69 | 36 | 10 | 245 |
| 2026-05 | 0 | 0 | 0 | 0 | 1 | 4 | 2 | 0 | 98 | 85 | 70 | 14 | 274 |
| 2026-06 | 0 | 0 | 0 | 0 | 2 | 2 | 5 | 0 | 115 | 33 | 73 | 9 | 239 |
| 2026-07 | 0 | 0 | 0 | 0 | 2 | 9 | 6 | 0 | 128 | 101 | 96 | 14 | 356 |
| 2026-08 | 4 | 2 | 1 | 1 | 4 | 1 | 4 | 0 | 79 | 48 | 51 | 17 | 212 |
| 2026-09 | 4 | 0 | 1 | 0 | 2 | 3 | 4 | 0 | 117 | 54 | 58 | 26 | 269 |
| **total** | 8 | 2 | 2 | 1 | 24 | 43 | 45 | 2 | 2451 | 1415 | 1474 | 288 | 5755 |

With CNA loaded (2026-09-26; Google News also includes the daily pulls after the backfill):

| month | newsapi DBS | newsapi OCBC | newsapi UOB | newsapi MULTI | yahoo_news DBS | yahoo_news OCBC | yahoo_news UOB | yahoo_news MULTI | google_news DBS | google_news OCBC | google_news UOB | google_news MULTI | cna DBS | cna OCBC | cna UOB | cna MULTI | total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023-01 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 20 | 14 | 11 | 0 | 0 | 1 | 0 | 1 | 47 |
| 2023-02 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 18 | 4 | 0 | 4 | 0 | 0 | 2 | 56 |
| 2023-03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 31 | 17 | 20 | 4 | 6 | 0 | 0 | 3 | 81 |
| 2023-04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 32 | 9 | 19 | 1 | 0 | 0 | 0 | 2 | 63 |
| 2023-05 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 26 | 32 | 2 | 3 | 1 | 0 | 2 | 103 |
| 2023-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 14 | 25 | 8 | 0 | 0 | 0 | 2 | 77 |
| 2023-07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 29 | 26 | 28 | 3 | 2 | 0 | 1 | 2 | 91 |
| 2023-08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 | 38 | 13 | 1 | 2 | 3 | 0 | 2 | 118 |
| 2023-09 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 16 | 17 | 5 | 1 | 0 | 1 | 1 | 69 |
| 2023-10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 41 | 26 | 24 | 3 | 6 | 0 | 1 | 4 | 105 |
| 2023-11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 38 | 32 | 23 | 9 | 6 | 1 | 0 | 5 | 114 |
| 2023-12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 17 | 13 | 1 | 1 | 0 | 0 | 0 | 60 |
| 2024-01 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 24 | 17 | 17 | 3 | 2 | 0 | 0 | 6 | 69 |
| 2024-02 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 39 | 19 | 44 | 1 | 4 | 1 | 4 | 4 | 116 |
| 2024-03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 22 | 9 | 31 | 7 | 3 | 0 | 0 | 1 | 73 |
| 2024-04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 22 | 19 | 30 | 5 | 1 | 1 | 0 | 2 | 80 |
| 2024-05 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 46 | 31 | 16 | 5 | 2 | 2 | 0 | 2 | 104 |
| 2024-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 29 | 25 | 13 | 2 | 2 | 2 | 0 | 0 | 73 |
| 2024-07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 44 | 27 | 26 | 3 | 2 | 1 | 0 | 0 | 103 |
| 2024-08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 72 | 13 | 26 | 3 | 5 | 0 | 0 | 4 | 123 |
| 2024-09 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 40 | 30 | 24 | 0 | 3 | 5 | 0 | 1 | 103 |
| 2024-10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 22 | 29 | 23 | 0 | 0 | 0 | 0 | 1 | 75 |
| 2024-11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 51 | 29 | 40 | 1 | 4 | 1 | 1 | 4 | 131 |
| 2024-12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 37 | 24 | 30 | 4 | 0 | 0 | 0 | 2 | 97 |
| 2025-01 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 35 | 13 | 14 | 4 | 1 | 1 | 0 | 0 | 68 |
| 2025-02 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 69 | 19 | 28 | 7 | 1 | 1 | 0 | 0 | 125 |
| 2025-03 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 63 | 26 | 32 | 5 | 1 | 0 | 1 | 0 | 128 |
| 2025-04 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 38 | 19 | 41 | 7 | 1 | 0 | 0 | 2 | 108 |
| 2025-05 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 47 | 23 | 32 | 4 | 4 | 1 | 0 | 2 | 113 |
| 2025-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 49 | 43 | 19 | 9 | 1 | 2 | 0 | 0 | 123 |
| 2025-07 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 | 63 | 35 | 6 | 1 | 2 | 2 | 1 | 169 |
| 2025-08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 39 | 40 | 7 | 2 | 1 | 0 | 1 | 150 |
| 2025-09 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 59 | 18 | 28 | 3 | 0 | 0 | 0 | 0 | 109 |
| 2025-10 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 61 | 27 | 41 | 12 | 0 | 0 | 1 | 0 | 146 |
| 2025-11 | 0 | 0 | 0 | 0 | 4 | 6 | 3 | 0 | 114 | 53 | 62 | 19 | 3 | 1 | 1 | 1 | 267 |
| 2025-12 | 0 | 0 | 0 | 0 | 1 | 4 | 1 | 0 | 44 | 19 | 21 | 7 | 0 | 0 | 0 | 2 | 99 |
| 2026-01 | 0 | 0 | 0 | 0 | 2 | 2 | 3 | 0 | 51 | 42 | 40 | 13 | 1 | 0 | 0 | 0 | 154 |
| 2026-02 | 0 | 0 | 0 | 0 | 4 | 2 | 3 | 1 | 107 | 57 | 49 | 10 | 1 | 1 | 2 | 3 | 240 |
| 2026-03 | 0 | 0 | 0 | 0 | 1 | 4 | 11 | 0 | 87 | 39 | 59 | 14 | 3 | 0 | 1 | 1 | 220 |
| 2026-04 | 0 | 0 | 0 | 0 | 0 | 5 | 1 | 0 | 124 | 69 | 36 | 10 | 3 | 0 | 0 | 1 | 249 |
| 2026-05 | 0 | 0 | 0 | 0 | 1 | 4 | 2 | 0 | 98 | 85 | 70 | 14 | 1 | 1 | 0 | 2 | 278 |
| 2026-06 | 0 | 0 | 0 | 0 | 2 | 2 | 5 | 0 | 115 | 33 | 73 | 9 | 2 | 0 | 0 | 0 | 241 |
| 2026-07 | 0 | 0 | 0 | 0 | 2 | 9 | 6 | 0 | 128 | 101 | 96 | 14 | 2 | 0 | 0 | 1 | 359 |
| 2026-08 | 4 | 2 | 1 | 1 | 4 | 1 | 4 | 0 | 85 | 52 | 54 | 18 | 2 | 0 | 0 | 1 | 229 |
| 2026-09 | 4 | 0 | 1 | 0 | 2 | 3 | 4 | 0 | 140 | 65 | 64 | 29 | 1 | 0 | 0 | 0 | 313 |
| **total** | 8 | 2 | 2 | 1 | 24 | 43 | 45 | 2 | 2480 | 1430 | 1483 | 292 | 90 | 30 | 16 | 71 | 6019 |
