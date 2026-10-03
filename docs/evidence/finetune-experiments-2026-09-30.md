# Fine-tuning experiments: longer training, the aspect input, cross-validation

Follows [finetune-2026-09-30.md](finetune-2026-09-30.md), where FinBERT
fine-tuned for 4 epochs scored test macro-F1 0.547 ± 0.013 against base
FinBERT zero-shot's 0.571, with dev macro-F1 still rising at epoch 4. Run
overnight 2026-09-30 to 2026-10-01 on this MacBook Air (M1, 16 GB, MPS), on
the same cleaned labels (978 train/dev, 299 test).

Two questions: does training longer help, and does telling the model the
aspect help at all?

```bash
# sentence + aspect, up to 8 epochs
.venv-plp/bin/python3 -m train.finetune --seed $s --epochs 8 --out-dir models/experiments-2026-09-30/e1-aspect-8ep
# sentence only
.venv-plp/bin/python3 -m train.finetune --seed $s --epochs 8 --no-aspect --out-dir models/experiments-2026-09-30/e2-noaspect-8ep
# each of those models
.venv-plp/bin/python3 -m train.evaluate --model-dir <out-dir>/seed_$s/final
# 5-fold cross-validation on train_dev, seed 42, both inputs
.venv-plp/bin/python3 -m train.finetune --seed 42 --epochs 8 [--no-aspect] --folds 5 --fold $f --out-dir models/experiments-2026-09-30/e3-cv
```

(`HF_HUB_OFFLINE=1` throughout; seeds 42, 1, 7; folds 0–4.) Early stopping
(patience 2 on dev macro-F1) and best-epoch selection are unchanged from the
30 Sep run. Note that `--epochs 8` also changes the learning-rate schedule:
the rate decays linearly over all 8 epochs, so it stays higher for longer.

## How the configuration was chosen

On dev scores only, as the plan requires. 4 epochs: best dev macro-F1 0.667,
0.607, 0.575 (mean 0.616). 8 epochs (sentence + aspect): 0.641, 0.642, 0.628 (mean 0.637,
sd 0.008). 8 epochs was chosen for the sentence-only and cross-validation
runs before any of their test scores existed.

## Result

Test split, n = 299 (39 negative, 166 neutral, 94 positive):

| configuration | dev macro-F1 | test macro-F1 (seeds 42, 1, 7) | mean ± sd | negative F1 | neutral F1 | positive F1 |
|---|---|---|---|---|---|---|
| base FinBERT, zero-shot | — | 0.571 | — | 0.30 | 0.78 | 0.64 |
| 30 Sep: sentence + aspect, 4 epochs | 0.616 | 0.534, 0.560, 0.548 | 0.547 ± 0.013 | 0.42 | 0.59* | 0.61* |
| **sentence + aspect, 8 epochs** | **0.637** | **0.607, 0.560, 0.563** | **0.577 ± 0.027** | 0.44 | 0.66 | 0.63 |
| sentence only, 8 epochs | 0.556 | 0.549, 0.534, 0.542 | 0.542 ± 0.008 | 0.29 | 0.70 | 0.63 |
| TF-IDF + logistic regression | — | 0.514 | — | 0.34 | 0.65 | 0.55 |
| VADER lexicon | — | 0.427 | — | 0.24 | 0.50 | 0.54 |

Per-class F1 is the mean over the three seeds, from each run's
`classification_report`. (*30 Sep: seeds 42 and 1 reported negative F1 0.42
and 0.41 and seed 7 0.44; neutral and positive shown for seed 7.)

Per seed, sentence + aspect: seed 42 stopped after 5 epochs (best epoch 3),
seed 1 after 7 (best 5), seed 7 after 5 (best 3); sentence only the same
pattern. Test accuracy: sentence + aspect 0.66, 0.60, 0.60; sentence only
0.63, 0.62, 0.63; base FinBERT 0.70.

**5-fold cross-validation on train/dev** (seed 42, 8 epochs; dev macro-F1
per fold 0–4):

