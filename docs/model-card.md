# FinBERT fine-tuned for aspect-based sentiment on Singapore bank text

*Model card for the three fine-tuned models of the PLP project (DBS, OCBC
and UOB). Upload it as the `README.md` of a Hugging Face model repo; see
"Sharing the data and models" in the project README.*

## Model

- **Base:** [`ProsusAI/finbert`](https://huggingface.co/ProsusAI/finbert),
  a BERT model further pre-trained on financial text. Check its licence
  before publishing these models publicly.
- **Task:** three-class sentiment (`negative`, `neutral`, `positive`) of a
  sentence *towards one of the three banks on one aspect*.
- **Input:** a sentence pair, `[CLS] sentence [SEP] aspect [SEP]`, at most
  128 tokens. The aspect is the readable label from `config/aspects.yaml`
  (for example "Dividend Policy", "Net Interest Margin",
  "Asset Quality / Provisioning"), as recorded in each folder's
  `input_format.json` (`{"with_aspect": true, "aspect_text": "label"}`).
- **Three seeds:** 42, 1 and 7, one folder each. Averaging their
  probabilities gives the best result (below).

## Training

| | |
|---|---|
| data | 978 labelled sentences (train/dev, stratified by aspect and polarity): Reddit, bank earnings reports, news |
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
| seed 42 / 1 / 7 | 0.630 / 0.617 / 0.565 | 0.61–0.68 |
| three seeds averaged | 0.615 | 0.66 |
| three seeds averaged, neutral margin 0.13 | **0.624** | 0.682 |

The neutral margin calls a sentence neutral unless the stronger of negative
and positive beats neutral by more than the margin in probability; it was
chosen on dev data. Most errors are neutral sentences called positive or
negative, typically descriptions of retail banking products.

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
label = polar if p - neu > 0.13 else "neutral"
```

In the project, `train/evaluate.py` and `aggregate/preview.py` load the
models this way.

## Limitations

- **Small and anchored data.** 978 training sentences; the test labels
  match the suggestion model annotators saw on 89% of rows, so absolute
  scores are optimistic (comparisons between models hold better).
- **A modest lead.** The gain over zero-shot FinBERT is about one seed
  standard deviation, and accuracy is lower. Cross-validation on three seeds
  found no effect from the readable aspect label itself.
- **Few negatives.** 39 negative test sentences: one sentence moves negative
  F1 by about 0.02.
- **Local context.** Trained on Singapore banking text; product names
  ("UOB One", "OCBC 360") and Singlish are where general models go wrong,
  and they are rare in the labelled set.
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
