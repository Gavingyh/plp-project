# Building the dashboard on the API

For whoever builds a frontend on the API. The Streamlit dashboard's data
views now use this API through `dashboard/api_client.py` and `dashboard/data.py`.
The Ask page uses `/suggestions` and `/chat` through `dashboard/chat.py`;
the dashboard imports no database or model backends. This page is how to run
the API, which endpoint feeds which view, what the responses look like, and
what the screen must say about the numbers.

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

## Dashboard presentation review — 18 October 2026

The presentation work is on `feat/dashboard-presentation`, starting from
`bd508d7` (the dashboard API integration merge). The comparisons below record
the earlier interface and the reviewed replacement for the project report.
The Topics "before" screenshots already include the new light theme and
sidebar toggle; the topic layout changed in a later step.

| Area | Before | After | Purpose |
|---|---|---|---|
| Appearance | Fixed dark background, pastel series colours and small chart labels | White by default, a sidebar dark-mode toggle, palettes for both modes and larger labels | Improve readability during the five-minute presentation and allow personal preference |
| Overview | Long page with source and analyst sections always expanded; weighting details in the introduction | Short introduction, visible all-data period, prominent bank scores, expandable source/analyst context and method notes | Keep the main bank comparison visible and let the presenter open supporting detail when needed |
| Topics opening view | All-topic heatmap followed by each bank's "strengths and weak spots" | Topic selector, plain-language topic description, comparison summary and three bank cards with sentence counts | Start with a concrete question about one topic across DBS, OCBC and UOB |
| Topic evidence | Navigate to Evidence and manually choose the bank and topic again | Each bank card has a View evidence button that carries both selections to Evidence; returning to Topics retains the chosen topic | Make the path from score to supporting text explicit |
| Topic detail | Sentence counts mainly in hover details and tables; "other" mixed into the main matrix | Expandable full heatmap with score and count in every cell; uncategorised text is optional; full tables remain available | Preserve analytical depth while shortening the default view |
| Relative rankings | "Best/weakest" wording; positive scores could be coloured red when ranked lowest | "Highest/lowest sentiment" wording; colour follows the score's sign, with a reminder that lowest need not mean negative | Avoid presenting sentiment rankings as financial strengths or weaknesses |
| Trends summary | Three scores and a historical chart, without a recent-movement interpretation | A summary from `/sentiment/trend`, with rolling-window scores and sentence counts together in each card | Explain recent movement using the backend's existing unshrunk comparison rather than subtracting displayed scores |
| Trends history | All history by default, a smooth filled curve and sample sizes mainly on hover | Latest 24 calendar months by default, monthly grouping, straight line segments, aligned sentence-volume bars, visible gaps and an incomplete-period note; All history, quarterly and weekly views remain available | Make recent movement readable while exposing changes in coverage and partial calendar periods |
| Evidence reading | Up to 30 sentences rendered together, with bank/topic controls only and an unexplained confidence percentage | Ten examples initially, Show next controls, source/sentiment filters and Reset filters; explicit Model confidence labels and original-source links, or a link-unavailable note | Let the reader inspect a manageable set of examples and understand their provenance and model metadata |
| Evidence scope | Recent examples without prominent loaded-set counts/date coverage | Loaded-row count and date range; source/sentiment filters explicitly apply only to the loaded recent set; an empty filter result does not imply no matches in the full dataset | Avoid implying full-corpus search or treating recent examples as a representative sample |
| Cross-page context | Topic-to-evidence navigation | Bank/topic context flows from Topics to Trends and then Evidence, and is included in the URL for refresh | Support a connected five-minute demonstration with minimal repeated selections |

The underlying API scores and selected sentiment model are the same. The old
heatmap uses two decimal places and the new focus cards use three: for example,
`+0.46` and `+0.455` can represent the same underlying result. A colour or
rounding change is not a model improvement. The existing sample rules remain:
the API suppresses scores below its volume floor (currently five sentences),
while topic headline comparisons and rankings require at least 30 sentences.
The 30-sentence rule is a display threshold, not a statistical confidence test.

Overview, Topics, Trends and Evidence have received layout reviews. Ask
inherits the shared styling and clearer labels; its complete layout review
is still pending.

The history range filters displayed calendar buckets, not the rolling-window
cards or the recent-trend calculation. A bucket overlapping the start of the
24-month range is retained in full. Evidence loads at most the latest 30 rows
for the bank/topic and pages/filters those rows locally. Overall evidence has
no per-topic sentiment labels in the current endpoint; sentiment filtering is
disabled until a specific topic is selected. Historical-period evidence and
full-corpus source/date filters would require additional API support.

Validation: 58 dashboard tests cover the API adapters, rendered views,
topic/trend/evidence navigation, sample suppression, 24-month range and gaps,
incomplete periods, evidence filters/reset/paging, mixed-format publication
dates normalised to UTC, and chat integration.
Browser checks compare live scores with the API and exercise navigation,
history grouping, evidence filters/paging and both themes.

Screenshots capture the first viewport at 1440 × 1000, in light mode:

- Trends: [before](screenshots/dashboard/trends-before.png) and
  [after](screenshots/dashboard/trends-after.png).
- Evidence: [before](screenshots/dashboard/evidence-before.png) and
  [after](screenshots/dashboard/evidence-after.png). The after example is
  reached from OCBC's dividend topic, so the selected bank/topic differs
  from the default before screenshot.

### Visual polish across the four data pages

A further visual pass uses a light canvas with white cards, a matching dark
palette, compact page headers and snapshot dates, consistent typography,
and quieter controls. Topics now places a bank comparison chart beside
compact bank cards with their actions inside; the full matrix, rankings and
tables are available through a secondary tab bar. Overview pairs its
conversation mix and history charts, Trends groups filters and history in
separate panels, and Evidence presents each excerpt with a source/date
header, sentiment label, model confidence and original-source link.
The chart uses the full −1 to +1 scale; suppressed scores remain absent.

These pairs use the same viewport, bank (DBS) and topic (capital & liquidity)
so the layout changes can be reviewed directly:

| Page | Before visual polish | After visual polish |
|---|---|---|
| Overview | [Before](screenshots/dashboard/overview-before-polish.png) | [After](screenshots/dashboard/overview-polished-light.png) |
| Topics | [Before](screenshots/dashboard/topics-before-polish.png) | [After](screenshots/dashboard/topics-polished-light.png) |
| Trends | [Before](screenshots/dashboard/trends-before-polish.png) | [After](screenshots/dashboard/trends-polished-light.png) |
| Evidence | [Before](screenshots/dashboard/evidence-before-polish.png) | [After](screenshots/dashboard/evidence-polished-light.png) |

The visual pass preserves the API integration, sample thresholds and existing
widget selections. Browser checks cover both themes at desktop and laptop
widths; the dashboard test suite still covers the data and navigation behavior.

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

### Streamlit chat behaviour

The Ask page stores successful question/answer pairs and their verification
flags in Streamlit session state. Every `/chat` request sends only earlier
`role`/`content` messages in `history`; the new question appears separately
in `message`. The API selects the backend and reconstructs the conversation.
The dashboard does not send provider keys or select models.

Citation and number warnings remain visible on reruns, and fixed replies
show a readable response type. Clearing the conversation removes all stored
turns and warnings. History belongs to the browser session and is not saved
to the database. Reloading or closing that session can reset it.

Suggested questions are cached for five minutes. Their failure shows a
warning while leaving typed chat available. Chat generation is never cached
or automatically retried. It allows a five-second connection timeout and a
600-second read timeout for local model/tool calls. Failed exchanges show an
error and are excluded from subsequent conversation history.

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
