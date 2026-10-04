# Design & Reasoning

Why this system is built the way it is. For how to run it, see
[RUNBOOK.md](RUNBOOK.md). For what is and isn't finished, see
[STATUS.md](STATUS.md).

---

## Before you trust any number

**[STATUS.md](STATUS.md) is the single source of truth for these caveats.**
It is kept current against the database; this page explains design reasoning
and will drift. The short version, as of 2026-10-01:

- Read blended cross-bank figures next to the per-source breakdown. DBS
  carries about 55% of all sentences and roughly six times the earnings
  volume of the other two banks.
- The fine-tuned model leads base FinBERT on macro-F1 and trails it on
  accuracy (0.604 ± 0.035 against 0.571; accuracy 0.66 against 0.70,
  [evidence](evidence/finetune-fixes-2026-10-01.md)). Every stored score is
  base FinBERT, zero-shot.
- Per-aspect scores are not meaningful yet: the current assignment gives a
  sentence 6.4 of the ten aspects on average. The LLM classifier of decision
  16 is built and evaluated (0.729 against 0.413) but not yet applied.
- The GPT backend has never been run against its real API; Gemini was
  verified on 2026-09-30 ([evidence](evidence/gemini-backend-2026-09-30.md)).
- Local chatbot models fabricate citations. The code-level check is a
  detector, not a fix.

What happens next, and in what order, is in [PLAN.md](PLAN.md).

---

## What the system does

Ingests public text about DBS, OCBC and UOB from several sources, splits it
into sentences, assigns each sentence to one or more financial aspects,
scores sentiment per (sentence, aspect), aggregates into a per-bank index,
and exposes the result through a REST API and a chatbot that answers
questions by querying that store, and a Streamlit dashboard maintained by a
teammate (decision 23).

```
 sources                  ingest/            preprocess/         aspects/
┌──────────────┐         ┌─────────┐        ┌───────────┐      ┌──────────────┐
│ Reddit       │────────▶│         │        │  clean    │      │ FinBERT      │
│ (ArcticShift)│         │ dedupe  │───────▶│  segment  │─────▶│ embeddings   │
│ NewsAPI      │────────▶│ normalise│       │  attribute│      │ + assignment │
│ Earnings PDFs│────────▶│ upsert  │        │  to bank  │      └──────┬───────┘
│ Yahoo consensus│──────▶│         │        └───────────┘             │
└──────────────┘         └────┬────┘                                  ▼
                              │                              ┌──────────────┐
                              │                              │ sentiment/   │
                         documents                           │ scoring      │
                              │                              └──────┬───────┘
                              ▼                                     ▼
                          sentences ──────────────────────▶ aspect_sentiment
                                                                    │
                                                                    ▼
                                                            aggregate/index
                                                                    │
                                    ┌───────────────────────────────┼────────────────┐
                                    ▼                               ▼                ▼
                              dashboard/                          api/  ──────▶  chatbot/
                              (Streamlit,                      (FastAPI)  POST  (tools + RAG)
                               a teammate's)                       ▲      /chat
                                                                   │ HTTP
                                                            any other frontend
```

Everything is stored in one SQLite file (`data/plp.db`). Tables:
`documents` → `sentences` → `sentence_aspects` + `aspect_sentiment` →
`sentiment_index`, plus a standalone `analyst_consensus`.

---

## Decision log

The consequential choices, with the evidence behind each. This is the
section most worth reading before changing anything.

### 1. The sentence is the unit of analysis, not the document

Aspect-based sentiment requires it. A single Reddit comment can praise a
bank's dividend and criticise its app in consecutive sentences; scoring the
document as a whole would average those into meaningless neutrality.
Everything downstream — aspect assignment, sentiment, the index, chatbot
citations — keys off `sentence_id`.

### 2. Reddit via Arctic Shift, not the official API or a paid scraper

Reddit declined the project's API application, so PRAW was unavailable.

| option | outcome |
|---|---|
| Reddit official API | application declined |
| Apify (commercial scraper) | ~$0.28–3.40 per 1,000 results; live scrape, not reproducible |
| **Arctic Shift** | free, no key, multi-year archive, reproducible |

