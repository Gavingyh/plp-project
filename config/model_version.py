"""
The sentiment model whose scores the index, the API and the chatbot read.

aspect_sentiment and sentiment_index can hold scores from more than one model
side by side (sentiment/score.py), so a before/after comparison stays
possible. Every reader filters on this version so the two never mix: without
the filter, a second model's rows would double every sentence and every index
cell. Change it in the same commit that re-scores the corpus with a new model.

This is the version the readers serve, not a setting for the scorer:
sentiment/score.py always tags its rows "finbert-base-zeroshot-v1", the model
it runs, so changing this constant can never relabel base-FinBERT scores as
another model's. Kept apart from sentiment/score.py, which imports torch, so
that the API and the chatbot can read it cheaply.
"""

# Base FinBERT's tag (sentiment/score.py writes it on every row it scores).
BASE_VERSION = "finbert-base-zeroshot-v1"
# Files used by our PyTorch loaders. Other framework weights are unnecessary;
# recent huggingface_hub versions require this filter for partial offline caches.
BASE_MODEL_DOWNLOAD_PATTERNS = [
    "config.json", "model.safetensors", "pytorch_model.bin", "tokenizer.json",
    "tokenizer_config.json", "special_tokens_map.json", "vocab.txt",
]
MODEL_VERSION = "finbert-adapted-finetuned-2026-10-11-3seed-m0"

# The models and neutral margin behind each fine-tuned version, so that once
# MODEL_VERSION names one, sentiment/score.py scores new sentences with it too
# (scripts/rescore.py scores the existing corpus). Paths are relative to the
# repository. The tag is scripts/rescore.py's: experiment, seeds, margin.
FINETUNED = {
    "finbert-finetuned-2026-10-01-3seed-m0.13": {
        "models": [f"models/experiments-2026-10-01/label/seed_{s}/final" for s in (42, 1, 7)],
        "margin": 0.13,
    },
    # The adapted encoder fine-tuned on the LLM's labels: the model the
    # comparison of every candidate chose (docs/evidence/model-rerun-2026-10-11.md).
    "finbert-adapted-finetuned-2026-10-11-3seed-m0": {
        "models": [f"models/experiments-2026-10-11/dapt/seed_{s}/final" for s in (42, 1, 7)],
        "margin": 0.0,
    },
}

# The fine-tuned version experiments use unless told otherwise (aggregate.preview,
# train.error_analysis, scripts/rescore.py).
DEFAULT_FINETUNED = "finbert-adapted-finetuned-2026-10-11-3seed-m0"
