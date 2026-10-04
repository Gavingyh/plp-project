"""
Tests for ingest/analyst_tag.py - the analyst-consensus proxy (broker name +
rating/action language). Both signals are required together, because
either alone is too weak (a broker named only as the article's own source
attribution, or generic rating words with no named analyst).
"""

from ingest.analyst_tag import is_analyst_view


def test_broker_and_rating_language_both_present():
    assert is_analyst_view("UOB Kay Hian maintains BUY on DBS, raises target price to S$50")


def test_broker_name_alone_is_not_enough():
    # "DBS Group Research" named, but no rating/action language at all.
    assert not is_analyst_view("DBS Group Research is a subsidiary of DBS Bank.")


def test_rating_language_alone_is_not_enough():
    assert not is_analyst_view("The stock is a solid BUY according to most retail investors.")


def test_neither_present():
    assert not is_analyst_view("DBS posted record quarterly profit.")


def test_case_insensitive_broker_match():
    assert is_analyst_view("citigroup upgrades DBS to overweight")


def test_empty_text():
    assert not is_analyst_view("")
    assert not is_analyst_view(None)
