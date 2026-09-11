# Earnings releases, analyst calls and consensus

Subject: Finance domain · Bloom target: Analyze / Evaluate / Create
Prerequisites: [singapore-banks-sgx-and-sti](singapore-banks-sgx-and-sti.md),
[bank-earnings-vocabulary](bank-earnings-vocabulary.md)

---

## 1. Why it matters here (Understand)

The proposal named four data streams, and two of them are the subject of this
topic: quarterly earnings releases and analyst consensus reports. One was
delivered richly and one was substituted, and the report needs to be precise
about which is which.

Getting the document types right also matters for the data. The corpus treats
a press release, a CEO slide deck and an analyst-call transcript as
interchangeable earnings text. They are not remotely the same kind of writing,
and the difference explains the project's largest measured skew.

---

## 2. The concept (Understand / Apply)

### What a bank publishes around results

| document | who writes it | register | length |
|---|---|---|---|
| **Media release / press release** | Corporate communications | Promotional prose, headline figures | Short |
| **Financial statements** | Finance, to accounting standards | Almost entirely tables | Long |
| **CEO presentation** | Management, for investors | Slide bullets, strategic framing | Medium |
| **CFO presentation** | Finance, for investors | Slide bullets, numbers and drivers | Medium |
| **Performance summary / highlights** | Investor relations | Condensed metrics | Short |
| **Analyst call transcript** | Verbatim record of a live call | **Dialogue** — analysts question management | Long |

The last row is qualitatively different from the rest. Everything above it is
the bank talking about itself in a controlled format. A transcript contains
someone else's questions.

### What "analyst consensus" is, and is not

An **analyst report** is a brokerage's research document: a rating, a target
price, and several pages of reasoning. It is intellectual property
distributed to paying clients.

**Analyst consensus** is the aggregate: how many analysts cover the stock, how
their ratings distribute, and the mean and median of their price targets. It
is a summary statistic over reports, not the reports.

Yahoo Finance's `quoteSummary` endpoint returns consensus for all three banks:

| field | meaning |
|---|---|
| `n_analysts` | How many analysts contribute |
| `recommendation_mean` | 1.0 strong buy … 5.0 strong sell |
| `recommendation_key` | The same as a word: "buy", "hold" |
| `target_mean`, `target_median`, `target_high`, `target_low` | Price target statistics |
| `strong_buy`, `buy`, `hold`, `sell`, `strong_sell` | The rating distribution |

Note the direction of `recommendation_mean`: **lower is more bullish.** A mean
of 2.19 is between "buy" and "hold", nearer buy.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| Consensus ingestion and its caveats | `ingest/yahoo_analyst.py` |
| `analyst_consensus` table, one snapshot per bank per day | `ingest/db.py` |
| Chatbot tool | `chatbot/tools.py`, `get_analyst_consensus` |
| API endpoint | `api/main.py`, `/analyst-consensus` |
| The news-derived proxy that found nothing | `ingest/analyst_tag.py` |
| PDF fetchers | `ingest/earnings_fetch.py`, `ingest/uob_wayback_fetch.py` |
| Reasoning | `docs/DESIGN.md` decisions 3 and 7 |

---

## 4. Analyze

### The transcript asymmetry, and what it costs

DBS publishes a quarterly analyst call transcript. OCBC and UOB do not.
Fourteen consecutive quarters are in the corpus.

This is simultaneously the project's **best** data and the cause of its
**worst** comparability problem.

Best, because a transcript is the only text in the corpus where a party other
than management sets the agenda. Named brokerage analysts ask about margins,
asset quality and guidance, and management answers unrehearsed. That is much
closer to the "analyst view" the proposal wanted than anything else obtained.

Worst, because transcripts are long. DBS carries 9,093 earnings sentences
against UOB's 1,600 and OCBC's 1,561 — roughly six times — and the blended
sentiment index tracks earnings volume:

| bank | blended | Reddit only | earnings only |
|---|---|---|---|
| DBS | +0.0559 | −0.0015 | +0.1681 |
| OCBC | +0.0441 | −0.0107 | +0.2059 |
| UOB | +0.0201 | −0.0106 | **+0.2291** |

UOB has the **highest** earnings-only score and the **lowest** blended score,
because it has the least earnings text. A reader taking the headline at face
value would conclude UOB is the least well-regarded of the three. On the one
source with comparable coverage it is level with the others, and on management
commentary it is the most positive of all.

