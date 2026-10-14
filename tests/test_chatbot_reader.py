"""
What the chatbot's model is given to answer a retail investor:
the reading of a score in words, the shares of positive and negative
sentences, a bank's strongest and weakest topics, a comparison's ranking, the
latest months when the 7- and 30-day windows are too thin, evidence without
repeats, and numbered citations. Before this a local model wrote "0.122 out of
1", called +0.124 "slightly negative", said a trend was "not available" with
66 months of data stored, and cited the same report sentence once a quarter.
The API's own results must stay as they were.
"""

import pytest

import config.model_version as current_model
from chatbot import tools
from chatbot.agent import _ToolCallTracker, number_citations
from chatbot.guards import unverified_numbers
from ingest.db import now_iso


def _add(temp_db, sid, bank, aspect, published, label, source="arctic_shift"):
    conn = temp_db.get_connection()
    conn.execute(
        "INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
        "norm_hash, processed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (sid, f"doc-{sid}", bank, f"text {sid}", published, source, "http://example.com",
         f"hash-{sid}", now_iso()))
    conn.execute("INSERT INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) VALUES (?,?,1.0,?)",
                 (sid, aspect, now_iso()))
    conn.execute("INSERT INTO aspect_sentiment (sentence_id, aspect, label, confidence, model_version, scored_at) "
                 "VALUES (?,?,?,1.0,?,?)", (sid, aspect, label, current_model.MODEL_VERSION, now_iso()))
    conn.commit()
    conn.close()


def _index(temp_db, cells):
    """cells: (bank, aspect, month, positive, neutral, negative) -> sentences in that month, then the index."""
    import aggregate.index as agg
    i = 0
    for bank, aspect, month, pos, neu, neg in cells:
        for label, count in (("positive", pos), ("neutral", neu), ("negative", neg)):
            for _ in range(count):
                _add(temp_db, f"s{i}", bank, aspect, f"{month}-{1 + i % 27:02d}T00:00:00+00:00", label)
                i += 1
    agg.run()


# --- the reading of a score ----------------------------------------------------

def test_reading_puts_a_score_in_words_on_the_right_side_of_zero():
    assert tools.reading(0.03) == "neutral"
    assert tools.reading(-0.049) == "neutral"
    assert tools.reading(0.124) == "slightly positive"      # an answer once called this "slightly negative"
    assert tools.reading(-0.05) == "slightly negative"
    assert tools.reading(0.2) == "moderately positive"
    assert tools.reading(-0.35) == "clearly negative"


# --- get_sentiment, compare_banks ----------------------------------------------------

def test_overall_score_comes_with_shares_topics_and_the_data_date(temp_db):
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 8, 2, 0),
                     ("DBS", "retail_banking_sentiment", "2026-08", 1, 3, 6),
                     ("DBS", "net_interest_margin", "2026-09", 4, 6, 0),
                     ("DBS", "asset_quality", "2026-09", 2, 7, 1)])
    r = tools.chat_get_sentiment("DBS")
    print(f"\n{r}")
    assert r["reading"] == tools.reading(r["score"])
    assert abs(r["positive_pct"] + r["neutral_pct"] + r["negative_pct"] - 100) < 0.2
    assert r["positive_pct"] == round(100 * r["positive_n"] / r["n"], 1)
    strongest = [t["topic_name"] for t in r["strongest_topics"]]
    weakest = [t["topic_name"] for t in r["weakest_topics"]]
    assert strongest[0] == "Dividend Policy" and weakest[0].startswith("Retail Banking")
    assert not set(strongest) & set(weakest)
    assert r["data_runs_to"].startswith("2026-09")
    for unreadable in ("computed_at", "model_version", "confidence_mean"):
        assert unreadable not in r


