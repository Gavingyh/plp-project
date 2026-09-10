# Verification ledger

Every number and claim added to the documentation on 2026-09-11, with the
command that produced it. The rule this run worked under: a figure that
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

`grep -rhE '^\s*def test_' tests/ | wc -l` gives 200 function definitions.
The gap to 214 is `@pytest.mark.parametrize` in
`tests/test_earnings_fetch.py`, `tests/test_logging_config.py` and
`tests/test_uob_wayback_fetch.py`, confirmed with
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

## 5. `ingest/earnings.py` prose extraction

```bash
git show HEAD:ingest/earnings.py | sed -n '60p' | od -c
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

## Claims marked "not verified" in the documents

- The FinBERT "88.2% vs 62.1% for lexicon-only" benchmark quoted in
  `.project-context/course-content/course-context.md`. Not traced to a primary
  source during this run.
- The SIAS-Beansprout and MDRT survey figures in the proposal. Carried as
  "as cited in proposal".
- The ">S$180B combined market cap, ~half the STI" claim. Carried as a
  proposal figure, not re-checked against a current index factsheet.
