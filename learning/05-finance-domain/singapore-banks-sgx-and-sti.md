# Singapore banks, SGX and the STI

Subject: Finance domain · Bloom target: Analyze / Evaluate / Create
Prerequisites: none. Pairs with
[bank-earnings-vocabulary](bank-earnings-vocabulary.md).

---

## 1. Why it matters here (Understand)

Three facts about the market shape this project more than any modelling
decision: which companies are being analysed, where their disclosures live,
and how often those disclosures appear. The third turns out to be the one that
quietly affects the data, because the earnings corpus is time-stamped from
filenames whose quarter markers do not all mean the same thing.

---

## 2. The concept (Understand / Apply)

### The three banks

| bank | full name | SGX ticker | Yahoo symbol |
|---|---|---|---|
| DBS | DBS Group Holdings Ltd | D05 | `D05.SI` |
| OCBC | Oversea-Chinese Banking Corporation Limited | O39 | `O39.SI` |
| UOB | United Overseas Bank Limited | U11 | `U11.SI` |

All three are Singapore-headquartered commercial banks listed on the Singapore
Exchange main board, regulated by the **Monetary Authority of Singapore**,
which is both the central bank and the financial regulator and which
implements the Basel capital framework locally.

The `.SI` suffix denotes the Singapore exchange in Yahoo Finance's symbology.
It matters practically: `ingest/alphavantage.py` originally sent `D05.SI` to
Alpha Vantage, which rejects periods in tickers, and stripping the suffix
revealed the deeper problem that Alpha Vantage does not index SGX names at
all.

### The disclosure landscape

| what | where it lives | reachable? |
|---|---|---|
| Results releases, presentations, transcripts | Each bank's own investor-relations site | DBS and OCBC yes; UOB blocked by a WAF, fetched via the Wayback Machine |
| Company announcements | SGXNet | Serves a browser-compatibility shell to non-browser clients |
| Third-party analyst reports | Brokerage clients only | No. Not on SGX either — they are brokerage IP behind entitlements |
| Consensus aggregates | Yahoo Finance `quoteSummary` | Yes, via an unofficial endpoint |

The most consequential line is the third. The proposal's fourth data stream
was "analyst consensus reports", and full analyst reports turned out to be
unobtainable by any legitimate free route. Yahoo consensus *aggregates* are the
substitute, and must not be described as analyst reports in the writeup.

### Reporting cadence, and why it is not quarterly

This is the part that surprises people. **SGX stopped requiring quarterly
reporting on 7 February 2020.** Previously any issuer above S$75 million market
capitalisation had to report quarterly. SGX RegCo replaced that with a
risk-based approach: quarterly reporting now applies only to issuers
associated with higher risk, everyone else reports **semi-annually**, and
voluntary business updates in between are encouraged rather than required.

So a bank's financial year produces:

- **1H** and **FY** — full half-year and full-year results
- **1Q** and **3Q** — voluntary business updates, typically shorter

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| Bank names, aliases, ticker mapping, detection | `ingest/base.py` |
| Yahoo symbols and the consensus fetch | `ingest/yahoo_analyst.py` |
| DBS and OCBC IR fetchers, filename date parsing | `ingest/earnings_fetch_ir.py` |
| UOB via the Wayback Machine | `ingest/earnings_fetch_uob.py` |
| Downloaded PDFs | `data/earnings_pdfs/<BANK>/` |
| Why SGX was rejected as a source | `docs/DESIGN.md` decision 3 |

---

## 4. Analyze

### What each bank actually publishes, counted

From the downloaded PDFs:

| bank | files | document types present |
|---|---|---|
| DBS | 75 | 14 analyst transcripts, 14 CEO presentations, 14 CFO presentations, 10 media transcripts, 7 trading updates, 7 performance summaries, plus press statements |
| UOB | 66 | 14 CEO presentations, 13 CFO presentations, 10 performance highlights, 10 news releases, plus slide decks |
| OCBC | 41 | CEO presentations, results presentations, press releases and highlights across 1Q/1H/3Q/FY |

**DBS publishes a quarterly analyst call transcript and the other two do
not.** Fourteen consecutive quarters are available. These are documents in
which named brokerage analysts question management directly about margins,
asset quality and guidance — the closest thing this project has to genuine
analyst input, and it arrived as a side effect of scraping IR sites rather
than through the analyst-report stream the proposal planned.

