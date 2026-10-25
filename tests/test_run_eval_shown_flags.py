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
    assert "The same, in the answer shown: 1/2" in summary and "rechecked on" in summary
