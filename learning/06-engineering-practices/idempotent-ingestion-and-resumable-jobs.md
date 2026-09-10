# Idempotent ingestion and resumable jobs

Subject: Engineering practices · Bloom target: Analyze / Evaluate / Create
Prerequisites: none

---

## 1. Why it matters here (Understand)

The proposal promises an index "recomputed after each batch cycle". That
sentence has an engineering consequence people underestimate: **the pipeline
must be safe to run repeatedly.** If running ingestion twice doubles the
corpus, every sentiment score becomes a function of how many times someone ran
a script.

Separately, the jobs here are long. A multi-year Reddit backfill runs for
hours. Machines sleep, terminals close, network calls fail. A job that loses
everything on interruption is a job that never finishes.

This project learned both lessons by getting them wrong first, which makes it
unusually good teaching material.

---

## 2. The concept (Understand / Apply)

### Idempotence

An operation is idempotent if running it twice has the same effect as running
it once. For ingestion this needs two things:

**A deterministic identifier.** `doc_id` is a hash of the source plus the
item's native ID. The same Reddit comment always produces the same `doc_id`,
on any machine, on any run.

**A conflict-tolerant write.** `INSERT OR IGNORE` — if the `doc_id` is already
present, do nothing.

Together, re-running any adapter is a no-op rather than a duplicate.

The same idea recurs downstream as "process only new work":

| step | what makes it incremental |
|---|---|
| `preprocess.pipeline` | Reads documents whose `doc_id` does not appear in `sentences` |
| `aspects.assign` | Skips sentences already assigned |
| `sentiment.score` | Skips pairs already scored at this `model_version` |
| `aggregate.index` | Full recompute — it is 2 seconds |

Note the last row. Idempotence does not require incrementality. When an
operation is cheap, recomputing everything is simpler and less likely to go
subtly stale.

### Resumability

Idempotence makes re-running *safe*. Resumability makes it *cheap* — the job
skips what it already did rather than redoing it.

Two mechanisms are used here:

| mechanism | where | granularity |
|---|---|---|
| Marker file of completed chunks | `scripts/overnight_backfill.py` | One month of Reddit |
| Append-only JSONL progress log | `train/llm_prelabel.py` | One row |

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| Deterministic `doc_id`, `INSERT OR IGNORE` | `ingest/db.py` |
| Chunked, resumable backfill | `scripts/overnight_backfill.py` |
| Checkpointed pre-labelling | `train/llm_prelabel.py` |
| Retry with backoff | `ingest/base.py`, `request_with_retries` |
| Idempotency tests | `tests/test_db_idempotency.py` |
| Service PID files and health checks | `scripts/start.sh` |

---

## 4. Analyze

### Three real failures, and what each taught

**1. The backfill that saved nothing.**

`run_daily_batch.py --reddit-since 2020-01-01` looks like it does the same
thing as the chunked script. It does not.
`ingest/arctic_shift.py`'s `pull()` accumulates every document in memory and
calls `upsert_documents()` exactly **once, at the end**. A multi-year harvest
runs for hours and commits nothing until it finishes. This was caught when a
run sat at 34 minutes elapsed with zero new rows in the database.

The fix is architectural rather than a patch: `scripts/overnight_backfill.py`
invokes `python -m ingest.arctic_shift` as a **separate process per
month-sized chunk**, and each chunk's own `__main__` commits immediately. An
interruption now loses at most one month.

*The lesson:* a long job's commit boundary is a design decision, not an
implementation detail. Ask where the durable write happens before leaving
anything running overnight.

**2. The overnight run lost to the wrong Python.**

A scheduled backfill was launched under miniforge's Python 3.9 instead of the
project's 3.14, almost certainly because a conda auto-activation in a shell
profile ran *after* `source .venv-plp/bin/activate` and silently took over
`python3`. This codebase uses `X | None` syntax throughout, which 3.9 cannot
parse, so **every module failed at import**. All 79 chunks failed identically
and the night produced nothing.

Two fixes, and the second is the interesting one. `overnight_backfill.py` now
fails immediately with a clear diagnosis. And the documented instruction
everywhere became: invoke `.venv-plp/bin/python3` by absolute path, never rely
on shell activation.

*The lesson:* a job that fails 79 times identically has an environment
problem, and the cheapest possible guard — assert your assumptions in the
first five lines — would have turned eight wasted hours into one clear error.
`scripts/start.sh` inherits the same check for the same reason.

**3. Pre-labelling with no checkpoint.**

An unattended pre-labelling run was lost in full because it had no
checkpointing. `train/llm_prelabel.py` now appends every result to a JSONL
progress file *immediately*, with `flush()` and `os.fsync()` so a hard kill
does not lose the buffer, and re-running skips every (sentence_id, aspect)
pair already recorded.

*The lesson:* `fsync` is the difference between surviving a clean exit and
surviving a `kill -9`. For a job measured in hours, that distinction is worth
the cost.

### Comparing four durability designs

| design | interruption cost | complexity | example here |
|---|---|---|---|
| Commit once at the end | **Everything** | Lowest | `pull()` — the bug |
| Commit per chunk, marker file | One chunk | Low | `overnight_backfill.py` |
| Commit per item, append-only log with fsync | One item | Moderate | `llm_prelabel.py` |
| Transactional queue with retries | One item, plus automatic retry | High | Not used, not warranted |

The project sits at rows 2 and 3, chosen by job shape. The backfill's unit is
naturally a month because the API is queried by date window. Pre-labelling's
unit is naturally a row because each row is one independent model call.

Row 4 would be over-engineering for a single-machine batch pipeline that a
person launches by hand.

### Idempotence has a subtle failure mode

