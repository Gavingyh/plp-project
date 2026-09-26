# Labelling and training

How labelled data is produced and turned into the fine-tuned model and its evaluation, as built and as planned. For the report's methodology section, and for the team, since this is the critical path.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
flowchart TB
  accTitle: Labelling and training workflow
  accDescr: Version 1 exported and pre-labelled candidates but was never labelled. Version 2, planned, classifies aspects first, re-draws candidates and labels aspect and sentiment. Training and evaluation are written but have never run.

  subgraph v1["Version 1, as built: stopped before annotation"]
    exp["Export 997 candidates<br/>preprocess.export_candidates"]
    pre1["LLM pre-labels, sentiment only<br/>train.llm_prelabel"]
    blind1["Blind test sheet<br/>preprocess.export_blind_test"]
    ann1["Annotation: not started,<br/>superseded by version 2"]
  end

  subgraph v2["Version 2 (planned, DESIGN 16 and 17)"]
    cls["LLM aspect classifier<br/>over every sentence"]
    redraw["Re-draw candidates<br/>Reddit, earnings, news"]
    pre2["Pre-label train/dev only"]
    blind2["New blind test sheet"]
    ann2["People label aspect and sentiment,<br/>or flag not about the bank"]
  end

  subgraph train["Built, never run: nothing is labelled yet"]
    agree["Agreement on 150 shared rows<br/>Cohen's kappa, train.agreement"]
    merge["Merge blind labels<br/>into the candidate set"]
    ft["Fine-tune FinBERT<br/>train.finetune"]
    ev["Evaluate on the frozen test split<br/>train.evaluate"]
  end

  base["Baselines: base FinBERT zero-shot,<br/>VADER lexicon, TF-IDF + logistic regression"]
  rescore["Re-score the corpus with the fine-tuned model<br/>(planned, PLAN section 5)"]

  exp --> pre1 --> blind1 --> ann1
  cls -.-> redraw -.-> pre2 -.-> blind2 -.-> ann2
  ann1 -. "was the route" .-> agree
  ann2 -.-> agree
  agree --> merge --> ft --> ev
  base --> ev
  ev -.-> rescore

  classDef planned stroke-dasharray: 5 5,color:#555,fill:#fafafa;
  class cls,redraw,pre2,blind2,ann2,rescore planned;
```

Rendered for the report: [SVG](img/09-labelling-training.svg) · [PNG](img/09-labelling-training.png)

## What this shows and doesn't show

Version 1 got as far as the sheets: 997 candidates, pre-labelled by a local model, with
a blind sheet for the test split. No one has labelled a row, and the team decided on
2026-09-26 not to label that sheet (DESIGN decision 17). Version 2 classifies aspects with
an LLM first (decision 16), so labels attach to the right aspect, then re-draws candidates
including news. Everything in the bottom box is written and tested but has never run, for
lack of labels. Planned in version 2 but not drawn: agreement reported separately for
aspect and sentiment, fine-tuning across at least three seeds, and evaluation of aspect
categorisation and NER alongside sentiment (PLAN section 3).

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| export candidates | `preprocess/export_candidates.py:59` | `def export(train_dev_target: int` |
| LLM pre-labels | `train/llm_prelabel.py:146` | `def run(model: str = DEFAULT_MODEL` |
| blind test sheet | `preprocess/export_blind_test.py:104` | `def export_blind(` |
| merge blind labels | `preprocess/export_blind_test.py:127` | `def merge_labels(` |
| agreement | `train/agreement.py:179` | `def run(file_a: str | None = None` |
| Cohen's kappa | `train/agreement.py:103` | `def score(pairs: pd.DataFrame)` |
| fine-tune | `train/finetune.py:94` | `def run(seed: int = 42` |
| evaluate | `train/evaluate.py:104` | `def run(model_dir: str | None):` |
| baseline: base FinBERT | `train/evaluate.py:43` | `def eval_base_finbert_zeroshot(` |
| baseline: lexicon | `train/evaluate.py:52` | `def eval_lexicon(` |
| baseline: TF-IDF + logistic regression | `train/evaluate.py:67` | `def eval_tfidf_logreg(` |
| version 1 superseded, don't label | `docs/annotation-guideline.md:7` | `don't label the current` |
| version 2: aspect and sentiment | `docs/PLAN.md:38` | `**Annotators record aspect and sentiment for each sentence**` |
| agreement on 150 shared rows | `docs/PLAN.md:152` | `Two people label the same 150 rows first` |

## Planned elements

| element | recorded in |
|---|---|
| LLM aspect classifier | DESIGN.md decision 16 |
| Re-drawn candidates, aspect + sentiment labelling | DESIGN.md decision 17; PLAN.md section 6 |
| Re-scoring the corpus | PLAN.md section 5, week of 12 Oct |
