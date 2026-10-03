"""Tests for preprocess/clean.py's per-source text cleaning."""

from preprocess.clean import clean_earnings, clean_for_source, clean_news, clean_reddit


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


def test_clean_reddit_unescapes_html_so_a_quoted_parent_line_is_dropped():
    # Reddit text arrives HTML-escaped, so a quoted parent line starts "&gt;"
    # and slipped past the quote rule, kept as the commenter's own words.
    result = clean_reddit("&gt; someone else's quoted comment\nDBS &amp; OCBC both cut rates &lt;3")
    assert result == "DBS & OCBC both cut rates <3"


def test_clean_reddit_drops_zero_width_spaces_and_markdown_escapes():
    text = ("&#x200B;\n\nRates fell \\~0.5%&nbsp;at DBS\\-OCBC, \\#1 is a\\_b\\_c 2\\*3\\*4\n"
            "\\> not a quote, an escaped bracket")
    assert clean_reddit(text) == ("Rates fell ~0.5% at DBS-OCBC, #1 is a_b_c 2*3*4 "
                                  "> not a quote, an escaped bracket")


def test_clean_reddit_strips_markdown_links():
    result = clean_reddit("check [this article](https://example.com) about DBS")
    assert "this article" in result
    assert "https://example.com" not in result


def test_clean_reddit_preserves_case():
    # Deliberate: FinBERT is cased-aware, casing carries sentiment signal.
    assert clean_reddit("DBS is GREAT this quarter") == "DBS is GREAT this quarter"


def test_clean_earnings_collapses_whitespace():
    assert clean_earnings("DBS   reported\n\nstrong   results") == "DBS reported strong results"


def test_clean_cna_ends_headline_and_paragraphs_as_sentences():
    text = "DBS sued in 1MDB-linked claim\nDBS rejected the claim\nSINGAPORE: Liquidators sued DBS Bank."
    assert clean_for_source("cna", text) == (
        "DBS sued in 1MDB-linked claim. DBS rejected the claim. Liquidators sued DBS Bank.")


def test_clean_cna_strips_each_dateline_form():
    text = "Headline\nWASHINGTON, Sept 19 : The US said so.\nSept 18 : NASA is in talks."
    assert clean_for_source("cna", text) == "Headline. The US said so. NASA is in talks."


def test_clean_cna_keeps_a_bank_name_before_a_colon():
    assert clean_for_source("cna", "Headline\nDBS: we will fight it.") == "Headline. DBS: we will fight it."


def test_clean_cna_drops_subheadings_footnotes_bullets_and_boilerplate():
    text = ("Headline\nNEW TALKS ON AI\n• OCBC could not be reached for comment\n"
            "($1 = 1.35 SGD)\nSource: CNA/rj")
    assert clean_for_source("cna", text) == "Headline. OCBC could not be reached for comment."