def test_one_banks_score_carries_where_it_ranks_among_the_three(temp_db):
    # Asked about DBS alone, the model said DBS ranked above OCBC, and asked about OCBC,
    # that OCBC ranked below both; OCBC was the highest. The ranking now comes with the score.
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 3, 7, 0),
                     ("OCBC", "dividend_policy", "2026-08", 8, 2, 0),
                     ("UOB", "dividend_policy", "2026-08", 1, 9, 0)])
    r = tools.chat_get_sentiment("DBS", "dividend_policy")
    assert r["ranking_high_to_low"] == ["OCBC", "DBS", "UOB"]
    assert set(r["other_banks"]) == {"OCBC", "UOB"}
    assert r["other_banks"]["OCBC"]["reading"] == tools.reading(r["other_banks"]["OCBC"]["score"])


def test_an_aspect_score_carries_its_topic_name_and_no_topic_lists(temp_db):
    _index(temp_db, [("OCBC", "dividend_policy", "2026-08", 6, 4, 0)])
    r = tools.chat_get_sentiment("OCBC", "dividend_policy")
    assert r["topic_name"] == "Dividend Policy"
    assert "strongest_topics" not in r


def test_comparison_ranks_the_banks_with_enough_data_high_to_low(temp_db):
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 3, 7, 0),
                     ("OCBC", "dividend_policy", "2026-08", 8, 2, 0),
                     ("UOB", "dividend_policy", "2026-08", 1, 1, 0)])     # 2 sentences: too few
    r = tools.chat_compare_banks("dividend_policy")
    assert r["ranking_high_to_low"] == ["OCBC", "DBS"]
    assert r["banks"]["UOB"]["insufficient_data"] is True and "reading" not in r["banks"]["UOB"]
    assert r["topic_name"] == "Dividend Policy"


def test_the_api_functions_return_what_they_did(temp_db):
    # The reader's fields are the chatbot's alone: the API serves the stored index unchanged.
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 4, 0)])
    plain = tools.get_sentiment("DBS")
    assert "computed_at" in plain and "reading" not in plain and "positive_pct" not in plain
    assert "ranking_high_to_low" not in tools.compare_banks()
    assert "latest_month" not in tools.get_trend("DBS")


# --- get_trend -----------------------------------------------------------------------

def test_trend_gives_the_latest_months_when_the_rolling_windows_are_thin(temp_db):
    # UOB has nothing in the weeks before the newest stored sentence (another
    # bank's), so its 7- and 30-day windows are empty: at first the model got
    # the all-time score alone and answered "not available".
    _add(temp_db, "newest", "DBS", "dividend_policy", "2026-12-01T00:00:00+00:00", "neutral")
    _index(temp_db, [("UOB", "net_interest_margin", "2026-06", 3, 7, 0),
                     ("UOB", "net_interest_margin", "2026-07", 4, 6, 0),
                     ("UOB", "net_interest_margin", "2026-08", 8, 2, 0)])
    r = tools.chat_get_trend("UOB", "net_interest_margin")
    print(f"\n{ {k: r[k] for k in ('trend_available', 'latest_month', 'previous_month', 'change_from_previous_month', 'month_on_month')} }")
    assert r["trend_available"] is False
    assert [p["period"] for p in r["monthly_series"]] == ["2026-06", "2026-07", "2026-08"]
    assert r["latest_month"]["period"] == "2026-08" and r["previous_month"]["period"] == "2026-07"
    expected = tools._unshrunk(r["latest_month"]) - tools._unshrunk(r["previous_month"])
    assert abs(r["change_from_previous_month"] - expected) < 1e-4
    assert r["month_on_month"] == "up"
    # Written out for the model (it once gave a month's +0.2185 as "-0.2185"), and every figure in it checks out.
    late, early = r["latest_month"], r["previous_month"]
    assert r["trend_in_words"] == (
        f"August 2026 ({late['score']:+.2f}, {late['n']} sentences) was up on "
        f"July 2026 ({early['score']:+.2f}, {early['n']} sentences).")
    assert unverified_numbers(r["trend_in_words"], [r]) == []
    # The all-time figure the trend falls back to is kept apart, so it can't be read as the week's.
    assert "score" not in r and "n" not in r and "reading" not in r
    assert r["all_time_not_recent"]["window"] == "all_time" and r["all_time_not_recent"]["n"] == 30
    assert r["recent_windows"].startswith("There is no figure for the last 7 days (0 sentences) or the last 30 days (0 sentences)")
    assert "for August 2026 and July 2026, not for the last 7 or 30 days" in r["recent_windows"]
    assert list(r)[0] == "recent_windows"


