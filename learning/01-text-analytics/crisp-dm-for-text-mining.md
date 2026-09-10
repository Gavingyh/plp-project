# CRISP-DM for text mining

Subject: Text Analytics (module 1) · Bloom target: Analyze / Evaluate / Create
Prerequisites: none. A good first file to read.

---

## 1. Why it matters here (Understand)

CRISP-DM is the process framework module 1 teaches for text mining projects.
It is worth knowing for the exam, and it is worth more here as a lens: mapping
this project onto its six phases shows immediately which phases were done
well, which were skipped, and which had to be repeated because an assumption
turned out to be wrong.

The report needs a methodology section. This is its skeleton.

---

## 2. The concept (Understand / Apply)

The Cross-Industry Standard Process for Data Mining has six phases, and the
arrows between them go both ways:

| phase | for text specifically |
|---|---|
| **1. Business understanding** | What decision does this inform, for whom? |
| **2. Data understanding** | What text exists, how much, how accessible, what register? |
| **3. Data preparation** | Corpus construction, cleaning, segmentation, annotation |
| **4. Modeling** | Feature representation and model training |
| **5. Evaluation** | Against business objectives, not just metrics |
| **6. Deployment** | Delivery, monitoring, documentation |

The point of the framework is that it is **iterative**. Phase 2 routinely
sends you back to phase 1 because the data you assumed exists does not.

---

## 3. Where it lives in this repo (Apply)

| CRISP-DM phase | this project | artifacts |
|---|---|---|
| 1. Business understanding | Retail investors lack research access on three banks | `.project-context/proposal/`, `docs/spec/functional-spec.md` |
| 2. Data understanding | Live testing of every candidate source | `docs/data-viability.md`, `run_data_survey.py` |
| 3. Data preparation | Ingestion, segmentation, aspect assignment, labelling exports | `ingest/`, `preprocess/`, `aspects/` |
| 4. Modeling | FinBERT embeddings and zero-shot scoring; fine-tuning **not run** | `sentiment/`, `train/` |
| 5. Evaluation | Chatbot gold set done; classifier evaluation **blocked** | `chatbot/run_eval.py`, `train/evaluate.py` |
| 6. Deployment | Dashboard, API, scripts, documentation | `dashboard/`, `api/`, `scripts/`, `docs/` |

---

## 4. Analyze

### Where this project's real sequence diverged from the plan

Four phase-2 findings sent the project back to phase 1. This is the most
report-worthy content in the whole methodology section, because each is a case
where implementation contradicted a documented assumption.

**Reddit's API was declined.** The proposal named PRAW. The application was
refused, and phase 2 substituted Arctic Shift, a public research archive. The
outcome was *better* than planned — multi-year history instead of a few
months — which is a useful counter to the assumption that a blocked path is a
worse path.

**SGX was the wrong target.** The plan assumed analyst reports could come from
SGX. They cannot: SGXNet carries company announcements, and third-party
analyst reports are brokerage IP behind entitlements. The banks' own IR sites
turned out to carry the same earnings material, including DBS's quarterly
analyst-call transcripts — closer to the original goal than SGX would have
provided.

**Alpha Vantage indexes no SGX ticker.** Tested live across three ticker
formats for all three banks, every response an empty feed. The four-source
proposal dropped to three.

**The aspect taxonomy did not emerge as predicted.** The plan assumed
clustering would surface the four proposed aspects. On a Reddit-only corpus it
surfaced a consumer-banking versus investment-discussion split instead. Adding
earnings text in 2026-09-11's re-run *did* produce analyst-style clusters —
leverage ratio, Basel III, fee income, return on equity — but 281 of them,
finer than the four aspects and cutting across them.

### The iteration the framework predicts, and this project lived

Adding earnings data is the cleanest example of CRISP-DM's backward arrows.

| step | what happened |
|---|---|
| Phase 3 | Earnings PDFs ingested to close a vocabulary gap |
| Phase 5 | Cross-bank comparison became **invalid** — earnings existed for two banks of three, and earnings text scores far more positive |
| Back to phase 3 | Weight cut 3.0 → 1.0, `source` dimension added to the index |
| Still invalid | Weighting cannot fix coverage asymmetry |
| Back to phase 2 | UOB's IR site is WAF-blocked; the Wayback Machine is not |
| Phase 3 again | 66 UOB PDFs fetched, 1,600 sentences |

**Adding a data source made a metric worse before it made it better.** That is
worth stating plainly in the report: more data is not automatically better if
it arrives unevenly.

### The phase this project is weakest on

Phase 5, evaluation, and the gap is structural rather than an oversight.

| what is evaluated | how | status |
|---|---|---|
| Chatbot behaviour | 23-question gold set, five models | Done |
| Aspect taxonomy geometry | Centroid separation, floor sweep | Done |
| Aspect assignment *correctness* | — | **Not measured** until a spot check on 2026-09-11 showed it failing for Reddit |
| Sentiment classifier | Frozen test set, three baselines | **Blocked** — zero labels |
| Retrieval quality | — | **Not measured**, no relevance judgements |
| Business objective | — | **Not evaluated at all** |

