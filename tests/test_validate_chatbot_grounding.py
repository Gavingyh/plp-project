"""Validation tests for the grounded-chatbot claim: each was written for a
confirmed weakness in the guards (3 Oct 2026) and passes since its fix.
Synthetic answers and trackers only: no model calls, no database.
"""

import pytest

from chatbot.agent import EVIDENCE_REMOVED_NOTE, _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers

SID = "a" * 24


def _tracker_with_results(results):
    return _ToolCallTracker.from_calls(
        [{"name": "search_evidence", "arguments": {"query": "q"}, "result": {"results": results}}])


def test_quote_text_is_checked_against_search_results():
    tracker = _tracker_with_results([{"sentence_id": SID, "text": "X"}])
    answer = '"Completely invented quote here" [DBS, sentence_id ' + SID + "]"
    assert tracker.answer_has_unverified_citation(answer)


def test_strip_removes_quote_and_url_from_first_paragraph():
    answer = 'DBS is positive, as one investor said "dividends are safe and growing" (https://x.com/a).'
    new, _ = enforce_evidence(answer, _ToolCallTracker(), "q", "strip")
    assert EVIDENCE_REMOVED_NOTE in new
    assert "dividends are safe and growing" not in new
    assert "https://x.com/a" not in new


def test_number_check_respects_sign():
    assert unverified_numbers("Sentiment rose by +0.05", [{"delta_7d_vs_30d": -0.05}]) == ["+0.05"]


@pytest.mark.parametrize("answer", [
    "One investor wrote “DBS will cut its dividend next quarter”.",
    'One investor wrote *"DBS will cut its dividend next quarter"*.',
    'One investor wrote "DBS will cut its\ndividend next quarter".',
])
def test_quote_variants_flagged_without_search(answer):
    assert _ToolCallTracker().answer_has_unverified_citation(answer)


def test_straight_quote_flagged_without_search_control():
    assert _ToolCallTracker().answer_has_unverified_citation(
        'One investor wrote "DBS will cut its dividend next quarter".')


def test_fraction_written_as_percent_is_flagged():
    assert unverified_numbers("Only 0.12% of mentions were negative", [{"share_negative": 0.12}]) == ["0.12%"]


# get_trend result recorded for gold-set question trend-1 in
# data/eval/chatbot_eval_results_llama8b_v2_idle.jsonl (copied; static).
_TREND_RESULT = {
    "bank": "DBS", "aspect": "dividend_policy", "trend_available": True, "direction": "improving",
    "delta_7d_vs_30d": 0.2177,
    "recent_7d": {"bank": "DBS", "aspect": "dividend_policy", "window": "7d", "score": 0.3657, "n": 25,
                  "positive_n": 10, "neutral_n": 15, "negative_n": 0, "confidence_mean": 0.8551,
                  "model_version": "finbert-base-zeroshot-v1",
                  "computed_at": "2026-09-30T07:34:44.594551+00:00", "insufficient_data": False},
    "baseline_30d": {"bank": "DBS", "aspect": "dividend_policy", "window": "30d", "score": 0.148, "n": 254,
                     "positive_n": 47, "neutral_n": 196, "negative_n": 11, "confidence_mean": 0.8434,
                     "model_version": "finbert-base-zeroshot-v1",
                     "computed_at": "2026-09-30T07:34:44.633436+00:00", "insufficient_data": False},
    "monthly_series": [
        {"period": "2025-10", "score": 0.1276, "n": 367}, {"period": "2025-11", "score": 0.2691, "n": 840},
        {"period": "2025-12", "score": 0.1431, "n": 338}, {"period": "2026-01", "score": 0.0798, "n": 324},
        {"period": "2026-02", "score": 0.3028, "n": 984}, {"period": "2026-03", "score": 0.1459, "n": 249},
        {"period": "2026-04", "score": 0.1637, "n": 361}, {"period": "2026-05", "score": 0.2304, "n": 774},
        {"period": "2026-06", "score": 0.1124, "n": 382}, {"period": "2026-07", "score": 0.2203, "n": 366},
        {"period": "2026-08", "score": 0.2713, "n": 1189}, {"period": "2026-09", "score": 0.1508, "n": 249},
    ],
    "series_note": "monthly, same weighting and shrinkage as the index; thin months omitted",
}


def test_ratio_set_does_not_accept_most_whole_percentages():
    accepted = [p for p in range(1, 100)
                if unverified_numbers(f"About {p}% of mentions were positive", [_TREND_RESULT]) == []]
    assert len(accepted) < 50, f"{len(accepted)}/99 accepted"


def test_number_after_iso_date_is_still_checked():
    assert unverified_numbers("2026-09-21 0.99", []) == ["0.99"]


def test_schemeless_url_is_checked():
    tracker = _tracker_with_results([])
    assert tracker.search_evidence_called
    assert tracker.answer_has_unverified_citation("Source: www.reddit.com/r/singaporefi/abc")


def test_percent_field_counts_as_a_percentage():
    # get_analyst_consensus returns implied_upside_pct already in percent.
    assert unverified_numbers("an implied upside of 0.9%", [{"implied_upside_pct": 0.9}]) == []
    assert unverified_numbers("an implied upside of -0.9%", [{"implied_upside_pct": -0.9}]) == []


def test_value_cut_off_at_the_shown_decimals_counts():
    assert unverified_numbers("a relevance score of at least 0.58", [{"relevance": 0.5853}]) == []
    assert unverified_numbers("a relevance score of 0.57", [{"relevance": 0.5853}]) == ["0.57"]