def test_trend_with_enough_recent_data_states_the_week_against_the_month_only(temp_db):
    # The model once blended a rising week with a falling month; it now gets one comparison.
    from datetime import datetime, timedelta, timezone
    import aggregate.index as agg
    now = datetime.now(timezone.utc)
    labels = [(1, "positive")] * 4 + [(2, "neutral")] * 2 + [(12 + i % 10, "positive" if i < 30 else "neutral")
                                                               for i in range(94)]
    for i, (days, label) in enumerate(labels):
        _add(temp_db, f"t{i}", "DBS", "dividend_policy", (now - timedelta(days=days)).isoformat(), label)
    agg.run()
    r = tools.chat_get_trend("DBS", "dividend_policy")
    recent, base = r["recent_7d"], r["baseline_30d"]
    print(f"\n{r['trend_in_words']}")
    assert r["trend_available"] is True and r["direction"] == "improving"
    assert r["trend_in_words"] == (f"The last 7 days ({recent['score']:+.2f}, {recent['n']} sentences) were up on "
                                   f"the last 30 days ({base['score']:+.2f}, {base['n']} sentences).")
    assert "latest_month" not in r
    assert unverified_numbers(r["trend_in_words"], [r]) == []


def test_trend_with_one_month_says_there_is_nothing_to_compare(temp_db):
    _add(temp_db, "newest", "DBS", "dividend_policy", "2026-12-01T00:00:00+00:00", "neutral")
    _index(temp_db, [("UOB", "net_interest_margin", "2026-08", 8, 2, 0)])
    r = tools.chat_get_trend("UOB", "net_interest_margin")
    assert r["month_on_month_available"] is False and "latest_month" not in r


# --- search_evidence ------------------------------------------------------------------

def _hit(sid, text, score, source="earnings", sentiment="neutral"):
    return {"sentence_id": sid, "text": text, "score": score, "source": source, "sentiment": sentiment}


def test_evidence_skips_a_sentence_repeated_with_only_the_quarter_changed():
    pool = [_hit("a", "The Scrip Dividend Scheme will not be applied to the 3Q24 Interim Dividend.", 0.95),
            _hit("b", "The Scrip Dividend Scheme will not be applied to the 2Q23 Interim Dividend.", 0.94),
            _hit("c", "Well DBS pays a quarterly dividend.", 0.90, "arctic_shift")]
    assert [r["sentence_id"] for r in tools._pick_evidence(pool, 3, 0.0)] == ["a", "c"]


def test_evidence_takes_at_most_two_from_one_source_unless_too_few_others_match():
    pool = [_hit(f"e{i}", f"report sentence number {w}", 0.9 - i / 100)
            for i, w in enumerate(["one", "two", "three", "four"])]
    pool.append(_hit("r", "a reddit comment about it", 0.5, "arctic_shift"))
    picked = [r["sentence_id"] for r in tools._pick_evidence(pool, 3, 0.0)]
    assert picked == ["e0", "e1", "r"]
    assert [r["sentence_id"] for r in tools._pick_evidence(pool, 5, 0.0)] == ["e0", "e1", "r", "e2", "e3"]


def test_evidence_raises_positive_and_negative_sentences_by_the_boost():
    pool = [_hit("n", "a neutral sentence about dividends", 0.90, "arctic_shift"),
            _hit("p", "a happy sentence about dividends paid", 0.88, "google_news", "positive")]
    assert [r["sentence_id"] for r in tools._pick_evidence(pool, 1, 0.03)] == ["p"]
    assert [r["sentence_id"] for r in tools._pick_evidence(pool, 1, 0.0)] == ["n"]


def test_evidence_results_name_their_source_for_the_reader(temp_db, monkeypatch):
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [
        {**_hit("1" * 24, "OCBC kept its dividend.", 0.9, "arctic_shift"), "bank": "OCBC",
         "published_at": "2026-09-02T01:00:00+00:00", "url": "http://r.example/1"}])
    item = tools.chat_search_evidence("dividend", bank="OCBC")["results"][0]
    assert item["source_name"] == "Reddit"
    assert item["cite_as"] == f"[OCBC, 2026-09-02, sentence_id {'1' * 24}]"


