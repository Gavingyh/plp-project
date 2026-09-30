# Verification ledger

Every number and claim added to the documentation on 2026-09-11, with the
command that produced it.

> **2026-09-30:** sentiment-index figures here counted a sentence once per
> aspect it matched. The index now counts each sentence once in its
> cross-aspect rows, so current values differ; see STATUS.md. The rule this run worked under: a figure that
cannot be traced to a command in this file does not go in a document.

Existing docs were treated as unverified sources, not as ground truth. That
was the right call — several of their numbers turned out to be wrong, and
those corrections are recorded here.

Machine: Apple M-series, macOS 25.2.0. Interpreter
`.venv-plp/bin/python3`, Python 3.14.0. All model steps run with
`HF_HUB_OFFLINE=1`.

---

## 1. Test suite

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest tests/ -q
```

| when | result |
|---|---|
| Baseline, before any change | 214 passed in 25.02s |
| After adding `tests/test_aspect_discover.py` | 217 passed in 59.50s |
| Final, after `tests/test_scripts.py` and `tests/test_agreement.py` | **251 passed in 62.12s** (idle machine); 106.17s when a model evaluation ran alongside |

`grep -rhE '^\s*def test_' tests/ | wc -l` gives 200 function definitions.
The gap to 214 is `@pytest.mark.parametrize` in
`tests/test_earnings_fetch_ir.py`, `tests/test_logging_config.py` and
`tests/test_earnings_fetch_uob.py`, confirmed with
`pytest --collect-only -q` (214 collected).

**Correction to `docs/RUNBOOK.md`:** it claimed "214 tests, ~2 minutes". The
count was right; the runtime was not. Measured runtime is now 59.5s, of which
roughly 35s is `umap`/`hdbscan` import cost (numba) newly introduced by the
discovery tests.

## 2. Corpus snapshot

All figures from `data/plp.db` on 2026-09-11, via `sqlite3` queries recorded
in full below.

```sql
SELECT COUNT(*) FROM documents;          -- 21,924
SELECT COUNT(*) FROM sentences;          -- 36,884
SELECT COUNT(*) FROM aspect_sentiment;   -- 79,987
SELECT COUNT(*) FROM sentence_aspects;   -- 79,987
```

```sql
SELECT source, COUNT(*) FROM documents GROUP BY source;
```

| source | documents | sentences |
|---|---|---|
| arctic_shift | 21,726 | 24,591 |
| earnings | 178 | 12,254 |
| newsapi | 20 | 39 |
| **total** | **21,924** | **36,884** |

**Correction to `docs/STATUS.md`:** its by-source table read 18,620 /
177 / 18 documents, which sums to 18,815 and contradicts its own stated total
of 21,924 four lines above. The sentence counts in that table were correct.

```sql
SELECT bank, COUNT(*) FROM sentences GROUP BY bank;
-- DBS 20,907 · UOB 10,601 · OCBC 5,376
SELECT bank, COUNT(*) FROM sentences WHERE source='earnings' GROUP BY bank;
-- DBS 9,093 · UOB 1,600 · OCBC 1,561
SELECT MIN(published_at), MAX(published_at) FROM sentences;
-- 2020-01-06 .. 2026-09-10
```

Verified unchanged from STATUS: all six of these figures already matched.

```sql
SELECT bank, source, score, n FROM sentiment_index
WHERE window='all_time' AND aspect='ALL';
```

| bank | blended | Reddit only | earnings only | NewsAPI only |
|---|---|---|---|---|
| DBS | +0.0559 (n=45,124) | −0.0015 (n=29,701) | +0.1681 (n=15,386) | +0.3080 (n=37) |
| OCBC | +0.0441 (n=11,942) | −0.0107 (n=8,967) | +0.2059 (n=2,968) | +0.3323 (n=7) |
| UOB | +0.0201 (n=22,921) | −0.0106 (n=19,986) | +0.2291 (n=2,921) | −0.0215 (n=14) |

Verified: STATUS's Reddit-only and earnings-only figures match to the
precision it quotes them at. Its "UOB blended moved to +0.020" matches
+0.0201.

Label distribution across `aspect_sentiment`: negative 3,299 · neutral
69,912 · positive 6,776.

## 3. The 48% vs 43.5% fabrication discrepancy

`docs/STATUS.md` reports `llama3.2:3b` at 11/23 (48%). The tagged run file
reports 10/23 (43.5%).

```bash
.venv-plp/bin/python3 -c "import json; rs=[json.loads(l) for l in open('data/eval/chatbot_eval_results.jsonl')]; print(len(rs), sum(1 for r in rs if r.get('citation_fabricated')))"
# 23 11
```

Resolved: they are two different runs of the same model, not an arithmetic
error. The 11/23 figure comes from the untagged run of 2026-09-07
(`chatbot_eval_summary.md` header: "Run at: 2026-09-07T17:31:43"). The 10/23
figure comes from the tagged re-run of 2026-09-10
(`chatbot_eval_results_llama3.2_3b.jsonl`, logged in
`data/eval/model_comparison.log` as `fabrication_rate: 0.435`).

Both are correct for their run. The documentation now says so and reports the
spread rather than picking one, because a single-run rate on 23 questions is
not stable to within one question.

## 4. SQLite limits

```bash
.venv-plp/bin/python3 -c "import sqlite3; c=sqlite3.connect('data/plp.db'); print(c.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER))"
# 32766
```

| property | value | command |
|---|---|---|
| Max bound parameters | 32,766 | `getlimit(SQLITE_LIMIT_VARIABLE_NUMBER)` |
| page_size | 4,096 | `PRAGMA page_size` |
| page_count | 21,222 | `PRAGMA page_count` |
| max_page_count | 4,294,967,294 | `PRAGMA max_page_count` |
| journal_mode | wal | `PRAGMA journal_mode` |
| SQLite version | 3.50.4 | `sqlite3.sqlite_version` |

Capacity ceiling is therefore about 4.4 TB against a current 83 MB file. The
`too many SQL variables` failure was a statement-construction limit, not a
storage limit. Recorded because it prompted a real question about whether to
change database, and the answer rests on these numbers.

## 5. `ingest/earnings_extract.py` prose extraction

```bash
git show HEAD:ingest/earnings_extract.py | sed -n '60p' | od -c
#   f o r   l i n e   i n   t e x t . s p l i t ( " " ) :
.venv-plp/bin/python3 -c "'a\nb'.split('')"
# ValueError: empty separator
```

Confirmed: before the fix, `extract_prose` raised `ValueError` on every page
of every PDF, and `pull()`'s per-file exception handling turned that into a
silent zero-document run.

## 6. Aspect discovery scaling failure

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.discover
# sqlite3.OperationalError: too many SQL variables
```

