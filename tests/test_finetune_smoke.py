"""
Smoke test for train/finetune.py + train/evaluate.py using SYNTHETIC, clearly
fake labels - not real annotation. Purpose: catch code/API bugs (Trainer
argument names, tokenizer calls, metric computation) before real labeled
data exists tomorrow, since neither script has ever actually been run.
transformers 5.16.1 is a very new major version - its TrainingArguments API
has changed across versions before, worth confirming now rather than after
a week of real labeling.

This does NOT produce a usable model - 48 synthetic examples, 1 epoch, text
that isn't even about banks. It only proves the pipeline runs end-to-end
without crashing. Marked slow; skip with `-m "not slow"` if needed.
"""

import random

import pandas as pd
import pytest

pytestmark = [pytest.mark.slow, pytest.mark.usefixtures("train_on_the_cpu")]

_ASPECTS = ["dividend_policy", "asset_quality", "net_interest_margin", "management_guidance"]
_TEMPLATES = {
    "positive": ["{bank} reported strong {aspect} this quarter, beating expectations.",
                 "Analysts praised {bank}'s {aspect} as a clear strength."],
    "neutral": ["{bank}'s {aspect} was broadly in line with the prior quarter.",
                "No major change in {bank}'s {aspect} was noted."],
    "negative": ["{bank}'s {aspect} disappointed investors this quarter.",
                 "Concerns grew over {bank}'s {aspect} amid weaker guidance."],
}


def _make_synthetic_candidates(n_per_class_train=14, n_per_class_test=4) -> pd.DataFrame:
    rng = random.Random(42)
    rows = []

    def gen_rows(n_per_class, split, sampling_method):
        for label in ("positive", "neutral", "negative"):
            for _ in range(n_per_class):
                bank = rng.choice(["DBS", "OCBC", "UOB"])
                aspect = rng.choice(_ASPECTS)
                template = rng.choice(_TEMPLATES[label])
                rows.append({
                    "sentence_id": f"synthetic-{len(rows)}", "aspect": aspect,
                    # Test rows get their own clause, so they aren't near-copies of
                    # training rows (train.labels.check_splits refuses those).
                    "text": template.format(bank=bank, aspect=aspect.replace("_", " "))
                            + ("" if split == "train_dev"
                               else f" Separately, held-out case {len(rows)} covers quite unrelated reporting only."),
                    "bank": bank, "source": "synthetic", "url": "", "published_at": "2026-01-01",
                    "split": split, "sampling_method": sampling_method,
                    "base_finbert_label": "", "base_finbert_confidence": "",
                    "label": label, "annotator": "smoke-test", "labeled_at": "",
                    "llm_prelabel": "", "was_corrected": "",
                })

    gen_rows(n_per_class_train, "train_dev", "stratified")
    gen_rows(n_per_class_test, "test", "random")
    return pd.DataFrame(rows)


def test_finetune_and_evaluate_pipeline_runs_without_crashing(tmp_path, monkeypatch):
    import train.evaluate as evaluate_module
    import train.finetune as finetune_module

    candidates_path = tmp_path / "candidates.csv"
    _make_synthetic_candidates().to_csv(candidates_path, index=False)

    model_out_dir = tmp_path / "models"
    monkeypatch.setattr(finetune_module, "CANDIDATES_PATH", str(candidates_path))
    monkeypatch.setattr(finetune_module, "MODEL_OUT_DIR", str(model_out_dir))
    monkeypatch.setattr(evaluate_module, "CANDIDATES_PATH", str(candidates_path))

    metrics = finetune_module.run(seed=42, epochs=1, batch_size=8)
    assert "eval_macro_f1" in metrics or "eval_loss" in metrics  # Trainer.evaluate()'s actual keys

    final_model_dir = model_out_dir / "seed_42" / "final"
    assert final_model_dir.exists(), "fine-tuned model was not saved where evaluate.py expects it"

    # evaluate.py's baselines (base FinBERT, TF-IDF+logreg) plus the fine-tuned
    # model - confirms the whole comparison pipeline runs, not just training.
    evaluate_module.run(model_dir=str(final_model_dir))