def test_evidence_comes_with_the_banks_score_and_the_data_date(temp_db, monkeypatch):
    # Seen once: asked what people say and how they feel, the model searched only, called the mood
    # "neutral" with no score fetched, and gave a quote's date as the date the data runs to.
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 3, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    r = tools.chat_search_evidence("dividends", bank="DBS", aspect="dividend_policy", sentiment="negative")
    context = r["topic_score"]
    assert context["topic_name"] == "Dividend Policy" and context["reading"] == tools.reading(context["score"])
    assert context["positive_pct"] == 60.0 and context["negative_pct"] == 10.0
    assert r["data_runs_to"].startswith("2026-08")
    # The model may state that score: the figure check accepts it.
    assert unverified_numbers(f"Overall {context['score']:+.2f}, {context['positive_pct']}% positive.", [r]) == []
    # Searched without a topic, the score given is the bank's overall one, and says so.
    overall = tools.chat_search_evidence("dividends", bank="DBS")
    assert "topic_score" not in overall and overall["bank_overall_score"]["topic_name"] == "overall"


def test_evidence_context_gives_the_neutral_share_too(temp_db, monkeypatch):
    # Validation: a model that worked out the neutral share from the other two was flagged.
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 3, 1)])
    monkeypatch.setattr(tools, "_search_evidence", lambda *a, **kw: [])
    r = tools.chat_search_evidence("dividends", bank="DBS", aspect="dividend_policy")
    assert r["topic_score"]["neutral_pct"] == 30.0
    assert unverified_numbers("60% positive, 30% neutral and 10% negative.", [r]) == []


# --- what the reader sees ----------------------------------------------------------

def _tracker_with(*items):
    return _ToolCallTracker.from_calls([{"name": "search_evidence", "arguments": {"query": "q"},
                                         "result": {"results": list(items)}}])


SID_A, SID_B, SID_X = "a" * 24, "b" * 24, "c" * 24
ITEM_A = {"sentence_id": SID_A, "bank": "DBS", "source": "arctic_shift", "source_name": "Reddit",
          "date": "2026-09-02", "text": "dividends look safe", "url": "http://r.example/a"}
ITEM_B = {"sentence_id": SID_B, "bank": "DBS", "source": "cna", "source_name": "CNA",
          "date": "2026-08-15", "text": "a special dividend", "url": "http://cna.example/b"}


def test_citations_become_numbers_with_the_sources_listed_below():
    answer = (f'One investor wrote "dividends look safe" [DBS, 2026-09-02, sentence_id {SID_A}], and CNA '
              f'reported "a special dividend" [DBS, 2026-08-15, sentence_id {SID_B}]. Again '
              f'[DBS, 2026-09-02, sentence_id {SID_A}].')
    shown = number_citations(answer, _tracker_with(ITEM_A, ITEM_B))
    print(f"\n{shown}")
    assert "sentence_id" not in shown
    assert '"dividends look safe" [1]' in shown and '"a special dividend" [2]' in shown and "Again [1]." in shown
    assert shown.endswith("Sources:\n- [1] Reddit, DBS, 2 Sep 2026: http://r.example/a\n"
                          "- [2] CNA, DBS, 15 Aug 2026: http://cna.example/b")


def test_a_citation_no_search_returned_is_left_as_written_and_warnings_stay_last():
    answer = (f'"dividends look safe" [DBS, 2026-09-02, sentence_id {SID_A}] and '
              f'[DBS, 2026-01-01, sentence_id {SID_X}]\n\n⚠️ VERIFICATION WARNING: ...')
    shown = number_citations(answer, _tracker_with(ITEM_A))
    assert f"sentence_id {SID_X}" in shown
    assert shown.index("Sources:") < shown.index("⚠️") and shown.endswith("⚠️ VERIFICATION WARNING: ...")