Arctic Shift is a public research archive in the Pushshift lineage. Two
constraints found by testing it rather than reading its docs: keyword search
times out on active subreddits (so the pipeline harvests whole subreddits by
date window and filters locally), and pagination requires a moving `after`
cursor with `sort=asc` because there is no page token.

Subreddit selection was also corrected empirically. `r/SingaporeInvestments`
has had no posts since Oct 2023; `r/singapore` and `r/investing` returned
zero bank-mentioning items across 7,000+ sampled. `r/singaporefi` is the
only productive source.

### 3. Earnings from bank IR sites, not SGX

SGX looks like the obvious source and is the wrong one. SGXNet carries
company announcements and SGX's own commentary; third-party analyst reports
are brokerage IP behind client entitlements and are not on SGX at all. Its
API also returns 403 behind a WAF.

DBS and OCBC publish the same earnings material openly on their own IR
sites — plain HTTP, no bot protection, no ToS grey area. UOB sits behind an
F5 WAF that answers scripted requests with a challenge stub.

The choice there was deliberate: rather than escalate to fingerprint-spoofing
tools to defeat the WAF, the same PDFs are fetched from the Wayback Machine,
which archived them at their original UOB URLs and is not behind that WAF
(`ingest/earnings_fetch_uob.py`). The bytes are UOB's own published documents;
only the transport differs. This respects the signal the WAF is sending while
still closing a coverage gap that had invalidated every cross-bank
comparison in the project — UOB went from 4 earnings sentences to 1,600.

This also produced the closest thing the project has to genuine analyst
input: DBS publishes a quarterly **analyst call transcript**, in which named
brokerage analysts question management on margins, asset quality and
guidance. Fourteen consecutive quarters are available.

### 4. Aspect assignment is frozen-centroid, not re-clustered per batch

> **Superseded 2026-09-26 by decision 16.** Kept as the record of why the
> first design was chosen; the seed-centroid assignment survives only as the
> baseline decision 16 is measured against.

Clustering runs once, offline, to derive a taxonomy (`aspects/discover.py`).
Assignment then matches sentences to those frozen centroids every batch
(`aspects/assign.py`). Re-clustering per batch would renumber and rename
aspects between runs, so a dashboard user would see categories shift
underneath them.

### 5. Similarity floor raised 0.35 → 0.65

> **Superseded 2026-09-26 by decision 16.** No floor fixes the underlying
> problem, which the 2026-09-24 evidence below decision 16 explains.

The original floor did not discriminate between anything. Measured sweep on
the real corpus:

| floor | avg aspects matched per sentence | % falling to "other" |
|---|---|---|
| 0.35 | 2.00 / 2 | 0.1% |
| 0.50 | 1.96 | 0.6% |
| 0.60 | 1.89 | 2.8% |
| 0.70 | 1.63 | 9.2% |
| 0.75 | 1.29 | 18.9% |

At 0.35 even a deliberately coarse two-aspect taxonomy matched *both*
aspects on essentially every sentence. 0.65 is a calibration point, not a
final answer — re-sweep when the corpus or taxonomy changes materially.

**Re-swept 2026-09-11** on the full 36,884-sentence corpus, which is the
material change this note anticipated. At 0.65 the proposal taxonomy now
matches 1.80 of 4 aspects per sentence and sends 37.3% of the corpus to
`other`; the sweep from 0.35 to 0.80 shows no floor at which it both
discriminates and retains the corpus. The comparison tool had itself been
measuring at a hardcoded 0.35 while this config said 0.65, so its earlier
output described a threshold the pipeline had stopped using. Full results:
[evidence/taxonomy-comparison-2026-09-11.md](evidence/taxonomy-comparison-2026-09-11.md).

### 6. Earnings source weight 3.0 → 1.0, and the index gained a source dimension

The 3.0 weight was set when earnings was assumed to be a handful of
high-signal documents. It became the second-largest source, and it is
measurably the most positive one:

| source | positive | neutral | negative |
|---|---|---|---|
| Reddit | 2.3% | 94.8% | 3.0% |
| earnings | 24.7% | 67.9% | 7.4% |

Triple-weighting that amplified a known skew. Weight is now 1.0, and
`sentiment_index` carries a `source` column so every blended row sits
alongside its components — the blend is kept (the proposal calls for it) but
is no longer opaque.

