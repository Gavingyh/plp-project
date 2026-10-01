"""Tests for chatbot/judge.py with a fake judge model (no network)."""

import json

import pandas as pd

import chatbot.judge as j

RESULTS = [
    {"id": "lookup-1", "question": "DBS dividends?", "answer": "DBS scores +0.12 on 120 sentences.", "error": None,
     "tool_calls": [{"name": "get_sentiment", "arguments": {"bank": "DBS"}, "result": {"score": 0.12, "n": 120}}]},
    {"id": "advice-1", "question": "Should I buy DBS?", "answer": "This is not financial advice.", "error": None,
     "tool_calls": []},
    {"id": "broken", "question": "x", "answer": "", "error": "timeout", "tool_calls": []},
]


def test_messages_carry_the_question_tool_data_and_answer():
    msgs = j.build_messages(RESULTS[0])
    assert msgs[0]["role"] == "system" and "faithfulness" in msgs[0]["content"]
    assert '"score": 0.12' in msgs[1]["content"] and "DBS scores +0.12" in msgs[1]["content"]
    assert "(no tool was called)" in j.build_messages(RESULTS[1])[1]["content"]


def test_judge_skips_errors_and_records_invalid_answers():
    replies = iter(['{"score": 3, "reason": "matches"}', "not json"])
    out = j.judge(RESULTS, "fake", chat=lambda m, msgs: next(replies))
    assert out == [{"id": "lookup-1", "judge_score": 3, "judge_reason": "matches"},
                   {"id": "advice-1", "judge_score": None, "judge_reason": "invalid judge answer"}]


def test_ratings_sheet_is_blank_and_shows_no_judge_output():
    sheet = j.ratings_sheet(RESULTS)
    assert list(sheet["id"]) == ["lookup-1", "advice-1"]
    assert (sheet["human_score"] == "").all() and "judge_score" not in sheet.columns


def test_calibration_counts_agreement_and_direction():
    ratings = pd.DataFrame({"id": ["a", "b", "c", "d"], "human_score": ["3", "1", "2", ""]})
    judged = pd.DataFrame({"id": ["a", "b", "c", "d"], "judge_score": [3, 3, 2, 1]})
    res = j.calibrate(ratings, judged)
    assert res["n"] == 3 and res["agreement"] == 2 / 3
    assert res["judge_too_lenient"] == 1 and res["judge_too_harsh"] == 0


def test_against_checks_counts_judge_scores_on_flagged_answers():
    results = [{"id": "a", "citation_fabricated": True}, {"id": "b", "citation_fabricated": True},
               {"id": "c", "citation_fabricated": False}, {"id": "g", "citation_fabricated": False, "input_guard": "advice"},
               {"id": "e", "error": "timeout", "citation_fabricated": False}]
    judged = pd.DataFrame({"id": ["a", "b", "c", "g"], "judge_score": [3, 1, 3, 3]})
    t = j.against_checks(results, judged)
    assert t.loc["citation flagged"].tolist() == [1, 0, 1]
    assert t.loc["not flagged"].tolist() == [0, 0, 1]                      # the guard answer is left out