def test_a_report_stored_on_this_machine_is_listed_by_name_not_path():
    item = {**ITEM_A, "source_name": "bank results report",
            "url": "file:///Users/someone/plp/data/earnings_pdfs/OCBC/FY23 Results.pdf"}
    shown = number_citations(f'"dividends look safe" [DBS, 2026-09-02, sentence_id {SID_A}]', _tracker_with(item))
    assert shown.endswith("- [1] bank results report, DBS, 2 Sep 2026: FY23 Results.pdf")


def test_a_date_without_its_year_is_not_a_figure_but_a_figure_after_a_month_is():
    # The prompt asks for the date the data runs to; "September 25th" was once flagged. It is
    # skipped because a tool returned that date; a date no tool returned is checked as figures.
    tools = [{"n": 1, "data_runs_to": "2026-09-25"}, {"data_runs_to": "2026-09-24"}]
    assert unverified_numbers("The data runs to September 25th, and to 24 Sep for UOB.", tools) == []
    assert unverified_numbers("The data runs to September 25th.", [{"n": 1}]) == ["25"]
    assert unverified_numbers("It scored in September 0.34.", [{"score": 0.1}]) == ["0.34"]


DAYS_RETURNED = [{"n": 45, "data_runs_to": "2026-09-25"}, {"data_runs_to": "2026-09-26"}]


@pytest.mark.parametrize("answer", ["In September 25 sentences were negative.", "In Sept 25 posts were negative.",
                                    "September 25 of them were negative."])
def test_a_returned_day_with_a_word_after_it_is_a_count(answer):
    # Validation: with data to 25 September, "In September 25 sentences" hid the 25.
    assert unverified_numbers(answer, DAYS_RETURNED) == ["25"]


@pytest.mark.parametrize("answer", [
    "The data runs to September 25.", "The data runs to September 25\nfor all three.", "Up to September 25 (DBS).",
    "The data runs to September 25th for DBS.", "Data from September 25 and 26.", "From Sept 25 to 26.",
    "The data runs to Sept 25-26.",
])
def test_a_returned_day_or_range_where_the_date_ends_is_not_a_figure(answer):
    assert unverified_numbers(answer, DAYS_RETURNED) == []


def test_a_range_running_past_the_returned_days_is_checked():
    assert unverified_numbers("The data runs to Sept 25-27.", DAYS_RETURNED) == ["-27"]
    assert unverified_numbers("In September 25-30% were negative.", DAYS_RETURNED) == ["25", "30%"]


# Validation: a returned day with a word after it was flagged ("Data runs to
# September 25 for DBS"). After the seventh validation a returned day after a
# month is a date only where it clearly reads as one: after "on", "as of", "the", "runs to"
# (a range also after "from"), or before punctuation, a line end or a word such as "until".
@pytest.mark.parametrize("answer", [
    "Data runs to September 25 for DBS.", "On September 25 DBS scored 0.31.", "As of September 25 the score was 0.31.",
    "The September 25 data show 0.31.", "Data runs to September 25 with 45 sentences.",
    "Data runs to Sep 25 in all three banks.",
    "From Sept 25 to 26 posts were negative.",     # a range after "from": a date range (at first, ["26"])
])
def test_a_returned_day_before_another_word_is_a_date(answer):
    assert unverified_numbers(answer, DAYS_RETURNED + [{"score": 0.31}]) == []


def test_a_returned_day_before_for_is_checked():
    # After the eighth validation "for" no longer makes a returned day a date:
    # "September 25 for DBS against 40 for UOB" hid the 25. A real date before "for" with no
    # "on", "as of", "the" or "runs to" before it is flagged, an accepted false alarm.
    assert unverified_numbers("Data covers Sept 25-26 for DBS.", DAYS_RETURNED) == ["25", "26"]
    assert unverified_numbers("Data runs to Sept 25-26 for DBS.", DAYS_RETURNED) == []


