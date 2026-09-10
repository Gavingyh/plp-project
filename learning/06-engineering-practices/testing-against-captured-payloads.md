# Testing against captured payloads

Subject: Engineering practices · Bloom target: Analyze / Evaluate / Create
Prerequisites: none

---

## 1. Why it matters here (Understand)

This project's code is mostly glue between external services and a database.
That is the hardest kind of code to test, because the interesting behaviour is
"what happens when NewsAPI returns *this*", and NewsAPI is not going to return
this on demand.

The stakes are specific. Several bugs in this project's history caused
**silence** rather than errors: a pipeline that ran and stored nothing, a
script that failed 79 times identically, an extractor that returned an empty
list for every input. Tests are the only thing that catches a function whose
failure mode is producing nothing.

---

## 2. The concept (Understand / Apply)

### The rule

**246 tests, no network calls.** External APIs are mocked with *captured real
payloads*, so a provider changing its response shape surfaces as a failing
test rather than a silent production break.

The important word is *captured*. There are two ways to mock an API:

| approach | what it proves | what it misses |
|---|---|---|
| Hand-written fixture | Your parser handles the shape you imagined | Everything about the real shape |
| **Captured real payload** | Your parser handles what the API actually sent | Changes since capture — which is the point, since the test then fails |

A hand-written fixture tests your assumptions against themselves.

### Why no network in tests

| reason | consequence if violated |
|---|---|
| Determinism | A test that passes or fails by network weather teaches nothing |
| Speed | 246 tests in a minute or two; network calls would make that far worse |
| Rate limits | NewsAPI's free tier allows 100 requests a day |
| Courtesy | archive.org is a donated service |
| Offline work | Tests run on a train |

### The `temp_db` fixture

`tests/conftest.py` redirects `ingest.db.DB_PATH` to a throwaway file per test
and creates every table, including the three normally created lazily by
`aspects/assign.py`, `sentiment/score.py` and `aggregate/index.py`.

So tests never touch `data/plp.db`, and they cannot interfere with each other
through shared state. Given the live database holds hours of pipeline output,
this is not a nicety.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| `temp_db` fixture | `tests/conftest.py` |
| Idempotency | `tests/test_db_idempotency.py` |
| API contract and validation | `tests/test_api.py` |
| Chatbot backends and tools | `tests/test_chatbot_backends.py`, `tests/test_chatbot_tools.py` |
| Fine-tune pipeline smoke test | `tests/test_finetune_smoke.py` |
| Regressions with a documented cause | `tests/test_earnings_extract.py`, `tests/test_aspect_discover.py`, `tests/test_scripts.py` |
| `HF_HUB_OFFLINE=1` set for the whole suite | `tests/conftest.py` |

---

## 4. Analyze

### Four tests that exist because of four real bugs

The most instructive tests here are the ones whose docstrings say what broke.

**1. Earnings extraction returned nothing, silently.**
`extract_prose` called `text.split("")` — an empty separator, which raises
`ValueError` on every page of every PDF. `pull()` catches per-file exceptions
and continues, so the earnings source degraded to zero documents *while
exiting successfully*. The corpus already held earnings sentences from an
earlier working run, so nothing downstream looked wrong either.

`tests/test_earnings_extract.py` states the lesson in its own docstring: **a
function whose failure mode is "silently returns nothing" needs a test that
asserts it returns something.**

**2. Aspect discovery died above 32,766 sentences.**
`run()` bound one SQL parameter per cached embedding, and SQLite caps that at
32,766. The script was fine on the 2,888-sentence corpus it was developed
against and became unrunnable exactly when the corpus grew large enough for
clustering to be worth doing.

`tests/test_aspect_discover.py` exercises the lookup at 33,000 rows, and is
parametrised with a small case too, so a failure says whether the lookup is
broken generally or only past the ceiling. **A size-dependent query needs a
test that exercises it above the size limit.**

**3. The fine-tune pipeline had two bugs nobody could see.**
`train/finetune.py` cannot run for real — it needs labelled data that does not
exist. A smoke test with synthetic labels found two genuine bugs in code that
had never executed.

