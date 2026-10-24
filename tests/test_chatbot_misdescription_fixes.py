"""The fixes for answers a person rated unfaithful although every number in
them came from a tool: the wrong year for the data, the wrong rank, invented
sub-topics, and evidence ranked worse than chance within one topic."""

import pytest

import chatbot.retrieval as retrieval
import chatbot.tools as tools
from chatbot.guards import unverified_years
from config.model_version import MODEL_VERSION
from ingest.db import now_iso


def test_the_data_date_is_given_in_words():
    assert tools._day_in_words("2026-09-25") == "25 September 2026"
    assert tools._day_in_words("2026-09-05T10:00:00+00:00") == "5 September 2026"
    assert tools._day_in_words(None) is None


def test_the_rank_is_a_sentence_that_names_every_place():
    s = tools._rank_in_words("OCBC", ["DBS", "OCBC", "UOB"], "Asset Quality / Provisioning")
    assert s == "Of the three banks on Asset Quality / Provisioning, OCBC is second (DBS first, OCBC second, UOB third)."
    assert tools._rank_in_words("UOB", ["DBS", "UOB"], None) == \
        "Of the 2 banks with enough data overall, UOB is second (DBS first, UOB second)."
    assert tools._rank_in_words("OCBC", ["DBS"], None) is None


def test_topics_and_the_scope_of_one_topic_are_sentences():
    strong = [{"topic_name": "Dividend Policy", "score": 0.4553}]
    weak = [{"topic_name": "Retail Banking", "score": -0.0284}]
    assert tools._topics_in_words(strong, weak) == "Topics lifting it: Dividend Policy (+0.46); dragging it: Retail Banking (-0.03)."
    assert tools._topics_in_words([], []) is None
    assert "no breakdown into smaller topics" in tools._topic_scope("Macro / Market Environment")


@pytest.mark.parametrize("answer, results, question, flagged", [
    ("The data runs to September 2023, based on 414 sentences.", [{"data_runs_to": "2026-09-25"}], "", ["2023"]),
    ("The data runs to 25 September 2026.", [{"data_runs_to": "2026-09-25"}], "", []),
    ("August 2024 was up on July 2024.", [{"latest_month": {"period": "2024-08"}}], "", []),
    ("Compared with 2021, as you asked.", [{}], "How did 2021 compare?", []),
    ("A score of 2,023 out of 3,000, or 0.2023.", [{}], "", []),
    ("Sentiment fell in 2019 and 2019 again.", [{}], "", ["2019"]),
])
def test_a_year_no_tool_returned_is_flagged(answer, results, question, flagged):
    assert unverified_years(answer, results, question) == flagged


def test_an_unreturned_year_is_rewritten_or_trimmed_like_any_figure():
    from chatbot.agent import _figure_and_reading_flags, _ToolCallTracker
    tracker = _ToolCallTracker()
    tracker.calls.append({"name": "get_sentiment", "arguments": {}, "result": {"score": 0.4553, "n": 414, "data_runs_to": "2026-09-25"}})
    figures, _ = _figure_and_reading_flags("The score is +0.46 on 414 sentences; the data runs to September 2023.", tracker, "")
    assert figures == ["2023"]


def _sentence(conn, sid, text, published_at, aspect="dividend_policy"):
    conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, norm_hash, "
                 "processed_at) VALUES (?, 'd', 'DBS', ?, ?, 'arctic_shift', 'u', ?, ?)", (sid, text, published_at, f"h{sid}", now_iso()))
    conn.execute("INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, scored_at) "
                 "VALUES (?, ?, 'neutral', 0.9, ?, ?)", (sid, aspect, MODEL_VERSION, now_iso()))


def test_within_a_topic_evidence_is_ordered_by_its_words_then_newest(temp_db, monkeypatch):
    monkeypatch.setattr(retrieval, "load_for_search", lambda: ([], None))
    conn = temp_db.get_connection()
    _sentence(conn, "old_match", "The dividend went up again.", "2024-01-01T00:00:00+00:00")
    _sentence(conn, "new_match", "Their dividend policy looks steady.", "2026-09-01T00:00:00+00:00")
    _sentence(conn, "newest_other", "I opened an account last week.", "2026-09-20T00:00:00+00:00")
    _sentence(conn, "mid_match", "Dividend policy is generous.", "2025-06-01T00:00:00+00:00")
    conn.commit(); conn.close()
    hits = retrieval.search_evidence("What do people say about DBS's dividend policy?", bank="DBS",
                                     aspect="dividend_policy", k=4)
    assert [h["sentence_id"] for h in hits] == ["new_match", "mid_match", "old_match", "newest_other"]


def test_a_search_within_a_topic_needs_no_embedding(temp_db, monkeypatch):
    def unused(*_):
        raise AssertionError("a search within a topic should not embed or load vectors")
    monkeypatch.setattr(retrieval, "load_for_search", unused)
    monkeypatch.setattr(retrieval, "embed_sentences", unused)
    conn = temp_db.get_connection()
    _sentence(conn, "s1", "Their dividend policy looks steady.", "2026-09-01T00:00:00+00:00")
    conn.commit(); conn.close()
    hits = retrieval.search_evidence("dividend policy", bank="DBS", aspect="dividend_policy", k=3)
    assert [h["sentence_id"] for h in hits] == ["s1"]
