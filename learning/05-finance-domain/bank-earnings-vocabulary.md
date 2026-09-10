# Bank earnings vocabulary

Subject: Finance domain · Bloom target: Analyze / Evaluate / Create
Prerequisites: none. Helps before
[earnings-calls-and-consensus](earnings-calls-and-consensus.md) and
[aspect-based-sentiment-analysis](../02-sentiment-mining/aspect-based-sentiment-analysis.md).

---

## 1. Why it matters here (Understand)

You cannot label a sentence's sentiment toward a bank *as an investment*
without knowing what the sentence says. "Specific allowances rose 12 basis
points" carries clear negative valence to anyone who knows what a specific
allowance is, and reads as neutral arithmetic to anyone who does not. The
annotation guideline makes this explicit: a factual statement with clear
valence is not neutral.

This matters twice over. Annotators need it to label the 998-row candidate
set. And the report needs it to explain why the aspect taxonomy is built
around dividend policy, asset quality, net interest margin and management
guidance rather than some other four things.

---

## 2. The concept (Understand / Apply)

A bank makes money in two broad ways: lending at a higher rate than it pays
for funding, and charging fees. It loses money when borrowers default, and it
is constrained by how much capital regulators require it to hold. Almost every
term below sits in one of those four buckets.

### Earning money

| term | what it means | why it moves sentiment |
|---|---|---|
| **Net interest income (NII)** | Interest earned on loans minus interest paid on deposits and other funding | The largest revenue line for all three banks |
| **Net interest margin (NIM)** | NII as a percentage of interest-earning assets | The efficiency of that lending. Quoted in basis points; a 4bp move is material |
| **Basis point (bp)** | One hundredth of a percentage point | "NIM fell 4bp to 2.11%" means from 2.15% |
| **Fee income** | Non-interest revenue: cards, transaction services, investment banking, wealth fees | Diversification away from rate sensitivity, so growth here is read positively |
| **Wealth management** | Managing money for affluent customers; generates recurring fees | A strategic priority for all three banks and heavily discussed |
| **Return on equity (ROE)** | Profit as a percentage of shareholders' equity | The headline profitability number. Return on *tangible* equity excludes goodwill and intangibles, so it is usually higher |
| **Cost-to-income ratio** | Operating expenses divided by income | Efficiency. Lower is better, and a rising ratio is negative |

### Losing money

| term | what it means | why it moves sentiment |
|---|---|---|
| **Non-performing loan (NPL)** | A loan where the borrower has stopped paying, typically 90+ days overdue | Direct measure of credit trouble |
| **NPL ratio** | NPLs as a percentage of total loans | The comparable version. A rise is negative even stated as bare fact |
| **Allowance / provision** | Money set aside against expected losses | Rising provisions signal management expects more defaults |
| **Specific allowance** | Set aside against loans already identified as impaired | Backward-looking; reflects damage already visible |
| **General allowance** | Set aside against the portfolio as a whole for losses not yet identified | Forward-looking; can rise on macro pessimism with no actual defaults |
| **Credit cost** | Provisions as a proportion of loans, often in basis points | The comparable "how expensive is bad lending this quarter" figure |

### Capital and constraints

| term | what it means | why it moves sentiment |
|---|---|---|
| **CET-1 ratio** | Common Equity Tier 1 capital over risk-weighted assets: the highest-quality capital against the riskiness of what the bank holds | The core solvency measure. Higher means safer but also means capital that could have been returned to shareholders |
| **Basel III** | The international regulatory framework setting those capital requirements | Rule changes move CET-1 without the bank doing anything |
| **Leverage ratio** | Capital against total exposure, ignoring risk weighting | A backstop to CET-1, insensitive to how risk is modelled |
| **Risk-weighted assets (RWA)** | Assets scaled by riskiness | The denominator of CET-1 |
| **MAS** | The Monetary Authority of Singapore, the central bank and regulator | Implements Basel rules locally |

### Returning money

| term | what it means | why it moves sentiment |
|---|---|---|
| **Dividend** | Cash paid per share | The single most discussed topic in the Reddit corpus |
| **Dividend yield** | Dividend as a percentage of share price | How income-oriented investors compare banks |
| **Payout ratio** | Dividends as a proportion of earnings | Sustainability. A high ratio may not survive an earnings fall |
| **Special dividend** | A one-off payment outside the normal schedule | Usually positive, but signals surplus capital rather than recurring strength |
| **Share buyback** | The bank purchasing its own shares | Another route for returning capital |

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| Seed terms defining each aspect centroid | `config/aspects.yaml` |
| The labelling rule that facts carry valence | `docs/annotation-guideline.md` |
| The worked NPL example ("NPL ratio rose to 1.4%" is negative) | `docs/annotation-guideline.md`, and repeated in `train/llm_prelabel.py`'s system prompt |
| Where this vocabulary actually appears | `sentences` where `source='earnings'` |

