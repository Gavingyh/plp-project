# Aspect discovery — re-run on the full corpus

Run 2026-09-11 (SGT) against all 36,884 embedded sentences. The previous
discovery run recorded in `config/aspects.yaml` and `docs/data-viability.md`
used 2,888 sentences, before the full Reddit backfill and before any earnings
text existed.

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.discover
```

Raw output: `aspect-discovery-2026-09-11.raw.txt` alongside this file.

**This run was not possible before today.** `aspects.discover` fetched
sentence text with one bound SQL parameter per embedding, and SQLite caps
that at 32,766. At 36,884 sentences every invocation died with `too many SQL
variables` before reaching UMAP. The script had been fine on the
2,888-sentence corpus it was written against and became unrunnable exactly
when the corpus grew large enough for clustering to be worth doing. Fixed in
this branch and covered by `tests/test_aspect_discover.py`.

---

## Headline

| | 2026-09-06 run | this run |
|---|---|---|
| sentences | 2,888 | 36,884 |
| clusters | 9 | 281 |
| noise | 52% | 67% (24,814 sentences) |

Cluster sizes: smallest 10, median 23, largest 592. Twenty-six clusters hold
100 or more sentences; 117 hold fewer than 20. Clustered sentences total
12,070 against 24,814 left as noise.

---

## The finding that matters: analyst-style aspects finally exist

The earlier run's conclusion was that the corpus split along a coarse axis,
consumer-banking service against investment discussion, and did not subdivide
into the proposal's dividend, asset-quality, margin and guidance aspects.
That conclusion was drawn from a Reddit-only corpus and it no longer holds.

With earnings text in, clusters of exactly the kind the proposal anticipated
appear on their own:

| cluster | n | what it is |
|---|---|---|
| 10 | 17 | Leverage ratio against the regulatory minimum |
| 12 | 17 | Fee income by line (investment banking, transaction services, cards) |
| 13 | 31 | Final Basel III reforms and their CET-1 effect |
| 18 | 27 | Common Equity Tier-1, transitional against fully phased-in |
| 19 | 17 | Return on equity and return on tangible equity |

These are bank-fundamental topics stated in analyst vocabulary, and none of
them appeared in the Reddit-only run. This is direct evidence that ingesting
earnings material closed a real vocabulary gap rather than merely adding
volume, which is the strongest available justification for the effort spent
on the DBS and OCBC investor-relations fetchers and the UOB Wayback route.

Consumer-banking clusters remain, and remain distinctly Reddit: cluster 16 is
DBS Multiplier account questions, cluster 7 is savings-account bonus-rate
cuts across all three banks.

## What it does not support

**281 clusters is not a taxonomy.** With a median size of 23 sentences these
are topics, not aspects. Turning them into a taxonomy means a human grouping
them, which is the manual step the script's own closing message asks for.
Nothing here can be pasted into `config/aspects.yaml`.

**Noise rose rather than fell.** Two thirds of the corpus clusters with
nothing, up from just over half. A larger corpus did not produce cleaner
structure at these HDBSCAN settings; `min_cluster_size` was left at its
default of 10 for comparability with the earlier run, and a serious taxonomy
attempt should sweep it rather than accept this figure.

**The proposal's four aspects still do not emerge as four groups.** Real
financial topics now exist, but they are finer than `asset_quality` or
`management_guidance` and they cut across those labels. That the raw material
is present does not mean the a-priori grouping is the right one, and it does
not resolve the taxonomy decision recorded in `docs/STATUS.md`.

---

## Extraction artifacts: visible, but 2.6% of the corpus

Several clusters are made of text that should never have become sentences:

- **Cluster 0** mixes character-spaced PDF extraction (`I p r h ef a o s r e
  m`, `% ∆ in c o n s ta n t`) with French-language Reddit posts.
- **Clusters 1, 5 and 14** are earnings boilerplate and chart axis labels
  (`PrivateandConfidential`, `Sep 23 Dec 23 Mar 24 Jun 24`, `Note: Financial
  statistics as at 30 September 2021`).
- **Cluster 3** is Reddit markdown table fragments (`| 23,000 | | 2 | DBS |
  8000 |`).

Clustering makes this look worse than it is, because HDBSCAN's job is to
gather similar things and near-identical junk is highly similar. Measured
across the whole corpus with four heuristics, the prevalence is modest:

| heuristic | sentences | share | mostly from |
|---|---|---|---|
| fewer than 4 real words | 874 | 2.4% | Reddit 605, earnings 269 |
| more than 60% numeric tokens | 79 | 0.2% | earnings 75 |
| character-spaced text | 29 | 0.1% | earnings 29 |
| markdown table fragment | 20 | 0.1% | Reddit 20 |
| **any of the above** | **953** | **2.6%** | |

By source the rates are almost identical: 2.7% of earnings sentences and 2.5%
of Reddit sentences. The heuristics are deliberately crude and were written
for this measurement, so treat 2.6% as an order of magnitude rather than a
precise rate; they will miss artifacts that read as plausible prose and may
flag terse but genuine sentences.

The practical reading is that extraction quality is a real but second-order
problem. It is not distorting the sentiment index at 2.6% prevalence, and it
is worth a cleanup pass before anyone reports cluster listings in the report,
because a reader shown cluster 0 will reasonably doubt the whole corpus.

---

## Suggested next steps

1. Sweep `--min-cluster-size` before drawing any taxonomy conclusion. The
   default of 10 produces 281 clusters and 67% noise, which is too fine to be
   useful either way.
2. Add the four heuristics above to `preprocess/clean.py` as filters, or at
   minimum drop sentences with fewer than four real words. This is a small
   change with a visible effect on cluster listings.
3. Group the fundamental clusters (10, 12, 13, 18, 19) by hand and check
   whether they map onto `asset_quality`, `net_interest_margin` and
   `management_guidance` or cut across them. That is the concrete input the
   taxonomy decision needs, and it is human work.