# After the eighth validation: before a comma a returned day reads as a date
# only when no number follows in the rest of its clause, or one right after the comma;
# before an opening bracket, only when no number follows and no "of" stands inside it.
@pytest.mark.parametrize("answer, figures", [
    ("September 25, 45 posts.", []),                         # one number, right after the comma
    ("September 25, the latest data.", []),                  # no number in the rest of the clause
    ("September 25 (the latest data).", []),
    ("September 25; 31 posts.", ["31"]),                     # the clause ends at the day
    ("September 25, 31 and 45 posts.", ["25", "31"]),        # a list of counts
    ("September 25, 31, 45 posts.", ["25", "31"]),
    ("In September 25 (out of 45) posts were negative.", ["25"]),   # "of" inside the bracket
    ("In September 25 [out of 45] posts were negative.", ["25"]),
    ("September 25 (DBS) and 45 (OCBC) posts.", ["25"]),     # a number after the bracket
    ("September 25 [the latest].", []),
    # A number later in the clause: the day is checked, a false alarm when it is a date.
    ("September 25, DBS had 45 posts.", ["25"]),
])
def test_a_returned_day_before_a_comma_or_a_bracket(answer, figures):
    assert unverified_numbers(answer, DAYS_RETURNED) == figures


@pytest.mark.parametrize("answer, figures", [
    ("In September 25 more negative posts appeared.", ["25"]),
    ("In September 25 negative and 20 positive sentences.", ["25", "20"]),
    ("In September 25 were negative.", ["25"]),
    ("In September 25 out of 45 posts were negative.", ["25"]),
    ("In September 25 per cent were negative.", ["25"]),
    ("In September 25 to 30% of posts were negative.", ["25", "30%"]),
    ("In September 25 to 30 per cent were negative.", ["25", "30"]),
    ("Sept 25 & 45 sentences", ["25"]),      # "&" before a number: no date (at first read as one)
])
def test_a_returned_day_before_a_count_or_a_share_is_checked(answer, figures):
    assert unverified_numbers(answer, DAYS_RETURNED) == figures


# The rule after the seventh validation, each way a returned day reads as a date,
# and the false alarms it accepts (docs/evidence/chatbot-answers-2026-10-04.md, Known limits).
@pytest.mark.parametrize("answer", [
    "As at September 25 the score was 0.31.", "Figures dated September 25 show 0.31.",
    "The data ran to September 25, with 45 sentences.", "Data runs to **September 25**.",
    "Data to Sept 25 and DBS scored 0.31.", "Data to September 25 when DBS scored 0.31.",
    "Data to September 25th - DBS scored 0.31.", "Between Sept 25 and 26 DBS scored 0.31.",
    "Data to September 25 — the latest.",
])
def test_a_returned_day_that_reads_as_a_date_is_not_a_figure(answer):
    assert unverified_numbers(answer, DAYS_RETURNED + [{"score": 0.31}]) == []


@pytest.mark.parametrize("answer, figures", [
    ("September 25th sentences were negative.", ["25"]),           # an ordinal day is no longer always a date
    ("In September 25th negative posts appeared.", ["25"]),
    ("In September 25 to 26 posts were negative.", ["25", "26"]),  # a range not read as a date: both ends
    ("Sept 25 and 26 posts were negative.", ["25", "26"]),
    ("September 25 — 30 posts were negative.", ["25", "30"]),   # a dash before a number, an em dash too
    ("September 25—30 posts were negative.", ["25", "30"]),
    # False alarms the rule accepts: a returned date before a word it doesn't list.
    ("Data covers September 25 in all three banks.", ["25"]),
    ("Data to Sept 25/26.", ["25", "26"]),
])
def test_a_returned_day_that_does_not_read_as_a_date_is_checked(answer, figures):
    assert unverified_numbers(answer, DAYS_RETURNED) == figures


