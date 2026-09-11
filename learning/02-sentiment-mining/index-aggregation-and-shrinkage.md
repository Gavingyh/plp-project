# Index aggregation and shrinkage

Subject: New Media and Sentiment Mining (module 2) · Bloom target: Analyze / Evaluate / Create
Prerequisites: [levels-and-the-opinion-quintuple](levels-and-the-opinion-quintuple.md)

---

## 1. Why it matters here (Understand)

Scoring individual sentences is the machine-learning part. Turning 79,987
scored (sentence, aspect) pairs into one number a retail investor can read is
the part that decides whether the dashboard informs or misleads.

The project's own design notes are blunt about the risk: *a sentiment number
without its sample size is the main way this dashboard could mislead someone.*
Everything in this topic follows from taking that seriously.

---

## 2. The concept (Understand / Apply)

### From labels to a score

Each classified pair contributes a value:

| label | value |
|---|---|
| positive | +1.0 |
| neutral | 0.0 |
| negative | −1.0 |

The raw score is a weighted mean of those values, where each pair's weight
combines the classifier's confidence and a per-source weight.

### Shrinkage: the important part

The raw mean is then pulled toward neutral:

```
score = raw_mean × n / (n + k)        with k = 5
```

Why this matters, with the arithmetic:

| observations (n) | raw mean | multiplier n/(n+5) | reported score |
|---|---|---|---|
| 1 | +1.00 | 0.17 | **+0.17** |
| 5 | +1.00 | 0.50 | +0.50 |
| 20 | +1.00 | 0.80 | +0.80 |
| 100 | +1.00 | 0.95 | +0.95 |
| 1,000 | +1.00 | 0.995 | +1.00 |

Without shrinkage, **one** enthusiastic Reddit comment produces a score of
+1.0, identical to a thousand consistently positive sentences. Shrinkage
encodes the idea that a small sample is weak evidence about a population, and
`k` is the number of observations at which you trust the sample about half as
much as its face value.

This is a frequentist shortcut to a Bayesian idea: it behaves like a prior
centred on neutral with a strength of `k` pseudo-observations.

### Two more defences

**A volume floor.** Below 5 observations, the system reports
`insufficient_data` instead of a number at all. Shrinkage makes small samples
*less wrong*; the floor stops them being reported.

**`n` travels with every score.** It is stored in `sentiment_index`, displayed
in the dashboard, and returned by the API.

### Source weights

| source | weight |
|---|---|
| `arctic_shift` (Reddit) | 1.0 |
| `earnings` | 1.0 |
| `newsapi` | 1.5 |
| `alphavantage` | 1.5 |

Earnings was **3.0** originally, on the assumption it would be a handful of
high-signal documents. It became the second-largest source and the most
positively skewed one, so triple-weighting amplified a known bias rather than
correcting it. It was cut to 1.0.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| `SHRINKAGE_K = 5`, label values, source weights | `aggregate/index.py` |
| `_summarize` — the one place a score is computed | `aggregate/index.py` |
| `MIN_VOLUME_FOR_SCORE = 5` | `chatbot/tools.py` |
| Continuous series, reusing `_summarize` | `aggregate/index.py`, `compute_time_series` |
| The `source` dimension on every index row | `sentiment_index` schema |
| Reasoning | `docs/DESIGN.md` decision 6, and "Volume shrinkage in the index" |

`compute_time_series` deliberately calls the same `_summarize` the stored index
uses. A chart computed a slightly different way would quietly disagree with the
headline number, and there would be no way to tell which was right.

---

## 4. Analyze

### The blending problem, measured

The proposal specifies blending all streams into one index. The data says the
streams are not comparable:

| source | positive | neutral | negative |
|---|---|---|---|
| Reddit | 2.3% | 94.8% | 3.0% |
| earnings | **24.7%** | 67.9% | 7.4% |

Earnings text is management describing its own results. It is roughly **ten
times** more likely to be scored positive than retail chatter.

The consequence for the headline numbers:

