"""
Tests for ingest/base.py's bank detection/resolution - the logic behind two
regressions this suite guards against:
  1. NewsAPI's bare "DBS" query term matched unrelated global news.
  2. preprocess/pipeline.py inheriting doc-level bank onto every sentence in
     a long Reddit thread produced noise ("Calling you for $8 transaction
     is a red flag itself." tagged as DBS).
These tests don't re-test the query-construction or inheritance-source
logic directly (that's preprocess/pipeline.py's job, tested separately) -
they lock down the underlying detect_banks/resolve_bank primitives both bugs
ultimately depend on.
"""

from ingest.base import detect_banks, resolve_bank


def test_detects_full_name():
    assert detect_banks("DBS Group posted record profits") == ["DBS"]


def test_detects_bare_acronym():
    assert detect_banks("just transfer to DBS") == ["DBS"]


def test_detects_ticker():
    assert detect_banks("D05.SI hit a new high") == ["DBS"]


def test_no_bank_mentioned():
    assert detect_banks("I like index funds") == []


def test_multiple_banks_in_one_sentence():
    found = detect_banks("OCBC and UOB both reported higher profits")
    assert set(found) == {"OCBC", "UOB"}


def test_case_insensitive():
    assert detect_banks("dbs raised its dividend") == ["DBS"]


def test_word_boundary_no_partial_match():
    # "DBSK" (a K-pop group) or similar should NOT match bare "DBS" -
    # detect_banks must respect word boundaries, not substring search.
    assert detect_banks("DBSK reunion tour announced") == []


def test_resolve_bank_single_match():
    assert resolve_bank("DBS raised guidance") == "DBS"


def test_resolve_bank_multi_match_returns_multi():
    assert resolve_bank("OCBC and UOB both reported higher profits") == "MULTI"


def test_resolve_bank_no_match_returns_fallback():
    assert resolve_bank("the market was quiet today", fallback="DBS") == "DBS"


def test_resolve_bank_no_match_no_fallback_returns_none():
    assert resolve_bank("the market was quiet today") is None
