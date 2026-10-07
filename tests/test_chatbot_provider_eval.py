"""
Tests for the provider comparison: the evaluation's stop and resume when a rate limit is
reached, the report's arithmetic, and the orchestrator's key handling. No model and no
provider is called.
"""

import json
from types import SimpleNamespace

import pytest

from chatbot import provider_eval, provider_report, run_eval
from chatbot.eval_gold_set import GOLD_SET_V2, MULTI_TURN
from chatbot.ratelimit import DailyBudgetExhausted


def _turn(answer="ok", calls=(), guard=None):
    return SimpleNamespace(answer=answer, calls=list(calls), citation_unverified=[], model_answer=answer,
                           guard=guard, unverified_numbers=[], evidence_enforced=None, intent="in_scope")


@pytest.fixture
def eval_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(run_eval, "EVAL_DIR", str(tmp_path))
    return tmp_path


def test_a_run_that_hits_the_budget_saves_what_it_has_and_resumes_without_repeating(eval_dir, monkeypatch):
    asked = []

    def fake_turn(question, **kw):
        asked.append(question)
        if len(asked) == 4:
            raise DailyBudgetExhausted("groq: budget spent")
        return _turn()

    monkeypatch.setattr(run_eval, "answer_turn", fake_turn)
    first = run_eval.run(backend_name="ollama", limit=6, tag="t", gold="v2")
    assert first["n"] == 3 and first["planned"] == 6 and first["stopped"] == "groq: budget spent"
    saved = [json.loads(line) for line in open(eval_dir / "chatbot_eval_results_t.jsonl", encoding="utf-8")]
    assert len(saved) == 3, "answers given before the stop are kept"
    assert "Stopped early" in open(eval_dir / "chatbot_eval_summary_t.md", encoding="utf-8").read()

    asked.clear()
    monkeypatch.setattr(run_eval, "answer_turn", lambda q, **kw: asked.append(q) or _turn())
    second = run_eval.run(backend_name="ollama", limit=6, tag="t", gold="v2", resume=True)
    assert second["n"] == 6 and second["stopped"] is None
    assert len(asked) == 3, "only the three unanswered questions were asked again"


def test_a_failed_answer_is_asked_again_on_resume(eval_dir, monkeypatch):
    monkeypatch.setattr(run_eval, "answer_turn", lambda q, **kw: (_ for _ in ()).throw(RuntimeError("HTTP 500")))
    run_eval.run(backend_name="ollama", limit=2, tag="e", gold="v2")
    asked = []
    monkeypatch.setattr(run_eval, "answer_turn", lambda q, **kw: asked.append(q) or _turn())
    run_eval.run(backend_name="ollama", limit=2, tag="e", gold="v2", resume=True)
    assert len(asked) == 2


def test_each_result_records_its_time_and_hosted_requests(eval_dir, monkeypatch):
    monkeypatch.setattr(run_eval, "answer_turn", lambda q, **kw: _turn())
    run_eval.run(backend_name="ollama", limit=1, tag="c", gold="v2")
    row = json.loads(open(eval_dir / "chatbot_eval_results_c.jsonl", encoding="utf-8").readline())
    assert row["seconds"] >= 0 and row["model_requests"] == 0


class FakeConversation:
    budget_after = None
    asked = 0

    def __init__(self, backend_name=None):
        pass

    def ask(self, question):
        type(self).asked += 1
        if type(self).budget_after is not None and type(self).asked > type(self).budget_after:
            raise DailyBudgetExhausted("gemini: budget spent")
        return _turn()


def test_multi_turn_stops_at_the_budget_drops_the_scenario_in_progress_and_resumes(eval_dir):
    FakeConversation.asked, FakeConversation.budget_after = 0, 4
    first = run_eval.run_multi_turn(backend_name="ollama", tag="m", conversation=FakeConversation)
    assert first["stopped"] and first["scenarios"] < first["planned_scenarios"]
    kept = [json.loads(line) for line in open(eval_dir / "chatbot_multiturn_results_m.jsonl", encoding="utf-8")]
    sc_turns = {s["id"]: len(s["turns"]) for s in MULTI_TURN}
    for scenario in {r["scenario"] for r in kept}:
        assert len([r for r in kept if r["scenario"] == scenario]) == sc_turns[scenario], "no half scenario is kept"
    FakeConversation.asked, FakeConversation.budget_after = 0, None
    second = run_eval.run_multi_turn(backend_name="ollama", tag="m", conversation=FakeConversation, resume=True)
    assert "stopped" not in second and second["scenarios"] == len(MULTI_TURN)


# ----- the report -----

