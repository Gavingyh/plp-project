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

The sidebar distinguishes **Text through** (the newest stored sentence) from
**Scores computed** (when the selected model's aggregate was built). It shows
compact dates, with the exact UTC computation timestamp and an explanation
under **Snapshot details**. Empty API results show no-data messages; failed
requests show service errors.

- Interactive docs: `http://localhost:8000/docs`
- Machine-readable spec: [`docs/api/openapi.json`](api/openapi.json), for
  generating a client. A test fails if it falls behind the code; regenerate
  it with
  `.venv-plp/bin/python3 -c "import json; from api.main import app; open('docs/api/openapi.json','w').write(json.dumps(app.openapi(), indent=2, sort_keys=True) + '\n')"`
- `POST /chat` calls a model. **`POST /pipeline/runs` starts a worker which
  writes to the configured database.** The sentiment/evidence endpoints remain
  read-only; pipeline status/history reads may recover interrupted job metadata.
  CORS is open (`*`) and there is no authentication: run this API locally,
  not on the internet.

## Manual pipeline API (milestone 2)

The dashboard's Data Management page uses these endpoints through
`dashboard/pipeline_client.py`. A client can select local and online sources, launch a
separate worker, and poll its saved status. Model inference runs in the worker.
**All available sources** submits Google News, Reddit, configured NewsAPI, existing PDF folders
and the readable CNA article cache. Source cards show compact locations, with each API-host path
under **Folder locations**. The absolute paths are resolved by the existing
extractors from their checkout location; each teammate can use a different
checkout directory.

| Method and path | Result |
|---|---|
| `GET /pipeline/sources` | `sources`: key, label, `kind` (`local_pdf`, `local_cache` or `online`), folder, `exists`, `pdf_count`, `article_count`, `invalid_count`, `excluded_date_count` and optional `error`; `analysis_scope: "all_pending"`. CNA counts usable in-coverage articles and separately counts invalid/out-of-coverage records, with zero PDFs. Online options have an empty folder and zero file counts. NewsAPI has `exists: false` and setup guidance when its key is missing; other online options have `exists: true`. This endpoint never fetches online or returns credentials. |
| `POST /pipeline/runs` | HTTP 202, `{"run": {...}}`; `Location` is the status URL and `Retry-After: 2` suggests the polling interval |
| `GET /pipeline/runs?limit=20` | Newest run summaries and `active_run_id` (null when idle); limit 1–100 |
| `GET /pipeline/runs/{run_id}` | Full saved run under `run`, with stage metrics, file outcomes, warnings and imported document IDs |

The POST accepts any selection of `earnings`, `sgx_research`, `google_news`,
`arctic_shift` (Reddit), `cna` (local cache) and `newsapi`. Source order is normalised and duplicates removed.
Online requests optionally include both `since` and `until` as YYYY-MM-DD:
UTC start inclusive, end exclusive, 1–31 days, through at most tomorrow's UTC
midnight. Omitting both resolves the last seven days including today when
the job is queued. Dates on requests with no online source are rejected. Empty lists,
unknown sources, more than six items and extra fields give HTTP 422. The
request cannot supply a database path, filesystem command or model change.
NewsAPI credentials belong in the API host's ignored `.env` or environment,
not in this request. The worker fails preflight if a selected NewsAPI source
has no key; provider authentication/quota failures are visible source results.
Collection/import uses only selected sources; later analysis finishes all pending
database work, including work from earlier runs, then rebuilds the full index.

Example start request (**this writes to the configured database**):

```bash
curl -X POST http://localhost:8000/pipeline/runs \
  -H 'Content-Type: application/json' \
  -d '{"sources":["earnings","sgx_research"]}'
```

An online-only request can use
`{"sources":["google_news","arctic_shift"],"since":"2026-10-01","until":"2026-10-08"}`.
The saved run includes `collection_window` (null for local-only runs) and
`source_results`, keyed by online/cache source. Results contain `status` (`running`,
`completed`, `partial`, `failed` or `interrupted`), `fetched`, `documents_inserted`,
`duplicates`, `filtered`, `incomplete_windows` and `error`; online results also
include `batches_completed`. For CNA, `fetched` counts nonblank cache records
read, with `kind: "local_cache"`, `invalid_records`, `superseded_records` and
`filter_stats`, `excluded_date_records` and `coverage_start`. A partial CNA result means unusable records were skipped, with line-specific
input issues in the import stage's `files`. A cache with only unusable records
fails clearly. `cna` never performs discovery, page fetching or cache writes;
it considers usable cache records from 1 Jan 2023 through Singapore's current
date, independently of online collection dates.
Progress and successful commits are retained when another provider fails.
Partial/failed sources produce warnings, not silent empty successes; all
selected sources failing fails the run before analysis. Storage errors remain fatal.
Old run records without these additional fields remain readable.

The returned record initially has `status: "queued"`. Poll its `Location`
every two seconds; the worker may already have advanced by the first poll.
Status moves to `running`, then `completed`, `completed_with_warnings`,
`failed` or `interrupted`. HTTP 202 means the job was accepted; it does not
mean prerequisite checks or analysis succeeded. A missing model or source
folder is a failed **run**, visible at the status URL, rather than a long
blocked HTTP request.

HTTP 409 means another manual run already holds the lock, including while
its process is starting. HTTP 503 means the worker could not be launched or
its state storage is unavailable. A valid but unknown run ID gives 404;
malformed IDs give 422. The API only accepts the documented source keys.
If a POST response is lost, check history before trying again: the client
must not automatically retry a potentially successful launch.

History summaries omit the full file lists; `warnings_count` and
`documents_inserted` are counts recorded so far, not an estimate of remaining
work. Fetch the per-run URL for detailed results. Pending stages remain
pending if an earlier stage fails; earlier committed data is retained.
The dashboard polls every two seconds and shows an update-in-progress notice
on the other tabs. Terminal run records invalidate its cached
index/evidence/trend/series/source/analyst/suggestion responses and reload
the page. Failed/interrupted runs also invalidate caches because earlier
stages may have committed evidence. Chat history is retained. Run controls
are disabled during active jobs or unavailable status checks; start errors
require a status check and never cause automatic POST retries. Source folder
paths refer to the API host. Data Management remains accessible without an
existing sentiment index.

The launcher reserves the existing process lock before saving a queued job
and passes that same lock to its worker, so there is no unlocked startup
gap. A worker survives an API restart; saved records remain readable by the
new API process. Crashed/killed workers are recovered through the process
reaper or the next status/history request. Ordinary GET status calls do not
restart or resume work. macOS/Linux workers are supported; native Windows
can still use the existing data/chat API routes.

See [manual-pipeline.md](manual-pipeline.md) for prerequisites, terminal use,
failure recovery and the existing-data analysis scope.

## Dashboard presentation review — 18 October 2026

The presentation work is on `feat/dashboard-presentation`, starting from
`bd508d7` (the dashboard API integration merge). The comparisons below record
the earlier interface and the reviewed replacement for the project report.

| Area | Before | After | Purpose |
|---|---|---|---|
| Appearance | Fixed dark background, pastel series colours and small chart labels | Light canvas with white cards by default, a sidebar dark-mode toggle, palettes for both modes and larger labels | Improve readability during the five-minute presentation and allow personal preference |
| Sidebar | Navigation highlights sized to each label; theme control above navigation; long timestamps and a lengthy note | Equal-width navigation rows, compact snapshot dates and borderless details; a short note and Help/theme controls grouped at the bottom | Match the data pages and keep navigation, provenance and the theme control visible at laptop height |
| Overview | Long page with source and analyst sections always expanded; weighting details in the introduction | Short introduction, visible all-data period, prominent bank scores, expandable source/analyst context and method notes | Keep the main bank comparison visible and let the presenter open supporting detail when needed |
| Topics opening view | All-topic heatmap followed by each bank's "strengths and weak spots" | Topic selector, plain-language topic description, comparison summary and three bank cards with sentence counts | Start with a concrete question about one topic across DBS, OCBC and UOB |
| Topic evidence | Navigate to Evidence and manually choose the bank and topic again | Each bank card has a View evidence button that carries both selections to Evidence; returning to Topics retains the chosen topic | Make the path from score to supporting text explicit |
| Topic detail | Sentence counts mainly in hover details and tables; "other" mixed into the main matrix | Secondary tabs for the full heatmap, within-bank rankings and data tables; heatmap cells show score and count, with uncategorised text optional | Preserve analytical depth while keeping the selected-topic comparison prominent |
| Relative rankings | "Best/weakest" wording; positive scores could be coloured red when ranked lowest | "Highest/lowest sentiment" wording; colour follows the score's sign, with a reminder that lowest need not mean negative | Avoid presenting sentiment rankings as financial strengths or weaknesses |
| Trends summary | Three scores and a historical chart, without a recent-movement interpretation | A summary from `/sentiment/trend`, with rolling-window scores and sentence counts together in each card | Explain recent movement using the backend's existing unshrunk comparison rather than subtracting displayed scores |
| Trends history | All history by default, a smooth filled curve and sample sizes mainly on hover | Latest 24 calendar months by default, monthly grouping, straight line segments, aligned sentence-volume bars, visible gaps and an incomplete-period note; All history, quarterly and weekly views remain available | Make recent movement readable while exposing changes in coverage and partial calendar periods |
| Evidence reading | Up to 30 sentences rendered together, with bank/topic controls only and an unexplained confidence percentage | Ten examples initially, Show next controls, source/sentiment filters and Reset filters; explicit Model confidence labels and original-source links, or a link-unavailable note | Let the reader inspect a manageable set of examples and understand their provenance and model metadata |
| Evidence scope | Recent examples without prominent loaded-set counts/date coverage | Loaded-row count and date range; source/sentiment filters explicitly apply only to the loaded recent set; an empty filter result does not imply no matches in the full dataset | Avoid implying full-corpus search or treating recent examples as a representative sample |
| Cross-page context | Topic-to-evidence navigation | Bank/topic context flows from Topics to Trends and then Evidence, and is included in the URL for refresh | Support a connected five-minute demonstration with minimal repeated selections |
| Ask | Long introductory warnings, six large suggestion buttons, default chat avatars and disclosures beneath the conversation | Three starter cards, a narrower conversation with neutral/teal avatars, detailed help in the sidebar and a short note beneath the pinned input | Keep the conversation easy to read while retaining guidance and verification warnings |

The underlying API scores and selected sentiment model are the same. The old
heatmap uses two decimal places and the new focus cards use three: for example,
`+0.46` and `+0.455` can represent the same underlying result. A colour or
rounding change is not a model improvement. The existing sample rules remain:
the API suppresses scores below its volume floor (currently five sentences),
while topic headline comparisons and rankings require at least 30 sentences.
The 30-sentence rule is a display threshold, not a statistical confidence test.

Overview, Topics, Trends, Evidence and Ask have received layout reviews.
Ask uses the shared header and palette with a narrower conversation layout.

The history range filters displayed calendar buckets, not the rolling-window
cards or the recent-trend calculation. A bucket overlapping the start of the
24-month range is retained in full. Evidence loads at most the latest 30 rows
for the bank/topic and pages/filters those rows locally. Overall evidence has
no per-topic sentiment labels in the current endpoint; sentiment filtering is
disabled until a specific topic is selected. Historical-period evidence and
full-corpus source/date filters would require additional API support.

Validation: 61 dashboard tests cover the API adapters, rendered views,
topic/trend/evidence navigation, sample suppression, 24-month range and gaps,
incomplete periods, evidence filters/reset/paging, mixed-format publication
dates normalised to UTC, and chat integration.
Browser checks compare live scores with the API and exercise navigation,
history grouping, evidence filters/paging and both themes.

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

The visual pass preserves the API integration, sample thresholds and existing
widget selections. Browser checks cover both themes at desktop and laptop
widths; the dashboard test suite still covers the data and navigation behavior.

The sidebar aligns BankPulse and Streamlit's native collapse arrow in one
top row, with the subtitle underneath. The native button retains its keyboard
and collapse/expand behaviour. Clicking either the BankPulse name or pulse icon
returns to Overview within the current session, preserving chat history and
the selected theme. The brand also supports keyboard activation and truncates
when the sidebar is resized too narrowly. Navigation uses equal-width rows
and aligned icons. Its data
snapshot retains the sentence count and distinguishes the newest text date
from the index computation date. Snapshot details preserves the full UTC
timestamp and explains that recalculating scores does not imply new text
was collected. Help and Dark mode form one bottom utility group on all five
pages, separated from the snapshot by flexible space. The group sits near
the bottom of taller viewports and remains in the normal scroll flow on
short screens or when either disclosure expands. The redundant Display
heading is removed. **How BankPulse works** and **Snapshot details** share
the same borderless, transparent expander style. The Help expander explains score
interpretation, model/source limitations and data windows; on Ask it also
includes chatbot behaviour and verification. The same label and position
remain available when navigating between pages. Dark mode sits immediately
below Help. The data pages retain their short advice/date footer,
with the detailed method explanation available in the sidebar instead of a
duplicate expander below the page.
To find the chatbot-specific guidance, select **Ask**, then expand
**Help → How BankPulse works**. **How answers work** and **Verification**
appear first, followed by the shared score explanations.
Browser checks verify all five navigation items, keyboard navigation, the
snapshot disclosure and theme persistence after refresh. The compact sidebar
fits an 800-pixel-high laptop viewport with Snapshot details collapsed.

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
 "citation_unverified": false, "unverified_numbers": [],
 "unverified_readings": []}
