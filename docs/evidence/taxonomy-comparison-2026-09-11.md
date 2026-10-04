# Aspect taxonomy comparison — re-run on the full corpus

Run 2026-09-11 (SGT), against 36,884 embedded sentences. The previous
comparison recorded in `docs/data-viability.md` was run on 2,888 sentences,
before the full Reddit backfill and before any earnings text existed.

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.compare_taxonomies --sweep
```

`docs/DESIGN.md` decision 5 says to re-sweep when the corpus or taxonomy
changes materially. Both changed: the corpus grew about 13x and gained the
earnings vocabulary the proposal aspects are written in.

---

## The tool was measuring at the wrong floor

Before this run, `aspects/compare_taxonomies.py` carried
`SIMILARITY_FLOOR = 0.35` as a module constant, while `config/aspects.yaml`
had been recalibrated to `0.65` on 2026-09-06 and `aspects/assign.py` — the
code that actually populates `sentence_aspects` — reads the config value.

So the comparison was answering a question about a floor the pipeline had
stopped using two days earlier, and reproducing the already-known "0.35
separates nothing" result as though it were a fresh finding about the
enriched corpus. The first run of this job produced exactly that table and it
would have been misleading to act on.

The tool now reads `similarity_floor` from `config/aspects.yaml` by default,
takes `--floor` to override, and `--sweep` to produce the grid below. It does
not write to the config.

---

## Results at the production floor (0.65)

| candidate | aspects | avg matched/sentence | % other | centroid separation | avg top similarity |
|---|---|---|---|---|---|
| A — proposal-aligned | 4 | 1.80 | 37.3% | 0.1125 | 0.6577 |
| B — data-derived coarse | 2 | 1.69 | 7.7% | 0.1695 | 0.7688 |
| C — data-derived fine | 3 | 2.38 | 8.5% | 0.2222 | 0.7643 |

Candidate A is the proposal's `dividend_policy` / `asset_quality` /
`net_interest_margin` / `management_guidance`. B and C draw their seed terms
from real cluster exemplars found by `aspects/discover.py`, not from
invention; see that module's docstring.

## Full sweep

| floor | A avg/sent | A %other | B avg/sent | B %other | C avg/sent | C %other |
|---|---|---|---|---|---|---|
| 0.35 | 3.87 | 1.0% | 1.98 | 0.6% | 2.96 | 0.3% |
| 0.50 | 3.41 | 9.5% | 1.91 | 2.0% | 2.82 | 1.7% |
| 0.60 | 2.55 | 23.7% | 1.80 | 4.5% | 2.61 | 4.7% |
| **0.65** | **1.80** | **37.3%** | **1.69** | **7.7%** | **2.38** | **8.5%** |
| 0.70 | 0.94 | 57.9% | 1.49 | 14.5% | 1.96 | 15.9% |
| 0.75 | 0.26 | 83.7% | 1.11 | 28.6% | 1.26 | 31.4% |
| 0.80 | 0.03 | 97.9% | 0.55 | 55.8% | 0.50 | 61.8% |

Centroid separation and average top similarity do not vary with the floor.
They are properties of where the seed terms land in FinBERT's embedding
space, so they are the columns a floor change cannot flatter.

---

## What this says, and what it does not

**Centroid separation is the finding that survives any floor choice.** The
proposal taxonomy's four centroids are the least distinct of the three
candidates, at 0.1125 mean pairwise cosine distance against 0.1695 for the
coarse candidate and 0.2222 for the fine one. Because that number is
computed from the seed embeddings alone, no threshold tuning changes it. The
proposal's four aspects sit closer together in FinBERT's space than either
data-derived alternative.

**Candidate A cannot reach a usable operating point.** Reading down its
column, there is no floor at which it both discriminates and retains the
corpus. At 0.60 it still matches 2.55 of 4 aspects per sentence. At 0.65 it
discards 37.3% of the corpus to `other`. At 0.70 it discards 57.9%. The
choice on offer is "most sentences match most aspects" or "most sentences
match nothing", which is what a taxonomy whose centroids are 0.11 apart
looks like from the outside.

**The two data-derived candidates degrade far more gracefully.** B holds
between 1.98 and 1.11 matches per sentence across the entire 0.35 to 0.75
range while keeping `other` under 30%. C behaves similarly with one more
aspect. Both keep more of the corpus at every floor than A does.

**The earlier recalibration numbers no longer describe the corpus.**
`config/aspects.yaml` and `docs/data-viability.md` record that moving the
floor to 0.65 took candidate A from 3.97/4 matched to "roughly 2.3/4" with
`other` at "~31%". On the full corpus the same floor gives 1.80/4 and 37.3%.
The direction was right and the magnitudes have moved, which is the expected
consequence of adding 34,000 sentences.

### What it does not say

- It does not say B or C is the right taxonomy. They score better on
  separation and graceful degradation, and they are also coarser, so some of
  that advantage is arithmetic: fewer, broader aspects are easier to keep
  apart. A two-aspect taxonomy that cleanly separates "consumer banking" from
  "investment discussion" may still be useless for a dashboard whose whole
  promise is dividend, asset-quality, margin and guidance breakdowns.
- It does not measure whether assignments are *correct*. Every number here is
  geometry. `docs/STATUS.md` records the concrete accuracy problem — Reddit
  sentences assigned to `net_interest_margin` when the Reddit corpus contains
  zero occurrences of the phrase — and nothing in this table addresses it.
- It does not account for the proposal commitment. Dropping the four a-priori
  aspects is a change to what was proposed and needs a team decision,
  explained in the report, not a config edit.

### Suggested next step for the team

The honest options are to keep A and accept that a third of the corpus is
unclassified, adopt C and re-map the dashboard's aspect labels, or keep A for
earnings text while letting Reddit fall to a coarser split. Deciding needs a
human judgement about the deliverable, so this file stops at the evidence.