Embedding cache reported `{'already_cached': 36884, ...}`, and 36,884 exceeds
the 32,766 parameter limit from section 4. Fixed and covered by
`tests/test_aspect_discover.py`, which exercises the lookup at 33,000 rows.

## 7. Taxonomy comparison floor

```bash
grep -n 'SIMILARITY_FLOOR' aspects/compare_taxonomies.py   # was 0.35
grep -n 'similarity_floor' config/aspects.yaml             # 0.65
```

Confirmed the decision-support tool measured at a floor the pipeline had
stopped using. Full results and the sweep are in
`docs/evidence/taxonomy-comparison-2026-09-11.md` with its raw output
alongside.

Vectorisation of the similarity computation was checked against the previous
per-pair loop on random data: max absolute difference 1.19e-07, and identical
match counts at floors 0.35 and 0.65.

## 8. Environment facts

```bash
.venv-plp/bin/python3 --version        # Python 3.14.0
ollama list                            # llama3.1:8b, phi4-mini:latest,
                                       # gemma3:4b, qwen3:4b, llama3.2:3b
lsof -nP -iTCP:8501 -sTCP:LISTEN       # held by .venv-aegis (another project)
```

Port 8501 is occupied by an unrelated Streamlit process, which is why the
start script refuses rather than assuming the port is free.

## 9. Aspect assignment, measured directly

```sql
SELECT s.text, sa.similarity FROM sentence_aspects sa
JOIN sentences s ON s.sentence_id = sa.sentence_id
WHERE sa.aspect = 'net_interest_margin' AND s.source = 'arctic_shift'
ORDER BY sa.similarity DESC LIMIT 20;
```

All twenty are retail banking products: "No fees for ocbc" (0.860), "DBS Fixed
deposit interest." (0.857), "DBS My Account: no minimum balance and fees."
(0.851), "UOB Absolute Amex, 1.7% unlimited cashback" (0.834), "UOB credit
card application." (0.834). None is about net interest margin.

