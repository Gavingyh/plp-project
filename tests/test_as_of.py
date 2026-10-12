"""The 7- and 30-day windows end at the newest stored sentence, and the API
says which date that is (data_as_of)."""

import pytest
from fastapi.testclient import TestClient

from aggregate.index import as_of_fields, run as run_aggregate
from config.model_version import MODEL_VERSION
from ingest.db import now_iso


def _scored(temp_db, sid, bank, aspect, label, published_at):
    conn = temp_db.get_connection()
    conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, norm_hash, "
                 "processed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (sid, f"doc-{sid}", bank, "some text", published_at, "arctic_shift", "http://example.com",
                  f"hash-{sid}", now_iso()))
    conn.execute("INSERT INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) VALUES (?,?,1.0,?)",
                 (sid, aspect, now_iso()))
    conn.execute("INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, scored_at) "
                 "VALUES (?,?,?,?,?,?)", (sid, aspect, label, 0.9, MODEL_VERSION, now_iso()))
    conn.commit()
    conn.close()


@pytest.fixture
def stopped_corpus(temp_db):
    """Twelve DBS sentences in the week before 25 Sep 2026, the newest date: long
    before today, so only a window that ends at the newest sentence holds any."""
    for i in range(12):
        _scored(temp_db, f"s{i}", "DBS", "dividend_policy", "positive" if i % 3 else "negative",
                f"2026-09-{25 - i % 6:02d}T08:00:00+00:00")
    run_aggregate()
    return temp_db


def test_a_windowed_figure_says_when_it_ends(stopped_corpus):
    assert as_of_fields("all_time") == {"data_as_of": "2026-09-25"}
    week = as_of_fields("7d")
    assert week["data_as_of"] == "2026-09-25"
    assert "the 7 days to 2026-09-25" in week["window_note"] and "not to today" in week["window_note"]


def test_nothing_to_say_before_any_sentence_is_stored(temp_db):
    assert as_of_fields("7d") == {}


def test_the_api_says_as_of(stopped_corpus):
    from api.main import app
    client = TestClient(app)
    week = client.get("/sentiment", params={"bank": "DBS", "aspect": "dividend_policy", "window": "7d"}).json()
    assert week["insufficient_data"] is False and week["n"] == 12        # the stopped corpus still has a week
    assert week["data_as_of"] == "2026-09-25" and "not to today" in week["window_note"]
    assert "window_note" not in client.get("/sentiment", params={"bank": "DBS"}).json()
    grid = client.get("/sentiment/index", params={"window": "7d"}).json()
    assert grid["data_as_of"] == "2026-09-25" and "not to today" in grid["window_note"] and grid["rows"]
    assert client.get("/sentiment/compare", params={"window": "30d"}).json()["data_as_of"] == "2026-09-25"
    assert client.get("/sentiment/trend", params={"bank": "DBS"}).json()["data_as_of"] == "2026-09-25"


def test_the_chatbot_tools_are_left_as_they_were(stopped_corpus):
    """The chatbot already tells the reader when the data runs to
    (data_runs_to); the API's fields are not added to what the model reads."""
    import chatbot.tools as tools
    out = tools.chat_get_sentiment("DBS", "dividend_policy", window="7d")
    assert "data_as_of" not in out and "window_note" not in out and out["data_runs_to"] == "2026-09-25"
