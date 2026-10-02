# Validation: S2 API integrity (api/), 2026-10-02
Verdict: fix first

| claim | result | evidence |
|---|---|---|
| S1 Fine-tuning lead | UNTESTED | out of scope |
| S2 API integrity | DISPROVEN | Checked on two endpoints only: `/sentiment` matches the DB row (DBS all_time 0.122, n 24,431) and rejects 8 bad banks and 7 bad windows; `/sentiment/series` rejects 6 bad buckets. `/coverage` and `/evidence` accept any bank (R3). Other endpoints not checked |
| S3 Grounded chatbot | UNTESTED | out of scope |

## Confirmed issues
- R1 [med] chatbot/tools.py:120: trend direction compares shrunk 7d and 30d scores, so thin 7d windows read as "declining"; UOB ALL is "declining" (-0.045) though its unshrunk change is +0.12; 7 of 23 cells flip (test: tests/test_validate_api.py::test_r1_trend_not_declining_when_raw_7d_is_higher)
- R2 [med] chatbot/tools.py:74, aggregate/index.py:175, dashboard/app.py:89: readers don't filter `model_version`; with two versions `/sentiment/index` returns duplicate cells and `/sentiment` serves the old one. No effect today; it breaks at the re-score (test: test_r2_index_endpoint_has_no_duplicate_cells)
- R3 [med] api/main.py:130,135: `/coverage` and `/evidence` take any bank; `bank=dbs` reports a 24k-sentence bank as "no data" (test: test_r3_coverage_bad_bank_returns_422)
- R4 [low] functional-spec A2 promises 400 for an unknown bucket; the API can only return 422 (dead branch, api/main.py:217)
- R6 [low] api/main.py:93: `/sentiment/index` returns cells with n < 5 (12 of 35 in the 7d grid) without `insufficient_data`, against A4
- R10 [low] chatbot/tools.py:131: `except Exception` turns any series error into "no data"

## Open questions
- Should the 7d trend need the volume floor before it gets a direction at all (R1)?
- Week buckets are not ISO weeks (`2025-W00`); CNA's +08:00 timestamps mix local and UTC bucket edges (R7, R8)
- Validate `source` and `aspect` too? A2 lists only bank, window and bucket (R11)

## Top 3 fixes
1. R2: every reader picks one model version: done when the two `test_r2_*` tests pass and a two-version copy of the DB gives one row per (bank, aspect, source) on `/sentiment/index`. Before the 12 Oct re-score; the dashboard owner fixes `dashboard/app.py:89`.
2. R3: add the bank pattern to `/coverage` and `/evidence`: done when the `test_r3_*` tests pass and `docs/api/openapi.json` is regenerated.
3. R1: direction from unshrunk scores, or `insufficient_data` when 7d n < 5: done when `test_r1_*` pass and every cell's direction has the sign of its unshrunk change.