**The imbalance is a documentary-practice artifact.** DBS is not discussed
more favourably; DBS publishes more words.

### Why management text scores positive, and what that means

| source | positive | neutral | negative |
|---|---|---|---|
| Reddit | 2.3% | 94.8% | 3.0% |
| earnings | **24.7%** | 67.9% | 7.4% |

Ten times the positive rate. There is no conspiracy here — it is what the
documents are for. A results release exists to present performance
advantageously to investors. Even bad quarters are framed with
"resilient", "disciplined", "well-positioned".

That is a **holder effect** in the opinion-quintuple sense: management
describing itself is a systematically different opinion holder from a retail
investor. Blending the two produces an average of two different things.

**The transcript is a partial exception and deserves separate treatment.**
Analyst questions in a transcript are not promotional — an analyst asking
"why did credit costs rise more than guided?" is adversarial text sitting
inside a document labelled `earnings`. The corpus cannot distinguish the
question from the answer, so both are scored as the same source with the same
weight. Splitting transcripts into questions and answers would be an obvious
refinement and has not been done.

### Why the analyst-report stream failed, and what replaced it

The proposal's fourth stream was analyst consensus reports. What was tried:

| attempt | outcome |
|---|---|
| SGX | Hosts company announcements, not third-party research. Serves a browser-compatibility shell to scripted clients |
| sginvestors.io (aggregator) | Empty HTTP 202, Cloudflare challenge |
| News-derived proxy (`ingest/analyst_tag.py`) | Flagged **0 of 172** news documents |
| Fetching full article text to test the proxy | Straits Times and CNA both refused simple fetches |
| **Yahoo `quoteSummary`** | **Works** — real consensus for all three banks |

Keep the proxy result rather than deleting it. It tagged documents
naming a broker *and* using rating language, and matched nothing across 172
news documents. Two explanations were never distinguished: NewsAPI's free-tier
title-plus-description snippets may be too short to carry "Maintains BUY"
language even when the full article does, or that month genuinely had no such
coverage. `docs/data-viability.md` records this as unresolved, which is the
honest state.

### The naming discipline, which matters most

`ingest/yahoo_analyst.py` is emphatic: this provides consensus *aggregates*,
not the reasoning inside any analyst report, and **the writeup must not
describe it as "analyst reports"**.

That warning is doing real work. The proposal promised analyst reports.
Delivering aggregates and calling them by the promised name would misrepresent
the deliverable — a more serious problem than any data-access question,
because it would mislead a marker about what the system does.

The endpoint carries two further caveats, disclosed in the module, the
dashboard and the API response: it is unofficial, with no published terms
blessing it and a cookie-and-crumb handshake that exists to slow automation;
and it may change without notice.

---

## 5. Evaluate

**Yahoo consensus was a reasonable substitute**, given the alternatives were
paywalled or bot-protected. It is real, structured, and covers all three
banks. It is also a *different kind of data* from everything else in the
system — numeric aggregates rather than text — so it sits outside the
sentiment pipeline entirely and appears only as a dashboard panel and a
chatbot tool.

Be clear about this in the report: the fourth stream does not feed
the sentiment index at all. The system has three text sources, not four.

**Ingesting earnings text is the project's most consequential data decision.** It closed the vocabulary gap that made
analyst-style aspects impossible, and it is the reason the 2026-09-11
clustering run finds leverage-ratio and Basel III clusters that a Reddit-only
corpus could never produce.

**What the evidence does not show.** Nothing establishes that blending
management commentary with retail chatter produces a meaningful quantity.
`docs/STATUS.md` lists reconsidering blending as an open question, and the
UOB inversion above is the strongest argument that the blended figure is a
composition artifact rather than a measurement.

**The refinement nobody has made.** Document type is not stored. Every
earnings PDF becomes `source='earnings'` regardless of whether it is a
promotional press release or an adversarial analyst question. Storing
`doc_type` at that granularity would let the index separate management
commentary from analyst questioning, which is the single most interesting
split available in this corpus and is currently invisible.

---

## 6. Create

**Exercise (about ninety minutes).** Test whether analyst questions really do
score differently from management prose.