That single asymmetry explains the corpus imbalance that undermines every
blended comparison. DBS carries 9,093 earnings sentences against UOB's 1,600
and OCBC's 1,561 — roughly six times — not because DBS is discussed more, but
because **transcripts are long and DBS is the only one publishing them.** The
imbalance is a documentary-practice artifact, not a signal about the banks.

### OCBC's naming confirms the cadence change

OCBC's filenames carry `1H23`, `FY23`, `1Q23`, `3Q23`. Two different kinds of
document share one numbering scheme: the half-year and full-year files are
statutory results, the 1Q and 3Q files are voluntary business updates. UOB and
DBS use `1q-2021` and `1Q23` style markers throughout.

This has a direct effect on the data. `ingest/earnings_fetch_ir.py` maps a
filename's quarter to a nominal announcement date — `2Q26` becomes
2026-08-01 — because without it every historical document would carry
ingestion time and the entire back-catalogue would land inside the dashboard's
7-day and 30-day rolling windows at once. The mapping is deliberately
approximate: the day of month is nominal and the quarter is what matters for
windowing.

The residual issue is that a `1Q` update and a `1H` results release are not
equivalent documents, and nothing downstream distinguishes them. A business
update is shorter and less detailed than statutory results, so the corpus
mixes two document weights under one label.

### Comparing the routes to earnings data

| route | legitimacy | coverage | cost | used? |
|---|---|---|---|---|
| **Bank IR sites** | Clean. Public pages, plain HTTP, no bot protection | DBS and OCBC complete | Low | Yes |
| **Wayback Machine** | Clean. Archived copies of the same public PDFs at their original URLs | UOB 2020–2025, thinning recently | Low, but rate-limited | Yes, for UOB |
| SGXNet | Public, but serves a compatibility shell to scripted clients | Announcements only, not presentations | Would need a headless browser | No |
| Defeating UOB's WAF | Requires fingerprint spoofing against an explicit refusal signal | Would be complete | Moderate | **Deliberately not** |
| Paid data vendor | Clean | Complete, plus real analyst reports | Beyond a student budget | No |

The choice between rows 2 and 4 is the interesting one and is discussed in
[data-access-ethics](../06-engineering-practices/data-access-ethics.md).

---

## 5. Evaluate

**The three-bank scope was right.** They are similar enough to compare
and distinct enough that comparison is meaningful, they dominate the local
index, and they are discussed together constantly, which gives the entity
detection something real to do. A single-bank scope would have removed the
comparison basis entirely.

**"Analyst consensus" was never a realistic fourth stream.** The project
context flagged it as an unresolved risk in advance without resolving it.
What was delivered is consensus aggregates from an unofficial endpoint, plus
DBS transcripts that arrived by accident. The report should say the stream was
substituted rather than delivered.

**What the market facts here do not establish.** The proposal's ">S$180B
combined market cap, roughly half the Straits Times Index" claim is carried
throughout this project's documents and **was not verified** during this pass.
Market capitalisation moves daily and index weights are rebalanced, so a
figure quoted from a 2026 proposal needs re-checking against a current index
factsheet before it appears in a graded report.

**The cadence finding matters more than it looks.** Any statement in the
report about "quarterly earnings" should be checked against what these banks
actually file. Describing 1Q and 3Q documents as quarterly *results* would be
wrong: since February 2020 they are voluntary business updates.

---

## 6. Create

**Exercise (about an hour).** Establish whether document type, not sentiment,
explains the earnings imbalance.

```python
# .venv-plp/bin/python3
import sqlite3, re, collections
c = sqlite3.connect("data/plp.db")

rows = c.execute("""
    SELECT bank, source_detail, url, COUNT(*) AS n
    FROM documents WHERE source='earnings'
    GROUP BY bank, source_detail, url
""").fetchall()

# Bucket by document type inferred from the filename in the URL.
def kind(u):
    u = (u or "").lower()
    for k in ("analyst", "transcript", "ceo", "cfo", "press", "release",
              "highlight", "summary", "update", "presentation"):
        if k in u:
            return k
    return "other"

per = collections.defaultdict(collections.Counter)
for bank, detail, url, n in rows:
    per[bank][kind(url)] += 1

for bank, counts in per.items():
    print(bank, dict(counts.most_common()))

# Now the sentence weight each type carries
q = c.execute("""
    SELECT d.bank, d.url, COUNT(s.sentence_id)
    FROM documents d JOIN sentences s ON s.doc_id = d.doc_id
    WHERE d.source='earnings' GROUP BY d.doc_id
""").fetchall()
w = collections.defaultdict(int)
for bank, url, n in q:
    w[(bank, kind(url))] += n
for k_, v in sorted(w.items(), key=lambda kv: -kv[1])[:12]:
    print(f"{k_[0]:5s} {k_[1]:14s} {v:6d} sentences")
```

