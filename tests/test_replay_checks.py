"""Tests for scripts/replay_checks.py: the grounding checks re-run over recorded answers,
on a made-up results folder (no model, no data/eval/)."""

import importlib.util
import json
import os

_spec = importlib.util.spec_from_file_location(
    "replay_checks", os.path.join(os.path.dirname(__file__), "..", "scripts", "replay_checks.py"))
replay_checks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replay_checks)

REAL = "the app keeps logging me out every single time i open it"
SEARCH = {"name": "search_evidence", "arguments": {"query": "app"},
          "result": {"results": [{"sentence_id": "a" * 24, "text": REAL, "url": "https://r.example/a"}]}}
SCORE = {"name": "get_sentiment", "arguments": {"bank": "DBS"}, "result": {"score": 0.31, "n": 45}}


def _write(path, rows):
    with open(path, "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)


def _folder(tmp_path):
    _write(tmp_path / "chatbot_eval_results_demo_v2.jsonl", [
        {"id": "q-1", "question": "DBS app?", "model_answer": f'Users say "{REAL}" and the score is 0.31 on 46.',
         "tool_calls": [SEARCH, SCORE], "unverified_numbers": ["46"], "citation_fabricated": False},
        {"id": "q-2", "question": "Buy DBS?", "answer": "I can't advise.", "input_guard": "advice", "tool_calls": []},
    ])
    _write(tmp_path / "chatbot_multiturn_results_demo.jsonl", [
        {"scenario": "mt-1", "turn": 1, "question": "DBS app?", "answer": "Slightly positive.", "tool_calls": [SEARCH]},
        {"scenario": "mt-1", "turn": 2, "question": "Quote one", "answer": f'One said "{REAL}".', "tool_calls": []},
    ])
    return str(tmp_path)


def test_flags_recorded_at_run_time_are_compared(tmp_path):
    lines = replay_checks.recorded_flags(_folder(tmp_path))
    assert "demo_v2: 1 answers; figure flags changed none; citation flags changed none" in lines
    assert "reader_v2: missing" in lines         # a named run not on this machine


def test_a_snapshot_holds_every_answer_and_no_text(tmp_path, capsys):
    folder = _folder(tmp_path)
    snap = tmp_path / "before.json"
    replay_checks.main(["--save", str(snap), "--eval-dir", folder])
    saved = json.loads(snap.read_text())
    assert sorted(saved) == ["demo/mt-1/1", "demo/mt-1/2", "demo_v2/q-1"]      # the fixed reply is no model answer
    assert saved["demo_v2/q-1"]["figures"] == ["46"] and not saved["demo_v2/q-1"]["cited"]
    assert not saved["demo/mt-1/2"]["cited"]     # a follow-up may quote what an earlier turn's search returned
    assert "logging" not in snap.read_text()
    assert "Every recorded answer: 3" in capsys.readouterr().out


def test_compare_names_the_answers_whose_checks_changed(tmp_path, capsys):
    folder = _folder(tmp_path)
    snap = tmp_path / "before.json"
    replay_checks.main(["--save", str(snap), "--eval-dir", folder])
    before = json.loads(snap.read_text())
    before["demo_v2/q-1"]["figures"] = []
    before["demo/mt-1/2"]["strip"] = "0" * 12
    snap.write_text(json.dumps(before))
    capsys.readouterr()
    replay_checks.main(["--compare", str(snap), "--eval-dir", folder])
    out = capsys.readouterr().out
    assert "differing from" in out and ": 2" in out
    assert "demo_v2/q-1: figures [] -> ['46']" in out and "demo/mt-1/2: strip" in out
