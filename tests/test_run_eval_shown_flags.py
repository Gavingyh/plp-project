"""The evaluation records the checks' flags on the model's first draft and on the
answer the reader saw, which differ since a failing draft is rewritten or trimmed
before it is shown; --recheck fills in the second for older results files. No
model is called."""

import json
from types import SimpleNamespace

import pytest

from chatbot import run_eval


@pytest.fixture
def eval_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(run_eval, "EVAL_DIR", str(tmp_path))
    return tmp_path


def _turn(first_draft_figures, shown_figures=None, repaired=None):
    t = SimpleNamespace(answer="ok", calls=[], citation_unverified=False, model_answer="ok", guard=None,
                        unverified_numbers=first_draft_figures, evidence_enforced=None, intent="in_scope",
                        repaired=repaired)
    if shown_figures is not None:
        t.shown_flags = lambda: {"citation_unverified": False, "unverified_numbers": shown_figures,
                                 "unverified_readings": []}
    return t


def test_a_run_records_the_first_draft_and_the_answer_shown(eval_dir, monkeypatch):
    monkeypatch.setattr(run_eval, "answer_turn", lambda q, **kw: _turn(["24"], [], "rewritten"))
    run_eval.run(backend_name="openai", limit=1, tag="s", gold="v2")
    row = json.loads(open(eval_dir / "chatbot_eval_results_s.jsonl", encoding="utf-8").readline())
    assert row["unverified_numbers"] == ["24"] and row["shown_unverified_numbers"] == []
    assert row["repaired"] == "rewritten"
    summary = open(eval_dir / "chatbot_eval_summary_s.md", encoding="utf-8").read()
    assert "figure no tool returned, in the model's first draft: 1/1" in summary
    assert "The same, in the answer shown: 0/1" in summary
    assert "(first draft only; the answer shown passes)" in summary


def test_a_turn_without_shown_flags_reports_its_first_draft(eval_dir, monkeypatch):
    monkeypatch.setattr(run_eval, "answer_turn", lambda q, **kw: _turn(["77"]))
    run_eval.run(backend_name="ollama", limit=1, tag="o", gold="v2")
    row = json.loads(open(eval_dir / "chatbot_eval_results_o.jsonl", encoding="utf-8").readline())
    assert row["shown_unverified_numbers"] == ["77"]


def test_recheck_fills_in_the_answer_shown_from_stored_answers(eval_dir):
    uob = {"name": "get_sentiment", "arguments": {"bank": "UOB"},
           "result": {"bank": "UOB", "score": 0.1069, "n": 13092, "data_runs_to": "2026-09-24",
                      "data_runs_to_in_words": "24 September 2026"}}
    rows = [
        # The first draft was flagged; the final answer the reader saw passes.
        {"id": "a", "category": "lookup", "question": "How is UOB doing?", "error": None,
         "answer": "x", "model_answer": "UOB is at +0.11 on 13,092 sentences; data runs to 24 September 2026.",
         "tool_calls": [uob], "citation_fabricated": False, "unverified_numbers": ["24"],
         "tool_selection_check": {"applicable": False}, "behavior_check": {"applicable": False}},
        # A figure no tool returned is still in the final answer.
        {"id": "b", "category": "lookup", "question": "How is UOB doing?", "error": None,
         "answer": "x", "model_answer": "UOB is at +0.11, with 77% of sentences positive.",
         "tool_calls": [uob], "citation_fabricated": False, "unverified_numbers": ["77%"],
         "tool_selection_check": {"applicable": False}, "behavior_check": {"applicable": False}},
    ]
    with open(eval_dir / "chatbot_eval_results_r.jsonl", "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")
    (eval_dir / "chatbot_eval_summary_r.md").write_text(
        "Model: `OpenAIBackend / gpt-6-luna`  \nRun at: 2026-10-24T10:00:00+00:00  \n", encoding="utf-8")
    out = run_eval.recheck("r")
    saved = {r["id"]: r for r in map(json.loads, open(eval_dir / "chatbot_eval_results_r.jsonl", encoding="utf-8"))}
    assert saved["a"]["shown_unverified_numbers"] == [] and saved["a"]["unverified_numbers"] == ["24"]
    assert saved["b"]["shown_unverified_numbers"] == ["77%"]
    assert out["rechecked"] == 2 and out["shown_unverified_numbers"] == 1
    summary = open(eval_dir / "chatbot_eval_summary_r.md", encoding="utf-8").read()
    assert "`OpenAIBackend / gpt-6-luna`" in summary and "Run at: 2026-10-24T10:00:00+00:00" in summary
    assert "The same, in the answer shown: 1/2" in summary and "Rechecked on" in summary


# --- The refusal check: how a hosted model declines a bank the store doesn't cover ---

_OOS_1 = "I only have sentiment data on DBS, OCBC and UOB, not Standard Chartered. I can’t report sentiment on Standard Chartered’s dividend policy."
_OOS_2 = "I only have sentiment data on DBS, OCBC and UOB, not HSBC, so I can’t report how the market feels about HSBC."


_OOS_2_EARLIER = "I can only report sentiment data for DBS, OCBC and UOB, not HSBC."


@pytest.mark.parametrize("answer", [_OOS_1, _OOS_2, _OOS_2_EARLIER])
def test_a_hosted_models_refusal_counts_as_declining(answer):
    from chatbot.eval_gold_set import GOLD_SET_V2
    item = next(i for i in GOLD_SET_V2 if i["id"] == "oos-1")
    assert run_eval._check_behavior(item, answer)["correct"]


def test_typographic_apostrophes_match_the_listed_phrases():
    from chatbot.eval_gold_set import looks_like_declining_unrelated_part, looks_like_no_data_response
    assert looks_like_declining_unrelated_part("I can’t help with the weather.")
    assert looks_like_no_data_response("I don’t have data on Maybank.")


def test_an_answer_that_gives_a_score_still_fails():
    from chatbot.eval_gold_set import GOLD_SET_V2
    item = next(i for i in GOLD_SET_V2 if i["id"] == "oos-2")
    assert not run_eval._check_behavior(item, "Sentiment on HSBC is slightly positive at +0.21.")["correct"]


def test_recheck_scores_the_refusal_check_again(eval_dir):
    row = {"id": "oos-2", "category": "out_of_scope", "question": "How does the market feel about HSBC right now?",
           "error": None, "answer": _OOS_2, "model_answer": _OOS_2, "tool_calls": [], "citation_fabricated": False,
           "unverified_numbers": [], "shown_unverified_numbers": [], "shown_citation_unverified": False,
           "tool_selection_check": {"applicable": False},
           "behavior_check": {"applicable": True, "correct": False, "reason": "answered without declining or flagging no data"}}
    (eval_dir / "chatbot_eval_results_b.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    out = run_eval.recheck("b")
    saved = json.loads(open(eval_dir / "chatbot_eval_results_b.jsonl", encoding="utf-8").readline())
    assert out["behavior_rescored"] == 1 and saved["behavior_check"]["correct"]
    assert "Behavior (advice decline / no-data acknowledgement): 1/1 correct" in open(eval_dir / "chatbot_eval_summary_b.md", encoding="utf-8").read()