# --- second review, 4 Oct 2026 ------------------------------------------------------

def test_the_models_own_search_query_does_not_vouch_for_a_quote():
    tracker = _ToolCallTracker.from_calls([{
        "name": "search_evidence", "arguments": {"query": "investors fear OCBC bad loans will surge 37.5% this year"},
        "result": {"query": "investors fear OCBC bad loans will surge 37.5% this year",
                   "results": [{"sentence_id": SID, "text": "Something unrelated about deposit rates."}]}}])
    assert tracker.answer_has_unverified_citation('Investors say "investors fear OCBC bad loans will surge".')


def test_the_models_own_search_query_does_not_vouch_for_a_number():
    result = {"query": "bad loans will surge 37.5% this year", "results": [{"text": "Deposit rates fell."}]}
    assert unverified_numbers("Bad loans will surge 37.5%.", [result]) == ["37.5%"]


def test_strip_after_a_search_removes_an_invented_sentence_id():
    tracker = _tracker_with_results([{"sentence_id": SID, "text": "Real text about DBS dividends here."}])
    fake = "0123456789abcdef01234567"
    new, flagged = enforce_evidence(f"DBS looks positive.\n\nEvidence: see sentence_id {fake}.", tracker, "q",
                                    "strip")
    assert fake not in new and not flagged


def test_strip_after_a_search_removes_a_quote_that_wraps_a_line():
    tracker = _tracker_with_results([{"sentence_id": SID, "text": "Real text about DBS dividends here."}])
    new, flagged = enforce_evidence('One investor: "OCBC is cutting the dividend\nnext quarter for sure".',
                                    tracker, "q", "strip")
    assert "cutting the dividend" not in new and not flagged


def test_a_count_is_not_a_percentage():
    result = {"bank": "DBS", "score": 0.11, "n": 58, "positive_n": 23, "neutral_n": 20, "negative_n": 15}
    assert unverified_numbers("23% of mentions were positive and 58% neutral.", [result]) == ["23%", "58%"]
    assert unverified_numbers("40% of mentions were positive.", [result]) == []       # 23 of 58, derived


def test_figures_inside_the_harness_evidence_are_not_flagged(monkeypatch):
    from chatbot import agent

    class Backend:
        name, model = "fake", "fake"

        def ask(self, question, system, schemas, execute, verbose=True, history=None):
            execute("get_sentiment", {"bank": "DBS"})
            return 'DBS sentiment is positive at 0.31, as one investor said "dividends will keep growing nicely".'

    monkeypatch.setattr(agent, "TOOL_FUNCTIONS", {
        "get_sentiment": lambda **kw: {"bank": "DBS", "score": 0.31, "n": 40},
        "search_evidence": lambda **kw: {"query": kw["query"], "results": [
            {"sentence_id": SID, "text": "DBS paid $0.54 per share, up 12.5% on the year.", "cite_as": "[DBS]"}]}})
    monkeypatch.setenv("CHATBOT_ENFORCE_EVIDENCE", "search")
    r = agent.answer_turn("How is DBS?", backend=Backend(), verbose=False)
    assert "0.54" in r.answer and r.unverified_numbers == []


def test_a_follow_up_may_repeat_a_quote_retrieved_earlier_in_the_conversation():
    earlier = [{"name": "search_evidence", "arguments": {"query": "q"},
                "result": {"results": [{"sentence_id": SID, "text": "The dividend outlook looks very solid this year."}]}}]
    tracker = _ToolCallTracker.from_calls([{"name": "get_sentiment", "arguments": {"bank": "DBS"},
                                            "result": {"score": 0.3, "n": 40}}], earlier=earlier)
    assert not tracker.answer_has_unverified_citation(
        f'That quote, "the dividend outlook looks very solid this year", is about dividends [DBS, sentence_id {SID}].')
    assert tracker.answer_has_unverified_citation('Another investor said "the bank is in deep trouble now".')


def test_a_markdown_blockquote_without_a_search_is_flagged_and_stripped():
    answer = "> OCBC has the worst app in Singapore, I am switching to DBS\n\nScore -0.12 (n=58)."
    assert _ToolCallTracker().answer_has_unverified_citation(answer)
    new, _ = enforce_evidence(answer, _ToolCallTracker(), "q", "strip")
    assert "worst app" not in new


def test_a_redd_it_link_is_a_link():
    assert _ToolCallTracker().answer_has_unverified_citation("See redd.it/abc123 for the thread.")


def test_words_that_start_like_a_month_do_not_hide_figures():
    assert unverified_numbers("Mentions declined 4321 times; the market saw 1234 holders.", [{"n": 40}]) == \
        ["4321", "1234"]
    assert unverified_numbers("Data up to Mar 2025 and 24 September 2026.", [{"n": 40}]) == []


def test_timestamps_and_links_in_a_result_do_not_vouch_for_counts():
    result = {"score": 0.2, "n": 40, "computed_at": "2026-10-03T07:34:45.19+00:00", "url": "https://x.sg/55/77"}
    assert unverified_numbers("34 Reddit posts and 45 news articles, 55 in all.", [result]) == ["34", "45", "55"]


def test_compare_banks_figures_still_vouch():
    result = {"aspect": "ALL", "window": "all_time",
              "banks": {"DBS": {"score": 0.1242, "n": 24431}, "OCBC": {"score": 0.1362, "n": 7412}}}
    assert unverified_numbers("DBS 0.124 on 24,431 sentences; OCBC 0.136 on 7412.", [result]) == []
