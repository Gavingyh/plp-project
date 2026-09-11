# Clustering with UMAP and HDBSCAN

Subject: Text Analytics (module 1) · Bloom target: Analyze / Evaluate / Create
Prerequisites: [tfidf-versus-contextual-embeddings](tfidf-versus-contextual-embeddings.md)

---

## 1. Why it matters here (Understand)

The project's unsupervised text-mining deliverable is aspect discovery: letting
the data propose which financial topics people discuss, rather than assuming
the four the proposal named. That is a clustering problem over sentence
embeddings, and it is the one place in the pipeline where the corpus gets to
answer back.

It has also produced the project's most awkward finding, which makes it good
material for the report: the clustering does not agree with the taxonomy the
system actually uses.

---

## 2. The concept (Understand / Apply)

FinBERT gives each sentence a 768-dimensional vector. Two problems follow
immediately.

**Distance stops discriminating in high dimensions.** As dimensionality grows,
the ratio between the nearest and furthest neighbour of a point tends toward
1, so "nearest" carries less and less information. Density-based clustering
depends on that ratio being meaningful.

**Most clustering algorithms force every point into a cluster.** In a corpus
of Reddit chatter, most sentences genuinely belong to no financial topic at
all, and an algorithm that assigns them anyway manufactures structure.

The pipeline addresses these in order.

### UMAP: reduce first

Uniform Manifold Approximation and Projection maps 768 dimensions down to 10
while trying to preserve local neighbourhood structure. Settings used here
(`aspects/discover.py`):

| parameter | value | effect |
|---|---|---|
| `n_neighbors` | 15 | How much local structure to preserve; higher looks more globally |
| `min_dist` | 0.0 | Lets points pack tightly, which is what a clustering step wants |
| `n_components` | 10 | Target dimensionality |
| `metric` | cosine | Right choice for text embeddings, where direction matters and magnitude does not |
| `random_state` | 42 | Reproducible, at the cost of single-threaded execution |

Note `min_dist=0.0`: for *visualisation* you would use something
like 0.1 so points spread out and are legible, but for *clustering* you want
them packed so density differences are stark.

### HDBSCAN: cluster with an opt-out

Hierarchical Density-Based Spatial Clustering of Applications with Noise
builds a hierarchy of density-connected regions and extracts the most stable
clusters. Its decisive property here: **points in no dense region are labelled
noise (`-1`) rather than forced into a cluster.**

`min_cluster_size` (10 here) is the smallest group that counts as a cluster.
It is the parameter that most changes the answer, and it was left at its
default for this run.

### Reading the clusters

Clusters come out as numbered groups with no names. `aspects/discover.py`
labels each with its top TF-IDF terms, excluding bank names, which would
otherwise dominate every cluster without distinguishing any of them.

---

## 3. Where it lives in this repo (Apply)

| what | where |
|---|---|
| UMAP + HDBSCAN + TF-IDF cluster labelling | `aspects/discover.py` |
| Cached embeddings the clustering reads | `aspects/embed_store.py` |
| The frozen taxonomy discovery is supposed to inform | `config/aspects.yaml` |
| Quantitative comparison of candidate taxonomies | `aspects/compare_taxonomies.py` |
| Full results of the 2026-09-11 run | `docs/evidence/aspect-discovery-2026-09-11.md` |

Discovery runs **once, offline**. Assignment (`aspects/assign.py`) then matches
sentences to frozen centroids every batch. Re-clustering per batch would
renumber and rename aspects between runs, so a dashboard user would watch
categories shift underneath them.

---

## 4. Analyze

### What the full-corpus run produced

| | 2026-09-06 run | 2026-09-11 run |
|---|---|---|
| sentences | 2,888 | 36,884 |
| clusters | 9 | 281 |
| noise | 52% | 67% (24,814 sentences) |

Cluster sizes: smallest 10, median 23, largest 592. Twenty-six clusters hold
100 or more sentences; 117 hold fewer than 20.

**A thirteen-fold larger corpus produced more noise, not less.** That is
counter-intuitive and worth understanding. `min_cluster_size` stayed at 10
while the corpus grew, so the *relative* density threshold effectively fell:
a group of 10 similar sentences was 0.35% of the old corpus and is 0.03% of
the new one. HDBSCAN found many more small pockets and left a larger share of
the long tail unassigned. The parameter should have scaled with the corpus,
and this run's noise figure should be read as "at these settings" rather than
as a property of the data.

