"""Tests for preprocess/clean.py's per-source text cleaning."""

from preprocess.clean import clean_earnings, clean_news, clean_reddit


def test_clean_news_strips_truncation_marker():
    assert clean_news("DBS posted record profits [+2130 chars]") == "DBS posted record profits"


def test_clean_news_strips_dateline():
    assert clean_news("(Reuters) - DBS posted record profits") == "DBS posted record profits"


def test_clean_news_strips_urls():
    assert "http" not in clean_news("Read more at https://example.com/article DBS profits up")


def test_clean_reddit_drops_automod_comments():
    assert clean_reddit("I am a bot, and this action was performed automatically.") is None


def test_clean_reddit_strips_quoted_parent_text():
    result = clean_reddit("> someone else's quoted comment\nMy actual reply about DBS")
    assert "quoted comment" not in result
    assert "DBS" in result


def test_clean_reddit_strips_markdown_links():
    result = clean_reddit("check [this article](https://example.com) about DBS")
    assert "this article" in result
    assert "https://example.com" not in result


def test_clean_reddit_preserves_case():
    # Deliberate: FinBERT is cased-aware, casing carries sentiment signal.
    assert clean_reddit("DBS is GREAT this quarter") == "DBS is GREAT this quarter"


def test_clean_earnings_collapses_whitespace():
    assert clean_earnings("DBS   reported\n\nstrong   results") == "DBS reported strong results"