def test_the_model_reads_fewer_fields_than_the_turn_records(monkeypatch):
    # Links, ids and counts cost prompt tokens without helping an answer; the checks and the
    # numbered sources still need them, so the record keeps them.
    import json
    from chatbot import agent
    result = {"results": [{**ITEM_A, "relevance": 0.9, "evidence_id": "E1", "cite_as": "[DBS, ...]"}],
              "n": 10, "positive_n": 4, "positive_pct": 40.0}
    monkeypatch.setitem(agent.TOOL_FUNCTIONS, "search_evidence", lambda **kw: result)
    tracker = _ToolCallTracker()
    seen = json.loads(tracker.execute("search_evidence", {"query": "q"}))
    item = seen["results"][0]
    assert "sentence_id" not in item and "relevance" not in item
    assert item["url"] == ITEM_A["url"]            # the hosted backends' privacy filter needs the link
    assert item["text"] == ITEM_A["text"] and item["cite_as"] == "[DBS, ...]"
    assert "positive_n" not in seen and seen["positive_pct"] == 40.0
    assert tracker.calls[0]["result"]["results"][0]["url"] == ITEM_A["url"]
    assert SID_A in tracker.known_ids()


def test_a_reading_in_quote_marks_is_not_taken_for_an_invented_quote():
    # Seen once: 'a reading of "clearly positive"' was stripped as unsearched evidence, leaving "a reading of."
    from chatbot.agent import enforce_evidence
    tracker = _ToolCallTracker.from_calls([{"name": "get_trend", "arguments": {"bank": "UOB"},
                                            "result": {"reading": "clearly positive", "topic_name": "Net Interest Margin"}}])
    answer = 'In September the score was +0.55, a reading of "clearly positive", on "Net Interest Margin".'
    assert not tracker.answer_has_unverified_citation(answer)
    assert enforce_evidence(answer, tracker, "q", "strip") == (answer, False)
    invented = answer + ' One investor said "margins will collapse next year".'
    assert tracker.answer_has_unverified_citation(invented)


def test_the_field_name_copied_with_a_citation_is_dropped():
    answer = f'It "dividends look safe" (cite_as: [DBS, 2026-09-02, sentence_id {SID_A}]).'
    assert number_citations(answer, _tracker_with(ITEM_A)).startswith('It "dividends look safe" [1].')


def test_an_answer_without_retrieved_citations_is_unchanged():
    answer = "DBS is slightly positive."
    assert number_citations(answer, _tracker_with(ITEM_A)) == answer


def test_the_number_check_accepts_the_shares_the_model_is_given(temp_db):
    _index(temp_db, [("DBS", "dividend_policy", "2026-08", 6, 3, 1)])
    r = tools.chat_get_sentiment("DBS", "dividend_policy")
    answer = f"About {r['positive_pct']:.0f}% of sentences were positive and {r['negative_pct']}% negative."
    assert unverified_numbers(answer, [r]) == []


def test_the_prompt_no_longer_asks_for_labelled_sections():
    from chatbot.prompts import SYSTEM_PROMPT
    # The old rule 6: "direct answer first, then supporting evidence ..., then the sample size ..., then any caveats".
    assert "answer format" not in SYSTEM_PROMPT.lower() and "sample size" not in SYSTEM_PROMPT.lower()
    assert "No headings or section labels" in SYSTEM_PROMPT
    for field in ("reading", "positive_pct", "ranking_high_to_low", "strongest_topics", "trend_in_words", "source_name"):
        assert field in SYSTEM_PROMPT, field


# After the ninth validation: a clause ends at ".", ";", ":", "!" or "?"
# only before a line end or a space and a capital or a digit, never at the full stop of
# an abbreviation ("In September 25, vs. 45 in August" hid the 25); after "by", "up to",
# "through" and the like, a comma with no number right after it ends a date; a bracket
# ends one only when it holds no digit and no word of approximation and its clause ends
# right after it; and after "in" a returned day is always checked.
@pytest.mark.parametrize("answer, figures", [
    ("In September 25, e.g. 40 posts were negative.", ["25", "40"]),
    ("In September 25, etc. 40 posts were negative.", ["25", "40"]),
    ("In September 25, incl. 40 posts were negative.", ["25", "40"]),
    ("In September 25, cf. 40 in August.", ["25", "40"]),
    ("In September 25, no. 40 was the worst.", ["25", "40"]),
    ("In September 25, ca. 40 posts were negative.", ["25", "40"]),
    ("September 25, the latest data. but 40 posts were negative.", ["25", "40"]),   # no capital: one clause
    ("September 25, the latest data. 40 posts were negative.", ["40"]),
    ("September 25, the latest data.\n40 posts were negative.", ["40"]),
    # the full stop of a month's or a company's short form ends no clause either
    ("September 25, against Aug. 31 in August.", ["25", "31"]),
    ("Data covers Sept. 25, DBS Bank Ltd. 37 posts.", ["37"]),
    ("September 25, avg. 40 a day.", ["25", "40"]),
])
def test_a_clause_runs_past_an_abbreviation(answer, figures):
    assert unverified_numbers(answer, DAYS_RETURNED) == figures


