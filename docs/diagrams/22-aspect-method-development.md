# How the aspect method was chosen

From discovering the aspects to classifying sentences into them: what was tried, how each was measured against the human aspect labels, and what waits for the team. For the report's solution-approach section. Evidence: `aspect-taxonomy-2026-09-25`, `aspect-discovery-sweep-2026-09-30`, `aspect-assignment-calibration-2026-09-30`, `llm-aspect-classifier-2026-10-01`, `opus-labeller-2026-10-01`, `labelling-topup-2026-10-01`.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
flowchart TB
  accTitle: Aspect method development
  accDescr: FinBERT sentence embeddings are reduced with UMAP and clustered with HDBSCAN; the clusters were labelled into ten aspects. Seed-centroid assignment by cosine similarity was calibrated against the human aspect labels and found weak at any floor. A local LLM choosing one aspect from a fixed list was evaluated on the same labels and was far better, more so where two models agree; Opus 5.5 gives a reference. The classifier's answers for the corpus are being cached; applying them, and distilling them into a smaller model, wait.

  emb["FinBERT sentence embeddings<br/>mean-pooled, 768-d<br/>aspects.embed_store"]
  disc["Discovery: UMAP to 10-d (cosine)<br/>then HDBSCAN; min_cluster_size swept<br/>aspects.discover"]
  tax["10 aspects + other<br/>config/aspects.yaml (DESIGN 21)"]
  cent["Seed-centroid assignment:<br/>cosine to each aspect's centroid, floor 0.65<br/>aspects.assign"]
  cal["Against 1,277 human aspects:<br/>top-1 0.413 (commonest aspect 0.374),<br/>6.4 aspects a sentence; no floor fixes it"]
  llm["LLM, zero-shot: one aspect from a JSON-schema list<br/>temperature 0; llama3.1:8b, qwen3:4b without thinking<br/>aspects.llm_classify"]
  ev["Against the same labels:<br/>llama 0.729 · qwen 0.719<br/>where both agree (76%): 0.835"]
  opus["Opus 5.5 as a reference rater<br/>0.842, κ 0.80 with people"]
  top["Blind top-up sheet for the five thin aspects<br/>checked by Opus: macro falls short"]
  cache["Corpus answers cached, resumable<br/>no database writes"]
  apply["Apply to the database, with a rule<br/>for where the two models disagree<br/>(planned, team decision, DESIGN 16)"]
  distil["Distil into a FinBERT classifier<br/>(planned, terms to check)"]

  emb --> disc --> tax --> cent --> cal
  tax --> llm --> ev
  ev --> opus
  ev --> top
  ev --> cache
  cache -. planned .-> apply
  opus -. planned .-> distil
  style apply stroke-dasharray: 5 5
  style distil stroke-dasharray: 5 5
```

Rendered for the report: [SVG](img/22-aspect-method-development.svg) · [PNG](img/22-aspect-method-development.png)

## What this shows and doesn't show

Why the pipeline's aspect method should change, and how each option was measured. Not shown: the per-aspect scores and confusions, the 338 discovery clusters, or the prompt text; they are in the evidence files and `aspects/llm_classify.py`.

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| UMAP reduction | `aspects/discover.py:90` | `reducer = umap.UMAP(n_neighbors=15, min_dist=0.0, n_components=10, metric="cosine",` |
| HDBSCAN clustering | `aspects/discover.py:95` | `clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean")` |
| similarity floor | `config/aspects.yaml:224` | `similarity_floor: 0.65` |
| calibration against human aspects | `aspects/assignment_eval.py:52` | `def label_metrics(sims: np.ndarray, aspects: list[str], human: list[str], floor: float) -> dict:` |
| one aspect from a fixed list | `aspects/llm_classify.py:97` | `"format": {"type": "object", "properties": {"aspect": {"type": "string", "enum": keys}},` |
| temperature 0 | `aspects/llm_classify.py:99` | `"options": {"temperature": 0},` |
| corpus cache | `aspects/llm_classify.py:160` | `def corpus_rows(conn, seed: int = 2026, limit: int | None = None) -> pd.DataFrame:` |
| Opus rounds | `train/opus_labels.py:269` | `def extra_batches(name: str) -> list[str]:` |
| top-up sheet | `preprocess/export_topup.py:97` | `def select(pool: pd.DataFrame, llm_aspect: pd.Series, targets: dict[str, int]) -> pd.DataFrame:` |