### The finding that changed the project's story

The earlier conclusion, recorded in `config/aspects.yaml`, was that clustering
found only a coarse split between consumer-banking service and investment
discussion, and never subdivided into the proposal's four aspects. That was
measured on a Reddit-only corpus.

With earnings text present, clusters like these emerge unprompted:

| cluster | n | content |
|---|---|---|
| 10 | 17 | Leverage ratio against the regulatory minimum |
| 12 | 17 | Fee income by line: investment banking, transaction services, cards |
| 13 | 31 | Final Basel III reforms and their CET-1 effect |
| 18 | 27 | Common Equity Tier-1, transitional against fully phased-in |
| 19 | 17 | Return on equity and return on tangible equity |

This is the strongest evidence the project has that ingesting earnings
material brought in vocabulary the corpus lacked entirely, not just bulk. It
also does not rescue the taxonomy: these are *finer* than `asset_quality` or
`management_guidance` and cut across them.

### Garbage clusters, and a lesson about salience

Several clusters are extraction artifacts rather than topics: character-spaced
PDF text (`I p r h ef a o s r e m`), chart axis labels (`Sep 23 Dec 23 Mar 24
Jun 24`), boilerplate (`PrivateandConfidential`), Reddit markdown table
fragments, and French-language posts.

Reading a cluster listing, this looks like a corpus full of junk. Measured
across all 36,884 sentences with four crude heuristics, it is **2.6%** (2.7%
of earnings, 2.5% of Reddit).

The discrepancy is the lesson. HDBSCAN's job is to gather similar things, and
near-identical junk is extremely similar, so artifacts concentrate into tight
clusters while genuine variety spreads out. **A cluster listing systematically
over-represents low-variety content.** Judging corpus quality from cluster
samples will mislead you every time; measure prevalence directly instead.

### Comparing three approaches

| approach | forces every point into a cluster? | needs cluster count up front? | shape assumption | fits here? |
|---|---|---|---|---|
| **UMAP + HDBSCAN** | No, labels noise | No | Arbitrary, density-based | Chosen. The noise opt-out is what a mixed corpus needs |
| k-means | Yes | Yes (k) | Spherical, similar-sized | Poor. Would force 24,814 topic-less sentences into topics, and k is the thing we are trying to learn |
| LDA topic modelling | Soft, gives a distribution | Yes (number of topics) | Bag-of-words, ignores order | Reasonable, and word-based rather than embedding-based, so it would miss paraphrase. The proposal named it as an option |

The decisive criterion was the noise opt-out. In a corpus where most sentences
are Reddit chatter about bank accounts, an algorithm that insists every
sentence belongs to a financial aspect will produce a confident and false
taxonomy. HDBSCAN's 67% noise is uncomfortable to report and more honest than
a clean partition would be.

---

## 5. Evaluate

**UMAP plus HDBSCAN was the right choice, and this run under-configured it.**
The implementation has a real flaw: leaving `min_cluster_size` at its default
while the corpus grew thirteen-fold makes the 281-cluster, 67%-noise result
hard to interpret. The tooling is right and this particular run is
under-configured.

**What the evidence does not show.** Three limits:

1. **It does not validate assignment.** Every number here is geometry.
   Whether a sentence assigned to `net_interest_margin` is *about* net
   interest margin is untested, and the lexical evidence suggests often not.
2. **It does not choose a taxonomy.** 281 clusters with a median size of 23
   are topics. Converting them into an aspect set is human work.
3. **Cluster quality is unmeasured.** No silhouette score, no stability
   analysis across seeds. UMAP with a fixed `random_state` is reproducible but
   that is not the same as stable.

**When the opposite choice would be right.** If you needed every sentence
classified, k-means or LDA would be preferable, because HDBSCAN would leave
two thirds of your corpus unlabelled. That is precisely the situation
`aspects/assign.py` is in, which is why assignment uses nearest-centroid with
a floor rather than clustering.

**The honest position for the report.** Aspect discovery ran, it produced real
structure that only appeared once earnings text was ingested, and it did not
produce the proposal's four aspects. Report that clearly rather than tuning
the parameters until the clusters flatter the taxonomy.

---

## 6. Create

**Exercise (about ninety minutes).** Fix the parameter problem this page
identifies and see whether the picture changes.