### 7. Analyst consensus from Yahoo Finance, with the caveat stated

Full analyst reports are paywalled. The news-derived proxy in
`ingest/analyst_tag.py` matched zero documents. Yahoo Finance's
`quoteSummary` endpoint returns real consensus data (analyst counts, ratings,
price targets) for all three banks.

It is an **unofficial API** — the endpoint the `yfinance` library wraps, with
no published terms blessing it and a cookie/crumb handshake that exists to
slow automated access. It also provides consensus *aggregates*, not analyst
report text. Both caveats are surfaced in the module, the dashboard and the
API response. Since 2026-09-24 Yahoo is also a news source; see decision 14.

### 8. Chatbot uses a plain tool-calling loop, not a framework

The loop is roughly fifty lines. A framework would add abstraction to explain
in the report without adding capability at this scale. Tools are ordinary
Python functions over SQLite, so the model backend is swappable without
touching them.

### 9. Grounding rules are enforced in code, not requested in the prompt

Two mechanisms exist because prompt instructions alone failed in testing:

- **Volume floor.** `get_sentiment` returns `insufficient_data` below 5
  observations rather than a number the model might report as fact.
- **Citation verification.** If `search_evidence` was never called, any
  quoted evidence, `sentence_id` or URL in the answer is fabricated by
  definition, and the response is flagged. This was added after a local
  model invented sources twice — once as plausible-looking URLs, once as
  placeholder tokens that a URL-matching check alone would have missed.

### 10. Retrieval is cosine similarity over cached embeddings, not a vector DB

At tens of thousands of sentences, brute-force cosine over an in-memory
matrix is as correct as FAISS or Chroma and far simpler. SQL pre-filters on
bank/aspect/date first, so the embedding comparison runs on a small
candidate set. A small lexical-overlap boost is added so exact identifiers
(ticker codes, product names) are not found by semantic proximity alone.

### 11. Local model support (Ollama) alongside hosted models

The project needs to be runnable by someone without an API key. Backend
selection auto-detects: a hosted model if a key is present, Ollama
otherwise. *Changed 2026-10-04:* the default is Ollama with `llama3.1:8b`, the
demo model, whatever keys are set; `CHATBOT_BACKEND=auto` keeps the old
behaviour (PLAN section 2). `llama3.2:3b` is the default — its tool-calling was confirmed
against a running instance, and it is roughly seven times faster per call
than `qwen3:4b`, which emits a hidden reasoning chain first.

### 12. Logging is centralised, and logs go to stderr

Third-party libraries (transformers, huggingface_hub) print progress bars
and load reports that bury pipeline output. `config/logging_config.py`
silences them by default and restores them under `DEBUG=true`. Logs go to
stderr so stdout carries only real program output — the chatbot's answer can
be piped on its own. A rotating file captures DEBUG regardless of console
level, so unattended overnight runs remain diagnosable.

### 13. News from Google News RSS and Yahoo, through one shared filter

*2026-09-24.* News had been 20 NewsAPI rows over one month, because NewsAPI's
free tier reaches back about a month and Yahoo's news stream has no history.
Google News RSS accepts `after:`/`before:` date operators, which makes
history reachable one month at a time. The corpus now holds about 5,800 news
articles covering every month from January 2023.

