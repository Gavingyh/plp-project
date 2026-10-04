"""
Tests for ingest/db.py - the idempotent-upsert contract every ingest adapter
relies on. This is the property confirmed in practice (a
re-run of the same Arctic Shift window produced 0 new inserts on the second
pass) - these tests lock it down so a future change can't silently break it.
"""

from ingest.db import make_doc_id, upsert_documents


def _doc(doc_id, bank="DBS", body="DBS raised guidance"):
    return {
        "doc_id": doc_id, "source": "newsapi", "source_detail": "test",
        "bank": bank, "doc_type": "article", "title": "t", "body": body,
        "published_at": "2026-01-01T00:00:00+00:00", "url": "http://example.com/1",
    }


def test_make_doc_id_deterministic():
    assert make_doc_id("newsapi", "abc") == make_doc_id("newsapi", "abc")


def test_make_doc_id_distinguishes_source():
    assert make_doc_id("newsapi", "abc") != make_doc_id("arctic_shift", "abc")


def test_upsert_new_document_inserts(temp_db):
    attempted, inserted = upsert_documents([_doc("id1")])
    assert (attempted, inserted) == (1, 1)


def test_upsert_same_doc_id_twice_is_noop_second_time(temp_db):
    upsert_documents([_doc("id1")])
    attempted, inserted = upsert_documents([_doc("id1")])
    assert (attempted, inserted) == (1, 0)
    assert temp_db.total_count() == 1  # not duplicated


def test_upsert_mixed_new_and_seen(temp_db):
    upsert_documents([_doc("id1")])
    attempted, inserted = upsert_documents([_doc("id1"), _doc("id2")])
    assert (attempted, inserted) == (2, 1)
    assert temp_db.total_count() == 2


def test_upsert_empty_list_is_safe(temp_db):
    assert upsert_documents([]) == (0, 0)


def test_count_by_source_bank(temp_db):
    upsert_documents([_doc("id1", bank="DBS"), _doc("id2", bank="OCBC")])
    counts = dict(((s, b), n) for s, b, n in temp_db.count_by_source_bank())
    assert counts[("newsapi", "DBS")] == 1
    assert counts[("newsapi", "OCBC")] == 1
