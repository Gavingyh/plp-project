"""
The REST API: the system's interface. The dashboard is a separate project
that builds on it (DESIGN decision 23; docs/api-integration.md is the
contract, docs/api/openapi.json the machine-readable one). Deliberately
thin: every endpoint is a pass-through to an existing function in
chatbot/tools.py (already tested against the real DB) or a plain read of the
database. No new business logic lives here.

CORS is wide open (allow_origins=["*"]) - this is a school project running
locally/on a grader's machine, not a public deployment; a real deployment
would need to tighten this.

USAGE:
  uvicorn api.main:app --reload --port 8000
  # then e.g. curl http://localhost:8000/sentiment?bank=DBS
  # interactive docs at http://localhost:8000/docs
"""

import os

import config.model_version as current_model

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from chatbot.agent import Conversation
from aggregate.index import compute_time_series
from chatbot.suggestions import get_suggestions
from config.logging_config import get_logger, setup_logging
from chatbot.tools import (MIN_VOLUME_FOR_SCORE, compare_banks, get_analyst_consensus,
                            get_coverage, get_sentiment, get_trend, search_evidence)
from ingest.db import get_connection

setup_logging()
logger = get_logger(__name__)

BANKS = ["DBS", "OCBC", "UOB"]
ASPECTS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "aspects.yaml")

