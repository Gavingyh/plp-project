# Aspect discovery, swept over `min_cluster_size`

The unsupervised discovery task (text-mining task 1) re-run on the full
current corpus, CNA included, at four HDBSCAN `min_cluster_size` values.
Run 2026-09-30 on 44,345 sentences (all already embedded).

```bash
for n in 10 25 50 100; do
  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.discover --min-cluster-size $n
done
```

UMAP: 10 dimensions, `n_neighbors=15`, cosine, `random_state=42`
(`aspects/discover.py`). Each run took about 3 minutes. Raw reports:
`aspect-discovery-2026-09-30-mcs{10,25,50,100}.raw.txt` (no email addresses
appeared in tonight's samples; the redaction step ran anyway).

## Result

| `min_cluster_size` | clusters | noise | median cluster | largest clusters |
|---|---|---|---|---|
| 10 | 358 | 65% (29,004) | 22 | 809, 792, 548, 377, 359 |
| 25 | 4 | 0% | — | **44,252**, 34, 31, 28 |
| 50 | 3 | 1% (417) | — | **43,453**, 381, 94 |
| 100 | 25 | 52% (22,876) | 535 | 6,700, 2,066, 1,688, 1,561, 1,198 |

**At 25 and 50 the clustering collapses**: one cluster takes 98–99.8% of
the corpus. The rest are small: at 25, extraction debris (quarter-ended
headers, garbled PDF text); at 50, audit boilerplate (381) and deposit-rate
cuts (94). HDBSCAN's cluster selection can prefer one large cluster
over many small ones, and does here; these two runs describe nothing.

**At 10 it matches the 25 Sep run** (338 clusters and 65% noise on 42,690
sentences): 358 clusters, still fine-grained, median 22 sentences. The
workstream built the 10-aspect taxonomy from that level of detail
([aspect-taxonomy-2026-09-25.md](aspect-taxonomy-2026-09-25.md)).

**At 100, 25 coarse clusters appear, and they line up with the ten aspects
without being asked to.** By their top terms (21,469 sentences clustered):

| aspect | clusters at 100 (size: top terms) |
|---|---|
| retail banking | 1,688: account, card, savings · 1,561: account, card, money, credit · 1,198: transfer, app, open · 996: card, spend, miles, cashback · 850: outage, digital, disruption, MAS · 547: fixed deposit, 100k · 535: account, custodian, IBKR · 224: credit card, cashback, visa · 217: better rates |
| income and profit results | 2,066: income, net, rose, higher · 844: income, lower, fell · 211: income, profit, yoy, qoq, record · 340: profit, record, stock, high, rises · 127: profit, drops, stock |
| wealth business | 6,700: growth, wealth, new, AI, banking · 113: banking, products, trading, wealth |
| asset quality | 827: income, profit, loans, ratio, non(-performing) · 187: loans, exposure, risks · 177: ratio, allowances, basis points, specific |
| dividend policy | 179: dividend, cents, share, payout, declared |
| investor stock sentiment | 640: does, did, buy, know |
| management guidance | 147: results, review, briefing |
| not an aspect (`other`) | 547: CEO, appoints, chairman · 337: financial statements, audit · 211: awards, world's best bank |

Net interest margin, capital and liquidity, and the macro environment have
no cluster of their own at 100; their sentences sit in noise or inside the
income clusters. Two results clusters split by direction ("rose, higher"
against "fell, lower"; "record, rises" against "drops"), so at this level
the clustering separates polarity as well as topic.

## What this says

- The fine clusters (10) are too small to name one by one, and the middle
  settings collapse. 100 gives a readable set whose structure resembles the
  taxonomy adopted on 25 Sep, which is independent support for it, with
  one qualification: the largest cluster (6,700) mixes wealth with general
  growth and AI commentary, so it is a theme, not a clean aspect.
- Half the corpus stays noise at 100 and two-thirds at 10. Discovery
  finds structure in part of the corpus; it cannot assign every sentence,
  which is why assignment is a separate step (DESIGN decisions 4, 16).
- This labels no clusters and proposes no taxonomy: the mapping above is by
  top terms only, for the report's discussion of task 1.
