# FinBERT fine-tuned for aspect-based sentiment on Singapore bank text

*Model card for three fine-tuned FinBERT models from the PLP project, which
measures sentiment towards DBS, OCBC and UOB. The three are seeds 42, 1 and 7
of one configuration, and each scores sentences about any of the banks.
Upload it as the `README.md` of a Hugging Face model repo; see
"Sharing the data and models" in the project README.*

## Model

- **Base:** [`ProsusAI/finbert`](https://huggingface.co/ProsusAI/finbert),
  BERT further trained on a large financial corpus and fine-tuned for
  financial sentiment on the Financial PhraseBank (its
  [model card](https://huggingface.co/ProsusAI/finbert); "FinBERT: Financial
  Sentiment Analysis with Pre-trained Language Models", arXiv:1908.10063).
  Check its licence before publishing these models publicly.
- **Task:** three-class sentiment (`negative`, `neutral`, `positive`) of a
  sentence *towards one of the three banks on one aspect*.
- **Input:** a sentence pair, `[CLS] sentence [SEP] aspect [SEP]`, at most
  128 tokens. The aspect is the readable label from `config/aspects.yaml`
  (for example "Dividend Policy", "Net Interest Margin",
  "Asset Quality / Provisioning"), as recorded in each folder's
  `input_format.json` (`{"with_aspect": true, "aspect_text": "label"}`).
- **Three seeds:** 42, 1 and 7, one folder each. Averaging their
  probabilities is the safer choice: it scores close to the better seeds
  without depending on which seed is picked (below). Seed 42 alone scores
  higher on the test split, but the differences are within the spread
  between seeds.

## Training

| | |
|---|---|
| data | 978 labelled train/dev sentences from Reddit, bank earnings reports and news, drawn in equal thirds by base FinBERT's predicted label so that positive and negative sentences aren't swamped by neutral ones (not stratified by aspect or by the human label); each seed trains on 831 and early-stops on the other 147 |
| labels | two annotators, sentiment κ 0.93; annotators saw a model's suggestion (see limitations) |
| method | fine-tuning with the Hugging Face `Trainer`: AdamW, learning rate 2e-5, batch 16, 10% linear warm-up then linear decay, up to 8 epochs, early stopping (patience 2) on dev macro-F1, best epoch kept, plain cross-entropy |
| selection | on dev and 5-fold cross-validation only; the test split was scored once per final configuration |
| hardware | Apple M1 GPU (MPS); not bit-for-bit reproducible |

## Evaluation

A frozen random test split of 299 sentences (39 negative, 166 neutral, 94
positive):

| model | macro-F1 | accuracy |
|---|---|---|
| base FinBERT, zero-shot | 0.571 | 0.70 |
| seed 42 / 1 / 7 | 0.630 / 0.617 / 0.565 (mean 0.604 ± 0.035) | 0.61–0.68 |
| three seeds averaged | 0.615 | 0.66 |
| three seeds averaged, neutral margin 0.133 | **0.624** | 0.682 |

The neutral margin calls a sentence neutral unless the stronger of negative
and positive beats neutral by more than the margin in probability. Each seed's
margin was chosen on its own dev rows (0.15, 0 and 0.25); the average uses
their mean, 0.133, and the scores above were measured at that value (the
project's index preview rounds it to 0.13). Without the margin, most of the
average's errors (57 of 101) are neutral sentences called positive or
negative, over half of them (31) about retail banking; read rather than
counted, they are mostly descriptions of product features. The margin cuts
those to 44 but raises polar sentences called neutral from 32 to 39 (95
errors in all).

## How to use

```python
import numpy as np, torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

sentence = "DBS raised its quarterly dividend to 60 cents."
aspect = "Dividend Policy"                       # the readable label from config/aspects.yaml
probs = []
for seed in ("seed_42", "seed_1", "seed_7"):
    path = f"models/experiments-2026-10-01/label/{seed}/final"
    tok = AutoTokenizer.from_pretrained(path)
    model = AutoModelForSequenceClassification.from_pretrained(path).eval()
    with torch.no_grad():
        logits = model(**tok(sentence, aspect, truncation=True, max_length=128, return_tensors="pt")).logits
    probs.append(torch.softmax(logits, -1).numpy()[0])
neg, neu, pos = np.mean(probs, axis=0)                 # labels 0, 1, 2
polar, p = ("positive", pos) if pos >= neg else ("negative", neg)
label = polar if p - neu > 0.133 else "neutral"   # the seeds' mean dev-chosen margin
```

In the project, `train/evaluate.py` and `aggregate/preview.py` load the
models this way.

## Limitations

- **Small and anchored data.** 978 train/dev sentences, 831 of them used
  for training. Annotators saw a suggestion model's label, and the final
  labels match it on 92% of train/dev rows (904 of 978) and 89% of test rows
  (266 of 299). The fine-tuned models learned from these labels and base
  FinBERT never saw them, so the anchoring may favour the fine-tuned models
  in the comparison itself. That hasn't been measured; scoring both models
  against the independent Opus labels would measure it.
- **A modest lead.** The seeds' mean macro-F1, 0.604 ± 0.035, is 0.033
  above zero-shot FinBERT, about one standard deviation; the averaged model
  with the margin is 0.053 above. Accuracy is lower than zero-shot
  FinBERT's (0.682 against 0.70). Cross-validation on three seeds
  found no effect from the readable aspect label itself.
- **Few negatives.** 39 negative test sentences: one sentence moves negative
  F1 by about 0.02.
- **Local context.** Singapore product names are common: "UOB One" or
  "OCBC 360" appears in 82 of the 1,277 labelled sentences (55 train/dev,
  27 test), and descriptions of product features account for many of the
  errors (above). Singlish is barely measured: only about a dozen labelled
  sentences contain any Singlish, slang or emoji (the exact count depends on
  which words count as slang).
- **Not investment advice.** The scores describe what people wrote, not
  how the banks will perform.

## Files and checksums

Each folder holds `config.json`, `model.safetensors` (437,961,724 bytes),
`tokenizer.json`, `tokenizer_config.json` and `input_format.json`.
`training_args.bin` is left out of any upload: it records a local path and
nothing needs it to load the model.

| folder | SHA-256 of `model.safetensors` |
|---|---|
| `seed_42` | `e536ffe3af5694c1a15625202cf292542a2f7c0e0517fbd9455c285715729633` |
| `seed_1` | `116a79d79f2a27953ff50fdfa19cc3129a6b23f4b1de2f9fba25e9a481f01dda` |
| `seed_7` | `d2f0ef04f768991a601222775c79ce3188fa0ec2b538756603b8eb28ad10909c` |

Evidence: `docs/evidence/finetune-fixes-2026-10-01.md`,
`error-analysis-2026-10-01.md`, `noise-floor-cv-2026-10-02.md`.
