# Validation: API integrity, after the fixes of 3 Oct, 2026-10-03
Verdict: fix first

| claim | result | evidence |
|---|---|---|
| Fine-tuning lead | UNTESTED | out of scope |
| API integrity | PROVEN | `tests/test_validate_api_integrity.py`: every cell of `/sentiment`, `/sentiment/compare` and `/sentiment/index` (each source) equals its stored row (108 cells; 249 rows for every source at all_time); the trend's 7d and 30d blocks and the series totals match the stored rows; 13 bad banks, 9 bad windows and 8 bad buckets get 422 on every endpoint that takes them (routes read from the app) |
| Grounded chatbot | UNTESTED | out of scope |

## Confirmed issues
- **Trend contradicts itself** [med] chatbot/tools.py:137: the direction and delta come from unshrunk scores, but only the shrunk 7d and 30d scores are returned, so UOB reads "improving" (+0.123) beside a 7d score (0.244) below its 30d score (0.289); the chatbot could misquote it (test: test_r1_trend_delta_reproducible_from_returned_fields)
- **Wrong model version looks like no data** [low] config/model_version.py:14: a version with no rows makes `/sentiment` say the pipeline hasn't run and `/suggestions` return nothing, with no warning (test: test_r4_wrong_model_version_is_distinguishable_from_no_data)
- **Unbounded `k`** [low] api/main.py:145: `/evidence?k=-1` returns every candidate but the last (`scored[:k]`, chatbot/retrieval.py:171)

## Open questions
- Is a 7-day window of 5 to 10 sentences enough for a direction? One sentence moves its unshrunk score by about 0.14 against a ±0.02 threshold; a higher floor for the trend, or a test against the spread, would settle it.
- Should `source` and `aspect` be checked too? A typo returns an empty answer that looks like no data.

## Top 3 fixes
1. Return the unshrunk 7d and 30d scores with the trend: done when the delta can be recomputed from the response and the trend test passes without its xfail marker.
2. Say when the configured model version has no rows, and log it: done when the wrong-version test passes without its marker.
3. Bound `k` to 1–50 on `/evidence`: done when `k=-1` and `k=0` get 422.
