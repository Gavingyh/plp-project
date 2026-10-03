# Validation: API integrity (api/), 2026-10-02
Verdict: fix first

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | DISPROVEN | Checked on two endpoints only: `/sentiment` matches the DB row (DBS all_time 0.122, n 24,431) and rejects 8 bad banks and 7 bad windows; `/sentiment/series` rejects 6 bad buckets. `/coverage` and `/evidence` accept any bank. Other endpoints not checked |
| Grounded chatbot | UNTESTED | out of scope |

## Confirmed issues
- **Trend compares shrunk scores** [med] chatbot/tools.py:120: trend direction compares shrunk 7d and 30d scores, so thin 7d windows read as "declining"; UOB ALL is "declining" (-0.045) though its unshrunk change is +0.12; 7 of 23 cells flip (test: tests/test_validate_api.py::test_trend_not_declining_when_raw_7d_is_higher)
- **Readers mix model versions** [med] chatbot/tools.py:74, aggregate/index.py:175, dashboard/app.py:89: readers don't filter `model_version`; with two versions `/sentiment/index` returns duplicate cells and `/sentiment` serves the old one. No effect today; it breaks at the re-score (test: test_index_endpoint_has_no_duplicate_cells)
- **Bank unchecked on two endpoints** [med] api/main.py:130,135: `/coverage` and `/evidence` take any bank; `bank=dbs` reports a 24k-sentence bank as "no data" (test: test_coverage_bad_bank_returns_422)
- **Spec promises an impossible 400** [low] the functional spec's input-validation requirement promises 400 for an unknown bucket; the API can only return 422 (dead branch, api/main.py:217)
- **Thin index cells not flagged** [low] api/main.py:93: `/sentiment/index` returns cells with n < 5 (12 of 35 in the 7d grid) without `insufficient_data`, against the spec's no-data requirement
- **Series errors read as no data** [low] chatbot/tools.py:131: `except Exception` turns any series error into "no data"

## Open questions
- Should the 7d trend need the volume floor before it gets a direction at all?
- Week buckets are not ISO weeks (`2025-W00`); CNA's +08:00 timestamps mix local and UTC bucket edges
- Validate `source` and `aspect` too? The spec's input-validation requirement lists only bank, window and bucket

## Top 3 fixes
1. Readers mix model versions: every reader picks one model version: done when the model-version tests pass and a two-version copy of the DB gives one row per (bank, aspect, source) on `/sentiment/index`. Before the 12 Oct re-score; the dashboard owner fixes `dashboard/app.py:89`.
2. Bank unchecked on two endpoints: add the bank pattern to `/coverage` and `/evidence`: done when the two bad-bank tests pass and `docs/api/openapi.json` is regenerated.
3. Trend compares shrunk scores: direction from unshrunk scores, or `insufficient_data` when 7d n < 5: done when the trend test passes and every cell's direction has the sign of its unshrunk change.
