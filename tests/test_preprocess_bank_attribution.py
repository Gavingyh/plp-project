"""
Tests for preprocess/pipeline.py's per-sentence bank attribution — this is
the exact logic that produced real noise during development: inheriting a
document's bank onto every sentence in a long Reddit thread pulled in
unrelated sentences ("Calling you for $8 transaction is a red flag itself.")
as if they were about DBS. The fix restricts inheritance to short,
single-topic sources (news) and requires an explicit in-sentence mention for
long multi-topic sources (Reddit). These tests lock that distinction down.
"""

from preprocess.pipeline import _resolve_sentence_bank, _norm_hash


def test_explicit_mention_wins_regardless_of_source():
    assert _resolve_sentence_bank("DBS raised its dividend", "MULTI", "arctic_shift") == "DBS"
    assert _resolve_sentence_bank("DBS raised its dividend", "OCBC", "newsapi") == "DBS"


def test_news_source_inherits_doc_bank_when_sentence_names_none():
    # A news title+description is short and single-topic — safe to inherit.
    assert _resolve_sentence_bank("Shares rose 3% on the news", "DBS", "newsapi") == "DBS"
    assert _resolve_sentence_bank("Shares rose 3% on the news", "DBS", "alphavantage") == "DBS"
    assert _resolve_sentence_bank("Shares rose 3% on the news", "DBS", "earnings") == "DBS"


def test_reddit_does_not_inherit_doc_bank():
    # This is the fix for the real bug: a long Reddit comment about many
    # things should NOT tag every sentence with the doc's bank.
    assert _resolve_sentence_bank("Calling you for $8 transaction is a red flag itself.",
                                   "DBS", "arctic_shift") is None


def test_multi_doc_never_inherits_even_for_news():
    # MULTI means the document names more than one bank — no single bank to
    # safely inherit, regardless of source.
    assert _resolve_sentence_bank("Shares rose on the news", "MULTI", "newsapi") is None


def test_sentence_naming_two_banks_is_ambiguous():
    assert _resolve_sentence_bank("OCBC and UOB both beat estimates", "MULTI", "newsapi") is None


def test_no_mention_no_inheritable_source_drops():
    assert _resolve_sentence_bank("just a generic comment", "DBS", "arctic_shift") is None


def test_norm_hash_ignores_case_and_punctuation():
    # This is what catches syndicated wire copy republished with minor
    # formatting differences across outlets (plan Phase 2, dedup).
    assert _norm_hash("DBS raised its dividend!") == _norm_hash("dbs raised its dividend")


def test_norm_hash_distinguishes_different_text():
    assert _norm_hash("DBS raised its dividend") != _norm_hash("UOB raised its dividend")
