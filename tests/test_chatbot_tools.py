"""
Tests for chatbot/tools.py - the structured-data tools the agent calls.
Includes a regression test for a previously-fixed defect:
get_coverage's `where` clause list was built for one query (joined to
sentence_aspects when `aspect` was given) and reused verbatim for a second
query that never performed that join, causing
"sqlite3.OperationalError: no such column: sa.aspect".
"""

from chatbot.tools import ASPECT_KEYS, TOOL_SCHEMAS, get_coverage, get_sentiment
from ingest.db import now_iso


def _insert_scored_sentence(temp_db, sentence_id, bank, aspect, label, confidence, n_docs=1):
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


def test_get_coverage_with_bank_and_aspect_does_not_crash(temp_db):
    # This is the exact regression case: bank + aspect both given, which
    # triggers the join-mismatch bug if it's reintroduced.
    _insert_scored_sentence(temp_db, "s1", "OCBC", "dividend_policy", "positive", 0.9)
    result = get_coverage(bank="OCBC", aspect="dividend_policy")
    assert result["has_data"] is True
    assert result["n"] == 1
    assert result["by_source"] == {"arctic_shift": 1}


def test_get_coverage_bank_only(temp_db):
    _insert_scored_sentence(temp_db, "s1", "DBS", "dividend_policy", "positive", 0.9)
    result = get_coverage(bank="DBS")
    assert result["has_data"] is True
    assert result["n"] == 1


def test_get_coverage_no_data_returns_false(temp_db):
    result = get_coverage(bank="UOB", aspect="net_interest_margin")
    assert result["has_data"] is False
    assert result["n"] == 0


def test_get_sentiment_no_data_flags_insufficient(temp_db):
    result = get_sentiment("DBS", "asset_quality")
    assert result["insufficient_data"] is True


# ---------------------------------------------------------------------------
# Aspect normalization - regression coverage for a real bug found while
# building the chatbot evaluation harness: a model called get_sentiment with
# aspect="dividend policy" (space) instead of "dividend_policy" (the real
# key), silently getting insufficient_data on a perfectly valid question.
# ---------------------------------------------------------------------------

def test_normalize_aspect_converts_spaces_to_underscores():
    from chatbot.tools import normalize_aspect
    assert normalize_aspect("dividend policy") == "dividend_policy"


def test_normalize_aspect_case_insensitive():
    from chatbot.tools import normalize_aspect
    assert normalize_aspect("Net Interest Margin") == "net_interest_margin"


def test_normalize_aspect_leaves_unrecognised_value_untouched():
    from chatbot.tools import normalize_aspect
    # An unknown aspect must not be silently mapped to something else -
    # left as-is so it still surfaces as insufficient_data downstream.
    assert normalize_aspect("totally_wrong_aspect") == "totally_wrong_aspect"


def test_normalize_aspect_passes_none_through():
    from chatbot.tools import normalize_aspect
    assert normalize_aspect(None) is None


def test_coerce_tool_arguments_normalizes_aspect_for_get_sentiment():
    from chatbot.tools import coerce_tool_arguments
    result = coerce_tool_arguments("get_sentiment", {"bank": "DBS", "aspect": "dividend policy"})
    assert result["aspect"] == "dividend_policy"


def test_all_aspect_schema_properties_have_the_real_enum():
    """Every tool that takes an aspect must constrain it to the real
    taxonomy, not accept an arbitrary string - that's what let the bug above
    happen in the first place."""
    for schema in TOOL_SCHEMAS:
        props = schema["input_schema"].get("properties", {})
        if "aspect" in props:
            assert props["aspect"].get("enum") == ASPECT_KEYS, schema["name"]
