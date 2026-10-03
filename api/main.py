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


import config.model_version as current_model
from config import aspect_taxonomy

import sqlite3
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from chatbot.agent import Conversation
from chatbot.backends.base import BackendUnavailable
from aggregate.index import MIN_N, compute_time_series
from chatbot.suggestions import get_suggestions
from config.logging_config import get_logger, setup_logging
from chatbot.tools import (ASPECT_KEYS, MIN_VOLUME_FOR_SCORE, compare_banks, get_analyst_consensus,
                            get_coverage, get_sentiment, get_trend, normalize_aspect, search_evidence)
from ingest.base import BANK_NAMES
from ingest.db import get_connection

setup_logging()
logger = get_logger(__name__)

BANKS = list(BANK_NAMES)

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


def valid_aspect(aspect: str | None = Query(
        None, description="An aspect key such as dividend_policy (\"dividend policy\" also works), "
                          "or ALL / empty for every aspect")) -> str | None:
    """The aspect as a key, or None for all aspects. An unknown aspect is a 422,
    not an empty result that reads as "no data" (4 Oct 2026)."""
    if aspect is None or aspect.strip().upper() in ("", "ALL"):
        return None
    key = normalize_aspect(aspect)
    if key not in ASPECT_KEYS:
        raise HTTPException(status_code=422, detail=f"unknown aspect {aspect!r}; one of {', '.join(ASPECT_KEYS)}")
    return key


def valid_source(source: str = Query(
        "ALL", description="ALL (blended), * (every source) or one source in the index, e.g. arctic_shift")) -> str:
    """A source the index holds, ALL or *. An unknown one is a 422, not an empty
    result that reads as "no data" (4 Oct 2026)."""
    if source in ("ALL", "*"):
        return source
    conn = get_connection()
    try:
        known = {r[0] for r in conn.execute("SELECT DISTINCT source FROM sentiment_index WHERE source != 'ALL'")}
    except sqlite3.OperationalError:
        known = set()
    finally:
        conn.close()
    if source not in known:
        raise HTTPException(status_code=422, detail=f"unknown source {source!r}; one of ALL, *, "
                                                    f"{', '.join(sorted(known)) or '(none yet)'}")
    return source


@app.get("/sentiment")
def sentiment(bank: str = Query(..., pattern="^(DBS|OCBC|UOB)$"),
              aspect: str | None = Depends(valid_aspect),
              window: str = Query("all_time", pattern="^(7d|30d|all_time)$")):
    return get_sentiment(bank, aspect, window)


@app.get("/sentiment/compare")
def sentiment_compare(aspect: str | None = Depends(valid_aspect),
                       window: str = Query("all_time", pattern="^(7d|30d|all_time)$")):
    return compare_banks(aspect, window)


@app.get("/sentiment/trend")
def sentiment_trend(bank: str = Query(..., pattern="^(DBS|OCBC|UOB)$"), aspect: str | None = Depends(valid_aspect)):
    return get_trend(bank, aspect)


@app.get("/sentiment/index")
def sentiment_index_dump(window: str = Query("all_time", pattern="^(7d|30d|all_time)$"),
                          source: str = Depends(valid_source)):
    """Raw rows from sentiment_index for the given window - one call to build
    a full bank x aspect grid client-side, instead of one call per cell.

    `source` defaults to "ALL" (the blended headline number). Pass one source
    the index holds (an unknown one is a 422; /sources lists them) to get that
    component alone, or "*" for every row including all per-source
    breakdowns - useful for showing what the blend is made of, which matters
    because the source mix differs between banks (see /sources)."""
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
    blended index. Exposed because the source mix differs between banks (DBS
    has several times the earnings text of the other two), which makes a
    naive cross-bank comparison misleading unless a reader can see it."""
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
def coverage(bank: str | None = Query(None, pattern="^(DBS|OCBC|UOB)$"), aspect: str | None = Depends(valid_aspect)):
    return get_coverage(bank, aspect)


@app.get("/evidence")
def evidence(query: str, bank: str | None = Query(None, pattern="^(DBS|OCBC|UOB)$"),
             aspect: str | None = Depends(valid_aspect),
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
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e):
            raise           # a locked or broken database is an error, not "no consensus yet"
        rows = []   # the table doesn't exist before the first consensus pull
    finally:
        conn.close()
    return {"rows": rows}


@app.get("/evidence/latest")
def evidence_latest(bank: str = Query(..., pattern="^(DBS|OCBC|UOB)$"), aspect: str | None = Depends(valid_aspect),
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
    return {"aspects": [{"key": k, "label": label} for k, label in aspect_taxonomy.labels().items()]}


@app.get("/sentiment/series")
def sentiment_series(bank: str = Query(..., pattern="^(DBS|OCBC|UOB)$"),
                     aspect: str | None = Depends(valid_aspect),
                     bucket: str = Query("month", pattern="^(week|month|quarter)$"),
                     source: str = Depends(valid_source),
                     min_n: int = Query(MIN_N, ge=1)):
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
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    backend: Literal["claude", "openai", "gemini", "ollama"] | None = None  # None: auto-detect

    @field_validator("backend", mode="before")
    @classmethod
    def _lower_backend(cls, value):
        return value.strip().lower() if isinstance(value, str) else value
    # Earlier turns, oldest first, so a follow-up ("and OCBC?") resolves. The API
    # stays stateless: the client sends the conversation back each time.
    history: list[ChatMessage] = []


@app.post("/chat")
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")
    conv = Conversation.from_messages([m.model_dump() for m in req.history], backend_name=req.backend)
    try:
        turn = conv.ask(req.message)
    except BackendUnavailable as e:   # no Ollama running, a missing or rejected key: the service, not the request
        logger.warning("chat backend unavailable: %s", e)
        raise HTTPException(status_code=503, detail=f"chat backend unavailable: {e}")
    return {"question": req.message, "answer": turn.answer, "guard": turn.guard,
            "citation_unverified": turn.citation_unverified,
            "unverified_numbers": turn.unverified_numbers}