app = FastAPI(
    title="SG Bank Sentiment API",
    description="The system's interface: the sentiment index, its evidence, analyst "
                 "consensus and the chatbot, for any dashboard or client to read. "
                 "Read-only except POST /chat, which only calls a model. "
                 "Integration guide: docs/api-integration.md.",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/banks")
def banks():
    return {"banks": BANKS}


@app.get("/sentiment")
def sentiment(bank: str = Query(..., pattern="^(DBS|OCBC|UOB)$"),
              aspect: str | None = None,
              window: str = Query("all_time", pattern="^(7d|30d|all_time)$")):
    return get_sentiment(bank, aspect, window)


@app.get("/sentiment/compare")
def sentiment_compare(aspect: str | None = None,
                       window: str = Query("all_time", pattern="^(7d|30d|all_time)$")):
    return compare_banks(aspect, window)


@app.get("/sentiment/trend")
def sentiment_trend(bank: str = Query(..., pattern="^(DBS|OCBC|UOB)$"), aspect: str | None = None):
    return get_trend(bank, aspect)


@app.get("/sentiment/index")
def sentiment_index_dump(window: str = Query("all_time", pattern="^(7d|30d|all_time)$"),
                          source: str = "ALL"):
    """Raw rows from sentiment_index for the given window - one call to build
    a full bank x aspect grid client-side, instead of one call per cell.

    `source` defaults to "ALL" (the blended headline number). Pass a specific
    source ("earnings", "arctic_shift", "newsapi") to get that component
    alone, or "*" for every row including all per-source breakdowns - useful
    for showing what the blend is made of, which matters here because
    earnings coverage is very unequal across banks (see /sources)."""
    conn = get_connection()
    try:
        if source == "*":
            rows = conn.execute(
                "SELECT bank, aspect, source, score, n, pos_n, neu_n, neg_n, "
                "confidence_mean, model_version, computed_at FROM sentiment_index "
                "WHERE window = ? AND model_version = ?",
                (window, current_model.MODEL_VERSION)).fetchall()
        else:
            rows = conn.execute(
                "SELECT bank, aspect, source, score, n, pos_n, neu_n, neg_n, "
                "confidence_mean, model_version, computed_at FROM sentiment_index "
                "WHERE window = ? AND source = ? AND model_version = ?",
                (window, source, current_model.MODEL_VERSION)).fetchall()
    finally:
        conn.close()
    cols = ["bank", "aspect", "source", "score", "n", "pos_n", "neu_n", "neg_n",
            "confidence_mean", "model_version", "computed_at"]
    # Cells below the volume floor keep their score but say they're thin, as
    # /sentiment does, so a grid built from this call can grey them out.
    out = [{**dict(zip(cols, r)), "insufficient_data": r[4] < MIN_VOLUME_FOR_SCORE} for r in rows]
    return {"window": window, "source": source, "rows": out}


@app.get("/sources")
def sources_breakdown():
    """Per-bank, per-source sentence counts - the composition behind the
    blended index. Exposed because earnings coverage is currently very
    unequal (UOB's IR site is WAF-blocked, so it has almost no earnings
    material), which makes a naive cross-bank comparison misleading unless a
    reader can see this."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT bank, source, COUNT(*) FROM sentences GROUP BY bank, source"
        ).fetchall()
    finally:
        conn.close()
    breakdown: dict[str, dict[str, int]] = {}
    for bank, source, n in rows:
        breakdown.setdefault(bank, {})[source] = n
    return {"sentences_by_bank_and_source": breakdown}


@app.get("/coverage")
def coverage(bank: str | None = Query(None, pattern="^(DBS|OCBC|UOB)$"), aspect: str | None = None):
    return get_coverage(bank, aspect)


@app.get("/evidence")
def evidence(query: str, bank: str | None = Query(None, pattern="^(DBS|OCBC|UOB)$"),
             aspect: str | None = None,
             sentiment: str | None = Query(None, pattern="^(positive|neutral|negative)$"),
             k: int = Query(5, ge=1, le=50)):
    return search_evidence(query, bank=bank, aspect=aspect, sentiment=sentiment, k=k)


@app.get("/analyst-consensus")
def analyst_consensus(bank: str = Query(..., pattern="^(DBS|OCBC|UOB)$")):
    return get_analyst_consensus(bank)


@app.get("/analyst-consensus/latest")
def analyst_consensus_latest():
    """Every bank's newest consensus row in one call. Banks are fetched
    separately and can carry different dates; each bank's own newest row is
    returned, so a bank fetched a day earlier is never dropped."""
    from ingest.yahoo_analyst import LATEST_PER_BANK_SQL
    conn = get_connection()
    try:
        cur = conn.execute(LATEST_PER_BANK_SQL)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:
        rows = []   # the table doesn't exist before the first consensus pull
    finally:
        conn.close()
    return {"rows": rows}


@app.get("/evidence/latest")
def evidence_latest(bank: str = Query(..., pattern="^(DBS|OCBC|UOB)$"), aspect: str | None = None,
                    limit: int = Query(30, ge=1, le=200)):
    """The newest sentences for a bank, optionally one aspect, with their stored
    sentiment label: a drill-down list for a dashboard. (`/evidence` is the
    semantic search the chatbot uses, and needs a query.)"""
    conn = get_connection()
    try:
        if aspect:
            cur = conn.execute(
                """SELECT s.sentence_id, s.text, s.source, s.url, s.published_at, ase.aspect,
                          ase.label, ase.confidence
                   FROM sentences s JOIN aspect_sentiment ase ON ase.sentence_id = s.sentence_id
                   WHERE s.bank = ? AND ase.aspect = ? AND ase.model_version = ?
                   ORDER BY s.published_at DESC LIMIT ?""",
                (bank, aspect, current_model.MODEL_VERSION, limit))
        else:
            cur = conn.execute(
                """SELECT sentence_id, text, source, url, published_at FROM sentences
                   WHERE bank = ? ORDER BY published_at DESC LIMIT ?""", (bank, limit))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()
    return {"bank": bank, "aspect": aspect, "rows": rows}


@app.get("/aspects")
def aspects():
    """The aspect keys with their readable labels, from config/aspects.yaml, for labelling a UI."""
    import yaml
    with open(ASPECTS_PATH) as f:
        cfg = yaml.safe_load(f)["aspects"]
    return {"aspects": [{"key": k, "label": v.get("label", k)} for k, v in cfg.items()]}


@app.get("/sentiment/series")
def sentiment_series(bank: str = Query(..., pattern="^(DBS|OCBC|UOB)$"),
                     aspect: str | None = None,
                     bucket: str = Query("month", pattern="^(week|month|quarter)$"),
                     source: str = "ALL",
                     min_n: int = Query(5, ge=1)):
    """Continuous sentiment series for charting.

    /sentiment/trend answers "up or down" from two fixed windows; this returns
    the whole shape. Buckets below min_n come back with sufficient=false
    rather than being dropped, so a chart can show a gap instead of
    interpolating across data that isn't there.
    """
    return {"bank": bank, "aspect": aspect or "ALL", "bucket": bucket,
            "source": source,
            "series": compute_time_series(bank, aspect, bucket=bucket,
                                          source=source, min_n=min_n)}


@app.get("/suggestions")
def suggestions(limit: int = Query(6, ge=1, le=20)):
    """Starter questions for a chat UI to show as clickable prompts.

    Every question returned is one the current data can answer - they are
    generated from the sentiment index rather than hardcoded, so a bank or
    aspect with too little data never gets suggested. Advice-seeking and
    out-of-scope questions are excluded by design; the chatbot declines
    those, so offering them would be misleading.
    """
    return {"suggestions": get_suggestions(limit=limit)}


class ChatMessage(BaseModel):
    role: str      # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    backend: str | None = None  # "claude" | "openai" | "gemini" | "ollama" | None (auto-detect)
    # Earlier turns, oldest first, so a follow-up ("and OCBC?") resolves. The API
    # stays stateless: the client sends the conversation back each time.
    history: list[ChatMessage] = []


@app.post("/chat")
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")
    conv = Conversation.from_messages([m.model_dump() for m in req.history], backend_name=req.backend)
    turn = conv.ask(req.message)
    return {"question": req.message, "answer": turn.answer, "guard": turn.guard,
            "citation_unverified": turn.citation_unverified,
            "unverified_numbers": turn.unverified_numbers}