This converts STATUS's long-standing "assignment is not yet validated" caveat
into a measured failure for this aspect and source. Full output in the
scratchpad at run time; reproducible with the query above.

Supporting term frequencies, word-boundary matched over all 36,884 sentences:

| term | Reddit | earnings |
|---|---|---|
| `net interest margin` | 0 | 375 |
| `\bNIM\b` | 4 | 300 |
| `asset quality` | 0 | 198 |
| `\bNPLs?\b` | 1 | 270 |
| `\bdividends?\b` | 561 | 511 |

**A trap worth recording.** The first attempt used SQL `LIKE '%nim%'` and
returned 433 Reddit matches, which would have contradicted the documented
finding. 393 of those were "minimum". Any frequency claim built on substring
matching of a short abbreviation needs re-checking with word boundaries.

## 10. Inter-annotator agreement tooling

```bash
.venv-plp/bin/python3 -m train.agreement --file data/labeled/candidates.csv \
    --col-a llm_prelabel --col-b base_finbert_label
```

| | value |
|---|---|
| Rows compared | 997 |
| Observed agreement | 0.462 |
| Cohen's κ | 0.215 (fair) |

Confusion matrix shows the disagreement is one-directional: the local model
called 208 sentences positive and 135 negative that base FinBERT called
neutral. Consistent with the local model having been prompted with the
guideline's factual-valence rule while FinBERT was not.

This is model-to-model agreement. **No human-to-human κ has ever been
computed**, because zero rows are human-labelled.

## 11. Service scripts

Verified by a full lifecycle run on 2026-09-11, not by inspection:

| test | result |
|---|---|
| `start.sh dashboard` on port 8501 (held by another project) | Refused, printed the owning process, exit 1 |
| `start.sh api` on free port 8009 | Started, `/health` returned `{"status":"ok"}` |
| `start.sh api` again | "already running", did not start a second copy |
| `status.sh` | Correctly showed the foreign process on 8501 and the healthy API |
| `stop.sh api` | Stopped, pid file removed, port released |
| `stop.sh api` again | "not running", exit 0 |
| `start.sh dashboard` on free port 8511 | Started, `/_stcore/health` returned 200 |
| Foreign process on 8501 afterwards | **Untouched** (pid 97113 still running) |

The Streamlit health endpoint was confirmed against the installed source, not
assumed: `create_health_routes` in
`.venv-plp/lib/python3.14/site-packages/streamlit/web/server/starlette/starlette_routes.py`
documents `/_stcore/health` returning 200 when ready and 503 otherwise, with
`BASE_ROUTE_CORE = "_stcore"`. Streamlit version 1.63.0.

`shellcheck` is **not installed** on this machine. `bash -n` was run over every
script instead, and `tests/test_scripts.py` runs it in CI.

A parsing bug was found during this testing: `. .env` executes the file as
shell, and `.env.example` ships with
`REDDIT_USER_AGENT=plp-practice-module/0.1 by u/your_username`, whose unquoted
spaces made the shell attempt to run `by`. Replaced with a line-by-line parser.

## 12. Pipeline invariants

Checked against `data/plp.db` on 2026-09-11. All hold, and **nothing in the
test suite asserts any of them**:

| invariant | result |
|---|---|
| `aspect_sentiment` rows whose `sentence_id` is absent from `sentences` | 0 |
| `sentences` whose `doc_id` is absent from `documents` | 0 |
| `sentences` with a null or malformed `published_at` | 0 |
| `sentence_aspects` rows never scored | 0 |

## 13. FinBERT benchmark — a withdrawn claim

`.project-context/course-content/course-context.md` recorded: "FinBERT
benchmarks at ~88.2% accuracy vs. ~62.1% for lexicon-only (Loughran-McDonald)
scoring — this number is accurate per published research, safe to cite in the
report."

**Neither figure is in the FinBERT paper.** arXiv:1908.10063 was fetched and
its Table 2 extracted directly from the PDF with `pdfplumber`:

