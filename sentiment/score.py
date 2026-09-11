"""
Sentiment scoring. See docs/DESIGN.md for the reasoning behind the index this
feeds.

STATUS: this uses BASE FinBERT's own classification head (ProsusAI/finbert,
whole-sentence 3-class positive/neutral/negative), NOT the fine-tuned
aspect-conditioned classifier the proposal calls for. That model does not
exist yet: it needs ~1,000 human-labelled examples, and nobody has labelled
any (docs/STATUS.md).

Base FinBERT zero-shot is also the first of the three baselines
train/evaluate.py compares a fine-tuned model against, so running it here is
not a stopgap that gets thrown away. It means the full pipeline (ingestion ->
sentences -> aspects -> SCORING -> index -> dashboard -> chatbot) runs
end-to-end today, and when a fine-tuned model arrives you swap it in behind
the same output contract (sentence_id, aspect, label, confidence,
model_version). Both sets of scores then sit in the same table distinguished
by model_version, and the before/after comparison falls out for free.

Whole-sentence sentiment is attributed to whichever aspect(s) the sentence was
assigned. That is a simplification: the real formulation feeds the
(sentence, aspect) pair to the model so it can condition on the aspect, which
only a fine-tuned model can do.

USAGE:
  python -m sentiment.score
"""

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from config.logging_config import get_logger, setup_logging
from ingest.db import get_connection, init_db, now_iso

logger = get_logger(__name__)

MODEL_NAME = "ProsusAI/finbert"
MODEL_VERSION = "finbert-base-zeroshot-v1"  # bump when the fine-tuned model replaces this
_BATCH_SIZE = 32
_MAX_LENGTH = 128

_SCHEMA = """
CREATE TABLE IF NOT EXISTS aspect_sentiment (
    sentence_id   TEXT NOT NULL REFERENCES sentences(sentence_id),
    aspect        TEXT NOT NULL,
    label         TEXT NOT NULL,      -- positive | neutral | negative
    confidence    REAL NOT NULL,
    model_version TEXT NOT NULL,
    scored_at     TEXT NOT NULL,
    PRIMARY KEY (sentence_id, aspect, model_version)
);
CREATE INDEX IF NOT EXISTS idx_aspect_sentiment_aspect ON aspect_sentiment(aspect);
CREATE INDEX IF NOT EXISTS idx_aspect_sentiment_model ON aspect_sentiment(model_version);
"""

_tokenizer = None
_model = None
_device = None
_id2label = None


def _get_model():
    global _tokenizer, _model, _device, _id2label
    if _model is None:
        _device = "mps" if torch.backends.mps.is_available() else "cpu"
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME).to(_device).eval()
        _id2label = {k: v.lower() for k, v in _model.config.id2label.items()}
    return _tokenizer, _model, _device, _id2label


def classify_sentences(texts: list[str]) -> list[tuple[str, float]]:
    """Returns [(label, confidence), ...] for each input text."""
    tokenizer, model, device, id2label = _get_model()
    results = []
    with torch.no_grad():
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i:i + _BATCH_SIZE]
            enc = tokenizer(batch, padding=True, truncation=True,
                             max_length=_MAX_LENGTH, return_tensors="pt").to(device)
            logits = model(**enc).logits
            probs = torch.softmax(logits, dim=-1)
            top_prob, top_idx = probs.max(dim=-1)
            for p, idx in zip(top_prob.tolist(), top_idx.tolist()):
                results.append((id2label[idx], round(p, 4)))
    return results


def run() -> dict:
    init_db()
    conn = get_connection()
    conn.executescript(_SCHEMA)

    rows = conn.execute("""
        SELECT sa.sentence_id, sa.aspect, s.text
        FROM sentence_aspects sa
        JOIN sentences s ON s.sentence_id = sa.sentence_id
        WHERE NOT EXISTS (
            SELECT 1 FROM aspect_sentiment ase
            WHERE ase.sentence_id = sa.sentence_id AND ase.aspect = sa.aspect
              AND ase.model_version = ?
        )
    """, (MODEL_VERSION,)).fetchall()

    if not rows:
        conn.close()
        return {"already_scored_or_no_assignments": True, "newly_scored": 0}

    texts = [r[2] for r in rows]
    predictions = classify_sentences(texts)
    ts = now_iso()
    to_insert = [
        (sentence_id, aspect, label, conf, MODEL_VERSION, ts)
        for (sentence_id, aspect, _text), (label, conf) in zip(rows, predictions)
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO aspect_sentiment
           (sentence_id, aspect, label, confidence, model_version, scored_at)
           VALUES (?,?,?,?,?,?)""",
        to_insert,
    )
    conn.commit()
    conn.close()
    return {"newly_scored": len(to_insert), "model_version": MODEL_VERSION}


if __name__ == "__main__":
    setup_logging()
    logger.info("Scoring complete: %s", run())