```bash
# Baseline is already saved:  docs/evidence/aspect-discovery-2026-09-11.raw.txt
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.discover --min-cluster-size 50 \
    > /tmp/discover_50.log 2>&1
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.discover --min-cluster-size 150 \
    > /tmp/discover_150.log 2>&1

for f in /tmp/discover_50.log /tmp/discover_150.log; do
  echo "== $f"; grep -E "Found [0-9]+ clusters" "$f"
done
```

Each run takes several minutes, most of it UMAP. Then build a small table:
`min_cluster_size` against number of clusters, noise percentage, and median
cluster size. Read the top terms of the ten largest clusters at your best
setting.

**Expected outcome.** Larger `min_cluster_size` should give far fewer clusters
and, quite possibly, *more* noise rather than less, since small pockets that
previously formed clusters get absorbed into it. The question to answer is
whether any setting produces something recognisable as four to eight
dashboard-worthy aspects, or whether the corpus simply does not have that
structure.

**Write for the report:** the parameter sweep table, plus two or three
sentences on whether the number of clusters at your chosen setting supports
the proposal's four aspects, a coarser split, or neither.

---

## 7. Self-check

1. Why reduce to 10 dimensions with UMAP before clustering instead of
   clustering the 768-dimensional vectors directly?
2. Why `min_dist=0.0` here, when a visualisation would use a larger value?
3. Why does HDBSCAN's ability to label points as noise matter for this corpus
   specifically?
4. A thirteen-fold larger corpus gave more noise, not less. Give the most
   likely explanation.
5. Cluster listings look full of garbage, but only 2.6% of sentences are
   artifacts. Why the gap?

<details>
<summary>Answers</summary>

1. Because distance concentrates in high dimensions: the ratio of nearest to
   furthest neighbour approaches 1, so "dense region" stops being meaningful.
   Density-based clustering needs that ratio to discriminate, so reducing
   first is what makes HDBSCAN's notion of density work.
2. `min_dist` controls how tightly points may pack in the low-dimensional
   space. Clustering wants tight packing so density contrasts are sharp;
   visualisation wants points spread out so a human can see them. Different
   goals, different value.
3. Because most sentences in this corpus genuinely belong to no financial
   aspect — the dominant source is personal-finance chatter about accounts and
   cards. An algorithm that assigns every point to a cluster would invent
   topics for them and produce a confident, false taxonomy.
4. `min_cluster_size` stayed at 10 while the corpus grew, so the effective
   relative density threshold fell sharply. HDBSCAN found many more small
   pockets and left a larger share of the long tail unassigned. The parameter
   should scale with the corpus.
5. Clustering gathers similar things, and near-identical junk (repeated
   boilerplate, chart axis labels) is highly similar, so it concentrates into
   tight, visible clusters. Genuine content is varied and spreads across many
   clusters or into noise. Cluster listings therefore over-represent
   low-variety content, and prevalence must be measured directly.

</details>

---

## 8. Sources

**Repository**

- `aspects/discover.py` — parameters, TF-IDF labelling, bank-name exclusion
- `aspects/assign.py` — why the taxonomy is frozen rather than re-clustered
- `config/aspects.yaml` — the header records both discovery runs
- `docs/evidence/aspect-discovery-2026-09-11.md` and its `.raw.txt`
- `docs/evidence/extraction-quality-2026-09-11.txt` — the 2.6% measurement
- `docs/DESIGN.md` decision 4 — frozen centroids

**Measured in this repository (2026-09-11)**

- All cluster counts, sizes, noise percentages and the named example clusters,
  from the run recorded in the evidence file.

**External**

- McInnes, Healy and Melville (2018), *UMAP: Uniform Manifold Approximation
  and Projection for Dimension Reduction*, arXiv:1802.03426 — **referenced by
  name, not fetched during this pass.** Verify before citing specifics.
- HDBSCAN is documented at https://hdbscan.readthedocs.io — the installed
  version is `hdbscan>=0.8` per `requirements.txt`. **Docs not fetched during
  this pass.**

**Not verified**

- The distance-concentration explanation in section 2 is standard and is given
  here without a citation. Cite Beyer et al. (1999) or an equivalent if the
  report leans on it.
- Campello, Moulavi and Sander's original HDBSCAN paper is not cited here by
  reference; find it if the report describes the algorithm in detail.
- Whether the clusters are stable across UMAP random seeds. Not tested;
  `random_state=42` gives reproducibility, which is not the same thing.
