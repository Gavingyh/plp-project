"""
Shared pytest fixtures. `temp_db` redirects ingest.db.DB_PATH to a throwaway
file for the duration of a test, so tests never touch data/plp.db (the real
pipeline's live data) and don't depend on or interfere with each other.
"""

import os

import pytest

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # model is cached locally; avoids the HF rate-limit hang


@pytest.fixture(autouse=True)
def intent_in_scope(monkeypatch):
    """The chatbot's intent classifier calls Ollama; in tests it answers
    "in_scope" unless a test sets another answer, so no test reaches a model."""
    monkeypatch.setattr("chatbot.intent.ollama_chat", lambda model, messages, names: '{"intent": "in_scope"}')


@pytest.fixture(autouse=True)
def no_model_loading(monkeypatch):
    """The Ollama backend loads its model before the first request
    (chatbot/ollama_load.py); in tests it doesn't, so none reaches a real
    Ollama. Returns the real function for the tests of the step itself."""
    from chatbot import ollama_load
    real = ollama_load.ensure_loaded
    monkeypatch.setattr(ollama_load, "ensure_loaded", lambda *a, **k: False)
    return real


@pytest.fixture(autouse=True)
def no_real_chatbot_backend(monkeypatch):
    """A test that reaches the chatbot model must give it a fake backend: the
    configured one can be a real service (Gemini, when CHATBOT_BACKEND says so),
    and on 4 Oct 2026 a test reached it. Tests that set agent.get_backend replace this."""
    def refuse(*a, **k):
        raise RuntimeError("tests must not reach a real chatbot backend: pass a fake one")
    monkeypatch.setattr("chatbot.agent.get_backend", refuse)


@pytest.fixture(autouse=True)
def no_rate_limit_pacing(monkeypatch):
    """The hosted backends pace their requests and count them in data/ratelimit_state.json
    (chatbot/ratelimit.py). A test with a mocked HTTP call must neither sleep nor add to the
    real budget, so pacing is off unless a test builds a Pacer itself."""
    monkeypatch.setattr("chatbot.ratelimit.get_pacer", lambda provider: None)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    import ingest.db as db_module

    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()

    # sentence_aspects / aspect_sentiment / sentiment_index are normally
    # created lazily the first time aspects.assign / sentiment.score /
    # aggregate.index actually run - pull their schemas in here too so any
    # test can insert directly into them without running the full pipeline.
    import aggregate.index as aggregate_module
    import sentiment.score as score_module
    import aspects.assign as assign_module

    conn = db_module.get_connection()
    conn.executescript(assign_module._SCHEMA)
    conn.executescript(score_module._SCHEMA)
    conn.executescript(aggregate_module._SCHEMA)
    conn.commit()
    conn.close()

    yield db_module
