"""
Sentiment scoring. See docs/DESIGN.md for the reasoning behind the index this
feeds.

This module scores with BASE FinBERT's own classification head
(ProsusAI/finbert, whole-sentence 3-class positive/neutral/negative) and
always tags its rows with base FinBERT's version. Base FinBERT zero-shot is
the first baseline train/evaluate.py compares a fine-tuned model against, so
its scores are kept beside the served model's.

While config/model_version.py serves a fine-tuned version, run() then gives
the same pairs that version's scores too (sentiment/finetuned.py), behind the
same output contract (sentence_id, aspect, label, confidence, model_version).
Both sets of scores sit in the same table distinguished by model_version, so
the before/after comparison stays possible.

Base FinBERT scores the whole sentence and its label is given to the
sentence's aspect. The served fine-tuned model reads the (sentence, aspect)
pair, so its label can depend on the aspect (sentiment/finetuned.py).

Every batch's probabilities are checked before anything is written: the
Mac's GPU once, under memory pressure, returned garbage without an
error. If the check fails, rerun with --cpu.

USAGE:
  python -m sentiment.score [--cpu]
  python -m sentiment.score --sources sgx_research   # only these sources' sentences
"""

import os

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from config.device import best_device
from config.model_version import BASE_VERSION
from config.logging_config import get_logger, setup_logging
from ingest.db import get_connection, init_db, now_iso

logger = get_logger(__name__)

MODEL_NAME = "ProsusAI/finbert"
# The tag on every row this script writes. It names the model this script
# runs (MODEL_NAME), so it stays fixed: a fine-tuned scorer writes its own
# tag, and the readers pick a version through config/model_version.py.
MODEL_VERSION = BASE_VERSION
_BATCH_SIZE = 32
_MAX_LENGTH = 128
_CHUNK = 2000   # sentences classified and committed per step

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
        _device = best_device()
        revision = {"revision": os.environ["FINBERT_REVISION"]} if os.environ.get("FINBERT_REVISION") else {}
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, **revision)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, **revision).to(_device).eval()
        _id2label = {k: v.lower() for k, v in _model.config.id2label.items()}
    return _tokenizer, _model, _device, _id2label


def classify_sentences(texts: list[str]) -> list[tuple[str, float]]:
    """Returns [(label, confidence), ...] for each input text, in input order.

    Batches are formed from texts of similar length: each batch is padded to
    its longest text, so mixing a 20-token sentence with a 128-token one
    wastes most of the batch, and on Apple's MPS every new padded shape costs
    a graph compile. Each text is classified independently, so the order
    changes nothing but speed."""
    tokenizer, model, device, id2label = _get_model()
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    results: list[tuple[str, float] | None] = [None] * len(texts)
    with torch.no_grad():
        for start in range(0, len(order), _BATCH_SIZE):
            idx_batch = order[start:start + _BATCH_SIZE]
            enc = tokenizer([texts[i] for i in idx_batch], padding=True, truncation=True,
                            max_length=_MAX_LENGTH, return_tensors="pt").to(device)
            probs = torch.softmax(model(**enc).logits, dim=-1)
            if not (torch.isfinite(probs).all()
                    and torch.allclose(probs.sum(dim=-1), torch.ones(len(idx_batch), device=probs.device),
                                       atol=1e-3)):
                raise RuntimeError("model probabilities don't sum to 1: the device returned garbage; "
                                   "rerun with --cpu")
            top_prob, top_idx = probs.max(dim=-1)
            for i, p, k in zip(idx_batch, top_prob.tolist(), top_idx.tolist()):
                results[i] = (id2label[k], round(p, 4))
    return results


def run(sources: set[str] | None = None) -> dict:
    init_db()
    conn = get_connection()
    conn.executescript(_SCHEMA)

    where = f" AND s.source IN ({','.join('?' * len(sources))})" if sources else ""
    rows = conn.execute(f"""
        SELECT sa.sentence_id, sa.aspect, s.text
        FROM sentence_aspects sa
        JOIN sentences s ON s.sentence_id = sa.sentence_id
        WHERE NOT EXISTS (
            SELECT 1 FROM aspect_sentiment ase
            WHERE ase.sentence_id = sa.sentence_id AND ase.aspect = sa.aspect
              AND ase.model_version = ?
        ){where}
    """, (MODEL_VERSION, *sorted(sources or ()))).fetchall()

    if not rows:
        return _finetuned_pass(conn, {"already_scored_or_no_assignments": True, "newly_scored": 0})

    # Base FinBERT never sees the aspect, so a sentence assigned to several
    # aspects gets the same prediction for each: classify each sentence once
    # and copy the result to its pairs, instead of once per pair.
    pairs_by_sentence: dict[str, list[str]] = {}
    text_of: dict[str, str] = {}
    for sentence_id, aspect, text in rows:
        pairs_by_sentence.setdefault(sentence_id, []).append(aspect)
        text_of[sentence_id] = text
    ids = list(pairs_by_sentence)

    # Commit chunk by chunk, so a long run shows progress and a re-run
    # resumes: the query above only returns pairs not yet scored.
    written = 0
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start:start + _CHUNK]
        predictions = classify_sentences([text_of[i] for i in chunk])
        ts = now_iso()
        to_insert = [(sid, aspect, label, conf, MODEL_VERSION, ts)
                     for sid, (label, conf) in zip(chunk, predictions)
                     for aspect in pairs_by_sentence[sid]]
        conn.executemany(
            """INSERT OR IGNORE INTO aspect_sentiment
               (sentence_id, aspect, label, confidence, model_version, scored_at)
               VALUES (?,?,?,?,?,?)""",
            to_insert,
        )
        conn.commit()
        written += len(to_insert)
        logger.info("scored %d/%d sentences (%d pairs)", min(start + _CHUNK, len(ids)), len(ids), written)
    return _finetuned_pass(conn, {"newly_scored": written, "sentences_classified": len(ids),
                                  "model_version": MODEL_VERSION})


def _finetuned_pass(conn, result: dict) -> dict:
    """While the readers serve a fine-tuned version, give new pairs its scores
    too (sentiment/finetuned.py); otherwise they would count in nothing served."""
    import config.model_version as current_model
    try:
        if current_model.MODEL_VERSION != MODEL_VERSION:
            from sentiment.finetuned import score_missing
            result["finetuned_version"] = current_model.MODEL_VERSION
            result["finetuned_scored"] = score_missing(conn, current_model.MODEL_VERSION, now_iso())
    finally:
        conn.close()
    return result


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Score assigned (sentence, aspect) pairs with base FinBERT.")
    p.add_argument("--cpu", action="store_true", help="run on the CPU instead of the GPU")
    p.add_argument("--sources", nargs="+", help="score only sentences from these sources")
    args = p.parse_args()
    if args.cpu:
        import train.evaluate
        best_device = lambda: "cpu"  # noqa: E731  (read by _get_model)
        train.evaluate.best_device = best_device       # the fine-tuned pass
    setup_logging()
    logger.info("Scoring complete: %s", run(set(args.sources) if args.sources else None))
