"""
Tests for ingest/news_filter.py: the bank-mention check, broker/venue/research
false-positive masking, and cross-source dedup that every news adapter runs
through before insert. No network calls.
"""

import csv

import pytest

import ingest.news_filter as nf
from ingest.db import upsert_documents
from ingest.news_filter import _Index, filter_and_dedup, mentioned_banks, normalise_url


@pytest.fixture
def flagged_path(tmp_path, monkeypatch):
    path = str(tmp_path / "news_flagged.csv")
    monkeypatch.setattr(nf, "FLAGGED_PATH", path)
    return path


def _doc(doc_id, title, source="google_news", published="2024-05-01T08:00:00+00:00",
         url=None, body=None):
    return {"doc_id": doc_id, "source": source, "source_detail": "pub", "bank": "DBS",
            "doc_type": "article", "title": title, "body": body or title,
            "published_at": published, "url": url or f"https://example.com/{doc_id}"}


def _flagged(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --- bank mention + false positives -------------------------------------

@pytest.mark.parametrize("title, banks, phrases", [
    ("DBS Profit Beats Estimates on Higher Lending", ["DBS"], []),
    ("DBS-led consortium wins deal", ["DBS"], []),
    ("FBP or DBSDY: Which Is the Better Value Stock", ["DBS"], []),
    ("POSB digital banking services restored", ["DBS"], []),
    ("Oversea-Chinese Banking (SGX:O39) valuation", ["OCBC"], []),
    ("DBSK reunion tour announced", [], []),
    ("Bank of Singapore hires 20 bankers", [], []),
    # broker / venue names that contain a bank's name
    ("UOB Kay Hian raises ComfortDelGro target price", [], ["UOB Kay Hian"]),
    ("UOB-Kay Hian names top picks", [], ["UOB Kay Hian"]),
    ("UOB Kay Hian upgrades DBS to buy", ["DBS"], ["UOB Kay Hian"]),
    ("DBS Vickers launches new trading app", ["DBS"], []),            # DBS's brokerage counts as DBS
    ("OCBC Cycle 2024 returns in May", [], ["OCBC Cycle"]),
    # the bank's research desk talking about something else
    ("DBS maintains 'buy' on IHH Healthcare", [], ["rating call"]),
    ("OCBC cuts gold and silver forecasts", [], ["rating call"]),
    ("OCBC's Lim raises fair value for SingPost to 49.5 cents", [], ["rating call"]),
    ("OCBC economist expects Singapore GDP to slow", [], ["research attribution"]),
    ("UOB analysts say DBS results beat estimates", ["DBS"], ["research attribution"]),
    # the bank's own news that uses a rating-ish verb must not be masked
    ("DBS raises dividend, shares hit record high", ["DBS"], []),
    ("DBS's CEO Tan Su Shan sells shares", ["DBS"], []),
    ("UOB CEO Lowers Loan Growth Forecast as First-Quarter Profit Leaps 67%", ["UOB"], []),
    ("OCBC keeps 2025 earnings guidance amid uncertainties; Q1 profit falls 5%", ["OCBC"], []),
    # the banks' daily market notes, syndicated by FX sites
    ("Australian Dollar: Gradual upside within capped range against US Dollar – UOB", [], ["market note"]),
    ("Japanese Yen: Two-way risks into BoJ meeting – OCBC", [], ["market note"]),
    ("Singapore Dollar: Range trade holds near recent lows – UOB", [], ["market note"]),
    # a trailing credit that isn't a market note stays a mention
    ("Citibank consumer banking acquisition to be complete by Nov: UOB", ["UOB"], []),
    ("Asia's best digital bank 2025: DBS", ["DBS"], []),
    ("Singapore’s best FX bank 2025: DBS", ["DBS"], []),
    ("Tokenized Physical Gold: DBS Unveils Strong 1-Gram Tokens", ["DBS"], []),
    ("E-hongbao for CNY: Avoid scanning QR gift card that looks tampered with, says DBS", ["DBS"], []),
])
def test_mentioned_banks(title, banks, phrases):
    assert mentioned_banks(title) == (banks, phrases)


def test_normalise_url_ignores_scheme_www_and_tracking():
    a = "https://www.example.com/story/1/?utm_source=x"
    b = "http://example.com/story/1"
    assert normalise_url(a) == normalise_url(b)


# --- dedup ----------------------------------------------------------------

def test_similar_title_within_window_is_duplicate():
    idx = _Index()
    idx.add("a", "DBS profit beats estimates on higher lending", "https://x.com/1",
            "2024-05-01T00:00:00+00:00")
    assert idx.find_duplicate("DBS Profit Beats Estimates On Higher Lending!", "https://y.com/2",
                              "2024-05-03T00:00:00+00:00") == "a"


def test_similar_title_outside_window_is_not_duplicate():
    idx = _Index()
    idx.add("a", "DBS profit beats estimates on higher lending", "https://x.com/1",
            "2024-05-01T00:00:00+00:00")
    assert idx.find_duplicate("DBS profit beats estimates on higher lending", "https://y.com/2",
                              "2024-08-01T00:00:00+00:00") is None


def test_different_title_same_day_is_not_duplicate():
    idx = _Index()
    idx.add("a", "DBS profit beats estimates on higher lending", "https://x.com/1",
            "2024-05-01T00:00:00+00:00")
    assert idx.find_duplicate("OCBC profit misses estimates on lower NIM", "https://y.com/2",
                              "2024-05-01T00:00:00+00:00") is None


# --- filter_and_dedup end to end ------------------------------------------

def test_filter_keeps_rejects_and_flags(temp_db, flagged_path):
    docs = [
        _doc("keep", "DBS profit beats estimates"),
        _doc("nobank", "Singapore core inflation eases"),
        _doc("broker", "UOB Kay Hian raises ComfortDelGro target price"),
        _doc("dup", "DBS Profit Beats Estimates", source="yahoo_news"),
        _doc("phrase", "UOB Kay Hian upgrades OCBC to buy"),
    ]
    kept, stats = filter_and_dedup(docs)

    assert [d["doc_id"] for d in kept] == ["keep", "phrase"]
    assert kept[1]["bank"] == "OCBC"  # re-resolved from text, not the queried bank
    assert kept[1]["raw"]["_masked_phrases"] == ["UOB Kay Hian"]
    assert stats["no_bank_mention"] == 1 and stats["false_positive_only"] == 1
    assert stats["duplicate"] == 1 and stats["kept_with_phrase"] == 1

    reasons = {r["doc_id"]: r["reason"] for r in _flagged(flagged_path)}
    assert reasons == {"nobank": "no_bank_mention", "broker": "false_positive_only",
                       "dup": "duplicate", "phrase": "kept_with_false_positive_phrase"}


def test_multi_bank_headline_becomes_multi(temp_db, flagged_path):
    kept, _ = filter_and_dedup([_doc("m", "OCBC and UOB both report higher profits")])
    assert kept[0]["bank"] == "MULTI"


def test_duplicate_of_already_stored_news_from_another_source(temp_db, flagged_path):
    upsert_documents([_doc("old", "Allianz to buy UOB's asset management arm", source="newsapi",
                           published="2026-08-06T10:00:00+00:00")])
    kept, stats = filter_and_dedup([_doc("new", "Allianz to buy UOB’s asset management arm",
                                         source="yahoo_news", published="2026-08-06T15:03:05+00:00")])
    assert kept == [] and stats["duplicate"] == 1


def test_rerun_is_idempotent(temp_db, flagged_path):
    docs = [_doc("keep", "DBS profit beats estimates"), _doc("nobank", "Singapore inflation eases")]
    kept, _ = filter_and_dedup(docs)
    upsert_documents(kept)
    n_flagged = len(_flagged(flagged_path))

    kept2, stats2 = filter_and_dedup(docs)
    assert kept2 == [] and stats2["already_stored"] == 1 and stats2["duplicate"] == 0
    assert len(_flagged(flagged_path)) == n_flagged  # review file doesn't grow on re-run


def test_trailing_attribution_is_kept_but_flagged(temp_db, flagged_path):
    kept, stats = filter_and_dedup([_doc("fx", "Vietnam currency to strengthen towards year-end: UOB")])
    assert [d["doc_id"] for d in kept] == ["fx"]  # kept: some such headlines are about the bank
    assert stats["kept_possible_commentary"] == 1
    assert _flagged(flagged_path)[0]["reason"] == "kept_possible_bank_commentary"


def test_audit_flags_stored_rows_without_changing_them(temp_db, flagged_path):
    upsert_documents([_doc("old", "OCBC's Lim cuts fair value for SingPost to 44 cents")])
    stats = nf.audit_stored()
    assert stats["fails_current_rules"] == 1
    assert temp_db.total_count() == 1  # audit never deletes
    assert _flagged(flagged_path)[0]["reason"] == "stored_fails_current_rules"


def test_rating_call_rejected_when_body_repeats_title(temp_db, flagged_path):
    # Google rows store the headline as both title and body. The rules once ran
    # on title + body, so the start-anchored "rating call" rule masked only the
    # first copy and the headline slipped through on the second.
    kept, stats = filter_and_dedup([_doc("rc", "DBS maintains 'buy' on IHH Healthcare")])
    assert kept == [] and stats["false_positive_only"] == 1


# --- full text over a headline-only copy --------------------------------

def test_full_text_is_kept_over_a_headline_only_copy(temp_db, flagged_path):
    upsert_documents([_doc("gn", "DBS sued for US$1 billion in 1MDB-linked claim",
                           published="2026-09-09T13:00:00+00:00")])
    article = _doc("cna", "DBS sued for US$1 billion in 1MDB-linked claim", source="cna",
                   published="2026-09-09T21:25:00+08:00",
                   body="DBS sued for US$1 billion in 1MDB-linked claim\nDBS rejected the claim.")
    kept, stats = filter_and_dedup([article])

    assert [d["doc_id"] for d in kept] == ["cna"]
    assert stats["kept_full_text_over_headline"] == 1 and stats["duplicate"] == 0
    row = _flagged(flagged_path)[0]
    assert row["reason"] == "kept_full_text_over_headline" and row["duplicate_of"] == "gn"


def test_full_text_is_still_a_duplicate_of_a_fuller_copy(temp_db, flagged_path):
    upsert_documents([
        _doc("gn", "DBS sued for US$1 billion in 1MDB-linked claim", published="2026-09-09T13:00:00+00:00"),
        _doc("yh", "DBS sued for US$1 billion in 1MDB-linked claim", source="yahoo_news",
             published="2026-09-09T14:00:00+00:00", body="Liquidators sued DBS Bank on Wednesday."),
    ])
    article = _doc("cna", "DBS sued for US$1 billion in 1MDB-linked claim", source="cna",
                   published="2026-09-09T21:25:00+08:00", body="Full story about DBS.")
    kept, stats = filter_and_dedup([article])
    assert kept == [] and stats["duplicate"] == 1


def test_headline_only_copy_of_stored_full_text_is_a_duplicate(temp_db, flagged_path):
    upsert_documents([_doc("cna", "DBS sued for US$1 billion in 1MDB-linked claim", source="cna",
                           published="2026-09-09T21:25:00+08:00", body="Full story about DBS.")])
    kept, stats = filter_and_dedup([_doc("gn", "DBS sued for US$1 billion in 1MDB-linked claim",
                                         published="2026-09-09T13:00:00+00:00")])
    assert kept == [] and stats["duplicate"] == 1