```python
# .venv-plp/bin/python3
import sqlite3, re
c = sqlite3.connect("data/plp.db")

rows = c.execute("""
    SELECT d.url, s.text, a.label
    FROM aspect_sentiment a
    JOIN sentences s ON s.sentence_id = a.sentence_id
    JOIN documents d ON d.doc_id = s.doc_id
    WHERE s.source = 'earnings'
""").fetchall()

def kind(u):
    u = (u or "").lower()
    if "analyst" in u or "transcript" in u: return "transcript"
    if "press" in u or "release" in u:      return "press_release"
    if "presentation" in u or "ceo" in u or "cfo" in u: return "presentation"
    return "other"

from collections import Counter, defaultdict
by = defaultdict(Counter)
for url, text, label in rows:
    by[kind(url)][label] += 1

for k, c_ in sorted(by.items(), key=lambda kv: -sum(kv[1].values())):
    n = sum(c_.values())
    print(f"{k:14s} n={n:6d}  " +
          "  ".join(f"{lab} {100*c_[lab]/n:.1f}%" for lab in
                    ("positive", "neutral", "negative")))
```

Then go further: within transcripts, separate analyst questions from
management answers. Questions often end in `?` or follow a speaker line, and
transcripts name the speaker. A crude split on sentences containing `?` is
enough for a first look.

**Expected outcome.** Press releases should be the most positive category.
Transcripts should be less positive than presentations — and if you can
isolate the questions within them, those should be the least positive text in
the entire earnings corpus, possibly less positive than Reddit.

**For the report:** the per-document-type table, and one sentence on whether
`source='earnings'` is too coarse a category to be treated as one thing. If
the split is as large as the Reddit-versus-earnings gap, that is an argument
for storing `doc_type` and a concrete piece of future work.

---

## 7. Self-check

1. What is the difference between an analyst report and analyst consensus?
2. In Yahoo's `recommendation_mean`, is 2.0 more or less bullish than 4.0?
3. Why does DBS have roughly six times the earnings sentences of the other two
   banks?
4. UOB has the highest earnings-only score and the lowest blended score.
   Explain in one sentence.
5. Why is an analyst call transcript different in kind from every other
   earnings document?

<details>
<summary>Answers</summary>

1. A report is a brokerage's full research document — rating, target price and
   pages of reasoning — distributed to paying clients. Consensus is the
   aggregate across such reports: how many analysts, how ratings distribute,
   and price target statistics. Consensus contains no reasoning.
2. More bullish. The scale runs 1.0 strong buy to 5.0 strong sell, so lower is
   more positive.
3. Because DBS publishes quarterly analyst call transcripts and the other two
   do not, and transcripts are long. Fourteen consecutive quarters are in the
   corpus. It is a difference in publishing practice, not in how much each
   bank is discussed.
4. Because the blended figure is dominated by whichever source contributes
   most text, and UOB has the least earnings text, so its blended score is
   pulled toward near-neutral Reddit content despite its management commentary
   being the most positive of the three.
5. Because it is the only earnings document where someone other than the bank
   sets the agenda. Named analysts ask unrehearsed questions, so it contains
   adversarial text inside a document the corpus labels the same as a
   promotional press release.

</details>

---

## 8. Sources

**Repository**

- `ingest/yahoo_analyst.py` — the endpoint, the fields, and the naming warning
- `ingest/analyst_tag.py` — the proxy that matched 0 of 172 documents
- `ingest/db.py` — the `analyst_consensus` schema
- `docs/DESIGN.md` decisions 3 and 7
- `docs/data-viability.md` — the SGX, sginvestors.io and full-article tests
- `docs/STATUS.md` — blending listed as an open question

**Measured in this repository (2026-09-11)**

- Earnings sentence counts and blended, Reddit-only and earnings-only index
  scores per bank, from `data/plp.db`.
- Document-type counts per bank, from `data/earnings_pdfs/`.
- The 2.3% vs 24.7% positive rates are carried from `docs/data-viability.md`
  (measured 2026-09-07) and were **not recomputed** in this pass.
- Yahoo consensus values in the database as at 2026-09-07: DBS 16 analysts,
  `recommendation_mean` 2.19; OCBC 16 and 2.19; UOB 15 and 2.93.

**Not verified**

- Whether analyst questions actually score less positively than management
  prose. The exercise in section 6 tests it; nobody has run it.
- Whether Yahoo's `recommendation_mean` uses exactly the same scale
  convention across all markets. The 1.0–5.0 direction is recorded in
  `ingest/db.py`'s schema comment; **Yahoo publishes no documentation for this
  endpoint**, which is part of why it is flagged as unofficial.
- Whether the news-derived proxy's zero result is a text-length artifact or a
  genuine absence. Explicitly unresolved in `docs/data-viability.md`.