| bank | blended | Reddit only | earnings only |
|---|---|---|---|
| DBS | +0.0559 | −0.0015 | +0.1681 |
| OCBC | +0.0441 | −0.0107 | +0.2059 |
| UOB | +0.0201 | −0.0106 | +0.2291 |

Read the Reddit column: the three banks are indistinguishable. Read the
blended column: DBS leads by nearly three times UOB. **The blended ordering is
almost entirely a function of how much earnings text each bank contributes**,
and DBS contributes about six times as much as the others because it publishes
long analyst-call transcripts.

Note the sharpest version of this: UOB has the *highest* earnings-only score
(+0.2291) and the *lowest* blended score (+0.0201). A naive reading of the
headline would conclude UOB is the least well-regarded bank, when on the
comparable source it is level with the others and on management commentary it
is the most positive. That is a composition artifact producing an inverted
conclusion.

### Why weighting could not fix it

Dropping the earnings weight from 3.0 to 1.0 moved DBS's blended score from
+0.101 to +0.056. It reduced the distortion and could not remove it, because
the cause is **coverage asymmetry, not weighting**. Weights scale each
source's contribution; they cannot conjure earnings text for a bank that
published less of it. A mixing parameter cannot repair a sampling problem.

The eventual fix was structural. Adding a `source` dimension to
`sentiment_index` means every blended row sits beside its components, so the
composition is visible rather than being argued about.

### Comparing four aggregation choices

| approach | one comment can swing it? | needs a floor? | interpretable? | used? |
|---|---|---|---|---|
| Plain mean of ±1 | Yes, to ±1.0 | Yes | Very | No |
| **Shrunk mean** | No, capped at ±0.17 at n=1 | Still yes, for honesty | Yes, with `n` shown | **Yes** |
| Bayesian posterior with a Beta/Dirichlet prior | No | No, credible interval carries it | Gives an interval, not just a point | No |
| Proportion positive minus proportion negative | Yes | Yes | Very, and discards confidence | No |

The Bayesian option is strictly better and was not taken. It would produce a
credible interval, which communicates uncertainty far better than a point
estimate with an `n` beside it, and it would remove the arbitrary `k`. The
cost is explaining a posterior in a report for a module that did not teach it.
Shrinkage is the pragmatic 90% solution, and `score × n/(n+k)` is
approximately a Dirichlet posterior mean with a neutral prior of strength `k`.

### Is k = 5 justified?

Honestly, no. It is not derived from anything. It is a plausible small number
that makes n=1 harmless and n=100 nearly unaffected. Nobody swept it against
an outcome, because there is no labelled outcome to sweep against. The report
should call it a chosen constant rather than a calibrated one, in the same way
`similarity_floor` is documented as a calibration point rather than a final
answer.

---

## 5. Evaluate

**Shrinkage was the right call.** It is cheap, it is explainable in one
line of arithmetic, and it eliminates the single most likely way this
dashboard could produce a dramatic and meaningless number.

**Keeping the blend is defensible now that composition is visible.**
The proposal specifies a blended index, and per-source rows let any reader
reconstruct what went into it. The alternative — refusing to blend — would
have meant not delivering what was proposed.

**What the evidence does not show.** Nothing here validates that the blended
number *means* anything. It is a well-behaved arithmetic summary of a
quantity whose components measure different things: management's
self-presentation and retail investors' opinions are not two samples of one
underlying sentiment. Averaging them produces a number, not necessarily a
measurement. That is the honest methodological caveat, and `docs/STATUS.md`
lists reconsidering blending as an open question for good reason.

**When you would not shrink.** If every cell were guaranteed large, shrinkage
does nothing but add a constant nobody can justify. It earns its place
precisely because per-aspect, per-window cells here are often small.

---

## 6. Create

**Exercise (about an hour).** Test how sensitive the headline is to choices
nobody validated.

