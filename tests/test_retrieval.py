"""
Tests for chatbot/retrieval.py's candidate handling. The embedding store and
model are replaced, so ranking falls back to lexical overlap.
"""

import chatbot.retrieval as retrieval
from ingest.db import now_iso


def test_sentiment_filter_returns_each_sentence_once(temp_db, monkeypatch):
    monkeypatch.setattr(retrieval, "load_for_search", lambda: ([], None))
    conn = temp_db.get_connection()
    conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
                 "norm_hash, processed_at) VALUES ('s1','d','DBS','DBS raised its dividend',"
                 "'2026-01-01','cna','u','h1',?)", (now_iso(),))
    for aspect in ("dividend_policy", "income_profit_results", "wealth_business"):
        conn.execute("INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, "
                     "scored_at) VALUES ('s1', ?, 'positive', 0.9, 'm', ?)", (aspect, now_iso()))
    conn.commit()
    conn.close()
    hits = retrieval.search_evidence("dividend", bank="DBS", sentiment="positive", k=5)
    assert [h["sentence_id"] for h in hits] == ["s1"]
