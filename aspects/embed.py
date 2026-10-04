"""
FinBERT sentence embeddings for aspect discovery ("Job 1" from the
proposal - no fine-tuning needed for this part, just measuring similarity).

Mean-pooled over token embeddings, NOT the CLS token - BERT-family CLS vectors
without a sentence-level training objective (like SBERT's) are known to be
poor similarity representations; mean pooling is materially better and costs
nothing. See docs/DESIGN.md, step 1.
"""

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

from config.device import best_device

MODEL_NAME = "ProsusAI/finbert"
_MAX_LENGTH = 128
_BATCH_SIZE = 32

_tokenizer = None
_model = None
_device = None


def _get_model():
    global _tokenizer, _model, _device
    if _model is None:
        _device = best_device()
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModel.from_pretrained(MODEL_NAME).to(_device).eval()
    return _tokenizer, _model, _device


def _mean_pool(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    summed = torch.sum(last_hidden_state * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def embed_sentences(sentences: list[str]) -> np.ndarray:
    """Returns an (n_sentences, 768) float32 array of mean-pooled FinBERT embeddings."""
    tokenizer, model, device = _get_model()
    all_vecs = []
    with torch.no_grad():
        for i in range(0, len(sentences), _BATCH_SIZE):
            batch = sentences[i:i + _BATCH_SIZE]
            enc = tokenizer(batch, padding=True, truncation=True,
                             max_length=_MAX_LENGTH, return_tensors="pt").to(device)
            out = model(**enc)
            pooled = _mean_pool(out.last_hidden_state, enc["attention_mask"])
            all_vecs.append(pooled.cpu().numpy())
    return np.concatenate(all_vecs, axis=0).astype(np.float32)