| model | acc (all data) | F1 | acc (100% agreement) | F1 |
|---|---|---|---|---|
| LSTM | 0.71 | 0.64 | 0.81 | 0.74 |
| LSTM + ELMo | 0.75 | 0.70 | 0.84 | 0.77 |
| ULMFit | 0.83 | 0.79 | 0.93 | 0.91 |
| LPS | 0.71 | 0.71 | 0.79 | 0.80 |
| HSC | 0.71 | 0.76 | 0.83 | 0.86 |
| FinSSLX | — | — | 0.91 | 0.88 |
| **FinBERT** | **0.86** | **0.84** | **0.97** | **0.95** |

There is **no Loughran-McDonald baseline in the table at all**. The paper also
identifies itself as an MSc thesis, University of Amsterdam, 25 June 2019.

A web search for the 88.2/62.1 pair returned nothing containing them. A
different paper (arXiv:2412.19245) reportedly gives 72.2% against
Loughran-McDonald's 50.1% on its own task; that came from a search-result
summary and **was not verified in the paper itself**, so it is not offered as
a replacement citation.

Corrected in place in the course-context file, with both accuracy columns
labelled, since quoting 0.97 as "FinBERT's accuracy" overstates it.

## 14. SGX reporting cadence

Verified against several independent legal summaries accessed 2026-09-11
(Allen & Gledhill, CNPLaw, Drew & Napier): SGX RegCo announced on 9 January
2020, effective **7 February 2020**, that quarterly reporting would no longer
be required of issuers above a S$75m market-capitalisation threshold, moving
to a risk-based approach with semi-annual reporting as the default and
voluntary business updates encouraged in between.

Corroborated by the corpus itself: OCBC's filenames carry `1H`/`FY` for
statutory results and `1Q`/`3Q` for updates.

**For the report, cite SGX's own rulebook or announcement**, not a law-firm
summary.

## 15. Bloom's taxonomy

The revised taxonomy of Anderson and Krathwohl (2001) — Remember, Understand,
Apply, Analyze, Evaluate, Create — verified against university teaching-centre
sources accessed 2026-09-11 (University of Illinois Chicago, Colorado
College). The 2001 revision turned Bloom's 1956 nouns into verbs and added a
knowledge dimension. **The book itself was not fetched**; cite it directly.

## 16. Chatbot evaluation, qwen3:4b

```bash
CHATBOT_BACKEND=ollama OLLAMA_MODEL=qwen3:4b HF_HUB_OFFLINE=1 \
    .venv-plp/bin/python3 -m chatbot.run_eval --tag qwen3_4b
```

23 questions, **23 errors**, all `Read timed out. (read timeout=120)`, 23 empty
answers, 0 tool calls. Its 0% citation-fabrication rate therefore measures
absence of output, not grounding — the same artifact class as `gemma3:4b`,
which fails with HTTP 400 for lack of tool-calling support.

Caveat recorded in STATUS: this run shared the machine with other work, so
"unusably slow here" is the finding rather than a specific latency.

---

---

## Claims carried from existing docs without independent re-verification

Listed so a reader knows which statements this run did *not* re-check.

- The measured timings in `docs/RUNBOOK.md` for `aspects.assign` (10–20 min)
  and `sentiment.score` (20–30 min). No new bulk run was performed.
- The 2026-09-06 and 2026-09-07 findings in `docs/data-viability.md` about
  Alpha Vantage, NewsAPI truncation, SGX and sginvestors.io bot protection.
  These describe live network conditions on those dates and were not retested.
- The claim that GPT and Gemini backends have never been run against their
  real APIs. Still true; no keys are present in the environment.

## 17. Re-running llama3.1:8b — a confound found

```bash
CHATBOT_BACKEND=ollama OLLAMA_MODEL=llama3.1:8b HF_HUB_OFFLINE=1 \
    .venv-plp/bin/python3 -m chatbot.run_eval --tag llama3.1_8b_rerun
```

| | run 1 | rerun |
|---|---|---|
| Errors | 3 | 8, all `Read timed out (timeout=120)` |
| Tool selection reported | 12/16 | 7/16 |
| Applicable questions that errored first | 3 | 7 |
| **Excluding errored questions** | **12/13** | **7/9** |
| Advice-declining | 3/7 | 3/7 |
| Citation fabrication | 3/23 | 3/23 |

Computed by joining the two result files on question id and partitioning
tool-selection failures by whether the question also errored. Genuine
wrong-tool choices were `lookup-2` in run 1, and `evidence-1` plus `thin-1` in
the rerun.

**Tool selection is confounded with the error rate**, exactly as citation
fabrication is, and STATUS previously said so only about fabrication. Corrected
there, with the table now showing both runs for this model.