Every news source passes `ingest/news_filter.py` before insert: the article
must name a bank; broker, venue, research-desk and market-note mentions
(UOB Kay Hian, OCBC Arena, "DBS maintains 'buy' on IHH", "Australian Dollar:
... – UOB") don't count as a mention; and near-duplicates across sources are
dropped by normalised URL or 90% headline similarity within three days. Every
rejection is logged in `data/news_flagged.csv`. The query set was chosen by a
pilot of seven techniques; only headline-restricted `intitle:` queries earned
their requests. Method, rules, pilot results and known gaps:
[news-data.md](news-data.md).

Consequence to state in the report: Google's ranking favours recent articles,
so news volume per month rises towards the present (about 77 a month in 2023,
244 in 2026). Normalise per month before comparing periods.

### 14. Yahoo Finance used despite the course notes excluding it

*2026-09-24.* The project's original context notes rejected Yahoo Finance as
"too fragile/ToS-risky for a graded deliverable". It is now used twice: the
analyst consensus aggregates (decision 7) and news headlines via `yfinance`.
The reversal is deliberate: the alternatives for both are paywalled, the
data used is headline text and published aggregates rather than scraped
article bodies, and the risk that matters for grading, an endpoint breaking,
is contained by freezing the corpus in snapshots (decision 15). In practice
Yahoo contributed 114 news articles, all from the first pull; its stream
changes little from day to day and three daily runs added nothing. Google
News carries the history. The report should say both things.

### 15. The database lives outside git, as dated snapshots

*2026-09-24.* `data/plp.db` passed GitHub's 100 MB file limit (about 103 MB)
and the embeddings cache was already over it. Both are gitignored. The
database is shared as a gzipped, checksummed snapshot (about 28 MB), listed in
the README with its SHA-256; the embeddings are a cache that
`python -m aspects.embed_store` rebuilds. Snapshots are also the record of
exactly which data a reported number came from.

### 16. Aspects assigned by a local LLM, one per sentence

*Decided 2026-09-26; to be implemented. Its taxonomy is replaced by decision
21's ten aspects; the method stands.* The seed-centroid assignment of
decisions 4 and 5 fails in a way no threshold fixes. The four centroids are
close to each other, so plain transactional or factual sentences ("transfer
the money to your DBS account") match three or four aspects at once: 46% of
assigned sentences did. Evaluative sentences, where the sentiment is, sit
further from the jargon-heavy seed terms and fall to `other`, which ends up
holding almost all the polarity (45% positive, 22% negative, against ≤ 3.6%
positive for every named aspect). Evidence:
[evidence/aspect-sentiment-concentration-2026-09-24.md](evidence/aspect-sentiment-concentration-2026-09-24.md).

The replacement asks a local model to classify each sentence into exactly one
of the proposal's four aspects or `other`, with a fixed prompt (role, task,
schema of the five categories with definitions, constraints, a few examples,
input) and structured output, following the course's zero-shot ABSA pattern
(NMSM Day 2). It keeps the proposal's aspects, so it changes the method, not
the taxonomy. It is validated against a human-checked sample before the full
run, and evaluated against the human aspect labels from decision 17, with
the seed-centroid assignment as its baseline. Clustering (`aspects/discover.py`)
still runs offline, as the unsupervised discovery task: it tests whether
`other` hides a real aspect the four don't cover.

### 17. Annotators label aspect and sentiment together

*Decided 2026-09-26; first round labelled 2026-09-27 (1,277 rows after
cleaning, sentiment κ 0.93; [evidence](evidence/annotation-agreement-2026-09-27.md)).
The round attached labels to candidate rows whose aspect annotators
corrected, rather than to one row per sentence, and had no "not about the
bank" flag; five aspects are below the 80-row floor.* Labels were attached to
automatically assigned (sentence, aspect) pairs, so a wrong assignment wasted
an annotator's effort and the assignment itself was never evaluated. Each row
is now one sentence: the annotator chooses its aspect and its sentiment toward
the bank as an investment on that aspect, or flags it as not about the bank.
Candidates are re-drawn across Reddit, earnings and news. The target of
200–300 rows per sentiment class is read as the proposal wrote it, per
sentiment class overall, with a floor of roughly 80 rows per aspect.

### 18. Bank entity recognition, scoped narrowly

*Decided 2026-09-26; to be implemented.* Bank attribution is alias matching
(`ingest/base.py`). It works for clean headlines but can't separate the bank
from things that share its name. The NER task recognises organisation
mentions with spaCy's pretrained model (installed; its NER is switched off
in segmentation today) and resolves each to DBS, OCBC, UOB or "not the bank":
POSB, lowercase "dbs" in Reddit text, UOB Kay Hian and DBS Vickers, Bank of
Singapore and Great Eastern, Aston Martin DBS. It is evaluated on a
~200-sentence gold set weighted to those cases, against alias matching. The
scope is kept to what improves attribution, so it doesn't compete with
labelling for time.

*Amended 2026-10-04:* DBS Vickers counts as DBS (DBS Group's list of
subsidiaries, 31 Dec 2024), and POSB counts as DBS at collection too (DBS
acquired POSBank in 1998). UOB Kay Hian stays a separate broker. PLAN
section 2, made on 2026-10-04.

