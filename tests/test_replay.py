"""Tests for chatbot/replay.py: enforcement applied to recorded answers, no model."""

import chatbot.replay as replay

RECORDED = [
    {"id": "lookup-7", "question": "UOB cards?", "error": None, "input_guard": None,
     "answer": ('UOB scores 0.0327.\n\nSupporting evidence:\n* "Fees are out of hand." (sentence_id: 12345)\n\n'
                "Caveats: thin data.\n\n⚠️ VERIFICATION WARNING: ..."),
     "citation_fabricated": True, "unverified_numbers": ["12345"],
     "tool_calls": [{"name": "get_sentiment", "arguments": {"bank": "UOB"}, "result": {"score": 0.0327}}]},
    {"id": "advice-1", "question": "Buy DBS?", "error": None, "input_guard": "advice", "answer": "Not advice.",
     "citation_fabricated": False, "unverified_numbers": [], "tool_calls": []},
]


def test_strip_replay_removes_the_invented_evidence_and_skips_guard_answers():
    rows = replay.replay(RECORDED, "strip")
    assert [r["id"] for r in rows] == ["lookup-7"]
    r = rows[0]
    assert r["changed"] and r["citation_flag_before"] and not r["citation_flag_after"]
    assert r["figures_before"] == ["12345"] and r["figures_after"] == []
    assert "Caveats: thin data." in r["answer_after"] and "VERIFICATION" not in r["answer_after"]


def test_summary_counts_before_and_after():
    md = replay.summary(replay.replay(RECORDED, "strip"), "run.jsonl", "strip")
    assert "| citation warning | 1 | 0 |" in md and "## lookup-7" in md