@pytest.mark.parametrize("answer, figures", [
    ("By September 25, DBS scored 0.31.", []),
    ("Until September 25, DBS scored 0.31.", []),
    ("Till Sept 25, DBS scored 0.31.", []),
    ("Data to September 25, DBS scored 0.31.", []),
    ("Since September 25, DBS scored 0.31.", []),
    ("Coverage ended September 25, with DBS at 0.31.", []),
    ("Data covers September 25, with DBS at 0.31.", []),
    ("Data covering Sept 25-26, DBS scored 0.31.", []),
    ("By September 25, 45 posts.", []),                                 # one number right after: as before
    ("By September 25, 31 and 40 posts were negative.", ["25", "40"]),  # a number after the comma: checked
    ("In September 25, DBS scored 0.31.", ["25"]),                      # no such word before: as before
])
def test_a_returned_day_before_a_comma_after_by_or_until_is_a_date(answer, figures):
    assert unverified_numbers(answer, DAYS_RETURNED + [{"score": 0.31}]) == figures


@pytest.mark.parametrize("answer, figures", [
    ("September 25 (the end of the data).", []),
    ("September 25 (DBS (all)).", []),
    ("By September 25 (DBS), the score was 0.31.", []),           # "by" before it, no number after the comma
    # a digit in the bracket: it may hold a count, so the day is one too (the tenth round)
    ("September 25 (45 posts).", ["25"]),
    ("Negative posts: September 25 (45 in August).", ["25"]),
    ("Complaints: September 25 (up from 12).", ["25", "12"]),
    ("September 25 (out of 45).", ["25"]),
    ("September 25 (of 40 posts).", ["25", "40"]),
    # a comma after the bracket ends a date only after "by", "until" and the like
    ("September 25 (DBS), 45 posts.", ["25"]),
    ("By September 25 (DBS), 37 (OCBC) posts were negative.", ["25", "37"]),
    ("September 25 (DBS), 37 and 40 posts.", ["25", "37", "40"]),
    ("September 25 (approx.).", ["25"]),                         # a word of approximation
    ("Negative: September 25 (about).", ["25"]),
    ("Negative: September 25 (or so).", ["25"]),
    ("September 25 (the latest", ["25"]),                        # never closed
])
def test_a_returned_day_before_a_bracket(answer, figures):
    assert unverified_numbers(answer, DAYS_RETURNED + [{"score": 0.31}]) == figures


# After "in" a returned day is always checked: "in September" names the month, so the
# number after it is a count, whatever follows (the tenth round: "In
# September 25 (DBS), 45 (OCBC) posts were negative" hid the 25 behind a bracket and a
# comma). Other words before the month keep the rules above.
@pytest.mark.parametrize("answer, figures", [
    ("In September 25 (DBS), 45 (OCBC) posts were negative.", ["25"]),
    ("In September 25.", ["25"]),
    ("In Sept 25, DBS scored 0.31.", ["25"]),
    ("In mid-September 25 posts were negative.", ["25"]),
    ("In late September 25 posts were negative.", ["25"]),
    ("Posts in **September 25** were negative.", ["25"]),
    ("Data runs to September 25.", []),
    ("On September 25 DBS scored 0.31.", []),
    ("Within September 25 posts.", ["25"]),                      # not "in": checked by the other rules
    ("Within September 25.", []),
])
def test_a_returned_day_after_in_is_checked(answer, figures):
    assert unverified_numbers(answer, DAYS_RETURNED + [{"score": 0.31}]) == figures
