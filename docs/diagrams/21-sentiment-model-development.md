# How the sentiment model was trained and tuned

The sequence of experiments behind the fine-tuned FinBERT, from the first run to the check on two more seeds, with the score each step produced. For the report's solution-approach and results sections. Evidence: `finetune-2026-09-30`, `finetune-experiments-2026-09-30`, `finetune-fixes-2026-10-01`, `error-analysis-2026-10-01`, `noise-floor-cv-2026-10-02`.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
flowchart TB
  accTitle: Sentiment model development
  accDescr: Labels are split into train/dev and a frozen random test split. FinBERT is fine-tuned on sentence and aspect pairs. Training length was chosen on dev, the aspect input on cross-validation, then one change at a time was cross-validated against a baseline and chosen by a rule fixed in advance. Three seeds were trained and scored once on test, errors analysed, a neutral margin chosen on dev, and the choice re-checked on two more seeds. Scoring the corpus with the model waits for the team.

  data["1,277 labelled sentences<br/>978 train/dev (stratified) · 299 test (random, frozen)<br/>train.labels"]
  base["Baselines on the test split<br/>VADER 0.427 · TF-IDF + logistic regression 0.515<br/>FinBERT zero-shot 0.571 (macro-F1)"]

  subgraph s1["30 Sep: the first runs"]
    r1["FinBERT on (sentence, aspect) pairs<br/>4 epochs, lr 2e-5, batch 16, early stopping<br/>test 0.547"]
    e1["8 epochs, chosen on dev (0.637 against 0.616)<br/>test 0.577"]
    e3["5-fold cross-validation:<br/>the aspect input beats sentence-only in 5 of 5 folds"]
  end

  subgraph s2["1 Oct: one change at a time, 5-fold CV"]
    bug["Code read before training:<br/>class weights were never applied"]
    var["Against the baseline (0.621):<br/>balanced weights 0.630 · source weights 0.633<br/>readable aspect label 0.637 · prior weights 0.525"]
    rule["Rule fixed beforehand: the combination (0.635)<br/>or the best single change (0.637)"]
    fin["Readable label, seeds 42, 1, 7<br/>test 0.604 ± 0.035, scored once"]
  end

  subgraph s3["1 Oct: errors and the decision threshold"]
    err["Error analysis: most errors are<br/>neutral sentences called polar"]
    mar["Neutral margin chosen on dev,<br/>three models averaged:<br/>test 0.624, accuracy 0.682"]
  end

  cv3["2 Oct: seeds 1 and 7 cross-validated<br/>readable label +0.005 over 15 paired folds:<br/>no measurable effect"]
  apply["Score the corpus with it<br/>(planned, team decision, PLAN section 5)"]

  data --> base
  data --> r1 --> e1 --> e3 --> bug --> var --> rule --> fin --> err --> mar --> cv3
  mar -. planned .-> apply
  style apply stroke-dasharray: 5 5
```

Rendered for the report: [SVG](img/21-sentiment-model-development.svg) · [PNG](img/21-sentiment-model-development.png)

## What this shows and doesn't show

How the configuration was chosen, and what each step scored. The rule throughout: choose on dev or cross-validation, score the test split once per final configuration. Not shown: the padding check (no effect), per-class scores, and the per-seed epochs; they are in the evidence files.

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| frozen test split | `train/labels.py:72` | `def check_splits(df: pd.DataFrame) -> None:` |
| sentence and aspect pairs | `train/finetune.py:225` | `enc = tokenizer(texts, aspect_inputs(df, aspect_text), truncation=True, max_length=128)` |
| early stopping | `train/finetune.py:331` | `callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],` |
| chosen on dev macro-F1 | `train/finetune.py:316` | `metric_for_best_model="macro_f1",` |
| 5-fold cross-validation | `train/finetune.py:232` | `def fold_split(train_dev_df: pd.DataFrame, folds: int, fold: int, seed: int):` |
| class weights, now applied | `train/finetune.py:372` | `parser.add_argument("--class-weights", choices=["none", "balanced", "prior"], default="none")` |
| readable aspect label | `train/finetune.py:375` | `parser.add_argument("--aspect-text", choices=["key", "label"], default="key",` |
| zero-shot baseline | `train/evaluate.py:47` | `def eval_base_finbert_zeroshot(df: pd.DataFrame) -> dict:` |
| lexicon and TF-IDF baselines | `train/evaluate.py:71` | `def eval_tfidf_logreg(train_dev_df: pd.DataFrame, test_df: pd.DataFrame) -> dict:` |
| neutral margin | `train/error_analysis.py:58` | `def apply_margin(` |
| margin chosen on dev | `train/error_analysis.py:67` | `def best_margin(` |