```

The UI must show the flags, not just the answer:

- `guard` names the intent whose fixed reply answered, without the chatbot
  model: `advice`, `other_bank`, `off_topic`, `greeting`, `thanks`,
  `goodbye`, `help`, `service`, `injection` or `feedback`; `null` when the
  model answered (`config/intents.yaml` has the replies);
- an answer is checked before it is returned (`CHATBOT_VERIFY_BEFORE_REPLY`,
  on by default): a draft with a figure, a reading or a quote no tool returned
  is rewritten, trimmed or replaced by a reply that says no answer could be
  backed up, so the three flags below are empty and the UI has no warning to
  show. They are set only when that setting is `false`;
- `citation_unverified: true` means the answer cites evidence the tools
  never returned: mark the answer as not to be trusted;
- `unverified_numbers` lists figures in the answer that match nothing the
  tools returned;
- `unverified_readings` lists words the answer uses for a score ("neutral",
  "slightly positive") that no tool returned as that score's reading.

A local model takes seconds to tens of seconds per answer; show a spinner.
To try the bot without any UI: `.venv-plp/bin/python3 -m chatbot.chat`.

### Streamlit chat behaviour

The Ask page stores successful question/answer pairs and their verification
flags in Streamlit session state. Every `/chat` request sends only earlier
`role`/`content` messages in `history`; the new question appears separately
in `message`. The API selects the backend and reconstructs the conversation.
The dashboard does not send provider keys or select models.

Citation, number and sentiment-description warnings remain visible on reruns
and navigation, and fixed replies show a readable response type. The adapter
accepts an omitted `unverified_readings` field for compatibility with older
API responses, but rejects malformed values when that field is present.
Clearing the conversation removes stored turns, warnings and failed-turn
display state. History belongs to the browser session and is not saved to
the database. Reloading or closing that session can reset it.

The Ask layout is in `dashboard/ask.py`. The empty state shows up to three
API-generated starter cards, with remaining suggestions under More questions.
Once a conversation starts, all suggestions move into a collapsed Suggested
questions section. The Clear conversation control is disabled when there is
nothing to clear. Messages use neutral and teal avatars in a reading column
at most 920 pixels wide, with a pinned input and expandable answer guidance.
Answers, citations and the backend's period disclosure are displayed as
returned; the dashboard does not rewrite or parse the answer text.

The shared **Help → How BankPulse works** expander is visible in the same
bottom sidebar utility group on every page, above Dark mode. On
Ask it adds chatbot behaviour and verification guidance to the score/method
limitations available throughout the dashboard. Neither the conversation nor
the data pages repeat the detailed guidance in a footer expander.
The snapshot retains the exact computation timestamp under Snapshot details.
A short, accessible caption beneath the pinned input reads: “AI answers can
contain mistakes. Check the evidence. Not financial advice.” The four data
pages retain their short financial-advice notice and snapshot-date footer.

Typed and suggested questions share a submission callback. Each pending
question is consumed once, and the view reruns after success without making
another chat request. A failed question stays visible as an error, with the
input available again, and is excluded from the history sent on the next
request. There is no automatic retry. Preparing your answer displays elapsed
time using `st.spinner(show_time=True)`. The input and its caption use the
public `st.bottom` container, introduced in Streamlit 1.57
([release notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2026#version-1570));
the minimum dependency version is 1.57. The local environment already uses 1.66.

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
