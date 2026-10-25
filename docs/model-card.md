# FinBERT adapted and fine-tuned for aspect-based sentiment on Singapore bank text

*Model card for the three fine-tuned models the PLP project serves. The
project measures sentiment towards DBS, OCBC and UOB, by bank and by topic
("aspect"). The three models are seeds 42, 1 and 7 of one configuration;
their probabilities are averaged, and each scores sentences about any of
the three banks. Upload this file as the `README.md` of the Hugging Face
model repo; see "Sharing the data and models" in the project README.*

## Model

- **Task:** three-class sentiment (`negative`, `neutral`, `positive`) of a
  sentence *towards one of the three banks on one aspect*.
- **Input:** a sentence pair, `[CLS] sentence [SEP] aspect [SEP]`, at most
  128 tokens. The aspect is the readable label from `config/aspects.yaml`
  (for example "Dividend Policy", "Net Interest Margin"), as recorded in
  each folder's `input_format.json`.
- **Base:** [`ProsusAI/finbert`](https://huggingface.co/ProsusAI/finbert),
  BERT further trained on a large financial corpus and fine-tuned for
  financial sentiment on the Financial PhraseBank ("FinBERT: Financial
  Sentiment Analysis with Pre-trained Language Models", arXiv:1908.10063).
- **Two training stages on top of it:** the encoder's masked-word training
  was continued on the project's own corpus, so that it meets forum
  language and local product names before any label; it was then fine-tuned
  for the task.
- **Three seeds, averaged.** The averaged model scores above every single
  seed on the test sentences (0.670 against 0.628, 0.657 and 0.662; below);
  with three seeds, that averaging helps in general is not established.

## Training

| | |
|---|---|
| pretraining data | 42,822 of the corpus's 45,844 sentences (Reddit, bank earnings reports, news, broker research). Left out: every labelled sentence (2,270 rows) and anything resembling one: 37 with the same text, 147 containing or contained in one, 568 sharing most of their words |
| pretraining method | masked-language modelling for 3 epochs, learning rate 5e-5, batch 32, at most 64 tokens |
| fine-tuning data | 1,563 labelled sentence-aspect pairs (616 positive, 586 neutral, 361 negative) from four labelling rounds: 917 first-round, 275 broker research, 240 top-up, 131 active-learning. Each seed trains on 1,328 and early-stops on the other 235 |
| labels | **from a large language model, not from people.** A hosted LLM, run as independent raters blind to every other label, labelled the sentences for aspect and sentiment under the project's annotation guideline. On the 1,277 first-round sentences it agrees with the two human annotators at kappa 0.80 on aspect and 0.79 on sentiment. Left out of training: the rows it flagged as not about the bank, and one near-copy of a test sentence |
| fine-tuning method | Hugging Face `Trainer`: AdamW, learning rate 2e-5, batch 16, 10% linear warm-up then linear decay, up to 8 epochs, early stopping on dev macro-F1 with the best epoch kept, plain cross-entropy |
| selection | the configuration by 5-fold cross-validation; the choice between candidate models by a rule written down before the test sentences were scored (test macro-F1 over three seeds, cross-validation as the tie-breaker) |
| hardware | Apple M1 GPU (MPS); not bit-for-bit reproducible |

## Evaluation

The test sentences carry **people's labels** and were never used in
training, tuning or pretraining: 299 drawn at random from the first round
(166 neutral, 94 positive, 39 negative) and 100 from broker research (42
positive, 35 neutral, 23 negative).

| test sentences | model | accuracy | macro-F1 | negative P / R | neutral P / R | positive P / R |
|---|---|---|---|---|---|---|
| first round, 299 | base FinBERT, no fine-tuning | 0.699 | 0.571 | 0.53 / 0.21 | 0.68 / 0.91 | 0.79 / 0.53 |
| | seed 42 / 1 / 7 | 0.666 / 0.706 / 0.696 | 0.628 / 0.657 / 0.662 (mean 0.649, sd 0.018) | | | |
| | **three seeds averaged** | **0.716** | **0.670** | 0.48 / 0.59 | 0.81 / 0.73 | 0.69 / 0.73 |
| broker research, 100 | base FinBERT, no fine-tuning | 0.690 | 0.687 | 0.70 / 0.83 | 0.68 / 0.49 | 0.69 / 0.79 |
| | **three seeds averaged** | **0.770** | **0.770** | 0.70 / 0.91 | 0.77 / 0.69 | 0.82 / 0.76 |
| both, 399 | base FinBERT, no fine-tuning | 0.697 | 0.648 | 0.64 / 0.44 | 0.68 / 0.84 | 0.75 / 0.61 |
| | **three seeds averaged** | **0.729** | **0.709** | 0.56 / 0.71 | 0.80 / 0.73 | 0.73 / 0.74 |

P / R is precision and recall.

- **Where the gain is.** On the first-round sentences base FinBERT finds
  21% of the negative sentences and 53% of the positive ones; the averaged
  model finds 59% and 73%. It pays in neutral recall, 0.91 to 0.73.
- **Accuracy is not where it leads.** On those 299 sentences the averaged
  model is right on 41 that base FinBERT gets wrong and wrong on 36 that
  base FinBERT gets right (exact McNemar p = 0.65;
  `data/eval/model-rerun-2026-10-11/report_data.json`). The lead is in how the
  errors are spread across the classes, which macro-F1 measures, not in the
  number of errors.
- **By source,** accuracy is 0.81 on earnings text (79 sentences), 0.77 on
  broker research (100), 0.68 on Reddit (184) and 0.68 on Google News (34).
- **Against plain fine-tuning.** The same labels without the pretraining
  stage score 0.631 mean macro-F1 on the first-round sentences. Over 15
  paired cross-validation folds the pretrained encoder is ahead by 0.014,
  in 11 of the 15 (p = 0.016).
- **No neutral threshold.** A margin for calling a sentence neutral was
  chosen on 601 held-out training rows and came out at zero: the most
  likely class is used as it is. Class weights and source weights were
  tried on this configuration and did not improve cross-validation.

Confusion on the 299 first-round sentences, three seeds averaged (rows are
people's labels):

| | called negative | called neutral | called positive |
|---|---|---|---|
| negative (39) | 23 | 11 | 5 |
| neutral (166) | 18 | 122 | 26 |
| positive (94) | 7 | 18 | 69 |

## How to use

```python
import numpy as np, torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

sentence = "DBS raised its quarterly dividend to 60 cents."
aspect = "Dividend Policy"                       # the readable label from config/aspects.yaml
probs = []
for seed in ("seed_42", "seed_1", "seed_7"):
    path = f"models/experiments-2026-10-11/dapt/{seed}/final"
    tok = AutoTokenizer.from_pretrained(path)
    model = AutoModelForSequenceClassification.from_pretrained(path).eval()
    with torch.no_grad():
        logits = model(**tok(sentence, aspect, truncation=True, max_length=128, return_tensors="pt")).logits
    probs.append(torch.softmax(logits, -1).numpy()[0])
neg, neu, pos = np.mean(probs, axis=0)                 # labels 0, 1, 2
label = ("negative", "neutral", "positive")[int(np.argmax([neg, neu, pos]))]
```

To get the models, download the `adapted-2026-10-11/` folder of this repo
and place it at `models/experiments-2026-10-11/dapt/` (commands in the
project README, "Sharing the data and models"). In the project,
`train/evaluate.py` and `aggregate/preview.py` load the models this way, and `config/model_version.py` lists them under the version
the product serves, `finbert-adapted-finetuned-2026-10-11-3seed-m0`.

## Limitations

- **The training labels are an LLM's.** They agree with people at kappa
  about 0.8, below the 0.93 the two human annotators reached with each
  other, and no person has checked them row by row. The models are tested
  only against people's labels.
- **Training and test labels follow different rules for retail products.**
  The training labels treat a product's fee or perk as sentiment towards
  the bank; the first-round test labels were made earlier, when such
  sentences were neutral. Some of the measured error on negative and
  positive is the rule, not the model. How much is not measured.
- **About half of what it calls negative, people did not** (precision 0.48
  on the first-round sentences). With 39 negative test sentences, one
  sentence moves negative recall by about 0.03.
- **The score depends a little on the aspect.** The aspect's name is part
  of the input, so the same sentence can be labelled differently under
  another aspect: when the project re-filed 6,914 corpus sentences under
  other aspects, 896 of them changed label, mostly from positive to neutral.
  An error in the aspect therefore reaches the sentiment.
- **Test labels were made with a model's suggestion in view.** Annotators of
  the first round saw a small local model's suggested label and kept it on
  about nine rows in ten, test rows included. This favours any model that
  resembles the suggester; neither base FinBERT nor these models is that
  model, but the first-round test set is not a blind one. The broker
  research test sentences were labelled with no suggestion.
- **Local context.** Singapore product names are common in the data ("UOB
  One", "OCBC 360"), and descriptions of product features are where earlier
  models made most of their errors. Singlish is barely measured: only about
  a dozen labelled sentences contain any Singlish, slang or emoji.
- **Not investment advice.** The scores describe what people wrote, not how
  the banks will perform.

## Publication

- **Published.** The weights are in the public Hugging Face model repo
  `plp-bank-sentiment/plp-finbert-absa`, folder `adapted-2026-10-11/`, and
  download without a login.
- **Still open: the licence.** This card declares none yet. The models are
  built on `ProsusAI/finbert`, whose licence the team's to-do page records
  as CC BY-NC-SA 4.0 (credit, non-commercial use, the same licence); the
  team has to confirm it and add it here.
- **Still open: the labeller's terms.** The training labels came from a
  hosted LLM. Its provider's terms on using a model's outputs to train
  another model have not been recorded here.
- **The text stays within the team.** The training text includes Reddit
  posts, news, CNA articles and broker research. The weights hold no text,
  but the corpus itself is shared only with the team and the assessors.

## Files and checksums

Each folder holds `config.json`, `model.safetensors` (437,961,724 bytes),
`tokenizer.json`, `tokenizer_config.json` and `input_format.json`.
`training_args.bin` and `dev_ids.json` are left out of any upload: the first
records a local path, and nothing needs either to load the model.

| folder (`adapted-2026-10-11/` in this repo, `models/experiments-2026-10-11/dapt/` in the project) | SHA-256 of `model.safetensors` |
|---|---|
| `seed_42/final` | `1677836f4ee226f2bcb5839dae8e6f2a2a30fd7ed8440c64fce4b3263e33d41c` |
| `seed_1/final` | `8ef23d69590fcf8a03e1cfbcafd321d3fc45c0e1299fd6a5961c8ebdbcaf2028` |
| `seed_7/final` | `627548907b1cd859ce7b10800c933bb177df2646b072ce6376443a9f860e47c4` |

## Earlier models

An earlier set, trained on people's labels alone
(`models/experiments-2026-10-01/label/`), scored mean macro-F1 0.604 (sd
0.035) on the same 299 sentences. It was used in early comparisons and never
served; its card is this file's earlier version in git.

Evidence: `docs/evidence/model-rerun-2026-10-11.md` (every candidate, with
precision and recall on three sets of test sentences),
`docs/evidence/llm-rater-new-rules-2026-10-10.md` (the labels),
`docs/evidence/rescore-wealth-wording-2026-10-14.md` (the dependence on the
aspect).
