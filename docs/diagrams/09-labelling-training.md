# Labelling and training

How the labelled data was produced and turned into the fine-tuned model in use and its evaluation. For the report's methodology section. Diagram 21 gives the experiments that chose the configuration, with each score.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
flowchart TB
  accTitle: Labelling and training workflow
  accDescr: The aspects came from labelling 338 discovery clusters. People labelled the first round, whose 299 test rows they kept, and the broker research test rows; an LLM rater labelled every round. FinBERT was further pretrained on the corpus, fine-tuned over three seeds on the LLM rater's labels, and tested against baselines on the sentences people labelled. The chosen model scores the whole corpus beside base FinBERT.

  subgraph tax["Aspects"]
    disc["Discovery: 338 clusters<br/>aspects.discover"]
    lab["Cluster labels drafted with an AI assistant:<br/>10 aspects + other in config/aspects.yaml"]
  end

  subgraph rounds["Labelling rounds"]
    first["First round: 1,277 sentences after cleaning,<br/>labelled by two people;<br/>978 train/dev, 299 test<br/>preprocess.export_candidates, export_blind_test"]
    agree["Sentiment kappa 0.93 between the two people<br/>train.agreement"]
    later["Broker research, top-up and active-learning rounds;<br/>100 broker research test rows labelled by people"]
    rater["An LLM rater labels every round, blind to the other labels:<br/>kappa 0.79 on sentiment, 0.80 on aspect with people<br/>train.rater_labels"]
    tests["Test rows, kept out of training,<br/>with people's labels:<br/>299 first-round, 100 broker research"]
  end

  subgraph use["Training"]
    dapt["Further pretraining on 42,822 corpus sentences,<br/>labelled ones and near-copies left out<br/>train.dapt"]
    ft["Fine-tune on 1,563 (sentence, aspect) pairs<br/>with the LLM rater's labels, seeds 42, 1, 7<br/>train.finetune"]
    ev["Test on people's labels, three seeds averaged:<br/>299 first-round rows, macro-F1 0.670 against 0.571;<br/>100 broker research rows, 0.770 against 0.687<br/>train.evaluate"]
  end

  base["Baselines: base FinBERT,<br/>VADER lexicon, TF-IDF + logistic regression"]
  rescore["Every stored sentence scored by the chosen model,<br/>beside base FinBERT<br/>scripts/rescore.py"]

  disc --> lab --> first
  first --> agree
  first --> rater
  later --> rater
  first --> tests
  later --> tests
  rater -- "training rows" --> ft
  dapt --> ft --> ev
  tests --> ev
  base --> ev
  ev --> rescore
```

Rendered for the report: [SVG](img/09-labelling-training.svg) · [PNG](img/09-labelling-training.png)

## What this shows and doesn't show

Every step has run. The first round's candidates were stratified within a 12,000-pair
sample scored on Colab, not the whole corpus. In that round the annotators corrected the
aspect once and shared it, so only sentiment agreement between the two people was measured
(kappa 0.93). Each annotator's blind test labels match their labels on the same rows in the
candidates sheet, where an LLM's suggestion was visible, so the test labels are not
independent of it. Cleaning removed 18 duplicate rows and 5 sentences that were in both
splits.

The model in use is trained on the LLM rater's labels, not on people's: 1,563 pairs from
four rounds (917 first-round, 275 broker research, 240 top-up, 131 active-learning), after
leaving out the rows the rater flagged as not about the bank. People's labels are used to test it: the
299 first-round test rows and 100 broker research rows, none of them in training, and none
of the labelled sentences in the further pretraining. The first fine-tuning on people's
labels alone scored 0.547 against base FinBERT's 0.571; how the configuration then improved
is diagram [21](21-sentiment-model-development.md). Version 1 of the candidate sheet
(September, four aspects) was never labelled and is not drawn.

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| discovery | `aspects/discover.py:49` | `def run(min_cluster_size: int = 10)` |
| 338 clusters | `docs/evidence/aspect-taxonomy-2026-09-25.md:11` | `338 clusters, 27,949 noise points (65%)` |
| labels drafted with an AI assistant | `docs/evidence/aspect-taxonomy-2026-09-25.md:16` | `notes record that an AI assistant (Claude, in a chat session) drafted` |
| export candidates | `preprocess/export_candidates.py:59` | `def export(train_dev_target: int` |
| LLM suggestions on the first round | `train/llm_prelabel.py:146` | `def run(model: str = DEFAULT_MODEL` |
| blind test sheet | `preprocess/export_blind_test.py:104` | `def export_blind(` |
| clean the labels | `train/labels.py:130` | `def prepare(candidates_path: str, blind_path: str, out_path: str,` |
| agreement | `train/agreement.py:125` | `def score(pairs: pd.DataFrame` |
| kappa 0.93 | `docs/evidence/annotation-agreement-2026-09-27.md:34` | `| candidates, both splits | 1,277 | 0.952 | **0.926** |` |
| the LLM rater's rounds | `train/rater_labels.py:273` | `def extra_batches(name: str) -> list[str]:` |
| the rater's agreement with people | `docs/model-card.md:37` | `kappa 0.80 on aspect and 0.79 on sentiment` |
| training rows, four rounds | `docs/model-card.md:36` | `917 first-round, 275 broker research, 240 top-up, 131 active-learning` |
| further pretraining | `train/dapt.py:221` | `def run(out_dir: str, epochs: float = 3` |
| 42,822 pretraining sentences | `docs/model-card.md:34` | `42,822 of the corpus's 45,844 sentences` |
| fine-tune | `train/finetune.py:269` | `def run(seed: int = 42` |
| trained on the LLM rater's labels | `train/finetune.py:7` | `` served models were trained with `--labels` on the LLM rater's labels `` |
| evaluate | `train/evaluate.py:139` | `def run(model_dir: str` |
| baseline: base FinBERT | `train/evaluate.py:46` | `def eval_base_finbert_zeroshot(` |
| baseline: lexicon | `train/evaluate.py:55` | `def eval_lexicon(` |
| baseline: TF-IDF + logistic regression | `train/evaluate.py:70` | `def eval_tfidf_logreg(` |
| test result | `docs/model-card.md:53` | `| | **three seeds averaged** | **0.716** | **0.670** |` |
| broker research test result | `docs/model-card.md:55` | `| | **three seeds averaged** | **0.770** | **0.770** |` |
| corpus scored with the chosen model | `scripts/rescore.py:197` | `def apply(conn, aspects` |
| first fine-tuning below base | `docs/evidence/finetune-2026-09-30.md:36` | `**Fine-tuning did not beat base FinBERT on macro-F1.**` |
| sample-stratified candidates | `notebooks/README.md:17` | `Candidates were stratified within that sample` |
