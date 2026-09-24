# Why the named aspects score almost all neutral

Checked 2026-09-24 against the pre-news state of `plp.db` (the
`plp-2026-09-24.db.gz` snapshot: 36,858 sentences with aspects, 79,949
sentence–aspect pairs scored by base FinBERT).

## The observation

In the baseline sentiment table, almost all polarity sits in `other`:

| aspect | pairs | positive | negative |
|---|---|---|---|
| dividend_policy | 22,556 | 2.3% | 0.7% |
| net_interest_margin | 18,274 | 0.6% | 0.3% |
| management_guidance | 17,973 | 0.7% | 0.2% |
| asset_quality | 7,425 | 0.3% | 2.0% |
| other | 13,721 | 43.5% | 21.0% |

## It isn't the scorer

`sentiment/score.py` classifies each sentence once, with base FinBERT's
whole-sentence head, and copies that label to every aspect the sentence was
assigned. The aspect never enters the model's input. A sentence has the
same label under every aspect it carries, so differences between aspects
come entirely from which sentences each aspect receives.

## It is the assignment

`aspects/assign.py` gives a sentence every named aspect whose seed-term
centroid it matches at cosine similarity 0.65 or above. If it matches none,
it goes to `other`. Grouping sentences by what they received:

| sentences assigned to | sentences | positive | negative | share from earnings |
|---|---|---|---|---|
| `other` only | 13,721 | 43.5% | 21.0% | 56.1% |
| 1 named aspect | 3,992 | 9.5% | 4.0% | 18.4% |
| 2 named aspects | 2,146 | 3.5% | 1.5% | 22.9% |
| 3 named aspects | 10,052 | 0.7% | 0.2% | 14.5% |
| 4 named aspects | 6,947 | 0.2% | 0.4% | 27.0% |

(`other` never co-occurs with a named aspect. Positive/negative are the
sentence's base-FinBERT label.)

17,000 sentences, 46% of those assigned, match three or four of the four
named aspects at once. They are plain transactional or factual lines, close
to all four centroids because the centroids are close to each other
(`config/aspects.yaml` records their mean pairwise cosine distance as 0.1125,
the least distinct of three taxonomies measured on 2026-09-11). A random draw
from the four-aspect group:

- "Go to your DBS account and transfer the money into IBKR's DBS account."
- "then is it not possible to transfer from uob cpf holding account back into cpf?"
- "Today, our interest rate sensitivity is only $4 million."
- "Note: (1) Comprising debt issuances, perpetual capital securities and interbank liabilities."

Sentences that carry an opinion or a result, which is where polarity lives,
are further from the jargon-heavy seed terms and fall below the floor into
`other`:

- "Net fee income grew by 23% and crossed $1 billion for the first time, …" (positive)
- "Loans declined 5% due to subdued credit demand and repayments." (negative)
- "I just had a super bad experience using the UOB One credit card …"

So a named aspect mostly collects neutral banking vocabulary, and `other`
collects the evaluative sentences, including many that are about margins,
credit quality or guidance in substance.

## What it means

- Per-aspect scores from the current taxonomy measure how neutral the
  matched vocabulary is, not investor sentiment on dividends, margins,
  guidance or asset quality. The dashboard's aspect breakdown and the
  sentiment index's aspect rows inherit this.
- The overall per-bank index is less affected: every sentence is still
  scored once. But its movement is driven by `other`.
- This strengthens the open taxonomy decision in `config/aspects.yaml`. The
  discovery re-run after the CNA feed is loaded is the natural point to act.
  Options, for the team to choose between:
  - assign each sentence only its single best aspect above the floor,
    instead of every aspect above it
  - replace seed-term centroids with centroids of discovered clusters
  - write seed terms that describe evaluative statements ("margin
    compressed", "provisions rose") rather than bare jargon
- It does not affect labelling: human labels are per (sentence, aspect) pair
  and are what the fine-tuned, aspect-conditioned model will learn from.

## Reproduce

```sql
WITH per AS (
  SELECT sentence_id, SUM(aspect = 'other') AS has_other, SUM(aspect <> 'other') AS n_named
  FROM sentence_aspects GROUP BY 1),
lab AS (SELECT sentence_id, MIN(label) AS label FROM aspect_sentiment GROUP BY 1)
SELECT CASE WHEN has_other = 1 THEN 'other only' ELSE 'named: ' || n_named END AS grp,
       COUNT(*) AS sentences,
       ROUND(100.0 * SUM(l.label = 'positive') / COUNT(*), 1) AS pos,
       ROUND(100.0 * SUM(l.label = 'negative') / COUNT(*), 1) AS neg,
       ROUND(100.0 * SUM(s.source = 'earnings') / COUNT(*), 1) AS pct_earnings
FROM per JOIN lab l USING (sentence_id) JOIN sentences s USING (sentence_id)
GROUP BY 1 ORDER BY 2 DESC;
```
