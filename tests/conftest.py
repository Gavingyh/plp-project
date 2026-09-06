"""
Shared pytest fixtures. `temp_db` redirects ingest.db.DB_PATH to a throwaway
file for the duration of a test, so tests never touch data/plp.db (the real
pipeline's live data) and don't depend on or interfere with each other.
"""

import os

import pytest

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # model is cached locally; avoids the HF rate-limit hang


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    import ingest.db as db_module

    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()

    # sentence_aspects / aspect_sentiment / sentiment_index are normally
    # created lazily the first time aspects.assign / sentiment.score /
    # aggregate.index actually run — pull their schemas in here too so any
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
