# Data access ethics: WAFs, archives and unofficial APIs

Subject: Engineering practices · Bloom target: Analyze / Evaluate / Create
Prerequisites: none

---

## 1. Why it matters here (Understand)

This project makes three access decisions that a marker could reasonably
challenge, and each one has a defensible answer only because it was thought
about in advance rather than justified afterwards:

- UOB's site refuses scripted requests, and the project fetched its documents
  from an archive instead.
- Yahoo Finance's consensus endpoint is unofficial and has a handshake
  designed to slow automation.
- Reddit declined the project's API application, and ingestion proceeded
  through a public archive.

None of these is obviously wrong. None is obviously fine either. The report
needs to say what was decided and why, and "the data was public" is not on its
own an argument.

---

## 2. The concept (Understand / Apply)

Four questions worth separating, because conflating them is where bad
reasoning starts:

| question | about |
|---|---|
| **Is it technically possible?** | Engineering |
| **Is it permitted?** | Terms of service, robots.txt, the law |
| **Is the operator signalling refusal?** | A WAF, a CAPTCHA, a rejected application |
| **Does it impose a cost on someone?** | Rate limits, donated infrastructure |

"Technically possible" answers none of the others. A WAF challenge is a
machine-readable statement that the operator does not want scripted access,
whatever robots.txt says.

### The specific mechanisms here

**A WAF** (web application firewall) sits in front of a site and filters
requests. UOB's answers scripted requests with a 199-byte challenge stub
containing `Request Redirected` and `TS.request.ID`, an F5 product signature.
Defeating it would mean spoofing browser fingerprints — TLS characteristics,
header ordering, JavaScript execution — which is deliberate circumvention
rather than incidental access.

**The Wayback Machine** is a public archive operated by the Internet Archive
that stores copies of public web pages at their original URLs. It is a
donated public service, and it rate-limits under load.

**An unofficial API** is an endpoint a site uses internally that is not
documented or supported for third parties. Yahoo's `quoteSummary` is the one
the widely-used `yfinance` library wraps. It requires a cookie-and-crumb
handshake that exists specifically to slow automated access.

---

## 3. Where it lives in this repo (Apply)

| decision | where | disclosed in |
|---|---|---|
| UOB via Wayback rather than defeating the WAF | `ingest/uob_wayback_fetch.py` | `docs/DESIGN.md` decision 3, RUNBOOK |
| Yahoo consensus as an unofficial API | `ingest/yahoo_analyst.py` | Module docstring, dashboard, API response |
| Reddit via Arctic Shift after the API was declined | `ingest/arctic_shift.py` | `docs/DESIGN.md` decision 2 |
| SGX and sginvestors.io not scraped | — | `docs/data-viability.md` |
| Backoff and retry against archive.org | `ingest/base.py`, `request_with_retries` | RUNBOOK |

---

## 4. Analyze

### The UOB decision, argued both ways

**The case that it is fine.** The bytes are UOB's own published PDFs, made
public by UOB on its own website for investors to read. The Wayback Machine
archived them at their original URLs, and reading a public archive is
ordinary. The WAF blocks a *transport*, not a *disclosure* — nothing being
accessed was ever confidential. And the alternative was a coverage gap that
invalidated every cross-bank comparison in the project.

**The case against.** The operator installed a control that says "not to
scripted clients". Routing around it obtains through a third party what was
refused directly. Consent to publication is not consent to bulk automated
collection, and choosing a different door does not change what was asked.

**Where the project landed, and why it holds up.** The decision was not "the
archive makes it fine". It was: *do not escalate.* Fingerprint spoofing to
defeat the WAF was explicitly rejected as disproportionate. Reading a public
archive is a lesser act than actively impersonating a browser, and the
distinction is real — one respects the signal by not fighting it, the other
overrides it.

Two things make it more defensible still. It is disclosed prominently in three
places rather than buried. And the residual concern is stated: archive
coverage thins for recent quarters, which is an honest limitation rather than
a silently patched hole.

**What would change the answer.** If the documents were paywalled, or the
archive copies were themselves obtained in breach, or the project were
commercial rather than academic, this would look different.

### The load question, which is separate

archive.org is donated infrastructure. The fetcher backs off and retries, and
the runbook says explicitly not to run it in a loop.

This is a distinct obligation from permission. Even entirely permitted access
can be inconsiderate at volume, and a free public service absorbing scraping
load from a student project is a real cost to a real organisation. Roughly 67
PDFs fetched once, with backoff, is proportionate.

### Yahoo, and the naming discipline

The interesting part of the Yahoo decision is not whether to use it. It is
what to call the result.

`ingest/yahoo_analyst.py` is emphatic: this provides consensus **aggregates**
(how many analysts, what average target), **not** the reasoning inside any
analyst report, and the writeup must not describe it as "analyst reports".

That matters because the proposal promised analyst reports as a data stream.
Delivering consensus aggregates and calling them analyst reports would
misrepresent the deliverable — a much more serious problem than any access
question here, because it would mislead the reader about what the system does.

### Comparing five access routes

| route | permitted? | operator refusing? | cost to others | used? |
|---|---|---|---|---|
| Bank IR sites (DBS, OCBC) | Yes, public pages | No | Negligible | Yes |
| Wayback Machine (UOB) | Yes, public archive | Indirectly — UOB blocks direct access | Donated service, rate-limited | Yes, with backoff |
| Arctic Shift (Reddit) | Yes, public research archive | Reddit declined the API application | Free service | Yes |
| Yahoo `quoteSummary` | Unclear. Undocumented, no blessing | Handshake slows automation | Commercial operator | Yes, disclosed |
| Defeating UOB's WAF | Almost certainly not | **Explicitly** | — | **No** |

