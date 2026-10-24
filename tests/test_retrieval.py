"""
Tests for chatbot/retrieval.py's candidate handling. The embedding store and
model are replaced, so ranking falls back to lexical overlap.
"""

import chatbot.retrieval as retrieval
from ingest.db import now_iso
from config.model_version import MODEL_VERSION


def test_sentiment_filter_returns_each_sentence_once(temp_db, monkeypatch):
    monkeypatch.setattr(retrieval, "load_for_search", lambda: ([], None))
    conn = temp_db.get_connection()
    conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
                 "norm_hash, processed_at) VALUES ('s1','d','DBS','DBS raised its dividend',"
                 "'2026-01-01','cna','u','h1',?)", (now_iso(),))
    for aspect in ("dividend_policy", "income_profit_results", "wealth_business"):
        conn.execute("INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, "
                     "scored_at) VALUES ('s1', ?, 'positive', 0.9, ?, ?)", (aspect, MODEL_VERSION, now_iso()))
    conn.commit()
    conn.close()
    hits = retrieval.search_evidence("dividend", bank="DBS", sentiment="positive", k=5)
    assert [h["sentence_id"] for h in hits] == ["s1"]


def _two_dividend_sentences(temp_db):
    conn = temp_db.get_connection()
    rows = [("s1", "What do people say about this, anyone?"),
            ("s2", "The board kept its dividend policy unchanged at 60 cents.")]
    for sid, text in rows:
        conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
                     "norm_hash, processed_at) VALUES (?,'d','DBS',?,'2026-01-01','cna','u',?,?)",
                     (sid, text, f"h-{sid}", now_iso()))
        conn.execute("INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, "
                     "scored_at) VALUES (?, 'dividend_policy', 'neutral', 0.9, ?, ?)", (sid, MODEL_VERSION, now_iso()))
    conn.commit()
    conn.close()


def test_aspect_query_flag_ranks_by_the_aspect_not_the_question_words(temp_db, monkeypatch):
    """Question words favour chatter by default; CHATBOT_ASPECT_QUERY ranks by the aspect.
    This is the FinBERT ordering, kept behind evidence.within_topic: embedding."""
    import numpy as np
    real_get = retrieval.settings.get
    monkeypatch.setattr(retrieval.settings, "get",
                        lambda path: "embedding" if path == "evidence.within_topic" else real_get(path))
    monkeypatch.setattr(retrieval, "load_for_search", lambda: (["s1", "s2"], np.eye(2)))
    embedded = []
    monkeypatch.setattr(retrieval, "embed_sentences", lambda texts: embedded.append(texts[0]) or np.array([[0.5, 0.5]]))
    _two_dividend_sentences(temp_db)
    q = "What do people say about DBS's dividend policy?"

    monkeypatch.setenv("CHATBOT_ASPECT_QUERY", "0")
    off = retrieval.search_evidence(q, bank="DBS", aspect="dividend_policy", k=2)
    assert off[0]["sentence_id"] == "s1" and embedded[-1] == q            # equal cosine; question words decide

    monkeypatch.delenv("CHATBOT_ASPECT_QUERY", raising=False)             # on by default
    flagged = retrieval.search_evidence(q, bank="DBS", aspect="dividend_policy", k=2)
    assert flagged[0]["sentence_id"] == "s2" and embedded[-1] == "Dividend Policy"


def test_a_report_disclaimer_is_never_returned_as_evidence(temp_db, monkeypatch):
    monkeypatch.setattr(retrieval, "load_for_search", lambda: ([], None))
    conn = temp_db.get_connection()
    rows = [("s1", "Please refer to Disclaimer Target Price && Ratings History -- OCBC dividend"),
            ("s2", "IF THIS REPORT IS DISTRIBUTED IN THE UNITED STATES IT IS DISTRIBUTED BY A BROKER, on OCBC dividend"),
            ("s3", "OCBC is targeting a dividend payout ratio of 60%.")]
    for sid, text in rows:
        conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
                     "norm_hash, processed_at) VALUES (?,'d','OCBC',?,'2026-01-01','sgx_research','u',?,?)",
                     (sid, text, f"h-{sid}", now_iso()))
    conn.commit()
    conn.close()
    hits = retrieval.search_evidence("OCBC dividend", bank="OCBC", k=5)
    assert [h["sentence_id"] for h in hits] == ["s3"]