**4. A start script could have killed an unrelated process.**
`scripts/start.sh` refuses a port it does not own. `tests/test_scripts.py`
binds a port and asserts the script declines it. This is the only test here
guarding against a *destructive* mistake rather than a wrong result.

### The pattern across all four

None of them tests a feature. Each defends a **property**: produces output,
scales past a limit, executes at all, does not destroy someone else's work.

That is what makes them worth their runtime. A test asserting
`get_sentiment("DBS")` returns a number is fine and would not have caught any
of the four.

### The cost, measured

| suite | tests | runtime |
|---|---|---|
| Before the discovery tests | 214 | 25 s |
| After | 217 | 59 s |
| After the script and agreement tests | 246 | 106 s (under load) |

The discovery tests roughly doubled the runtime, and almost none of that is
the tests themselves — they run in about one second. It is `umap` and
`hdbscan` importing, which triggers numba compilation.

That is a real trade. Thirty-five seconds on every run, forever, to guard one
bug class. It is worth it here because the bug it guards made a tool silently
unrunnable for days, and because a minute is still fast enough that nobody
skips the suite. At five minutes the calculus would change and the test would
belong behind a marker.

### Comparing four strategies for external dependencies

| strategy | fidelity | speed | catches API changes? |
|---|---|---|---|
| Live API calls | Highest | Slowest | Yes, and fails randomly |
| **Captured payloads** (used) | High at capture time | Fast | **Yes — as a failing test** |
| Hand-written fixtures | Low | Fast | No |
| Record/replay (VCR-style) | High | Fast | Yes, with cassette management |

Row 4 is the more sophisticated version of row 2 and would add a dependency
and a cassette-expiry problem. For a handful of adapters, captured payloads
checked into the tests are simpler and do the same job.

The honest weakness of row 2 is that a captured payload is a snapshot. If
NewsAPI changed its response shape tomorrow, the tests would keep passing
against the old capture until someone re-captured. The tests detect that your
*parser* still handles the *captured* shape, not that the API still sends it.
Nothing here periodically re-validates against the live API, and for a project
of this lifespan that is an acceptable gap worth naming.

---

## 5. Evaluate

**Is the testing approach right?** Yes. No-network is correct for this project
— determinism, rate limits, and courtesy to a donated archive all point the
same way — and captured payloads are the right fidelity compromise.

**Is 246 tests enough?** For the code paths that exist, roughly. The
significant gaps are not code paths but *properties nobody asserts*:

- Segmentation correctness has no gold set.
- Aspect assignment correctness has no test, which is how the Reddit failure
  went unnoticed until someone read the rows by hand.
- Retrieval relevance has no judgements.
- The backfill's mid-chunk recovery path has never been exercised.

Each of those needs labelled data or human judgement rather than more mocking,
which is why they are absent. Naming them is more useful than pretending 246
passing tests means the system is correct.

**What the suite does not tell you.** That the numbers are right. It tells you
the code does what it did when the tests were written. Every one of the four
bugs above was found by a *person* noticing something odd, and the test was
written afterwards to keep it fixed. The suite is a ratchet, not a detector.

**When the trade would change.** If the suite reached several minutes, people
would stop running it before committing and its value would collapse. Runtime
is a feature of a test suite, which is why the 35-second umap cost was worth
measuring rather than waving through.

---

## 6. Create

**Exercise (about an hour).** Write a test for a property nobody asserts.

Pick the pipeline's most important invariant: **every scored sentence has a
`sentence_id` that exists in `sentences`, and every sentence has a
`published_at` that parses.** Nothing checks either.

```python
# tests/test_pipeline_invariants.py
import pytest
from datetime import datetime

def test_scored_pairs_reference_real_sentences(temp_db):
    """An aspect_sentiment row whose sentence_id has no sentence is an
    orphan: the chatbot would cite an ID it cannot resolve."""
    conn = temp_db.get_connection()
    conn.execute(
        "INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, "
        "source, url, norm_hash, processed_at) VALUES "
        "('s1','d1','DBS','Net interest margin fell.', '2026-01-01T00:00:00+00:00',"
        " 'earnings','https://x','h1','2026-01-01T00:00:00+00:00')")
    conn.execute(
        "INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, "
        "model_version, scored_at) VALUES "
        "('s1','net_interest_margin','negative',0.9,'v1','2026-01-01T00:00:00+00:00')")
    conn.commit()

    orphans = conn.execute("""
        SELECT COUNT(*) FROM aspect_sentiment a
        LEFT JOIN sentences s ON s.sentence_id = a.sentence_id
        WHERE s.sentence_id IS NULL
    """).fetchone()[0]
    conn.close()
    assert orphans == 0
```

