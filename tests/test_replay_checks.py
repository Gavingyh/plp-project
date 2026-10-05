"""Tests for scripts/replay_checks.py: the grounding checks re-run over recorded answers,
on a made-up results folder and, for --against, a made-up git repository (no model, no
data/eval/)."""

import importlib.util
import json
import os

import pytest

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


def test_the_answers_holding_a_mark_the_checks_cannot_place_are_counted(tmp_path, capsys):
    folder = _folder(tmp_path)
    _write(tmp_path / "chatbot_eval_results_odd_v2.jsonl", [
        {"id": "q-3", "question": "DBS app?", "model_answer": 'One user said the bank cheats everyone" here.',
         "tool_calls": [SEARCH], "unverified_numbers": [], "citation_fabricated": True}])
    assert replay_checks.loose_marks(folder) == ["odd_v2/q-3"]
    replay_checks.main(["--eval-dir", folder])
    out = capsys.readouterr().out
    assert "holding a quote mark the checks can't place: 1\n    odd_v2/q-3" in out


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


# --against: a commit's checks, from its tracked files, without touching the repository.
# A made-up repository whose chatbot code flags nothing stands in for an older commit.

_STUB = {
    "chatbot/__init__.py": "",
    "chatbot/agent.py": (
        "import re\n"
        "EVIDENCE_FOUND_HEADING = '\\n\\nEvidence found by the system'\n"
        "_BARE_MARK = re.compile(r'\\[\\d+\\]')\n"
        "_QUOTE_PATTERN = re.compile(r'\"[^\"]+\"')\n"
        "class _ToolCallTracker:\n"
        "    dropped_marks = []\n"
        "    @classmethod\n"
        "    def from_calls(cls, calls, earlier=None):\n"
        "        return cls()\n"
        "    def answer_has_unverified_citation(self, answer):\n"
        "        return False\n"
        "def enforce_evidence(answer, tracker, question, mode):\n"
        "    return answer, False\n"),
    "chatbot/guards.py": "def unverified_numbers(answer, tool_results, question=''):\n    return []\n",
    "chatbot/judge.py": (
        "import json\n"
        "def load_results(path):\n"
        "    with open(path) as f:\n"
        "        return [json.loads(line) for line in f if line.strip()]\n"
        "def model_answer(r):\n"
        "    return r['model_answer'] if r.get('model_answer') is not None else (r.get('answer') or '')\n"),
}


def _git(repo, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
                               "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com"}).stdout


def _stub_repo(tmp_path):
    repo = tmp_path / "repo"
    for path, text in _STUB.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    _git(repo.parent, "init", "-q", str(repo))
    _git(repo, "add", *_STUB)
    _git(repo, "commit", "-q", "-m", "stub checks")
    return repo, _git(repo, "rev-parse", "HEAD").strip()


def test_against_compares_with_a_commits_checks_and_leaves_no_trace(tmp_path, capsys, monkeypatch):
    import tempfile
    folder = _folder(tmp_path)
    repo, commit = _stub_repo(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))      # where the commit's files are extracted
    state = [_git(repo, "status", "--porcelain"), _git(repo, "worktree", "list"), _git(repo, "branch", "-a"),
             _git(repo, "rev-parse", "HEAD")]
    replay_checks.main(["--against", commit, "--eval-dir", folder, "--repo", str(repo)])
    out = capsys.readouterr().out
    # The stub flags no figure; today's code flags the 46 no tool returned.
    assert f"differing from the checks of {commit}: 1" in out
    assert "demo_v2/q-1: figures [] -> ['46']; strip_figures [] -> ['46']" in out
    assert list(scratch.iterdir()) == []                         # the extracted files are gone
    assert state == [_git(repo, "status", "--porcelain"), _git(repo, "worktree", "list"),
                     _git(repo, "branch", "-a"), _git(repo, "rev-parse", "HEAD")]


def test_against_a_commit_that_is_not_there_stops_and_leaves_no_trace(tmp_path, monkeypatch):
    import tempfile
    repo, _ = _stub_repo(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    with pytest.raises(SystemExit, match="could not extract"):
        replay_checks.snapshot_at("0" * 40, _folder(tmp_path), str(repo))
    assert list(scratch.iterdir()) == []


# Only the results files git tracks are read, unless --include-untracked: runs that quote CNA
# text are kept out of git, so a comparison counting them can't be re-run from a checkout
# (eighth validation, 5 Oct 2026). A made-up repository holds one tracked run and one not.

def _git_folder(tmp_path):
    repo = tmp_path / "results_repo"
    folder = repo / "data" / "eval"
    folder.mkdir(parents=True)
    row = {"id": "q-1", "question": "DBS app?", "model_answer": f'Users say "{REAL}" and the score is 0.31 on 46.',
           "tool_calls": [SEARCH, SCORE], "unverified_numbers": ["46"], "citation_fabricated": False}
    _write(folder / "chatbot_eval_results_demo_v2.jsonl", [row])
    _write(folder / "chatbot_eval_results_reader_v2.jsonl", [row])        # a named run, not tracked
    _git(tmp_path, "init", "-q", str(repo))
    _git(repo, "add", "data/eval/chatbot_eval_results_demo_v2.jsonl")
    _git(repo, "commit", "-q", "-m", "one run")
    return str(folder)


def test_only_the_runs_git_tracks_are_read_unless_asked(tmp_path, capsys):
    folder = _git_folder(tmp_path)
    assert [os.path.basename(p) for p in replay_checks.results_files(folder)] == ["chatbot_eval_results_demo_v2.jsonl"]
    assert len(replay_checks.results_files(folder, include_untracked=True)) == 2
    assert "reader_v2: not tracked by git, so not read (--include-untracked reads it)" in \
        replay_checks.recorded_flags(folder)
    replay_checks.main(["--eval-dir", folder])
    out, err = capsys.readouterr()
    assert out.startswith("Results files read: 1; not tracked by git: 0\n") and "Every recorded answer: 1\n" in out
    assert "1 results files here are not tracked by git and were not read" in err
    replay_checks.main(["--eval-dir", folder, "--include-untracked"])
    out, err = capsys.readouterr()
    assert out.startswith("Results files read: 2; not tracked by git: 1\n") and "Every recorded answer: 2\n" in out
    assert "reader_v2: 1 answers" in out and err == ""


def test_against_reads_the_same_runs_as_the_comparison_it_makes(tmp_path, capsys, monkeypatch):
    import tempfile
    folder = _git_folder(tmp_path)
    repo, commit = _stub_repo(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    replay_checks.main(["--against", commit, "--eval-dir", folder, "--repo", str(repo)])
    assert f"differing from the checks of {commit}: 1\n    demo_v2/q-1: figures" in capsys.readouterr().out
    replay_checks.main(["--against", commit, "--eval-dir", folder, "--repo", str(repo), "--include-untracked"])
    out = capsys.readouterr().out
    assert f"differing from the checks of {commit}: 2" in out and "reader_v2/q-1: figures" in out
    assert "only in" not in out