The Reddit row deserves a note. The API application was *declined*, which is
an explicit refusal, and the project then used a third-party archive. The
argument that it is acceptable is that Arctic Shift is an independent public
research archive in the Pushshift lineage, not a channel Reddit refused, and
that the refusal was of API access rather than of research use. It is the
weakest of the four accepted rows and the report should not skip past it.

---

## 5. Evaluate

**For an academic project with disclosure these were the right calls**, and the
reasoning is more defensible than the outcomes. The line drawn —
*use public archives, do not circumvent active controls* — is coherent,
applied consistently, and was applied before the fact.

**What the project got right procedurally.** Every decision is documented at
the point of use, with the reasoning and the residual concern. The Yahoo
module warns against mislabelling its own output. That is unusual and it is
what makes the decisions inspectable, not just defensible.

**Where it is weakest.** The Reddit route. "Our API application was declined,
so we used an archive of the same content" needs a better answer than the
project currently gives. The strongest available version is that Arctic Shift
is an independent public archive used widely in research, and that the
declined application was for API access rather than a prohibition on studying
public posts. That should be stated explicitly rather than left implicit.

**What none of this establishes.** No lawyer looked at any of it. Terms of
service were not read in full for Reddit, Yahoo or archive.org. The reasoning
here is about proportionality and disclosure, which is the right frame for an
academic project, and it is not a legal opinion. The report should say so.

**When the answer changes.** Commercial use changes all of it. So does scale:
67 PDFs once is not 67,000 daily. So does personal data — this project stores
public post text with source URLs and does not build user profiles, which
keeps it well clear of the harder questions.

---

## 6. Create

**Exercise (about an hour).** Write the report's data-ethics paragraph, and
check the project's own claims first.

```bash
# What does UOB's site actually return to a scripted client?
curl -s -o /tmp/uob.html -w "status %{http_code}  bytes %{size_download}\n" \
  "https://www.uobgroup.com/investor-relations/financial-information/index.page"
head -c 400 /tmp/uob.html; echo

# What does the same client get from the archive?
curl -s -o /dev/null -w "wayback status %{http_code}\n" \
  "http://archive.org/wayback/available?url=uobgroup.com"

# And what the project's own dry run reports
.venv-plp/bin/python3 -m ingest.uob_wayback_fetch --dry-run 2>&1 | tail -20
```

Be considerate: run each once, not in a loop.

**Expected outcome.** UOB should return a small challenge stub rather than a
page, which is the documented WAF behaviour and confirms the premise of the
whole decision. The dry run should print per-year capture counts, showing the
thinning coverage for recent quarters.

**Then write 150–250 words** for the report covering: what was accessed, by
what route, what the operator's signal was, what was deliberately not done,
and what the residual limitation is. Include the sentence about Yahoo
consensus not being analyst reports. That paragraph is a deliverable in
itself, and writing it from verified behaviour rather than from memory is the
point of the exercise.

---

## 7. Self-check

1. Why is "the data is public" insufficient to justify automated collection?
2. What does a WAF challenge communicate that robots.txt might not?
3. Why is fetching from the Wayback Machine treated as different from
   defeating the WAF, given both obtain the same bytes?
4. Why must Yahoo's consensus data not be called "analyst reports"?
5. Which of the project's four accepted access routes is hardest to defend?

<details>
<summary>Answers</summary>

1. Because publication is consent to being read, not necessarily to bulk
   automated collection, and it says nothing about the load imposed or about
   an operator's explicit refusal. Permission, refusal signals and cost to
   others are separate questions.
2. It is an active, machine-readable refusal aimed at scripted clients
   specifically. robots.txt is a passive convention that may be stale or
   unmaintained; a WAF is a deployed control someone chose to run.
3. Because the archive route does not fight the control — it reads a copy a
   third party already made of a public page. Defeating the WAF means actively
   impersonating a browser to override a refusal. The bytes are the same; the
   act is not.
4. Because it supplies aggregates — analyst counts, mean ratings, price
   targets — not the reasoning inside any report. The proposal promised
   analyst reports as a stream, so calling aggregates by that name would
   misrepresent what was delivered.
5. Reddit. The project's API application was explicitly declined and
   ingestion proceeded through a third-party archive of the same content. The
   defence is that Arctic Shift is an independent public research archive and
   the refusal was of API access rather than of studying public posts, but
   that argument should be made explicitly rather than assumed.

</details>

---

## 8. Sources

**Repository**

- `ingest/uob_wayback_fetch.py` — the WAF signature and the archive rationale
- `ingest/yahoo_analyst.py` — the unofficial-API caveat and the naming warning
- `ingest/arctic_shift.py` — why PRAW was unavailable
- `ingest/base.py` — `request_with_retries`, the backoff
- `docs/DESIGN.md` decisions 2, 3 and 7
- `docs/data-viability.md` — the live tests against sgx.com and sginvestors.io
- `docs/RUNBOOK.md` — the instruction not to loop archive.org

**Measured in this repository**

- The 199-byte challenge stub, `Request Redirected` and `TS.request.ID`
  markers, recorded in `ingest/uob_wayback_fetch.py` and `docs/RUNBOOK.md`
  from live testing on 2026-09-10. **Not re-tested during this pass** — the
  exercise in section 6 re-checks it.

**Not verified**

- **No terms of service were read in full** for Reddit, Yahoo Finance or
  archive.org during this pass. The reasoning here is about proportionality
  and disclosure, not legal compliance, and no legal advice was taken.
- That F5 is the WAF vendor. Inferred from the `TS.request.ID` cookie name,
  which is characteristic of F5 BIG-IP ASM, and **not confirmed** with UOB or
  by fingerprinting.
- Whether Arctic Shift's own terms permit this use. Not checked.