Then run the same check against the **live** database, as a script rather than
a test:

```python
import sqlite3
c = sqlite3.connect("data/plp.db")
print("orphan scored pairs:", c.execute("""
    SELECT COUNT(*) FROM aspect_sentiment a
    LEFT JOIN sentences s ON s.sentence_id = a.sentence_id
    WHERE s.sentence_id IS NULL""").fetchone()[0])
print("unparseable dates:", c.execute("""
    SELECT COUNT(*) FROM sentences
    WHERE published_at IS NULL OR length(published_at) < 10""").fetchone()[0])
```

**Expected outcome.** All of them are zero — this was run against
`data/plp.db` on 2026-09-11:

| invariant | result |
|---|---|
| Scored pairs with no matching sentence | 0 |
| Sentences with no matching document | 0 |
| Sentences with a missing or malformed `published_at` | 0 |
| Assigned aspects never scored | 0 |

So the exercise is not bug-hunting; it is converting four properties that
currently hold *by luck of correct code* into properties that **stay** holding.
Nothing in the suite asserts any of them today, so a future change to the
pipeline's incremental logic could break one silently — which is exactly the
failure class every other test in this file was written after the fact to
catch.

---

## 7. Self-check

1. Why are captured payloads better than hand-written fixtures?
2. Give three reasons the test suite makes no network calls.
3. What is the lesson `tests/test_earnings_extract.py` states in its own
   docstring?
4. Why is `tests/test_aspect_discover.py` parametrised with both 10 rows and
   33,000?
5. What does a passing suite here *not* tell you?

<details>
<summary>Answers</summary>

1. Because a hand-written fixture encodes what you imagined the API returns,
   so it tests your assumptions against themselves. A captured payload is what
   the API actually sent, so if the provider changes shape the test fails
   instead of passing against a fiction.
2. Determinism (no failures from network weather), speed (about 60 seconds
   rather than minutes), rate limits (NewsAPI allows 100 requests a day),
   courtesy to donated services like archive.org, and the ability to work
   offline.
3. That a function whose failure mode is "silently returns nothing" needs a
   test asserting it returns something. `extract_prose` raised on every input
   while the caller swallowed the exception, so the source degraded to zero
   documents while exiting successfully.
4. So a failure tells you which bug you have. The 33,000-row case exercises the
   SQLite parameter ceiling that caused the original crash; the 10-row case
   confirms the lookup works at all. Without both, a failure is ambiguous.
5. That the system produces correct numbers. It tells you the code still does
   what it did when the tests were written. All four documented bugs were
   found by a person noticing something odd; the tests were written afterwards
   to keep them fixed.

</details>

---

## 8. Sources

**Repository**

- `tests/conftest.py` — `temp_db`, `HF_HUB_OFFLINE`
- `tests/test_earnings_extract.py` — the silent-failure lesson
- `tests/test_aspect_discover.py` — the SQLite ceiling
- `tests/test_finetune_smoke.py` — two bugs in never-executed code
- `tests/test_scripts.py` — the port-refusal guard
- `docs/RUNBOOK.md` — the suite's runtime and no-network claim
- `docs/verification-ledger.md` — measured test counts and timings

**Measured in this repository (2026-09-11)**

- 214 tests in 25 s before this branch's additions; 246 in 106 s after (that
  final run shared the machine with a model evaluation).
  The roughly 35-second increase is `umap`/`hdbscan` import cost, measured by
  running the discovery tests alone.

**Not verified**

- Whether the captured payloads still match what each provider currently
  returns. Nothing re-validates them against the live APIs, so they are
  accurate as at their capture date and no later.
- The four pipeline invariants in section 6 were checked against
  `data/plp.db` on 2026-09-11 and all hold. Nothing in the test suite asserts
  them, so they are currently properties of correct code rather than
  guaranteed ones.
