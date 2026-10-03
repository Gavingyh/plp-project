"""
Validation of the 4 Oct 2026 input checks, against the routes read from the app
(not a hand-kept list):

- every endpoint that takes `aspect` gives 422 for an unknown aspect;
- a readable name ("dividend policy", "Dividend-Policy") is accepted on every
  such endpoint, for every aspect key, and gives the same body as the key;
- ALL, empty or no aspect means every aspect;
- POST /chat gives 422 for an unknown `backend` or history `role`, and accepts
  the four known backends.

Synthetic database (temp_db); no model, no network.
"""

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from api.main import app
from chatbot.tools import ASPECT_KEYS
from config.model_version import MODEL_VERSION
from ingest.db import now_iso

# Required params other than aspect, so the route answers at all.
REQUIRED = {"/sentiment": {"bank": "DBS"}, "/sentiment/trend": {"bank": "DBS"},
            "/sentiment/series": {"bank": "DBS"}, "/evidence": {"query": "dividend"},
            "/evidence/latest": {"bank": "DBS"}}


def _query_params(dependant) -> set[str]:
    """Query params of a route, including those of its Depends() functions."""
    names = {p.name for p in dependant.query_params}
    for d in dependant.dependencies:
        names |= _query_params(d)
    return names


def _routes_taking(param: str) -> list[str]:
    return sorted(r.path for r in app.routes
                  if isinstance(r, APIRoute) and param in _query_params(r.dependant))


ASPECT_ROUTES = _routes_taking("aspect")
BAD_ASPECTS = ["nope", "dividend polcy", "dividend_policyx", "dividend_policy;--", "ALLX",
               "dividend_policy,asset_quality", "dividend\npolicy"]


@pytest.fixture
def client(temp_db, monkeypatch):
    seen = []

    def fake_search(query, **kw):
        seen.append(kw)
        return {"query": query, "results": [], "n_found": 0}
    monkeypatch.setattr("api.main.search_evidence", fake_search)   # no embedding model
    conn = temp_db.get_connection()
    for i, (bank, aspect) in enumerate([("DBS", a) for a in ASPECT_KEYS]):
        sid = f"s{i}"
        conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
                     "norm_hash, processed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (sid, f"d{i}", bank, f"text {i}", "2026-09-01T00:00:00+00:00", "newsapi",
                      f"https://x/{i}", f"h{i}", now_iso()))
        conn.execute("INSERT INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) VALUES (?,?,?,?)",
                     (sid, aspect, 0.9, now_iso()))
        conn.execute("INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, "
                     "scored_at) VALUES (?,?,?,?,?,?)", (sid, aspect, "positive", 0.9, MODEL_VERSION, now_iso()))
        conn.execute("INSERT INTO sentiment_index (bank, aspect, source, window, score, n, pos_n, neu_n, neg_n, "
                     "confidence_mean, model_version, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (bank, aspect, "ALL", "all_time", 0.1 * (i + 1), 10 + i, 5, 3, 2, 0.8, MODEL_VERSION, now_iso()))
    conn.commit()
    conn.close()
    c = TestClient(app)
    c.search_kwargs = seen
    return c


def test_the_aspect_routes_are_the_expected_ones():
    print(f"\nroutes taking aspect: {ASPECT_ROUTES}")
    assert set(ASPECT_ROUTES) == {"/sentiment", "/sentiment/compare", "/sentiment/trend", "/sentiment/series",
                                  "/coverage", "/evidence", "/evidence/latest"}


@pytest.mark.parametrize("path", ASPECT_ROUTES)
@pytest.mark.parametrize("aspect", BAD_ASPECTS)
def test_unknown_aspect_is_422_on_every_route(client, path, aspect):
    resp = client.get(path, params={**REQUIRED.get(path, {}), "aspect": aspect})
    assert resp.status_code == 422, (path, aspect, resp.status_code, resp.text[:200])


@pytest.mark.parametrize("path", ASPECT_ROUTES)
@pytest.mark.parametrize("key", ASPECT_KEYS)
def test_readable_name_gives_the_same_answer_as_the_key(client, path, key):
    by_key = client.get(path, params={**REQUIRED.get(path, {}), "aspect": key})
    assert by_key.status_code == 200, by_key.text[:200]
    for readable in (key.replace("_", " "), key.replace("_", "-").title(), f"  {key.upper()} "):
        resp = client.get(path, params={**REQUIRED.get(path, {}), "aspect": readable})
        assert resp.status_code == 200, (path, readable, resp.text[:200])
        assert resp.json() == by_key.json(), (path, readable)


def test_readable_name_reaches_search_as_the_key(client):
    client.get("/evidence", params={"query": "q", "aspect": "dividend policy"})
    assert client.search_kwargs[-1]["aspect"] == "dividend_policy"


@pytest.mark.parametrize("path", ASPECT_ROUTES)
@pytest.mark.parametrize("all_value", ["ALL", "all", "", None])
def test_all_or_empty_aspect_means_every_aspect(client, path, all_value):
    params = {**REQUIRED.get(path, {}), **({} if all_value is None else {"aspect": all_value})}
    resp = client.get(path, params=params)
    assert resp.status_code == 200, (path, all_value, resp.text[:200])
    without = client.get(path, params=REQUIRED.get(path, {}))
    assert resp.json() == without.json()


class _FakeConversation:
    seen = None

    @classmethod
    def from_messages(cls, messages, backend_name=None):
        cls.seen = (messages, backend_name)
        return cls()

    def ask(self, message):
        from chatbot.agent import TurnResult
        return TurnResult(question=message, answer="ok")


@pytest.mark.parametrize("backend", ["nope", "", "anthropic", "gpt", "gemini-pro", 1])
def test_chat_unknown_backend_is_422(monkeypatch, backend):
    monkeypatch.setattr("api.main.Conversation", _FakeConversation)
    _FakeConversation.seen = None
    resp = TestClient(app).post("/chat", json={"message": "hi", "backend": backend})
    assert resp.status_code == 422, (backend, resp.status_code)
    assert _FakeConversation.seen is None      # no model was reached


@pytest.mark.parametrize("role", ["system", "tool", "User", "ASSISTANT", "", "model", "developer", None])
def test_chat_unknown_role_is_422(monkeypatch, role):
    monkeypatch.setattr("api.main.Conversation", _FakeConversation)
    _FakeConversation.seen = None
    body = {"message": "hi", "history": [{"role": "user", "content": "a"}, {"role": role, "content": "x"}]}
    resp = TestClient(app).post("/chat", json=body)
    assert resp.status_code == 422, (role, resp.status_code)
    assert _FakeConversation.seen is None


@pytest.mark.parametrize("backend", ["claude", "openai", "gemini", "ollama", None])
def test_chat_known_backend_is_accepted(monkeypatch, backend):
    monkeypatch.setattr("api.main.Conversation", _FakeConversation)
    body = {"message": "hi", "history": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]}
    if backend is not None:
        body["backend"] = backend
    resp = TestClient(app).post("/chat", json=body)
    assert resp.status_code == 200, resp.text[:200]
    assert _FakeConversation.seen[1] == backend
