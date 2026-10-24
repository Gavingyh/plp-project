"""
Tests for the minimal REST API (api/main.py). Every endpoint here is a thin
pass-through to a chatbot/tools.py function already tested elsewhere
(tests/test_chatbot_tools.py, tests/test_yahoo_analyst.py) - these tests
check the HTTP plumbing (routing, query params, validation, status codes),
not the underlying business logic again.

/chat is mocked (no live Ollama/Claude call) so this suite stays fast and
portable - the actual chatbot loop is covered by tests/test_chatbot_backends.py.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from ingest.db import now_iso
from config.model_version import MODEL_VERSION


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
        (sentence_id, aspect, label, confidence, MODEL_VERSION, now_iso()),
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
                           "citation_unverified": False, "unverified_numbers": [],
                           "unverified_readings": []}
    assert _FakeConversation.seen == {"messages": [], "backend": "ollama"}


def test_chat_passes_history_for_follow_ups(monkeypatch):
    monkeypatch.setattr("api.main.Conversation", _FakeConversation)
    history = [{"role": "user", "content": "DBS dividends?"},
               {"role": "assistant", "content": "Neutral."}]
    resp = TestClient(app).post("/chat", json={"message": "and OCBC?", "history": history})
    assert resp.status_code == 200
    assert _FakeConversation.seen["messages"] == history


def test_aspects_lists_every_key_with_its_label():
    body = TestClient(app).get("/aspects").json()
    keys = [a["key"] for a in body["aspects"]]
    assert "dividend_policy" in keys and "other" in keys and len(keys) == 11
    assert {"key": "dividend_policy", "label": "Dividend Policy"} in body["aspects"]


def test_evidence_latest_filters_by_bank_and_aspect(temp_db):
    _insert_scored_sentence(temp_db, "s1", "OCBC", "dividend_policy", "positive", 0.9)
    _insert_scored_sentence(temp_db, "s2", "OCBC", "asset_quality", "negative", 0.8)
    _insert_scored_sentence(temp_db, "s3", "DBS", "dividend_policy", "neutral", 0.7)
    client = TestClient(app)
    rows = client.get("/evidence/latest", params={"bank": "OCBC", "aspect": "dividend_policy"}).json()["rows"]
    assert [r["sentence_id"] for r in rows] == ["s1"] and rows[0]["label"] == "positive"
    all_ocbc = client.get("/evidence/latest", params={"bank": "OCBC"}).json()["rows"]
    assert {r["sentence_id"] for r in all_ocbc} == {"s1", "s2"}
    assert client.get("/evidence/latest", params={"bank": "HSBC"}).status_code == 422


def test_analyst_consensus_latest_keeps_each_banks_newest_row(temp_db):
    conn = temp_db.get_connection()
    for bank, day in (("DBS", "2026-09-25"), ("UOB", "2026-09-24"), ("UOB", "2026-09-10")):
        conn.execute("INSERT INTO analyst_consensus (bank, as_of_date, ticker, n_analysts, fetched_at) "
                     "VALUES (?,?,?,?,?)", (bank, day, f"{bank}.SI", 10, now_iso()))
    conn.commit()
    conn.close()
    rows = TestClient(app).get("/analyst-consensus/latest").json()["rows"]
    assert [(r["bank"], r["as_of_date"]) for r in rows] == [("DBS", "2026-09-25"), ("UOB", "2026-09-24")]


def test_committed_openapi_spec_matches_the_app():
    """docs/api/openapi.json is what the dashboard team generates clients from;
    regenerate it when an endpoint changes (command in docs/api-integration.md)."""
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "api", "openapi.json")
    with open(path) as f:
        assert json.load(f) == json.loads(json.dumps(app.openapi(), sort_keys=True))


# --- input that used to read as "no data" -------------------------------------------

@pytest.mark.parametrize("path", ["/coverage?bank=DBS&aspect=dividend%20polcy", "/evidence?query=x&aspect=nope",
                                  "/evidence/latest?bank=DBS&aspect=nope", "/sentiment?bank=DBS&aspect=nope"])
def test_an_unknown_aspect_is_rejected(temp_db, path):
    from fastapi.testclient import TestClient
    from api.main import app
    assert TestClient(app).get(path).status_code == 422


def test_a_readable_aspect_name_still_works(temp_db):
    from fastapi.testclient import TestClient
    from api.main import app
    r = TestClient(app).get("/coverage?bank=DBS&aspect=dividend%20policy")
    assert r.status_code == 200


@pytest.mark.parametrize("body", [{"message": "hi", "backend": "nope"},
                                  {"message": "hi", "history": [{"role": "system", "content": "x"}]}])
def test_chat_rejects_an_unknown_backend_or_role(body):
    from fastapi.testclient import TestClient
    from api.main import app
    assert TestClient(app).post("/chat", json=body).status_code == 422


def test_a_failing_chat_backend_is_a_503_not_a_500(monkeypatch):
    from fastapi.testclient import TestClient
    import api.main as api_main

    from chatbot.backends.base import BackendUnavailable

    def down(self, question, verbose=False):
        raise BackendUnavailable("Ollama isn't running")
    monkeypatch.setattr(api_main.Conversation, "ask", down)
    r = TestClient(api_main.app).post("/chat", json={"message": "How is DBS doing?"})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "backend_unavailable"
    assert "temporarily unavailable" in r.json()["detail"]["message"]


def test_a_bug_while_answering_is_a_500_not_backend_unavailable(monkeypatch):
    from fastapi.testclient import TestClient
    import api.main as api_main

    def broken(self, question, verbose=False):
        raise KeyError("a harness bug")
    monkeypatch.setattr(api_main.Conversation, "ask", broken)
    r = TestClient(api_main.app, raise_server_exceptions=False).post("/chat", json={"message": "How is DBS doing?"})
    assert r.status_code == 500 and "harness bug" not in r.text


def test_a_database_error_is_not_read_as_no_consensus(temp_db, monkeypatch):
    import sqlite3
    from fastapi.testclient import TestClient
    import api.main as api_main

    class Broken:
        def execute(self, *a):
            raise sqlite3.OperationalError("database is locked")

        def close(self):
            pass
    monkeypatch.setattr(api_main, "get_connection", lambda: Broken())
    assert TestClient(api_main.app, raise_server_exceptions=False).get("/analyst-consensus/latest").status_code == 500


def test_startup_says_when_the_served_version_has_no_index_rows(temp_db, caplog):
    # An empty index for config/model_version.py's version is reported when the
    # API starts, not first as "no data" at a reader.
    import logging
    with caplog.at_level(logging.ERROR, logger="api.main"), TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
    assert any("no sentiment_index rows for" in r.getMessage() for r in caplog.records)


def test_startup_is_quiet_when_the_served_version_has_rows(temp_db, caplog):
    import logging
    import ingest.db
    conn = ingest.db.get_connection()
    conn.execute("INSERT INTO sentiment_index (bank, aspect, source, window, score, n, pos_n, neu_n, neg_n, "
                 "confidence_mean, model_version, computed_at) VALUES ('DBS', 'ALL', 'ALL', 'all_time', 0.1, 10, "
                 "3, 5, 2, 0.8, ?, ?)", (MODEL_VERSION, now_iso()))
    conn.commit()
    conn.close()
    with caplog.at_level(logging.ERROR, logger="api.main"), TestClient(app):
        pass
    assert not any("no sentiment_index rows for" in r.getMessage() for r in caplog.records)