### 19. Chatbot changes drawn from the Conversational UIs module

*Decided and implemented 2026-09-26* (`chatbot/guards.py`, `chatbot/agent.py`).
Results: [evidence/chatbot-harness-2026-09-26.md](evidence/chatbot-harness-2026-09-26.md).
Three gaps, each matching a specific part of CNI Day 1:

- **No memory.** The dashboard shows the conversation, but only the latest
  question reaches the model, so "and OCBC?" loses its context. The fix
  passes recent turns and tracks the current bank, aspect and time window.
- **Advice-declining is prompt-only**, and works for 3 of 7 advice-seeking
  gold-set questions on every model tested. The fix is an input guard that
  detects advice-seeking before the model runs and answers with a fixed,
  reviewed reply: templates for critical responses, generation for the rest.
- **Numbers are not checked.** Citations are verified against what was
  retrieved (decision 9), numbers aren't. An output guard compares every
  figure in an answer with the tools' results.

The architecture stays a tool-calling loop (decision 8). CNI's rule, use the
least autonomous architecture that handles the task's variability, is the
reason for a guard over a model upgrade: the questions this bot faces are
narrow, and deterministic checks around the model are cheaper and more
reliable than trusting it more. Evaluation grows accordingly: a frozen gold
set of about 30 questions written before tuning, retrieval Hit@K and MRR,
faithfulness scored by an LLM judge calibrated on human ratings, multi-turn
scenarios, and a SASSI questionnaire with a handful of users.

Built alongside the three fixes: an off-topic reply for questions about
other banks or nothing the system covers; a check that cited sentence ids
were actually retrieved; evidence results packaged with a short id, a plain
date and a ready-made citation; a fixed reply when the model returns nothing
usable; decoding temperature 0.2 on every backend (`CHATBOT_TEMPERATURE`);
and an optional per-turn trace (`CHATBOT_TRACE_FILE`).

What it achieved, on the gold set with `llama3.2:3b`: advice and
out-of-scope questions went from 2 of 7 handled correctly to 7 of 7, all by
guards and so independent of the model. Invented citations stayed at
43–48%: the harness detects them but can't make a 3B model stop producing
them, so the demo model (an open decision in PLAN.md) matters more than any further prompt
work. Of 19 figures the number check flagged in the final run, 18 were
invented. The temperature change had no measurable effect at 23 questions.

### 20. CNA loaded as full text, found through the Wayback Machine

*2026-09-26.* CNA was the one planned addition to the frozen corpus (PLAN,
section 2). Its scraper read only the live RSS feed, which holds the latest items and
none about the banks, and wrote a file rather than the database.
`ingest/cna_archive.py` finds CNA bank articles from 2023 on through the
Wayback Machine's index of CNA URLs, whose slugs carry the headline. It
fetches each article's full text from CNA at robots.txt's 10-second crawl
delay, or from the archived copy when CNA no longer serves it, and loads it
through the shared news filter. That added 207 articles and 1,599 sentences.

Three choices came with it:

- **A full-text article beats a headline-only copy.** Google News had
  already stored 117 of the 207 as bare headlines, and first-copy-wins would
  have dropped the full text. The filter now keeps the fuller article, and the
  sentence-level hash in preprocessing stops the shared headline being
  counted twice. No stored row was deleted.
- **CNA sentences must name the bank themselves.** Unlike the other news
  sources, a CNA document is a whole article, not a headline and a line, so
  it doesn't lend its bank to sentences that name none. Many sentences that
  say "the bank" are lost; none are attributed to the wrong bank.
- **Weighted 1.5, like the other news sources** (decision 6).

CNA is not a complete record: only headlines whose URL names a bank are
found, and only what the archive captured, so months hold 0 to 13 articles.
It adds full text, not volume. Details: [news-data.md](news-data.md).

### 21. Ten aspects, derived from the clustered corpus

