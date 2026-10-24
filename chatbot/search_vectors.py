"""
Sentence vectors for the chatbot's evidence search, from a model trained to
match sentences by meaning (all-MiniLM-L6-v2). The FinBERT vectors in
aspects/embed_store.py stay for aspect discovery; for search they ranked
evidence no better than a random draw when no topic narrowed the pool, where
this model ranked about two and a half times better
(docs/evidence/search-models-2026-10-24.md). Within one topic the search
orders by the question's words and uses no vectors at all.

The store is kept up to date the same way as FinBERT's, incrementally, by
the topic step (aspects/assign.py) that runs after new sentences arrive.

USAGE:
  python -m chatbot.search_vectors   # embed any sentence not yet in the store
"""

import os

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

from aspects import embed_store
from config.logging_config import get_logger, setup_logging
from config.search_model import MODEL_NAME, MODEL_REVISION, WIDTH

logger = get_logger(__name__)

_MAX_LENGTH = 128
_BATCH_SIZE = 64

STORE_PATH = os.path.abspath(os.environ.get("PLP_SEARCH_EMBEDDINGS_PATH")
                             or os.path.join(embed_store.BASE_DIR, "data", "search_embeddings.npz"))

_tokenizer = None
_model = None


def _get_model():
    # On the processor: the model is small, a question takes milliseconds, and
    # the local language model keeps the GPU.
    global _tokenizer, _model
    if _model is None:
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, revision=MODEL_REVISION)
        _model = AutoModel.from_pretrained(MODEL_NAME, revision=MODEL_REVISION).float().eval()
    return _tokenizer, _model


def embed_sentences(sentences: list[str]) -> np.ndarray:
    """An (n, 384) float32 array: mean-pooled and scaled to length 1, as the
    model was trained."""
    if not sentences:
        return np.zeros((0, WIDTH), dtype=np.float32)
    tokenizer, model = _get_model()
    out = []
    with torch.no_grad():
        for i in range(0, len(sentences), _BATCH_SIZE):
            enc = tokenizer(sentences[i:i + _BATCH_SIZE], padding=True, truncation=True,
                            max_length=_MAX_LENGTH, return_tensors="pt")
            hidden = model(**enc).last_hidden_state
            mask = enc["attention_mask"].unsqueeze(-1).float()
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            out.append(torch.nn.functional.normalize(pooled, dim=-1).numpy())
            done = min(i + _BATCH_SIZE, len(sentences))
            if done % 1024 == 0 or done == len(sentences):
                logger.info("Search vectors: embedded %d/%d sentences", done, len(sentences))
    return np.concatenate(out).astype(np.float32)


def update() -> dict:
    """Embed any sentence in the database not yet in the store, and drop the
    ones no longer there."""
    return embed_store.update(path=STORE_PATH, embed=embed_sentences, width=WIDTH)


def load_for_search() -> tuple[list[str], np.ndarray]:
    """The store's sentence ids and vectors, read once until the file changes.
    Callers must not modify what it returns."""
    return embed_store.load_for_search(path=STORE_PATH)


if __name__ == "__main__":
    setup_logging()
    logger.info("Search vectors: %s", update())
