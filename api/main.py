"""
Minimal REST API over the sentiment store and chatbot — for a frontend other
than the Streamlit dashboard (dashboard/app.py) to consume. Deliberately
thin: every endpoint is a direct pass-through to an existing function in
chatbot/tools.py (already tested against the real DB) or a plain read of
sentiment_index. No new business logic lives here.

CORS is wide open (allow_origins=["*"]) — this is a school project running
locally/on a grader's machine, not a public deployment; a real deployment
would need to tighten this.

USAGE:
  uvicorn api.main:app --reload --port 8000
  # then e.g. curl http://localhost:8000/sentiment?bank=DBS
  # interactive docs at http://localhost:8000/docs
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from chatbot.agent import ask as chatbot_ask
from config.logging_config import get_logger, setup_logging
from chatbot.tools import (compare_banks, get_analyst_consensus, get_coverage,
                            get_sentiment, get_trend, search_evidence)
from ingest.db import get_connection

setup_logging()
logger = get_logger(__name__)

BANKS = ["DBS", "OCBC", "UOB"]

app = FastAPI(
    title="SG Bank Sentiment API",
    description="Minimal API over the sentiment store and chatbot. "
                 "See dashboard/app.py for the reference Streamlit UI this "
                 "same data backs — this API exists for any other frontend.",
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
    """Raw rows from sentiment_index for the given window — one call to build
    a full bank x aspect grid client-side, instead of one call per cell.

    `source` defaults to "ALL" (the blended headline number). Pass a specific
    source ("earnings", "arctic_shift", "newsapi") to get that component
    alone, or "*" for every row including all per-source breakdowns — useful
    for showing what the blend is made of, which matters here because
    earnings coverage is very unequal across banks (see /sources)."""
    conn = get_connection()
    try:
        if source == "*":
            rows = conn.execute(
                "SELECT bank, aspect, source, score, n, pos_n, neu_n, neg_n, "
                "confidence_mean, model_version, computed_at FROM sentiment_index "
                "WHERE window = ?", (window,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT bank, aspect, source, score, n, pos_n, neu_n, neg_n, "
                "confidence_mean, model_version, computed_at FROM sentiment_index "
                "WHERE window = ? AND source = ?", (window, source)).fetchall()
    finally:
        conn.close()
    cols = ["bank", "aspect", "source", "score", "n", "pos_n", "neu_n", "neg_n",
            "confidence_mean", "model_version", "computed_at"]
    return {"window": window, "source": source, "rows": [dict(zip(cols, r)) for r in rows]}


@app.get("/sources")
def sources_breakdown():
    """Per-bank, per-source sentence counts — the composition behind the
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
def coverage(bank: str | None = None, aspect: str | None = None):
    return get_coverage(bank, aspect)


@app.get("/evidence")
def evidence(query: str, bank: str | None = None, aspect: str | None = None,
             sentiment: str | None = Query(None, pattern="^(positive|neutral|negative)$"),
             k: int = 5):
    return search_evidence(query, bank=bank, aspect=aspect, sentiment=sentiment, k=k)


@app.get("/analyst-consensus")
def analyst_consensus(bank: str = Query(..., pattern="^(DBS|OCBC|UOB)$")):
    return get_analyst_consensus(bank)


class ChatRequest(BaseModel):
    message: str
    backend: str | None = None  # "claude" | "openai" | "gemini" | "ollama" | None (auto-detect)


@app.post("/chat")
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")
    answer = chatbot_ask(req.message, verbose=False, backend_name=req.backend)
    return {"question": req.message, "answer": answer}
