# Building the dashboard on the API

For whoever builds a frontend on the API. The Streamlit dashboard in
`dashboard/` (a teammate's) reads the database directly; everything it
shows is also available through a read-only REST API (DESIGN decision 23). This page is how to run it, which endpoint feeds which
view, what the responses look like, and what the screen must say about the
numbers.

## Run the API

You need the database (README, "Getting the database") and the Python
environment (README, "Quick start"). Then:

```bash
scripts/start.sh            # Ollama for /chat, the API on port 8000 and the dashboard on 8501
PLP_API_PORT=8100 scripts/start.sh api     # another port, API only (PLP_DASHBOARD_PORT for the dashboard)
scripts/status.sh
scripts/stop.sh
```

- Interactive docs: `http://localhost:8000/docs`
- Machine-readable spec: [`docs/api/openapi.json`](api/openapi.json), for
  generating a client. A test fails if it falls behind the code; regenerate
  it with
  `.venv-plp/bin/python3 -c "import json; from api.main import app; open('docs/api/openapi.json','w').write(json.dumps(app.openapi(), indent=2, sort_keys=True) + '\n')"`
- Every endpoint is `GET` and read-only, except `POST /chat`, which only
  calls a model. CORS is open (`*`), so a browser app on any port can call
  it. There is no authentication: run it locally, not on the internet.

## Which endpoint feeds which view

| dashboard view | endpoint | notes |
|---|---|---|
| headline score per bank | `GET /sentiment?bank=DBS` | `window` = `all_time` (default), `30d`, `7d`; `insufficient_data` is true when too few sentences |
| bank × aspect grid | `GET /sentiment/index?window=all_time` | one call, 36 rows (3 banks × 11 aspects + `ALL`); `aspect = "ALL"` is the bank's headline; each row's `insufficient_data` is true below 5 sentences |
| what the blend is made of | `GET /sentiment/index?window=all_time&source=*` and `GET /sources` | every per-source row (249), and sentence counts by bank and source |
| comparing the banks | `GET /sentiment/compare?aspect=dividend_policy` | all three banks for one aspect, or overall without `aspect` |
| sentiment over time | `GET /sentiment/series?bank=UOB&bucket=month` | `bucket` = `week`, `month`, `quarter`; optional `aspect`, `source`, `min_n` (default 5) |
| up or down lately | `GET /sentiment/trend?bank=DBS` | the last 7 days against the last 30, compared before the small-sample shrinkage: `delta_7d_vs_30d` is `recent_7d_unshrunk_score` minus `baseline_30d_unshrunk_score`, both returned; no direction when either window has fewer than 5 sentences |
| analyst consensus | `GET /analyst-consensus/latest` (all banks) or `GET /analyst-consensus?bank=DBS` | Yahoo Finance aggregates: rating, number of analysts, mean target, price |
| evidence drill-down | `GET /evidence/latest?bank=OCBC&aspect=dividend_policy&limit=30` | newest sentences with their stored label |
| evidence search | `GET /evidence?query=dividend+cut&bank=DBS&k=5` | semantic search, as the chatbot uses; `k` from 1 to 50 |
| data behind a cell | `GET /coverage?bank=DBS&aspect=dividend_policy` | count, date range and sources |
| labels for the UI | `GET /banks`, `GET /aspects` | aspect keys with readable names ("Dividend Policy") |
| chat | `POST /chat` | below |
| starter questions | `GET /suggestions?limit=6` | only questions the data can answer |
| liveness | `GET /health` | `{"status": "ok"}` |

## What the responses look like

Real responses from the 30 Sep database, shortened.

`GET /sentiment?bank=DBS`

```json
{"bank": "DBS", "aspect": "ALL", "window": "all_time", "score": 0.122, "n": 24431,
 "positive_n": 5468, "neutral_n": 16441, "negative_n": 2522, "confidence_mean": 0.856,
 "model_version": "finbert-base-zeroshot-v1", "computed_at": "2026-09-30T07:34:45.193278+00:00",
 "insufficient_data": false}
```

`score` runs from −1 (all negative) to +1 (all positive), weighted by the
model's confidence and by source, and shrunk towards 0 when there are few
sentences.

`GET /sentiment/index?window=all_time` (one row of 36)

```json
{"bank": "OCBC", "aspect": "asset_quality", "source": "ALL", "score": 0.2764, "n": 5232,
 "pos_n": 1476, "neu_n": 3628, "neg_n": 128, "confidence_mean": 0.864,
 "model_version": "finbert-base-zeroshot-v1", "computed_at": "2026-09-30T07:34:45.193278+00:00"}
```

`GET /sentiment/series?bank=UOB&bucket=quarter` (two points)

```json
{"bank": "UOB", "aspect": "ALL", "bucket": "quarter", "source": "ALL",
 "series": [{"period": "2020-Q2", "score": 0.1404, "n": 63, "pos_n": 22, "neu_n": 30, "neg_n": 11,
             "confidence_mean": 0.837, "sufficient": true},
            {"period": "2020-Q3", "score": 0.0027, "n": 108, "pos_n": 34, "neu_n": 42, "neg_n": 32,
             "confidence_mean": 0.8902, "sufficient": true}]}
```

Points with `"sufficient": false` have fewer than `min_n` sentences: draw a
gap, not a line through them, and not a zero.

`GET /analyst-consensus/latest` (fields shortened)

```json
{"rows": [{"bank": "DBS", "as_of_date": "2026-09-25", "recommendation_key": "buy", "n_analysts": 17,
           "target_mean": 78.14118, "current_price": 77.41},
          {"bank": "OCBC", "as_of_date": "2026-09-25", "recommendation_key": "buy", "n_analysts": 17,
           "target_mean": 31.52941, "current_price": 31.82},
          {"bank": "UOB", "as_of_date": "2026-09-24", "recommendation_key": "hold", "n_analysts": 16,
           "target_mean": 43.2975, "current_price": 42.5}]}
```

Banks are fetched separately, so their dates can differ; show each bank's
`as_of_date`.

`GET /evidence/latest?bank=OCBC&aspect=dividend_policy&limit=2` (one row)

```json
{"sentence_id": "3df8213fa19f99b46b433655",
 "text": "OCBC Sees Malaysia’s Fiscal Deficit At 3.6 Pct Of GDP In 2026, 2027",
 "source": "google_news", "url": "https://news.google.com/rss/articles/…",
 "published_at": "2026-09-25T10:08:15+00:00", "aspect": "dividend_policy",
 "label": "neutral", "confidence": 0.6287}
```

That row is filed under dividend policy although it isn't about dividends:
see "per-aspect scores" below.

## Chat

`POST /chat` is stateless: send the conversation so far with each message.

```json
{"message": "And OCBC?",
 "history": [{"role": "user", "content": "What is the overall sentiment on DBS?"},
             {"role": "assistant", "content": "DBS's overall sentiment is +0.12 …"}],
 "backend": null}
```

`backend` is `ollama`, `gemini`, `claude`, `openai`, or `null` to use the
server's default (`CHATBOT_BACKEND` in `.env`); anything else, or a message
`role` other than `user` or `assistant`, gets HTTP 422. If the backend fails
(Ollama not running, a missing or rejected key) the reply is HTTP 503 with
the reason in `detail`. The Gemini backend never receives Reddit evidence
text. The response:

```json
{"question": "And OCBC?", "answer": "…", "guard": null,
 "citation_unverified": false, "unverified_numbers": []}
```

The UI must show the flags, not just the answer:

- `guard` is `"advice"` or `"scope"` when the bot declined (investment
  advice, or off-topic) without asking the model;
- `citation_unverified: true` means the answer cites evidence the tools
  never returned: mark the answer as not to be trusted;
- `unverified_numbers` lists figures in the answer that match nothing the
  tools returned.

A local model takes seconds to tens of seconds per answer; show a spinner.
To try the bot without any UI: `.venv-plp/bin/python3 -m chatbot.chat`.

## What the screen must say

From [STATUS.md](STATUS.md), which is the authority; keep these visible
near the numbers they qualify.

- **Not financial advice.** Sentiment is an indicator, not a
  recommendation.
- **Blended scores follow the source mix.** Earnings text, written by the
  banks, scores far more positive than Reddit; DBS has about six times the
  earnings text of the others. Show the per-source rows next to any
  cross-bank comparison.
- **Per-aspect scores aren't reliable yet.** Aspects are matched by
  embedding similarity, which gives a sentence 6.4 of the ten aspects on
  average and picks the aspect a person would choose first only 41% of the
  time. An LLM classifier that picks it 73% of the time is built but not yet
  applied; when it is, the same endpoints return the new rows.
- **Scores come from base FinBERT, zero-shot.** `model_version` says which
  model produced a row. Every endpoint returns only the current model's rows,
  so when the team switches to the fine-tuned model the old rows stay in the
  database for comparison but stop appearing. If the configured model has no
  rows yet, `/sentiment` says so in its `reason` (and the server logs a
  warning) rather than reporting ordinary missing data.
- **`bank` must be exactly `DBS`, `OCBC` or `UOB`** on every endpoint that
  takes it; anything else (including `dbs`) gets HTTP 422.
- **`aspect` must be a known aspect** (`GET /aspects` lists them; a readable
  name such as `dividend policy` is accepted, and `ALL` or no value means
  every aspect); an unknown one gets HTTP 422 rather than an empty result.
- **News volume rises towards the present** because of how Google News
  ranks results: compare periods by score, not by count.
- **Analyst figures are Yahoo consensus aggregates**, not analyst reports.

## What can change

Field names and endpoints are stable. Values change when the team re-runs
the pipeline (new aspects from the LLM classifier, scores from the
fine-tuned model, NER re-attribution): `model_version` and `computed_at`
identify a run, and the database snapshot in the README says which run is
current.