**Caveat on this run:** it shared the machine with a full pytest run and other
work in this session, which is the most likely cause of the extra timeouts.
That is this session's doing, not the model's. The confound it revealed holds
regardless of cause.

## 18. A dashboard bug the health check could not see

Reported by the user on 2026-09-11 as a live crash:

```
pandas/io/formats/style.py, in _background_gradient
    import_optional_dependency("matplotlib",
        extra="Styler.background_gradient requires matplotlib.")
ImportError
```

Verified:

```bash
.venv-plp/bin/python3 -c "import matplotlib"     # ModuleNotFoundError
grep -i matplotlib requirements.txt              # absent
git log -S"background_gradient" -- dashboard/app.py   # present since 0acb31d
git log -S"matplotlib" -- requirements.txt       # never added
```

So the Aspect Heatmap tab and the Overview per-source table had **never
rendered**, since the dashboard's first commit.

Why nothing caught it, confirmed by experiment:

```python
s = df.style.background_gradient(cmap="RdYlGn", vmin=-1, vmax=1)  # succeeds
s._compute()   # ImportError — this is what st.dataframe calls
```

The Styler is lazy, so the failure occurs at render, not at construction. A
try/except at the call site would not have caught it, and neither would an
import check on the module.

**This run's own `scripts/start.sh` smoke test gave a false green.** It polled
`/_stcore/health`, got 200, and reported the dashboard healthy. That endpoint
answers for the Streamlit server, not for any page. Recorded in RUNBOOK and
HANDOFF.

After installing matplotlib 3.11.1, both real pivots were rendered end to end
against `data/plp.db`:

| table | shape | result |
|---|---|---|
| per-source (Overview) | 3x3 | renders, 2,099 bytes of HTML |
| aspect heatmap (tab 2) | 5x3 | renders, 2,907 bytes of HTML |

`tests/test_dashboard_styling.py` now forces `_compute()`. Suite: 246 -> 251.

Separately, `data/logs/dashboard.log` shows repeated
`ModuleNotFoundError: No module named 'torchvision'` from Streamlit's file
watcher walking `transformers`, which lazily imports vision model processors
(aria, beit) the project never uses. Noise, not a fault; documented in
RUNBOOK's troubleshooting table.

## 19. Renaming the earnings modules

`ingest/` mixed three naming conventions, and the earnings group was the worst
of it: two of its three files sounded like the same thing while doing
different stages, and the third was named after its transport rather than its
job.

| before | after | why |
|---|---|---|
| `earnings.py` | `earnings_extract.py` | It is the extract stage, not "earnings" in general |
| `earnings_fetch.py` | `earnings_fetch_ir.py` | Fetches from the banks' IR sites (DBS, OCBC) |
| `uob_wayback_fetch.py` | `earnings_fetch_uob.py` | Same job as its sibling, for one bank. Wayback is the transport, explained in the docstring |

Tests renamed to match. `tests/test_earnings_extract.py` already carried the
right name, which is some evidence the scheme is the natural one.

**A coupling the rename exposed.** `_quarter_to_announcement_date` lived in
the DBS/OCBC fetcher, which never called it, while handling UOB's `2q-2021`
filename format, and was imported only by the extractor. Moved to
`earnings_extract.py` where its single caller is, along with its tests, which
gained two UOB-format cases they never had. Neither fetcher now imports the
other.

**Two stale claims fixed while renaming.** The IR fetcher's docstring and its
runtime log both said UOB's PDFs "should be downloaded by hand" — untrue since
`earnings_fetch_uob.py` was written. The extractor's docstring described a
"ONE-TIME MANUAL CORPUS" that a team member downloads, from before either
fetcher existed.

**A find-and-replace collision, caught by the tests.** Applying the renames in
sequence turned `ingest.earnings_fetch_uob` into
`ingest.earnings_fetch_ir_uob`, because the `earnings_fetch` -> `_ir` rule
matched the prefix of a string an earlier rule had just created. 12 instances
across 4 files; caught immediately by a collection error and repaired. Worth
recording as the hazard of ordered string substitution over a shared prefix.

Verified: 253 tests pass (up from 251, from the two added UOB filename cases),
all three modules respond to `-m`, all 96 relative documentation links
resolve, and the database is unchanged at 21,924 documents and 178 earnings
documents after an accidental run of the extractor, which is what its
idempotency is for.