*2026-09-30, adopting the text-analytics workstream's work of 25–27 Sep.*
Decision 16 kept the proposal's four aspects. The workstream instead labelled
all 338 clusters of the 25 Sep discovery run and found that the four covered
a small part of what people write about the banks: retail banking and the
stock itself, which the proposal left in `other`, are the two largest themes.
The taxonomy is now ten aspects plus `other`: the proposal's four, broadened;
capital and liquidity; income and profit results; wealth business; investor
stock sentiment; retail banking; and the macro environment
([evidence/aspect-taxonomy-2026-09-25.md](evidence/aspect-taxonomy-2026-09-25.md)).
The first labelled round (decision 17) was done under it, and the corpus was
re-assigned and re-scored under it on 30 Sep.

This replaces decision 16's taxonomy, not its method. Seed-centroid
assignment is still a stopgap, and a worse one with ten aspects: at the
carried-over 0.65 floor a sentence matches 6.4 aspects on average, and
annotators changed the assigned aspect on 86% of candidate rows. The LLM
classifier of decision 16, given these ten aspects, remains the fix, and the
1,277 human aspect labels are now its evaluation set. Two things the report
must say: the cluster labels were drafted with an AI assistant and not
checked by a second person, and aspect agreement between annotators was not
measured.

### 22. Opus 5.5 as an additional labeller, never the gold label

*2026-10-01.* Claude Opus 5.5, run through Claude Code subagents, labels the
same sentences as the annotators, as one more rater: aspect blind, then
sentiment given the human aspect, with the annotation guideline quoted as
its instructions. Its answers live in `data/labeled/claude/`, apart from the
human labels, and change a gold label only through a person's decision on
the review queue. It fills two gaps in the 27 Sep round: aspect agreement
was never measured (one rater), and the sentiment labels were anchored on a
model suggestion. On the 1,277 rows it agrees with the human aspect at κ
0.80 and the human sentiment at κ 0.79
([evidence/opus-labeller-2026-10-01.md](evidence/opus-labeller-2026-10-01.md)).
The pipeline's aspect classifier stays local (decision 16): the Opus run
isn't re-runnable code and isn't sized for 44,345 sentences. The report's
GenAI declaration lists it, and its agreement figures are human–LLM, not
human–human.

*Applied 2026-10-04:* where Opus disagrees with the human (202 aspect and 173
sentiment labels), the human label stays and there is no full relabel. Only
the rows on the bank-economist and wealth-or-retail boundaries are fixed,
once the team decides those two rules (PLAN section 2).


### 23. The API serves every view a dashboard needs; the dashboard is a teammate's