---

## 4. Analyze

### The vocabulary lives in exactly one source

Counting sentences containing each term, by source, across all 36,884
sentences:

| term | Reddit | earnings | news |
|---|---|---|---|
| net interest margin | **0** | 375 | 0 |
| NIM | 4 | 300 | 0 |
| asset quality | **0** | 198 | 0 |
| non-performing | **0** | 201 | 0 |
| NPL | 1 | 270 | 0 |
| credit cost | **0** | 185 | 0 |
| CET-1 / CET1 | 1 | 188 | 0 |
| return on equity | **0** | 112 | 0 |
| cost-to-income | **0** | 106 | 0 |
| leverage ratio | **0** | 58 | 0 |
| Basel | **0** | 84 | 0 |
| fee income | 3 | 503 | 0 |
| allowance(s) | 13 | 1,092 | 0 |
| **dividend** | **561** | 511 | 5 |
| wealth management | 26 | 662 | 2 |
| guidance | 11 | 96 | 2 |

Reproduce with the script in section 6.

Read the table as two groups. **Analyst vocabulary is essentially absent from
Reddit.** Eleven of these terms appear zero to four times across 24,591 Reddit
sentences, and hundreds of times across 12,254 earnings sentences even though
earnings is half the size. **Dividend is the exception and it is a large one**:
561 Reddit sentences against 511 earnings sentences. Retail investors discuss
dividends constantly and margins never.

That single asymmetry explains most of this project's aspect problems. The
proposal's four aspects assume a corpus that talks about margins, asset
quality and guidance. One source does, and it is management describing itself.
The other source, which supplies two thirds of the corpus, talks about
dividends and bank accounts.

### A methodological trap worth internalising

The first version of this table was produced with SQL `LIKE '%nim%'` and
reported **433** Reddit sentences containing "NIM" — which would have
overturned the documented finding that the term is absent from Reddit.

It was wrong. Breaking the matches down by word:

| matched word | count |
|---|---|
| minimum | 393 |
| minimal | 27 |
| minimally | 6 |
| nim | 4 |
| everything else | ~13 |

Substring matching on a three-letter abbreviation finds "**mi*nim*um**".
With a word boundary (`\bNIM\b`) the true count is 4. The lesson generalises:
short financial abbreviations (NIM, NPL, ROE, CET1) are dangerous as
substrings, and any frequency claim built on `LIKE '%term%'` needs checking
before it goes in a report.

### Comparing three ways to identify these terms

| approach | what it catches | what it misses | cost |
|---|---|---|---|
| Exact substring (`LIKE`) | Everything containing the letters | Nothing — that is the problem. 99% false positives on "NIM" | Trivial |
| Regex with word boundaries | The token itself, case-insensitively | Synonyms, plurals it does not anticipate, implicit mentions | Trivial |
| Embedding similarity (what the pipeline uses) | Semantically related sentences with no shared vocabulary | Nothing lexically, but it also matches things it should not | An embedding pass |

The pipeline uses the third, and this is precisely why aspect assignment is
untrustworthy. Reddit sentences get assigned to `net_interest_margin` by
centroid similarity while containing zero occurrences of the phrase and four
of the abbreviation. Embedding similarity has decided those sentences are
*about* margins on the basis of financial-sounding language, and the lexical
evidence says otherwise.

---

## 5. Evaluate

**Was the proposal's four-aspect taxonomy a reasonable choice?** For earnings
text, clearly yes: all four vocabularies are richly present. For Reddit, no.
The taxonomy was chosen before anyone measured which words appear where, which
is a defensible thing to do at proposal time and an indefensible thing to
leave unchecked afterwards.

**What the evidence here does not show.** Term frequency is not aboutness. A
sentence can discuss asset quality without using the phrase — "a lot of their
loans are going bad" is exactly that. So zero occurrences of "asset quality"
in Reddit does not prove Reddit never discusses asset quality; it proves
Reddit does not use the analyst term. The honest claim is narrower than it
first appears, and the report should state the narrow one.

**When the opposite choice would be right.** If the corpus were entirely
earnings and analyst material, the four aspects would work well and this whole
discussion would not arise. The problem is a mixed-register corpus, not a bad
taxonomy in the abstract.

**A defensible response given the deadline.** Keep the four aspects for
earnings text and accept that Reddit populates mainly `dividend_policy` and
`other`. That is honest, it matches the vocabulary evidence, and it needs no
re-labelling. It should be stated as a limitation rather than presented as a
finding.

---

## 6. Create

**Exercise (about one hour).** Extend the frequency analysis to answer a
question the tables above cannot: *does the vocabulary gap close for the
subset of Reddit that discusses banks as investments rather than as service
providers?*

