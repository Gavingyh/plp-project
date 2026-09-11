# Data Viability Report

Findings from running the actual pipeline against live data (2026-09-06),
answering the unknowns flagged in the MVP plan before building further on them.

## Earnings ingestion + the cross-bank comparability problem (2026-09-07)

Earnings PDFs are now ingested automatically from DBS's and OCBC's own IR
sites (`ingest/earnings_fetch.py`) — 116 PDFs, 115 documents, 10,658
sentences. This closed the vocabulary gap that had crippled the aspect
taxonomy: "net interest margin" appears in 298 earnings sentences vs **0**
in the entire Reddit corpus; "asset quality" 128 vs 0; "non-performing"
159 vs 0.

It also introduced a serious comparability problem, caught immediately and
only partly fixable in code.

**Earnings material is measurably far more positive than any other source** —
it is management describing its own results:

| source | positive | neutral | negative |
|---|---|---|---|
| Reddit (arctic_shift) | 2.3% | 94.8% | 3.0% |
| earnings | **24.7%** | 67.9% | 7.4% |

**And its coverage is wildly unequal**, because UOB's IR site is WAF-blocked
while DBS's and OCBC's are open: DBS 15,386 earnings-derived aspect rows,
OCBC 2,968, **UOB 4**.

Two fixes applied:
1. Earnings source weight dropped 3.0 -> 1.0 in `aggregate/index.py`. The
   3.0 was set when earnings was assumed to be a handful of high-signal
   documents; triple-weighting the second-largest and most positively-skewed
   source amplified the skew instead of damping it.
2. `sentiment_index` gained a `source` dimension, so every blended row now
   sits alongside its per-source components, surfaced in the dashboard and
   via `/sentiment/index?source=*` and `/sources`. The blend stays (the
   proposal specifies blending all streams) but is no longer opaque.

**The decisive finding, once split by source:** Reddit — the only source with
comparable coverage across all three banks — shows **no meaningful cross-bank
difference at all**:

| bank | Reddit-only | earnings-only | blended headline |
|---|---|---|---|
| DBS | -0.002 (n=29,701) | +0.168 (n=15,386) | +0.056 |
| OCBC | -0.011 (n=8,967) | +0.206 (n=2,968) | +0.044 |
| UOB | -0.011 (n=19,986) | +0.044 (n=4) | -0.011 |

The apparent "DBS and OCBC lead UOB" gap in the blended headline is an
artifact of earnings coverage, not a sentiment finding. Retail sentiment is
essentially identical across all three.

**RESOLVED (Sep 2026):** the weight fix reduced the distortion (DBS's blended
score fell from +0.101 to +0.056) but could not remove it, because the root
cause was coverage asymmetry rather than weighting. UOB's earnings PDFs have
since been fetched from the Wayback Machine — UOB's IR site is WAF-blocked,
the archive is not — giving UOB 1,600 earnings sentences against 4 before.

The effect was immediate and belongs in the report: UOB's blended all-time score
moved from **-0.011 to +0.020** purely from closing the coverage gap, with no
change to the scoring method. Earnings-only scores are now DBS +0.168,
OCBC +0.206, UOB +0.229.

The blended comparison is usable now. The residual caveat is volume, not
absence: DBS carries ~6x the earnings sentences of either other bank because
it publishes long analyst-call transcripts, so blended figures should still
be read next to the per-source breakdown.

## Full backfill complete (2026-09-07)

`scripts/overnight_backfill.py` finished a full Reddit backfill via Arctic
Shift, 2020-01-01 through 2026-09-07 (82 monthly chunks, all succeeded on
the corrected run — see the script's own commit history for a real incident
where the first attempt silently failed all 79 real chunks under the wrong
Python interpreter and produced zero data). Final corpus:

| | documents | sentences |
|---|---|---|
| DBS | — | 11,814 |
| UOB | — | 9,001 |
| OCBC | — | 3,815 |
| **total** | **21,746** | **24,630** |

OCBC is still the thinnest bank by a wide margin (~3.1x behind DBS by
sentence count now, similar ratio to the original 12-month sample) but its
absolute volume (3,815 sentences) is now easily enough to support the
labelling per-class minimums even after a three-way split. The full
downstream pipeline (preprocess -> assign -> score -> aggregate) has been
re-run against this complete corpus; `sentiment_index` reflects it.

## Aspect discovery + similarity-floor calibration (added later same day)

