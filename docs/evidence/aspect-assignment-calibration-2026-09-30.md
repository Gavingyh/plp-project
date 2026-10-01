# Seed-centroid assignment against the human aspect labels

How well `aspects/assign.py` (a sentence gets every aspect whose centroid it
clears `similarity_floor` for; the centroid is the mean embedding of the
aspect's seed sentences) agrees with the aspect people chose, under the
10-aspect taxonomy, and whether any floor fixes it. Run 2026-09-30 on the
1,277 labelled rows of the 27 Sep round and the 44,345-sentence corpus.

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.assignment_eval
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m aspects.compare_taxonomies --sweep
```

`aspects/assignment_eval.py` reuses `assign.py`'s own centroid code and the
cached embeddings, and writes nothing.

## By floor

| floor | top-1 accuracy | recall | aspects matched per sentence (labelled / corpus) | `other` (labelled / corpus) |
|---|---|---|---|---|
| 0.55 | 0.421 | 0.887 | 8.52 / 8.34 | 1.6% / 1.3% |
| 0.60 | 0.417 | 0.857 | 7.64 / 7.42 | 2.7% / 2.3% |
| **0.65** (current) | **0.413** | **0.824** | **6.55 / 6.31** | **4.0% / 4.1%** |
| 0.70 | 0.406 | 0.731 | 4.86 / 4.80 | 6.9% / 6.9% |
| 0.75 | 0.379 | 0.596 | 2.91 / 2.91 | 17.9% / 14.2% |
| 0.80 | 0.343 | 0.430 | 1.23 / 1.24 | 39.5% / 35.7% |
| 0.85 | 0.228 | 0.241 | 0.31 / 0.31 | 76.7% / 75.6% |
| 0.90 | 0.108 | 0.109 | 0.04 / 0.03 | 96.5% / 97.4% |

Top-1 accuracy: the most similar centroid is the human aspect (`other` when
nothing clears the floor). Recall: the human aspect is among the matched
aspects. Over 1,277 rows.

**No floor makes the assignment accurate.** The floor only trades breadth
for `other`: top-1 accuracy is 0.41–0.42 up to 0.70 and falls above it. For
scale, always answering `retail_banking_sentiment`, the commonest human
aspect, scores 0.374 (477 of 1,277). Keeping the human aspect among the
matches (recall 0.82) costs 6.5 aspects per sentence, which is why the
per-aspect index rows look alike; bringing that down to about one aspect
(0.80) loses more than half the right ones and sends 36% of the corpus to
`other`.

## Where it goes wrong, at 0.65

Top-1 recall per human aspect (correct / rows): retail banking 294/477
(0.62), income and profit results 79/149 (0.53), dividend policy 13/33
(0.39), investor stock sentiment 35/89 (0.39), management guidance 28/93
(0.30), asset quality 22/78 (0.28), macro 5/22 (0.23), NIM 12/58 (0.21),
wealth 26/129 (0.20), capital and liquidity 8/49 (0.16), `other` 5/100
(0.05).

The largest confusions: retail banking read as investor stock sentiment (75)
or management guidance (51); wealth read as retail banking (54); `other`
read as wealth (36) or investor stock sentiment (23); income results read as
NIM (19) or dividend policy (14).

The centroids themselves sit close together: mean pairwise cosine distance
0.206 (0.113 for the proposal's four in September), and the closest pairs
are nearly the same direction: asset quality and capital/liquidity (cosine
0.938), NIM and income results (0.937), management guidance and retail
banking (0.905). Sentences near one are near the other, and no floor
separates them.

## What follows

Seed-centroid assignment is a baseline, not a method to tune: this file is
the baseline the LLM classifier (DESIGN decision 16) has to beat, on the
same 1,277 human labels. The floor stays at 0.65 until the team decides;
nothing here changed `config/aspects.yaml`.

## Caveats

- The labelled rows are not a random sample of sentences.
  `preprocess.export_candidates` draws (sentence, aspect) pairs, so a
  sentence matching many aspects was more likely to be drawn; the test rows
  were drawn at random from those pairs and the train/dev rows stratified by
  base FinBERT's label. Corpus-level accuracy may differ.
- `aspects.compare_taxonomies --sweep` still measures its own hard-coded
  four-aspect candidate A, not `config/aspects.yaml`, although its docstring
  says A is the current config; its output (A: 1.68 aspects per sentence and
  40.1% `other` at 0.65) describes the September taxonomy. Use
  `aspects.assignment_eval` for the current one.