```python
# learning_exercise.py  — run with .venv-plp/bin/python3
import sqlite3, re
c = sqlite3.connect("data/plp.db")
rows = c.execute("SELECT source, text FROM sentences").fetchall()

INVESTOR = re.compile(r"\b(share price|shares|stock|yield|dividend|SGX|D05|O39|U11|portfolio)\b", re.I)
ANALYST  = [("NIM", r"\bNIM\b|net interest margin"),
            ("asset quality", r"asset quality|non-?performing|\bNPLs?\b"),
            ("capital", r"\bCET-?1\b|Basel|leverage ratio"),
            ("profitability", r"\bROE\b|return on (tangible )?equity|cost[-/ ]to[- ]income")]

reddit = [t for s, t in rows if s == "arctic_shift"]
investor = [t for t in reddit if INVESTOR.search(t)]
print(f"reddit total {len(reddit)}, investor-flavoured {len(investor)}")
for name, pat in ANALYST:
    rx = re.compile(pat, re.I)
    a = sum(1 for t in reddit if rx.search(t))
    b = sum(1 for t in investor if rx.search(t))
    print(f"{name:14s} all reddit {a:5d} ({100*a/len(reddit):.2f}%)   "
          f"investor subset {b:4d} ({100*b/len(investor):.2f}%)")
```

**Expected outcome.** You should find that the investor-flavoured subset is a
minority of Reddit, and that analyst-vocabulary rates rise within it but stay
far below earnings levels — a few tenths of a percent rather than the several
percent earnings shows. If you find the gap closing substantially, check your
regex for a substring trap of the kind described in section 4 before believing
it.

**Then answer in two or three sentences, for the report:** does a
vocabulary-based relevance filter look like a viable way to improve aspect
assignment, or does it just shrink the corpus without fixing anything?

---

## 7. Self-check

1. A sentence says "specific allowances rose while general allowances fell."
   Why might these have opposite implications?
2. Why is NIM quoted in basis points rather than percent?
3. A bank reports a higher CET-1 ratio. Give one reading where that is
   positive and one where it is negative.
4. Reddit contains zero occurrences of "asset quality". What exactly does that
   license you to claim, and what does it not?
5. Why did `LIKE '%nim%'` return 433 Reddit sentences when the true count is 4?

<details>
<summary>Answers</summary>

1. Specific allowances relate to loans already identified as impaired, so a
   rise reflects damage already visible. General allowances cover the
   portfolio as a whole for losses not yet identified, so a fall can mean
   management has become more optimistic about the macro outlook. Rising
   specific with falling general is roughly "the known problems got worse, the
   unknown ones look less likely".
2. Because it moves in very small increments that matter. A shift from 2.15%
   to 2.11% is a 4 basis point move and is material to earnings; expressing it
   as "0.04 percentage points" is clumsy and inviting confusion with a 4%
   change.
3. Positive: more loss-absorbing capital, so the bank is safer and better able
   to sustain its dividend through a downturn. Negative: capital held is
   capital not returned to shareholders, so an unusually high ratio can read
   as inefficiency or as management signalling caution.
4. It licenses the claim that Reddit does not use the *analyst term* "asset
   quality". It does not license the claim that Reddit never discusses asset
   quality, since "their loan book is going to blow up" is that discussion in
   different words. The narrow claim is the defensible one.
5. Substring matching found "mi**nim**um" 393 times, plus "minimal",
   "minimally" and others. A word-boundary regex (`\bNIM\b`) gives 4.

</details>

---

## 8. Sources

**Repository**

- `config/aspects.yaml` — the four aspects and their seed terms
- `docs/annotation-guideline.md` — the rule that factual statements carry valence
- `docs/STATUS.md` — the aspect-assignment problem
- `docs/verification-ledger.md` — corpus figures and their queries

**Measured in this repository (2026-09-11)**

- All frequency counts in section 4, from `data/plp.db` via the
  word-boundary regex method shown in section 6. The 433-vs-4 substring
  discrepancy was measured directly.

**External**

- Monetary Authority of Singapore, https://www.mas.gov.sg — regulator and
  local implementer of Basel rules. Cited for institutional role only.

**Not verified**

- The precise Basel III definitions of CET-1, RWA and the leverage ratio are
  given here in working terms rather than regulatory ones. The same applies to
  the "90+ days overdue" NPL convention: it is the common threshold, it varies
  by jurisdiction and by exposure class, and **it was not checked against MAS
  rules or each bank's stated policy.** Anyone quoting
  these in the report should cite the Basel Committee framework or MAS Notice
  637 directly rather than this file.
- Which specific allowance categories each bank uses, and whether their
  definitions are directly comparable across DBS, OCBC and UOB. Not checked.