```python
# .venv-plp/bin/python3
import sqlite3
c = sqlite3.connect("data/plp.db")

rows = c.execute("""
    SELECT s.bank, s.source, a.label, a.confidence
    FROM aspect_sentiment a JOIN sentences s ON s.sentence_id = a.sentence_id
""").fetchall()

VAL = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}

def index(bank, k, weights):
    num = den = n = 0
    for b, src, label, conf in rows:
        if b != bank or label not in VAL:
            continue
        w = weights.get(src, 1.0) * conf
        num += VAL[label] * w; den += w; n += 1
    raw = num / den if den else 0.0
    return round(raw * n / (n + k), 4), n

base = {"earnings": 1.0, "arctic_shift": 1.0, "newsapi": 1.5}
for k in (0, 5, 50, 500):
    print(f"k={k:4d}", {b: index(b, k, base)[0] for b in ("DBS", "OCBC", "UOB")})

print()
for label, w in [("earnings 3.0 (the old weight)", {**base, "earnings": 3.0}),
                 ("earnings 0.0 (Reddit only)",   {**base, "earnings": 0.0})]:
    print(f"{label:32s}", {b: index(b, 5, w)[0] for b in ("DBS", "OCBC", "UOB")})
```

**Expected outcome.** `k` should barely matter at these sample sizes, because
`n` is in the tens of thousands, so `n/(n+5)` is essentially 1. That is the
point: shrinkage protects *small cells*, such as a single aspect in a 7-day
window, not the headline. The source weight, by contrast, should move the
bank ordering noticeably.

**Write for the report:** which of the two knobs actually changes the
conclusion, at what sample size shrinkage stops mattering, and therefore where
in the dashboard it is doing real work.

---

## 7. Self-check

1. With `k = 5`, what score does a single positive observation produce, and
   why is that better than +1.0?
2. Why does shrinkage barely change the all-time headline but matter a lot for
   a 7-day aspect cell?
3. Why couldn't reducing the earnings weight fix the cross-bank comparison?
4. UOB has the highest earnings-only score and the lowest blended score.
   Explain.
5. Why does `compute_time_series` reuse `_summarize` rather than computing its
   own average?

<details>
<summary>Answers</summary>

1. +0.17, from 1.0 × 1/(1+5). Better because one comment is weak evidence
   about a population, and reporting +1.0 would present it with the same
   confidence as a thousand consistently positive sentences.
2. Because the multiplier is n/(n+5). At n in the tens of thousands it is
   essentially 1 and changes nothing. At n=3 it is 0.375 and cuts the score by
   nearly two thirds, which is exactly where an unshrunk score would be most
   misleading.
3. Because the cause was coverage asymmetry, not weighting. UOB had almost no
   earnings text at the time; no weight applied to a source scales up data
   that is not there. Weights change each source's contribution, not its
   existence.
4. Composition. UOB's earnings text is the most positive of the three, but it
   has far less of it than DBS, so its blended figure is dominated by
   near-neutral Reddit content. The blended ordering tracks how much earnings
   text each bank contributes.
5. So a chart cannot disagree with the headline number. If the series computed
   its average even slightly differently, a user could see a line and a
   headline that contradict each other with no way to tell which is correct.

</details>

---

## 8. Sources

**Repository**

- `aggregate/index.py` — `SHRINKAGE_K`, `_LABEL_SCORE`, `_SOURCE_WEIGHT`,
  `_summarize`, `compute_time_series`, and the comment explaining the 3.0 → 1.0
  change
- `chatbot/tools.py` — `MIN_VOLUME_FOR_SCORE`
- `docs/DESIGN.md` decision 6
- `docs/data-viability.md` — the per-source positive/neutral/negative table
- `docs/verification-ledger.md` — the blended and per-source index figures

**Measured in this repository (2026-09-11)**

- All index scores and sample sizes in section 4, from `sentiment_index`.
- 2.3% vs 24.7% positive rates, carried from `docs/data-viability.md`
  (measured 2026-09-07, not recomputed in this pass).

**Not verified**

- That `k = 5` is a good value. It is not derived from anything and has never
  been swept against an outcome, because no labelled outcome exists. Treat it
  as a chosen constant.
- The claim that `score × n/(n+k)` approximates a Dirichlet posterior mean
  with a neutral prior of strength `k`. The correspondence is standard for
  Beta-Binomial shrinkage; the exact form for a three-class weighted mean was
  **not derived or checked here.** Do not put it in the report without
  working it through.