*2026-10-01, the team's call.* A teammate builds the dashboard as its own
project, so the Streamlit dashboard here was removed (its last version is
in git history before this date). The REST API is now the system's
interface, and was extended so a dashboard needs nothing else:
`/evidence/latest` for the drill-down list, `/analyst-consensus/latest` for
every bank at once (each bank's own newest row: the Streamlit page had taken
one date for all banks and so hid UOB's consensus), and `/aspects` for
readable labels. CORS is open, `docs/api/openapi.json` is the
machine-readable contract (a test fails if it drifts), and
[api-integration.md](api-integration.md) maps each view to its endpoint and
lists what the screen must say. The chatbot stays, reachable through
`POST /chat` and, for testing, a terminal chat (`python -m chatbot.chat`).
Streamlit and matplotlib left `requirements.txt` with the page.

*Amended later on 2026-10-01, the team's call.* The teammate building the
dashboard pushed a redesign of the Streamlit dashboard to this repository the
same night, so it stays here: `dashboard/`, its styling test, Streamlit and
matplotlib, and the start, stop and status scripts' `dashboard` target are
back. The teammate owns it. It reads the database directly; the API remains
the documented interface for any other frontend, and each view can move onto
it. Its analyst-consensus panel still takes one date for all three banks,
which hides UOB's consensus; `ingest.yahoo_analyst.latest_per_bank` is the
fix the API uses.

---

### 24. The chatbot's input is sorted by a model, not by word lists

*2026-10-04, at the project owner's request.* Since 26 Sep (decision 19) the
chatbot answered advice-seeking and off-topic questions with fixed replies,
chosen by regular expressions and keyword lists in `chatbot/guards.py`. The
lists declined all 7 advice questions in the gold set, but on 4 Oct a probe
found what word lists can't do well: a weather question asked mid-conversation
went to the model; "hi" and "what can you do?" got "That's outside what I can
help with"; "any news on the weather?" and "football results" passed because
"news" and "results" are bank words; and "what's my DBS account balance?"
reached a model with no tool for it. Extending the lists would only move the
edge, and they can't read paraphrases or other languages.

Decided: a local model sorts each question into one intent from
`config/intents.yaml` (in_scope, advice, other_bank, greeting, thanks,
goodbye, help, service, injection, feedback, off_topic), given the
conversation's bank, aspect and previous question, through Ollama's
structured output, the same pattern as the aspect classifier (decision 16).
Only in_scope reaches the chatbot model; every other intent gets its reviewed
fixed reply from the same file. The definitions, few-shot examples and
replies live in the YAML, not the code. A prompt rule covers questions that
mix an unrelated part with a real one.

Costs and how they are handled. A second model call per turn (about a second
or two locally): measured by `chatbot/eval_intent.py`, which scores the
classifier on every labelled question (accuracy, each intent's precision and
recall, real questions wrongly blocked, questions let through, latency). It
is no longer deterministic: an advice question could reach the model, whose
prompt still says to decline, so advice recall is reported on its own. If
the classifier is down it fails open: the question goes to the model and the
turn records no intent. The output checks (decision 19) stay rules, since
they compare the answer with what the tools returned.

*Decided 2026-10-04 (PLAN section 2):* every hosted backend (Gemini, Claude,
OpenAI or Groq) is denied Reddit text, CNA text and text from unlisted
sources, the safe default given Reddit's developer policy on third-party use
of its content; the demo model is `llama3.1:8b`; strip enforcement and the
aspect query are on by default; and the 7- and 30-day figures count back from
the newest sentence, labelled "as of" its date.

### 25. The chatbot writes for a retail investor, with the figures read for it

*2026-10-04, at the project owner's request.* Tried in the dashboard on 4
Oct, the chatbot's figures were right but its answers didn't help a retail
investor. Every answer had the same labelled sections, because the prompt
asked for "direct answer first, then supporting evidence, then the sample
size and time window, then caveats". A score was given as "0.122 out of 1"
with no scale, and +0.124 was called "slightly negative". "Has it changed
recently?" about UOB's net interest margin got "not available" though 66
months had enough sentences to score: its 7-day window held too few sentences, and the
monthly series was only sent when both windows had enough. Evidence was mostly
results-report boilerplate, often the same sentence once a quarter, cited by
24-character ids.

Decided:
- The prompt keeps its grounding rules and replaces the fixed format with a
  short guide to writing for a retail investor: the answer first in plain
  words, a score once with its scale, the share of positive and negative
  sentences, how the bank compares and which topics lift or drag it, no
  headings, about 60 to 120 words.
- What a small model can't be trusted to work out is worked out in code and
  handed to it, in the chatbot's own versions of the tools
  (`chatbot/tools.py`): each score's reading in words (bands in
  `config/chatbot.yaml`), the shares, a bank's two strongest and two weakest
  topics, where a bank ranks among the three with the other two's scores, and
  the date the data runs to. An evidence search for a bank also returns the
  bank's score, as `topic_score` or `bank_overall_score`, and the data date:
  asked what people say and how they feel, the model had searched only,
  called the mood "neutral" with no score, and given a quote's date as the
  data's. A trend comes with one sentence that states it
  (`trend_in_words`): the last 7 days against the last 30 when both have
  enough sentences, else the latest month against the one before (the change
  computed before shrinkage, as for 7 against 30 days). The API's results are
  unchanged.
- Found in the evaluation rounds and the dashboard tests, and fixed: the
  model invented comparisons between banks it hadn't fetched, which is why one bank's score now carries
  the other two; it misread the monthly series and blended a rising week with
  a falling month, which is why the trend is written out; it judged the
  overall mood from evidence filtered to one side, so the prompt keeps the
  sentiment filter for questions about complaints or praise; and a reading it
  put in quote marks was removed as an invented quote, so a reading or a
  real topic name a tool returned no longer counts as a quote.
