"""
Reviewer findings from the eighth validation of fix/chatbot-answers (after
31c7e98). Each test asserts the behaviour the grounded chatbot claim needs, or
that a correct answer is kept as written, so it fails while the finding is real;
a confirmed one carries xfail(strict=True). Synthetic data only, except the
replay test, which checks that every eval file the replay script reads is
tracked by git. No model, no network, no data/plp.db.
"""

import importlib.util
import os
import subprocess

import pytest

from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("replay_checks", os.path.join(ROOT, "scripts", "replay_checks.py"))
replay_checks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replay_checks)
SID = "a" * 24
CITE = f"[DBS, 2026-09-01, sentence_id {SID}]"
REAL = "the app is slow to load at night"
REAL2 = "branch queues are long on weekends"
SID2 = "b" * 24
CITE2 = f"[OCBC, 2026-09-02, sentence_id {SID2}]"
ITEMS = [
    {"sentence_id": SID, "bank": "DBS", "source": "reddit", "date": "2026-09-01",
     "text": REAL, "url": "https://x.example/1", "cite_as": CITE},
    {"sentence_id": SID2, "bank": "OCBC", "source": "reddit", "date": "2026-09-02",
     "text": REAL2, "url": "https://x.example/2", "cite_as": CITE2},
]
TOOL = [{"data_runs_to": "2026-09-25", "score": 0.31, "n": 40}]


def _searched():
    return _ToolCallTracker.from_calls([
        {"name": "search_evidence", "arguments": {"query": "q"},
         "result": {"query": "q", "results": ITEMS}},
        {"name": "get_sentiment", "arguments": {"bank": "DBS"}, "result": TOOL[0]}])


# Count before comma or for hidden
@pytest.mark.parametrize("answer", [
    "In September 25, 31 and 40 posts were negative for DBS, OCBC and UOB.",
    "September 25 for DBS against 40 for UOB.",
    "In September 25 (DBS), 31 (OCBC) and 40 (UOB) posts were negative.",
    "In September 25 (out of 40) posts were negative.",
])
def test_count_after_a_month_is_checked(answer):
    assert "25" in unverified_numbers(answer, TOOL)


# Words after a closing mark stripped
@pytest.mark.parametrize("answer", [
    f"One user: “{REAL}”DBS also scored 0.31.",
    f'One user wrote "{REAL}."OCBC users, by contrast, wrote "{REAL2}" {CITE2}',
    f'Comments: "{REAL}"s point is clear.',
])
def test_prose_after_a_closing_mark_is_kept(answer):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert out == answer and not flagged


# Cue nouns turn terms into quotes. Changed by DESIGN decision 26: the
# words stay, but a term of three or more words that no search returned loses its
# quote marks in strip mode.
@pytest.mark.parametrize("answer, shown", [
    ("Users call the app 'buggy and slow' often.", "Users call the app buggy and slow often."),
    ("Analysts report 'strong capital buffers'.", "Analysts report strong capital buffers."),
    ("Reports note 'stable asset quality'.", "Reports note stable asset quality."),
    ("Posts like 'DBS down again' were common.", "Posts like DBS down again were common."),
    ("In the post 'Best bank for savings accounts', users compared rates.",
     "In the post Best bank for savings accounts, users compared rates."),
])
def test_a_single_quoted_term_is_not_a_quote(answer, shown):
    out, flagged = enforce_evidence(answer, _searched(), "q", "strip")
    assert out == shown and not flagged


# Trailing mark after citation drops answer
@pytest.mark.parametrize("answer", [
    f'A user wrote "{REAL}" {CITE}."',
    f'He said "{REAL}""',
])
def test_a_stray_mark_does_not_drop_a_correct_line(answer):
    out, _ = enforce_evidence(answer, _searched(), "q", "strip")
    assert REAL in out


# Replay reads untracked eval files: fixed after this validation, the replay
# reads only the results files git tracks unless asked for the others
# (--include-untracked). The files it reads now come from the script itself.
def test_replay_reads_only_tracked_eval_files():
    eval_dir = os.path.join(ROOT, "data", "eval")
    read = set(replay_checks.results_files(eval_dir))
    tracked = set(subprocess.run(["git", "ls-files", "data/eval"], cwd=ROOT, capture_output=True,
                                 text=True, check=True).stdout.split())
    untracked = sorted(os.path.relpath(p, ROOT) for p in read if os.path.relpath(p, ROOT) not in tracked)
    assert untracked == []