def _write(eval_dir, name, rows):
    with open(eval_dir / name, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _row(item, tool=True, behavior=None, seconds=2.0, requests=3, fabricated=False, error=None):
    return {"id": item["id"], "category": item["category"], "question": item["question"], "error": error,
            "tool_selection_check": {"applicable": True, "correct": tool},
            "behavior_check": {"applicable": behavior is not None, "correct": bool(behavior)},
            "guard_check": {"applicable": False}, "citation_fabricated": fabricated,
            "unverified_numbers": [], "input_guard": None, "intent": "in_scope",
            "seconds": seconds, "model_requests": requests}


def test_the_report_computes_every_figure_from_the_result_files(tmp_path):
    items = GOLD_SET_V2
    _write(tmp_path, "chatbot_eval_results_ollama-v2.jsonl", [_row(i, tool=(n % 2 == 0), requests=0) for n, i in enumerate(items)])
    _write(tmp_path, "chatbot_eval_results_groq-v2.jsonl", [_row(i, tool=True, fabricated=(n == 0)) for n, i in enumerate(items)])
    report = provider_report.build(["ollama", "groq"], eval_dir=str(tmp_path), today="2026-10-06")
    n = len(items)
    assert f"| groq | {n}/{n} | 0 | {n}/{n} |" in report                       # answered, errors, every tool call right
    assert f"| ollama | {n}/{n} | 0 | {(n + 1) // 2}/{n} |" in report            # half right
    # groq: no behaviour or guard checks apply, one flagged citation, nothing unverified, none answered by a guard, 2.0 s each
    assert f"| groq | {n}/{n} | 0 | {n}/{n} | n/a | n/a | 1 | 0 | 0 | 0 | 2.0 |" in report
    assert f"{3 * n}" in report                                                 # groq's requests, summed from the rows


def test_the_report_says_when_an_arm_did_not_finish(tmp_path):
    _write(tmp_path, "chatbot_eval_results_gemini-v2.jsonl", [_row(i) for i in GOLD_SET_V2[:5]])
    report = provider_report.build(["gemini"], eval_dir=str(tmp_path), today="2026-10-06")
    assert f"| gemini | 5/{len(GOLD_SET_V2)} |" in report
    assert "This report is incomplete" in report


def test_the_report_lists_a_question_only_when_the_arms_disagree(tmp_path):
    items = GOLD_SET_V2
    _write(tmp_path, "chatbot_eval_results_ollama-v2.jsonl", [_row(i, tool=True) for i in items])
    _write(tmp_path, "chatbot_eval_results_groq-v2.jsonl", [_row(i, tool=(n != 3)) for n, i in enumerate(items)])
    report = provider_report.build(["ollama", "groq"], eval_dir=str(tmp_path), today="2026-10-06")
    section = report.split("## Questions where the arms differ")[1].split("## How to read this")[0]
    assert items[3]["id"] in section and items[4]["id"] not in section
    assert "pass | FAIL" in section


def test_the_report_has_no_em_dashes():
    report = provider_report.build([], eval_dir="nowhere", today="2026-10-06")
    assert "—" not in report


# ----- the orchestrator -----

def test_a_groq_key_is_found_in_either_variable_and_never_returned_in_a_message():
    env, why = provider_eval.arm_settings("groq", {"GROQ_API_KEY": "gsk_secret"})
    assert why is None and env["OPENAI_API_KEY"] == "gsk_secret" and env["OPENAI_BASE_URL"].startswith("https://api.groq.com")
    env, why = provider_eval.arm_settings(
        "groq", {"OPENAI_API_KEY": "gsk_other", "OPENAI_BASE_URL": "https://api.groq.com/openai/v1"})
    assert why is None and env["OPENAI_API_KEY"] == "gsk_other"


def test_an_openai_key_pointing_somewhere_else_is_not_taken_for_a_groq_key():
    _, why = provider_eval.arm_settings("groq", {"OPENAI_API_KEY": "sk-real-openai-key"})
    assert why and "sk-real" not in why


def test_an_arm_without_its_key_is_not_ready_and_says_which_variable_to_set():
    assert "GEMINI_API_KEY" in provider_eval.arm_settings("gemini", {})[1]
    assert provider_eval.arm_settings("gemini", {"GEMINI_API_KEY": "k"})[1] is None


def test_the_request_estimate_comes_from_the_local_runs_tool_calls(tmp_path):
    rows = [{"tool_calls": [{"name": "a"}, {"name": "b", "by": "model"}, {"name": "c", "by": "harness"}]},
            {"tool_calls": []}]
    _write(tmp_path, "chatbot_eval_results_ollama-v2.jsonl", rows)
    per_item, basis = provider_eval.requests_per_item(str(tmp_path))
    assert per_item == pytest.approx((3 + 1) / 2) and "measured" in basis        # (1 + 2 model calls, 1 + 0) / 2 answers
    assert provider_eval.requests_per_item(str(tmp_path / "empty"))[0] == provider_eval.DEFAULT_REQUESTS_PER_ITEM


def test_a_key_the_provider_rejects_is_reported_before_a_run_and_a_good_one_passes(monkeypatch):
    statuses = iter([401, 200, 429])
    seen = []
    monkeypatch.setattr(provider_eval.requests, "get",
                        lambda url, headers, timeout: seen.append((url, headers)) or SimpleNamespace(status_code=next(statuses)))
    gemini = {"GEMINI_API_KEY": "k"}
    assert "rejected the key (HTTP 401)" in provider_eval.key_problem("gemini", gemini)
    groq = {"OPENAI_API_KEY": "k", "OPENAI_BASE_URL": "https://api.groq.com/openai/v1"}
    assert provider_eval.key_problem("groq", groq) is None
    assert "HTTP 429" in provider_eval.key_problem("groq", groq)
    assert all("/models" in url for url, _ in seen), "only the model list is read: no prompt is sent"
    assert provider_eval.key_problem("ollama", {}) is None


def test_the_report_says_why_an_arm_was_not_run_and_marks_hosted_arms_as_hosted(tmp_path):
    _write(tmp_path, "chatbot_eval_results_ollama-v2.jsonl", [_row(i, requests=0) for i in GOLD_SET_V2])
    provider_eval.save_status({"gemini": {"state": "skipped", "note": "the provider rejected the key (HTTP 401)"}},
                              eval_dir=str(tmp_path))
    report = provider_report.build(["ollama", "gemini"], eval_dir=str(tmp_path), today="2026-10-07")
    assert "- **gemini**: not run (the provider rejected the key (HTTP 401))." in report
    assert "| gemini | `not run` | 8 / 200 | 0 |" in report           # a hosted arm is not "local"
    assert "mostly waiting" in report