The last row is the one CRISP-DM would flag hardest. Phase 5 asks whether the
solution meets the *business* objective, and nobody has asked a retail
investor whether this dashboard helps them. The proposal's problem statement
cites surveys about investors lacking research access; nothing tests whether
this artifact addresses that.

That is not fixable before the deadline, and naming it is better than
implying that a macro-F1 score answers it.

### Comparing CRISP-DM against how the project actually ran

| aspect | CRISP-DM as taught | this project |
|---|---|---|
| Phase order | Sequential with feedback loops | Followed, with heavy phase 2 to 3 looping |
| Business understanding | Rich, up front | Done in the proposal, **never revisited** with users |
| Data understanding | Before preparation | Done well, and its findings are the project's best evidence |
| Evaluation | Against business objectives | Only technical metrics, and the central one is blocked |
| Deployment | Includes monitoring | Interfaces and docs, no monitoring |

---

## 5. Evaluate

**Was CRISP-DM followed?** Substantially, and mostly implicitly — the phases
map cleanly onto what happened without the team having narrated them that way.
Phase 2 in particular was done unusually well: `docs/data-viability.md`
records live tests of every candidate source with the negative results kept,
which is what makes the project's data decisions defensible.

**Where the framework would have helped more.** Phase 1 was completed once and
never revisited. CRISP-DM treats business understanding as something you
return to when the data changes what is possible, and the data changed a great
deal: no analyst reports, one productive subreddit, an aspect taxonomy that
does not fit. Each of those alters what the dashboard can honestly claim to do
for a retail investor, and the proposal's framing has not been updated to
match.

**What this framing does not capture.** CRISP-DM is a process model, not a
quality standard. Following every phase says nothing about whether the model
is good. This project could complete all six phases and still ship a
zero-shot classifier and an unvalidated taxonomy, which is roughly where it
is.

**The most useful thing it offers the report.** A structure for the "where the
plan was wrong" section. Four documented cases where phase 2 contradicted
phase 1 make a stronger methodology narrative than a clean account of a plan
executed as written — and a marker can tell the difference.

---

## 6. Create

**Exercise (about an hour).** Build the methodology figure for the report.

Draw the six phases and add the **backward** arrows this project actually
traversed, annotating each with what forced it. You will need at least:

- Phase 2 → 1: Reddit API declined; no analyst reports available
- Phase 5 → 3: earnings weighting, after the source skew was measured
- Phase 5 → 2: UOB coverage gap, after weighting failed to fix it
- Phase 4 → 3: taxonomy not validated, sending work back to aspect definition

Then, for each backward arrow, find the commit or document that records it:

```bash
git log --oneline | head -40
grep -rn "RESOLVED\|STILL OPEN\|Superseded" docs/*.md | head -20
```

**Expected outcome.** A one-page figure plus a table of four to six
iterations, each with its trigger, its response, and its evidence file. That
is your methodology section's spine, and every claim in it is traceable.

**Then answer honestly in three sentences:** which phase is this project
weakest on, and what would you do with two more weeks? If your answer is not
"phase 5, and label the data", check your reasoning against
[docs/STATUS.md](../../docs/STATUS.md).

---

## 7. Self-check

1. Name the six CRISP-DM phases in order.
2. Give two phase-2 findings that invalidated a phase-1 assumption here.
3. Why is "adding a data source made a metric worse" a CRISP-DM story rather
   than a bug report?
4. Which phase is this project weakest on, and why is that structural rather
   than an oversight?
5. What does completing all six phases *not* tell you?

<details>
<summary>Answers</summary>

1. Business understanding, data understanding, data preparation, modeling,
   evaluation, deployment.
2. Any two of: Reddit's API application was declined so PRAW was unusable;
   SGX hosts no third-party analyst reports; Alpha Vantage indexes no SGX
   ticker; clustering did not surface the four proposed aspects.
3. Because it is a phase-5 evaluation finding sending work back to phase 3 and
   then phase 2 — exactly the backward arrow the framework predicts. Nothing
   was broken: ingesting earnings text was correct and it exposed a coverage
   asymmetry that only fixing coverage could resolve.
4. Phase 5. It is structural because the central evaluation depends on
   labelled data that does not exist, so no amount of care in the other phases
   unblocks it, and the business objective was never operationalised into
   something testable.
5. Whether the result is any good. CRISP-DM is a process model, not a quality
   standard; a project can traverse all six phases and still ship an
   unvalidated taxonomy and a zero-shot classifier.

</details>

---

## 8. Sources

**Repository**

- `docs/data-viability.md` — phase 2, with negative results preserved
- `docs/STATUS.md` — "Where the original plan was wrong"
- `docs/DESIGN.md` — the decision log
- `.project-context/plan/mvp-implementation-plan.md` — the four findings that
  changed the plan
- `.project-context/proposal/banks-plp-proposal.txt` — phase 1 as submitted

**Course material**

- `.project-context/course-content/TA-context.txt` day 1 — CRISP-DM walked
  through with text-specific sub-tasks per phase

**Not verified**

- CRISP-DM's canonical definition is taken from the course context file. The
  **original CRISP-DM 1.0 specification was not fetched** during this pass;
  cite it or the course material directly rather than this file.
- The mapping of this project's work onto the six phases is an
  interpretation made while writing this document, not a plan the team
  followed explicitly. It is a useful reconstruction, and the report should
  present it as one.