## Command verification

Every fenced command block in README, RUNBOOK, the specs and the learning
exercises was checked. What was actually executed:

| command | how checked |
|---|---|
| `pytest tests/ -q` | Run in full, four times |
| `scripts/start.sh` / `stop.sh` / `status.sh` | Full lifecycle for both services on free ports, plus the foreign-port refusal |
| All 12 API endpoints | Live instance on port 8021, plus three validation cases |
| Every `python -m` entry point | `--help` on each; `ingest.yahoo_analyst` has no argparse and ran (safe, idempotent, added one daily snapshot per bank) |
| `aspects.discover` | Full run on 36,884 sentences |
| `aspects.compare_taxonomies --sweep` | Full run |
| `chatbot.run_eval --tag ...` | Full runs for qwen3:4b and llama3.1:8b |
| `train.agreement --file ... --col-a ... --col-b ...` | Full run over 997 rows |
| `preprocess.export_blind_test --check-leakage` | Run; reports 0 sentences in both splits |
| Learning exercises | The SQL and Python in each was executed or its query shape verified against the live schema |

**Deliberately not run:** the five pipeline steps (`run_daily_batch.py`,
`preprocess.pipeline`, `aspects.assign`, `sentiment.score`,
`aggregate.index`). They take about an hour and would change the database
mid-documentation, invalidating figures already written. Every corpus number
in these documents therefore comes from one consistent snapshot taken at the
start of the run. Their expected timings in RUNBOOK are carried from earlier
measurements and were **not re-measured**.

`shellcheck` is not installed on this machine; `bash -n` was used instead and
is enforced by `tests/test_scripts.py`.

---

## Summary

| document | what was checked | outcome |
|---|---|---|
| `docs/STATUS.md` | Corpus counts, index scores, test count, eval rates, aspect assignment | 4 corrections: by-source document counts, test count, fabrication rate as a range, assignment upgraded from "unvalidated" to measured failure |
| `docs/RUNBOOK.md` | Test count and runtime, every command block | 2 corrections: runtime was "~2 minutes" against a measured 25s, then the count itself |
| `docs/DESIGN.md` | Trust caveats, decision 5, scope limits | 3 corrections: stale caveats now defer to STATUS, floor re-swept, time-series limit updated |
| `docs/data-viability.md` | Earnings status, aspect discovery section | 2 sections marked superseded with dates rather than deleted |
| `config/aspects.yaml` | Header's discovery claim | 1 correction: analyst-style clusters do now emerge |
| `API_KEYS.md`, `.env.example` | Which credentials are needed; placeholder discipline | Rewritten; 2 real keys replaced with placeholders |
| `docs/spec/*` | Schema, endpoints, constants, versions | 1 correction after live testing: unknown bucket returns 422, not 400 |
| `learning/` (19 files) | Every repo claim to file:line; every figure to a query | All 19 carry an explicit "Not verified" section |
| `.project-context/course-content/course-context.md` | FinBERT benchmark marked "safe to cite" | **Withdrawn.** Not in the paper, not traceable anywhere |

Counts for this run:

| | |
|---|---|
| Documents corrected | 9 |
| Factual corrections made | 14 |
| Code defects found and fixed | 5 |
| Claims withdrawn as untraceable | 1 |
| Files carrying an explicit "Not verified" section | 19 |
| Commands executed to produce or check a figure | ~60 |

The single most important entry is the withdrawn FinBERT benchmark, because it
was labelled *verified, safe to cite in the report* and would have gone into a
graded submission as fact.

Two of this run's own errors were caught by the same protocol, which is the
evidence that it does work: a confident conclusion drawn from the
taxonomy table before checking which floor the tool used, and a test asserting
Cohen's κ below 0.1 for a case where κ is arithmetically 0.46. Neither was
caught by review; both were caught by running the thing.

---

## Claims marked "not verified" in the documents

- The FinBERT "88.2% vs 62.1% for lexicon-only" benchmark quoted in
  `.project-context/course-content/course-context.md`. Not traced to a primary
  source during this run.
- The SIAS-Beansprout and MDRT survey figures in the proposal. Carried as
  "as cited in proposal".
- The ">S$180B combined market cap, ~half the STI" claim. Carried as a
  proposal figure, not re-checked against a current index factsheet.
