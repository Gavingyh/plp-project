# Building the dashboard on the API

For whoever builds a frontend on the API. The Streamlit dashboard's data
views now use this API through `dashboard/api_client.py` and `dashboard/data.py`.
The Ask page still calls the chatbot directly until the chat migration is
completed. This page is how to run the API, which endpoint feeds which
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

The Streamlit server connects to `http://127.0.0.1:8000` by default. Set
`PLP_API_PORT` for a different local port, or `PLP_API_URL` for the complete
address (for example, `http://api:8000` inside Docker Compose). This request
comes from the Streamlit server, not the browser. Data loaders cache successful
responses for five minutes. Start the API before opening the dashboard.

The sidebar distinguishes **Data as of** (the newest stored sentence) from
**Index computed** (when the selected model's aggregate was built). Empty
API results show no-data messages; failed requests show service errors.

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
| headline score per bank | `GET /sentiment?bank=DBS` | `window` = `all_time` (default), `30d`, `7d`; `insufficient_data` is true when too few sentences; `data_as_of` is the date the 7d and 30d windows end on |
| bank × aspect grid | `GET /sentiment/index?window=all_time` | one call, 36 rows (3 banks × 11 aspects + `ALL`); `aspect = "ALL"` is the bank's headline; each row's `insufficient_data` is true below 5 sentences |
| what the blend is made of | `GET /sentiment/index?window=all_time&source=*` and `GET /sources` | every per-source row (249), and sentence counts by bank and source |
| comparing the banks | `GET /sentiment/compare?aspect=dividend_policy` | all three banks for one aspect, or overall without `aspect` |
| sentiment over time | `GET /sentiment/series?bank=UOB&bucket=month` | `bucket` = `week`, `month`, `quarter`; optional `aspect`, `source`, `min_n` (default 5) |
| up or down lately | `GET /sentiment/trend?bank=DBS` | the 7 days against the 30 days to the newest stored data (`data_as_of`), compared before the small-sample shrinkage: `delta_7d_vs_30d` is `recent_7d_unshrunk_score` minus `baseline_30d_unshrunk_score`, both returned; no direction when either window has fewer than 5 sentences |
| analyst consensus | `GET /analyst-consensus/latest` (all banks) or `GET /analyst-consensus?bank=DBS` | Yahoo Finance aggregates: rating, number of analysts, mean target, price |
| evidence drill-down | `GET /evidence/latest?bank=OCBC&aspect=dividend_policy&limit=30` | newest sentences with their stored label |
| evidence search | `GET /evidence?query=dividend+cut&bank=DBS&k=5` | semantic search, as the chatbot uses; `k` from 1 to 50 |
| data behind a cell | `GET /coverage?bank=DBS&aspect=dividend_policy` | count, date range and sources |
| labels for the UI | `GET /banks`, `GET /aspects` | aspect keys with readable names ("Dividend Policy") |
| chat | `POST /chat` | below |
| starter questions | `GET /suggestions?limit=6` | only questions the data can answer |
| liveness | `GET /health` | `{"status": "ok"}` |

## What the responses look like

Real responses from the 14 Oct database, shortened.

`GET /sentiment?bank=DBS`

```json
{"bank": "DBS", "aspect": "ALL", "window": "all_time", "score": 0.143, "n": 24978,
 "positive_n": 7844, "neutral_n": 13115, "negative_n": 4019, "confidence_mean": 0.8372,
 "model_version": "finbert-adapted-finetuned-2026-10-11-3seed-m0",
 "computed_at": "2026-10-14T00:07:03.514167+00:00", "insufficient_data": false,
 "data_as_of": "2026-09-25"}
```

`score` runs from −1 (all negative) to +1 (all positive), weighted by the
model's confidence and by source, and shrunk towards 0 when there are few
sentences.

`GET /sentiment/index?window=all_time` (one row of 36)

```json
{"bank": "OCBC", "aspect": "asset_quality", "source": "ALL", "score": 0.0625, "n": 337,
 "pos_n": 98, "neu_n": 160, "neg_n": 79, "confidence_mean": 0.7928,
 "model_version": "finbert-adapted-finetuned-2026-10-11-3seed-m0",
 "computed_at": "2026-10-14T00:07:03.514167+00:00", "insufficient_data": false}
```

`GET /sentiment/series?bank=UOB&bucket=quarter` (two points)

```json
{"bank": "UOB", "aspect": "ALL", "bucket": "quarter", "source": "ALL",
 "series": [{"period": "2026-Q2", "score": 0.0542, "n": 507, "pos_n": 124, "neu_n": 286, "neg_n": 97,
             "confidence_mean": 0.848, "sufficient": true},
            {"period": "2026-Q3", "score": 0.1414, "n": 592, "pos_n": 179, "neu_n": 311, "neg_n": 102,
             "confidence_mean": 0.8442, "sufficient": true}]}
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
the reason in `detail`. No hosted backend (Gemini, Claude, OpenAI or Groq)
receives Reddit or CNA evidence text, or text from a source not listed in
`config/sources.yaml`, nor earlier answers that may quote them. The response:

```json
{"question": "And OCBC?", "answer": "…", "guard": null,
 "citation_unverified": false, "unverified_numbers": []}
```

The UI must show the flags, not just the answer:

- `guard` names the intent whose fixed reply answered, without the chatbot
  model: `advice`, `other_bank`, `off_topic`, `greeting`, `thanks`,
  `goodbye`, `help`, `service`, `injection` or `feedback`; `null` when the
  model answered (`config/intents.yaml` has the replies);
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
- **Recent figures are "as of" the newest data, not today.** Collection has
  stopped, so the `7d` and `30d` windows, and the trend, count back from the
  newest stored sentence. `/sentiment`, `/sentiment/compare`,
  `/sentiment/trend` and `/sentiment/index` return that date as
  `data_as_of` ("2026-09-25"), and `window_note` spells the window out. Show
  "as of <date>" next to any recent figure, and never label it "this week".
- **Each sentence has one aspect, chosen by a local LLM** (since the re-score
  of 12 Oct 2026). On the labelled sentences it picks the aspect a person
  would choose first 73% of the time; the embedding-similarity method it
  replaced managed 41% and gave a sentence 6.4 aspects on average. A
  per-aspect figure therefore rests on far fewer sentences than before: show
  `n` beside it, and grey out a cell whose `insufficient_data` is true.
- **Scores come from the fine-tuned model** (the adapted encoder trained on
  LLM labels, three seeds averaged). `model_version` says which model
  produced a row. Every endpoint returns only the served model's rows; base
  FinBERT's stay in the database for comparison but don't appear. A client
  that reads the database directly must filter on `model_version` itself, or
  it counts every sentence twice. If the database has no rows for the served
  model (an old snapshot), `/sentiment` says so in its `reason` and the
  server logs a warning, but `/sentiment/index` and `/sentiment/series`
  return empty lists: restore the latest snapshot.
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