**Expected outcome.** Analyst and media transcripts should account for a large
share of DBS's sentence count and none of the other two banks'. That converts
"DBS has six times the earnings text" from an unexplained imbalance into a
documented cause, which is a much stronger sentence in the report.

**Then answer:** would excluding transcripts make the three banks comparable,
and what would be lost by doing so? (The transcripts are the most
analyst-like text in the corpus, so this is a real trade-off, not an obvious
fix.)

---

## 7. Self-check

1. What are the three SGX tickers, and what does the `.SI` suffix do?
2. Since February 2020, what does a Singapore-listed bank have to publish, and
   how often?
3. Why does DBS have roughly six times the earnings sentences of the other two
   banks?
4. Why are third-party analyst reports absent from SGX?
5. Why does `ingest/earnings_fetch_ir.py` parse a date out of the filename rather
   than using ingestion time?

<details>
<summary>Answers</summary>

1. D05 (DBS), O39 (OCBC), U11 (UOB). `.SI` identifies the Singapore exchange in
   Yahoo Finance's symbology. Alpha Vantage rejects the period, which is why
   the adapter strips the suffix.
2. Semi-annual reporting is the default. Quarterly reporting applies only to
   issuers SGX RegCo assesses as higher risk, following the risk-based
   framework effective 7 February 2020. Voluntary business updates between
   half-year reports are encouraged, which is what 1Q and 3Q documents
   usually are.
3. Because DBS publishes quarterly analyst call transcripts and the other two
   do not, and transcripts are long. Fourteen consecutive quarters are in the
   corpus. It is a documentary-practice difference, not a difference in how
   much the banks are discussed.
4. Because they are brokerage intellectual property distributed to paying
   clients. SGXNet carries company announcements and SGX's own commentary, not
   third-party research.
5. Because otherwise every historical document would carry its ingestion
   timestamp, dropping the whole back-catalogue into the dashboard's 7-day and
   30-day rolling windows simultaneously.

</details>

---

## 8. Sources

**Repository**

- `ingest/base.py` — bank aliases and ticker mapping
- `ingest/yahoo_analyst.py` — Yahoo symbols and the unofficial-API caveat
- `ingest/earnings_fetch_ir.py` — filename date parsing and its rationale
- `ingest/earnings_fetch_uob.py` — the WAF and the archive route
- `docs/DESIGN.md` decision 3 — why not SGX
- `docs/data-viability.md` — Alpha Vantage and SGX access tests

**Measured in this repository (2026-09-11)**

- File and document-type counts per bank, from `data/earnings_pdfs/`:
  DBS 75, UOB 66, OCBC 41 files, and the type breakdown in section 4.
- Earnings sentence counts per bank, from `data/plp.db`.

**External**

- SGX quarterly reporting change: announced by SGX RegCo 9 January 2020,
  effective 7 February 2020, replacing the S$75m market-capitalisation
  threshold with a risk-based approach and semi-annual reporting as the
  default. Confirmed across several independent legal summaries, accessed
  2026-09-11, including Allen & Gledhill
  (https://www.allenandgledhill.com/sg/perspectives/articles/14128/sgkh-sgx-implements-new-approato-quarterly-reporting-and-enhances-continuous-disclosure-requirements-on-7-february-2020)
  and CNPLaw
  (https://www.cnplaw.com/changes-to-the-quarterly-reporting-framework-for-sgx-listed-companies-cnpupdate-mar2020/).
  **For the report, cite the SGX rulebook or SGX RegCo's own announcement
  rather than a law-firm summary.**
- Monetary Authority of Singapore, https://www.mas.gov.sg — cited for its role
  as central bank and regulator only.

**Not verified**

- **">S$180B combined market capitalisation, roughly half the Straits Times
  Index."** Carried from the proposal and not re-checked. Market
  capitalisation and index weights change continuously; verify against a
  current STI factsheet before putting it in the report.
- Whether all three banks are currently subject to semi-annual or quarterly
  reporting under the risk-based framework. The general rule is verified; each
  bank's specific obligation is not.
- The exact date each bank published each document. Filename quarter markers
  are mapped to nominal dates, which is approximate by design.