> **Superseded 2026-09-11.** Both findings below were measured on 2,888
> sentences and have been re-run on the full 36,884-sentence corpus. The
> headline conclusion has changed: analyst-style aspects *do* now emerge once
> earnings text is present. See
> [evidence/aspect-discovery-2026-09-11.md](evidence/aspect-discovery-2026-09-11.md)
> and [evidence/taxonomy-comparison-2026-09-11.md](evidence/taxonomy-comparison-2026-09-11.md).
> The 0.65 floor's measured effect has also moved (1.80/4 and 37.3% `other`,
> not 2.3/4 and ~31%). Kept as written because the sequence is part of the
> methodology story.

`python -m aspects.discover` (2,888 sentences) found 9 real clusters (52%
noise), but they split along a coarser axis than the proposal's 4 aspects —
"consumer banking service" vs. "investment/stock discussion" — rather than
subdividing into dividend/asset-quality/NIM/guidance. Full detail and the
decision this raises are in `config/aspects.yaml`'s header comment.

Separately, and more decisively: `aspects/compare_taxonomies.py` found the
original `similarity_floor: 0.35` in `config/aspects.yaml` wasn't
discriminating **for any taxonomy**, not just the proposal's one. Even a
2-aspect coarse candidate matched *both* aspects on ~100% of sentences at
that floor (avg 2.00/2 matched). A live sweep (0.35 -> 2.00 avg matched,
0.6% other; 0.50 -> 1.96, 0.6%; 0.60 -> 1.89, 2.8%; 0.70 -> 1.63, 9.2%;
0.75 -> 1.29, 18.9%) showed the floor needed to move much higher just to get
any real separation. Recalibrated to 0.65 (documented in `config/aspects.yaml`
as a starting point, not final — re-sweep when the corpus or taxonomy
changes materially). Effect on the real proposal-aligned taxonomy: avg
aspects-matched-per-sentence dropped from 3.97/4 to roughly 2.3/4, and
`other` went from ~0% to ~31% — the per-aspect sample sizes in
`sentiment_index` now actually differ meaningfully bank-to-bank instead of
being near-identical across all 4 aspects.

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
  specifically, and doing it before the labelling export would help if DBS ever
  looks thin relative to its actual coverage.
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

**Attempted, partially blocked (2026-09-06):** tried fetching full article
text for a JPMorgan-target-raise headline and a DBS-guidance headline to
check whether the full body (vs. NewsAPI's title+description snippet)
contains broker+rating language the proxy would catch. Both `straitstimes.com`
and `channelnewsasia.com` — the two outlets carrying the actual analyst-call
coverage in this pull — refused simple fetches outright, the same bot-
protection pattern hit earlier against `sgx.com` and `sginvestors.io`. A
third article (retailbankerinternational.com) fetched fine but was a
non-analyst HR/AI story, not a useful test case. **Still unresolved**: is
0/26 a text-length artifact or a real absence? Whoever picks this up next
should either get manual access to one full Straits Times/CNA article
behind their own login, or accept the proxy may need loosening and move on.

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

## Earnings PDFs — resolved (2026-09-11)

This section recorded earnings ingestion as a manual step needing a human to
download PDFs. It is fully automated now and has been since 2026-09-07;
kept here because the sequence matters to the story.

`ingest/earnings_fetch.py` pulls DBS's and OCBC's PDFs directly from their IR
sites, and `ingest/uob_wayback_fetch.py` pulls UOB's from the Wayback Machine
because UOB's own site is WAF-blocked. 178 documents and 12,254 sentences are
now in the corpus. See [RUNBOOK.md](RUNBOOK.md) for the commands.

One caveat found later, on 2026-09-11: `extract_prose` had been calling
`text.split("")`, an empty separator that raises `ValueError` on every page of
every PDF. `pull()` catches per-file exceptions and continues, so the earnings
source silently produced zero new documents while still exiting successfully.
The corpus already held earnings sentences from an earlier working run, so
nothing downstream looked wrong. Fixed, with a regression test.

## Volume gate check (≥300 Reddit items per bank per 12 months) — PASSED

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
Revisit this before the labelling export: OCBC's 430 sentences need to
comfortably cover 200-300 examples *per sentiment class* once split three
ways across positive/neutral/negative — thin, not failing, but the first
place to add more source volume (extra subreddits, deeper history) if the
labeling pool runs short for OCBC specifically.

## What this means for the pipeline as currently configured

- **Three live sources**: NewsAPI, Arctic Shift (Reddit), earnings (fully
  automated since 2026-09-07, including UOB via the Wayback Machine). Alpha
  Vantage confirmed dead, dropped. Yahoo Finance analyst consensus added as a
  fourth, with its unofficial-API caveat disclosed.
- **Analyst consensus**: proxy built, needs a volume check before being
  trusted as "working."
- All findings above are backed by a live, reproducible run on 2026-09-06 —
  not assumption. Re-run `python run_daily_batch.py` to refresh.
