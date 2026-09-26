"""
Tests for the minimal REST API (api/main.py). Every endpoint here is a thin
pass-through to a chatbot/tools.py function already tested elsewhere
(tests/test_chatbot_tools.py, tests/test_yahoo_analyst.py) — these tests
check the HTTP plumbing (routing, query params, validation, status codes),
not the underlying business logic again.

/chat is mocked (no live Ollama/Claude call) so this suite stays fast and
portable — the actual chatbot loop is covered by tests/test_chatbot_backends.py.
"""

from fastapi.testclient import TestClient

from api.main import app
from ingest.db import now_iso


def _insert_scored_sentence(temp_db, sentence_id, bank, aspect, label, confidence):
    conn = temp_db.get_connection()
    conn.execute(
        "INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
        "norm_hash, processed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (sentence_id, f"doc-{sentence_id}", bank, "some text", "2026-01-01T00:00:00+00:00",
         "arctic_shift", "http://example.com", f"hash-{sentence_id}", now_iso()),
    )
    conn.execute(
        "INSERT INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) VALUES (?,?,?,?)",
        (sentence_id, aspect, 0.9, now_iso()),
    )
    conn.execute(
        "INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, scored_at) "
        "VALUES (?,?,?,?,?,?)",
        (sentence_id, aspect, label, confidence, "test-model", now_iso()),
    )
    conn.commit()
    conn.close()


def test_health():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_banks():
    client = TestClient(app)
    assert client.get("/banks").json() == {"banks": ["DBS", "OCBC", "UOB"]}


def test_sentiment_invalid_bank_returns_422():
    client = TestClient(app)
    resp = client.get("/sentiment", params={"bank": "NOTABANK"})
    assert resp.status_code == 422


def test_sentiment_invalid_window_returns_422():
    client = TestClient(app)
    resp = client.get("/sentiment", params={"bank": "DBS", "window": "5years"})
    assert resp.status_code == 422


def test_sentiment_no_data_returns_insufficient(temp_db):
    client = TestClient(app)
    resp = client.get("/sentiment", params={"bank": "DBS", "aspect": "dividend_policy"})
    assert resp.status_code == 200
    assert resp.json()["insufficient_data"] is True


def test_sentiment_compare_returns_all_three_banks(temp_db):
    client = TestClient(app)
    resp = client.get("/sentiment/compare", params={"aspect": "dividend_policy"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["banks"].keys()) == {"DBS", "OCBC", "UOB"}


def test_sentiment_index_dump_shape(temp_db):
    client = TestClient(app)
    resp = client.get("/sentiment/index", params={"window": "all_time"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["window"] == "all_time"
    assert isinstance(body["rows"], list)


def test_coverage_no_data(temp_db):
    client = TestClient(app)
    resp = client.get("/coverage", params={"bank": "UOB"})
    assert resp.status_code == 200
    assert resp.json()["has_data"] is False


def test_coverage_with_data(temp_db):
    _insert_scored_sentence(temp_db, "s1", "OCBC", "dividend_policy", "positive", 0.9)
    client = TestClient(app)
    resp = client.get("/coverage", params={"bank": "OCBC", "aspect": "dividend_policy"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_data"] is True
    assert body["n"] == 1


def test_evidence_requires_query_param():
    client = TestClient(app)
    resp = client.get("/evidence")
    assert resp.status_code == 422  # `query` is required, no default


def test_evidence_returns_well_formed_response(temp_db):
    client = TestClient(app)
    resp = client.get("/evidence", params={"query": "dividend", "bank": "DBS", "k": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body and "n_found" in body


def test_evidence_invalid_sentiment_filter_returns_422():
    client = TestClient(app)
    resp = client.get("/evidence", params={"query": "x", "sentiment": "very_happy"})
    assert resp.status_code == 422


def test_analyst_consensus_no_data(temp_db):
    client = TestClient(app)
    resp = client.get("/analyst-consensus", params={"bank": "DBS"})
    assert resp.status_code == 200
    assert resp.json()["has_data"] is False


def test_analyst_consensus_invalid_bank_returns_422():
    client = TestClient(app)
    resp = client.get("/analyst-consensus", params={"bank": "FAKEBANK"})
    assert resp.status_code == 422


def test_chat_empty_message_returns_400():
    client = TestClient(app)
    resp = client.post("/chat", json={"message": "   "})
    assert resp.status_code == 400


class _FakeConversation:
    seen = {}

    @classmethod
    def from_messages(cls, messages, backend_name=None):
        cls.seen = {"messages": messages, "backend": backend_name}
        return cls()

    def ask(self, message):
        from chatbot.agent import TurnResult
        return TurnResult(question=message, answer="fake answer")


def test_chat_calls_agent_and_returns_answer(monkeypatch):
    monkeypatch.setattr("api.main.Conversation", _FakeConversation)
    client = TestClient(app)
    resp = client.post("/chat", json={"message": "hello", "backend": "ollama"})
    assert resp.status_code == 200
    assert resp.json() == {"question": "hello", "answer": "fake answer", "guard": None,
                           "citation_unverified": False, "unverified_numbers": []}
    assert _FakeConversation.seen == {"messages": [], "backend": "ollama"}


def test_chat_passes_history_for_follow_ups(monkeypatch):
    monkeypatch.setattr("api.main.Conversation", _FakeConversation)
    history = [{"role": "user", "content": "DBS dividends?"},
               {"role": "assistant", "content": "Neutral."}]
    resp = TestClient(app).post("/chat", json={"message": "and OCBC?", "history": history})
    assert resp.status_code == 200
    assert _FakeConversation.seen["messages"] == history