`doc_id` is deterministic, so the *same* document is never inserted twice. But
if a source changes an item's content while keeping its ID — an edited Reddit
comment, a corrected PDF republished at the same URL — `INSERT OR IGNORE`
keeps the **old** version silently.

That is the correct trade for this project: stability matters more than
freshness for a research corpus, and a changing corpus would make results
irreproducible. It is worth knowing the choice was made, because it is
invisible in the code — nothing says "we prefer stale".

---

## 5. Evaluate

**Was idempotent ingestion the right foundation?** Unarguably. The proposal's
batch-recompute model requires it, and the alternative is a corpus whose size
depends on operator behaviour.

**Was the chunked-process design right?** Yes, and it is a good example of
fixing a problem at the right level. The tempting fix — make `pull()` commit
periodically — would have worked and would have required understanding and
modifying the accumulation logic. Running each chunk as a separate process
that already commits correctly reuses existing, tested behaviour and gets
crash isolation for free.

**What the evidence does not show.** Nothing here has been tested against
adversarial interruption. `tests/test_db_idempotency.py` covers re-running an
adapter; nobody has killed a backfill mid-chunk and verified the marker file
and database agree afterwards. The design is sound and the recovery path is
untested.

**The pattern across all three failures.** Every one produced **silence**
rather than an error: a job running with nothing committed, 79 identical
failures nobody was watching, a killed process with no record. Long unattended
jobs fail quietly by nature, which is why the project also added a rotating
log file that captures DEBUG regardless of console level.

**When you would not bother.** For a job that finishes in a minute,
checkpointing is pure cost — re-run it. These techniques earn their place at
the point where re-running is expensive enough that losing progress hurts.

---

## 6. Create

**Exercise (about an hour).** Test the recovery path nobody has tested.

```bash
# Work on a COPY. Never do this to data/plp.db.
cp data/plp.db /tmp/plp_test.db
cp data/.backfill_progress.txt /tmp/progress_backup.txt

# 1. Confirm idempotence directly: how many documents before and after
#    re-running an adapter over a window already ingested?
.venv-plp/bin/python3 -c "
import sqlite3; print('before:', sqlite3.connect('data/plp.db').execute(
    'SELECT COUNT(*) FROM documents').fetchone()[0])"

.venv-plp/bin/python3 -m ingest.arctic_shift --since 2026-08-01 --until 2026-08-08

.venv-plp/bin/python3 -c "
import sqlite3; print('after: ', sqlite3.connect('data/plp.db').execute(
    'SELECT COUNT(*) FROM documents').fetchone()[0])"
```

The two counts should be identical, or differ only by genuinely new items if
that window was not fully ingested.

**Then test resumability properly.** Start the backfill over a short range,
kill it mid-chunk with Ctrl-C, and check three things: does the marker file
contain only *completed* chunks, does the database contain the completed
chunks' data, and does re-running skip them and resume cleanly?

```bash
caffeinate -i .venv-plp/bin/python3 scripts/overnight_backfill.py \
    --since 2026-06-01 --until 2026-09-01
# Ctrl-C partway through
cat data/.backfill_progress.txt
# then re-run the same command and watch for SKIP lines
```

**Expected outcome.** The marker file should not contain the interrupted
chunk, and re-running should skip completed chunks and redo only the
interrupted one. If a partially-completed chunk *is* marked done, you have
found a real bug and it is worth a commit.

---

## 7. Self-check

1. What two things make ingestion idempotent here?
2. Why does `aggregate.index` recompute everything while `sentiment.score`
   skips completed work?
3. Why did `run_daily_batch.py --reddit-since 2020-01-01` lose hours of work,
   and what fixed it?
4. Why does `llm_prelabel.py` call `os.fsync()` rather than relying on a
   normal file close?
5. A Reddit comment is edited after ingestion. What happens, and is that
   right?

<details>
<summary>Answers</summary>

1. A deterministic `doc_id` hashed from source plus native ID, and
   `INSERT OR IGNORE` so a repeat insert does nothing.
2. Because `aggregate.index` takes about 2 seconds, so a full recompute is
   simpler and cannot go subtly stale, whereas scoring 18,000 pairs takes
   20–30 minutes and redoing completed work would be wasteful.
3. `pull()` accumulated every document in memory and committed once at the
   very end, so a multi-hour harvest wrote nothing until it finished. The fix
   was to run each month as a separate process that commits on completion, so
   an interruption loses at most one chunk.
4. Because a normal close survives a clean exit but not a `kill -9` or a power
   loss, which leaves buffered writes unwritten. `fsync` forces them to disk,
   which is what makes the progress file trustworthy after a hard kill.
5. `INSERT OR IGNORE` keeps the original version, because the `doc_id` is
   unchanged. That is the right trade here: a stable corpus makes results
   reproducible, and a corpus that silently changed underneath the index would
   not.

</details>

---

## 8. Sources

**Repository**

- `ingest/db.py` — deterministic `doc_id`, `INSERT OR IGNORE`
- `scripts/overnight_backfill.py` — the module docstring documents both the
  commit-boundary bug and the wrong-interpreter incident in detail
- `train/llm_prelabel.py` — checkpointing, `flush()` and `fsync()`, and the
  lost run that prompted them
- `tests/test_db_idempotency.py`
- `docs/RUNBOOK.md` — the interpreter table and the backfill instructions
- `docs/DESIGN.md` — "Idempotent ingestion"

**Not verified**

- The recovery path after a mid-chunk interruption has never been tested. The
  exercise in section 6 exists to test it.
- The claim that conda auto-activation caused the wrong-interpreter incident
  is the diagnosis recorded in `scripts/overnight_backfill.py` and is
  described there as "almost certainly", not confirmed.