| input | fold 0 | fold 1 | fold 2 | fold 3 | fold 4 | mean ± sd |
|---|---|---|---|---|---|---|
| sentence + aspect | 0.667 | 0.614 | 0.601 | 0.628 | 0.598 | **0.622 ± 0.028** |
| sentence only | 0.659 | 0.565 | 0.566 | 0.599 | 0.590 | 0.596 ± 0.038 |
| difference | +0.008 | +0.049 | +0.036 | +0.029 | +0.009 | +0.026 ± 0.018 |

## What it shows

1. **Longer training helps, a little.** 8 epochs beats the 4-epoch runs on dev
   (0.637 against 0.616) and on test (0.577 against 0.547), and its test mean
   is now level with base FinBERT (0.571): within one seed standard
   deviation, so level, not ahead. Seed-to-seed spread is large (0.560 to
   0.607 on the same data), which is itself a finding at 978 training rows.
2. **The aspect input helps, and is where the gain on negative sentences
   comes from.** It wins in all five cross-validation folds (by 0.026 on
   average), on dev at 8 epochs (0.637 against 0.556), and on test (0.577 against 0.542).
   Without it, negative F1 falls to 0.29, base FinBERT's level. So the
   model is using the aspect, not only the sentence.
3. **The trade against base FinBERT is unchanged in kind.** Base FinBERT is
   still better on neutral (F1 0.78) and on accuracy (0.70); every
   fine-tuned model given the aspect is better on negative (0.41–0.47
   against 0.30), and the sentence-only ones are not (0.28–0.31). Macro-F1, which
   weights the three classes equally, puts them level.

Replacing base FinBERT for scoring the corpus is a team decision (PLAN
section 5); on these numbers it would change which sentences count as
negative more than it would change headline accuracy.

## Caveats

The caveats of [finetune-2026-09-30.md](finetune-2026-09-30.md) apply: the
test labels were not independent of the LLM's suggestion, and 39 negative
test rows means one sentence moves negative F1 by about 0.02. MPS training is
not bit-for-bit reproducible, so a rerun of the same seed can differ slightly.
Cross-validation used one seed; its folds share the fixed train/dev pool, so
it estimates variation across data splits, not across seeds.

## Model weights

Saved on the MacBook that ran them; `models/` is not in git (each file is
418 MB, over GitHub's 100 MiB limit). Share through the team folder and check
copies against these SHA-256 checksums of `model.safetensors`
(437,961,724 bytes each). Each `final/` folder also holds the tokenizer and
config, and the new ones an `input_format.json` that `train.evaluate` reads.
Cross-validation fold models were not kept.

| model | SHA-256 of `model.safetensors` |
|---|---|
| `models/finbert-absa/seed_42/final` (30 Sep, 4 epochs) | `497e95748288904776cbb1b2eae6cad3bfad69b4a780e331ece085586f9a1b37` |
| `models/finbert-absa/seed_1/final` | `4a17f415e606894abe0ff5488c7ea319c1957c737d122ff02b203719cd3e3bcc` |
| `models/finbert-absa/seed_7/final` | `d2a980cd028c54c857d8480cfeb673f00a591f66461e1c7364c8b48321db43f2` |
| `models/experiments-2026-09-30/e1-aspect-8ep/seed_42/final` | `465a5fa4fa8e7cd05f03bfe59c690cf73eb697b46705af27c283e95c6a8e83fd` |
| `models/experiments-2026-09-30/e1-aspect-8ep/seed_1/final` | `fd527dcbe1e66bab93349d73176beb84d3cf59dd8b8d2d1c295444b64eda28a3` |
| `models/experiments-2026-09-30/e1-aspect-8ep/seed_7/final` | `32f9a817462ba2b744a598b1ae69d31a5007cd64183eba8c063e68e65a5d9bf3` |
| `models/experiments-2026-09-30/e2-noaspect-8ep/seed_42/final` | `75ee211d54d62e9749c2017e5815b60a356d71fc4557258b01914b74050e95fc` |
| `models/experiments-2026-09-30/e2-noaspect-8ep/seed_1/final` | `be4d08ea19268e30aaefc4aaf3e156e0d905157139759a3897558b7b175f3586` |
| `models/experiments-2026-09-30/e2-noaspect-8ep/seed_7/final` | `14d47cd3634f30e4250abf4a8cbed9ee57ab97a870af2c576a458339e447f880` |