- Four validations of the branch (`docs/validation/2026-10-04-chatbot-answers*.md`)
  found gaps the change had opened in the grounding checks, and some old
  ones. Pattern fixes kept opening new gaps, so two rules replaced them.
  Quotes are found by pairing each paragraph's quote marks in order,
  whatever stands around them, a pair around fewer than ten characters
  being a word, not a quote, and an unpaired mark opening a quote to the end
  of its line. A date without its year is skipped by the figure check only
  when a tool's date field has that month and day and no decimal, thousands
  group or "%" follows it. Around them: the checks read the model's own text
  before the bare markers it wrote ("[2]") are dropped, and a dropped
  marker's figures are still checked; a marker inside a quote is shown only
  if the quoted sentence has it; history rebuilt for the API drops markers
  and sources; only real topic names count as tool wording; and a trend
  sentence whose printed scores point the other way says it's too close to
  call. The findings and their tests are listed in
  `docs/evidence/chatbot-answers-2026-10-04.md`.
- Evidence: from 50 candidates, a wording already picked is skipped, at most
  two come from one source unless too few others match, and a positive or
  negative sentence is lifted 0.03 over a neutral one when the search is
  filtered by topic and not by sentiment (retrieval returns a sentence's
  label only with a filter, and a sentiment filter leaves one label). Each result names its
  source ("Reddit", "news", "CNA", "bank results report", from
  `config/sources.yaml`).
- The reader sees numbered citations and a list of sources. The checks still
  run on the model's own text, sentence ids included, before the numbering.

Costs: answers are slower on a local model. Two parts were measured: the
longer tool results take longer to read (2.5 to 12 seconds more per answer),
and the longer prompt takes longer to read whenever Ollama hasn't cached it
(14 to 26 seconds); the answers themselves were not longer. A separate id field and raw counts are left out
of what it reads, to limit that (the turn's record keeps them; an id still
travels inside the citation the model copies). Links stay: the
hosted backends' privacy filter knows a Reddit post that came through a news
feed only by its link, and hiding links let such text through in a test. The
reading bands are a judgment, kept in config; and evidence is still ranked
by FinBERT embeddings, which favour report prose, so the evidence is better
rather than good. Measured before and after, with the times, in
`docs/evidence/chatbot-answers-2026-10-04.md`.

## Notable implementation details

**Idempotent ingestion.** Every document has a deterministic `doc_id` hashed
from source plus native ID, and inserts use `INSERT OR IGNORE`. Re-running
any adapter is a no-op rather than a duplicate.

**Per-sentence bank attribution.** An explicit in-sentence bank mention wins.
A document's bank is inherited only for short, single-topic sources (news,
earnings) — never for long Reddit threads, where inheriting pulled unrelated
sentences into a bank's corpus.

**Earnings dates parsed from filenames.** `2Q26_...` → 2026-08-01. Without
this, every historical earnings document would carry ingestion time and drop
the entire back-catalogue into the dashboard's 7d/30d rolling windows at
once.

**Volume shrinkage in the index.** Scores are shrunk toward neutral at low
volume (`score × n/(n+5)`), and `n` is always stored and displayed. A
sentiment number without its sample size is the main way this dashboard
could mislead someone.

---

## Deliberate scope limits

- Batch, not streaming. Sources are polled on demand. A daily launchd job
  exists (`scripts/com.plp.dailybatch.plist`) but is not running on any
  machine since 2026-09-26; the corpus is frozen for analysis.
- Text only. The speech content of the Conversational UIs module (Days 3–4)
  is out of scope.
- Alpha Vantage is retained in the codebase but contributes nothing — it
  does not index SGX-listed tickers (confirmed across all three, in several
  ticker formats).
- Annual reports and financial-statement PDFs are not ingested; they are
  near-entirely tables, which the prose extractor would strip to nothing.
- `get_trend`'s `direction` is still computed from two discrete windows
  (7d vs 30d). A continuous series now exists alongside it —
  `compute_time_series` buckets by week, month or quarter and is exposed at
  `GET /sentiment/series`, on the dashboard, and as up to 12 monthly points
  inside `get_trend`. It deliberately reuses the stored index's own
  `_summarize`, so a chart cannot quietly disagree with the headline number,
  and returns thin buckets marked `sufficient=false` rather than dropping
  them, so a gap in a line means missing data rather than neutral sentiment.
