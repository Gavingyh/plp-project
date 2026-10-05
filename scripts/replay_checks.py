"""
Re-run the chatbot's grounding checks over the answers recorded under
data/eval/, without calling a model: the citation check, the figure check and
strip mode (chatbot/agent.py, chatbot/guards.py). For checking a change to
them; a validation on 5 Oct 2026 found figures on the evidence page that came
from re-runs nobody had saved.

It prints two things:

  1. For each gold-set run (chatbot_eval_results_*_v2*.jsonl, the seven named
     on docs/evidence/chatbot-answers-2026-10-04.md first), the answers whose
     figure or citation flags now differ from those recorded when the run was
     made. Only runs that recorded the model's own text (model_answer) can be
     compared.
  2. Over every recorded answer (gold-set and multi-turn runs): how many hold
     a double quote mark the checks can't place (which flags an answer, and
     takes its line in strip mode), and which; with --save, a
     snapshot of each answer's citation flag, figure flags, the quotes found in
     it, its strip result and the flags left after strip; with --compare, the
     answers whose entry differs from a snapshot saved before a change; with
     --against, the answers whose entry differs from the snapshot a commit's
     chatbot code makes of the same recorded answers. A snapshot holds flags,
     figures and digests but no answer text, so it can be committed although
     some runs quote CNA text.

--against makes a comparison anyone can re-run from the repository
(validation, 5 Oct 2026: one on the evidence page rested on a snapshot kept
only in a session's scratch folder). It extracts the commit's tracked files
into a temporary directory with `git archive <commit> | tar -x`, which changes
no branch, worktree or index of the repository, runs this script there in a
subprocess (PYTHONPATH set to that directory, so it imports that commit's
chatbot code) over the current data/eval/, compares that snapshot with the
current code's, and removes the directory.

Runs that quote CNA text are kept out of git (the Caveats on the evidence
page): one missing on this machine is reported as missing.

USAGE (from the repository root):
  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 scripts/replay_checks.py --against 7446c89       # a commit's checks
  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 scripts/replay_checks.py --save before.json     # before the change
  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 scripts/replay_checks.py --compare before.json  # after it
"""

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from chatbot.agent import (EVIDENCE_FOUND_HEADING, _BARE_MARK, _QUOTE_PATTERN,  # noqa: E402
                           _ToolCallTracker, enforce_evidence)
from chatbot.guards import unverified_numbers  # noqa: E402
from chatbot.judge import load_results, model_answer  # noqa: E402

EVAL_DIR = os.path.join(ROOT, "data", "eval")
SEVEN = ["defaults_v2", "reader_v2", "reader2_v2", "reader3_v2", "final_v2", "final2_v2", "mix_v2"]


def _name(path: str, prefix: str) -> str:
    """The run's tag: "reader_v2" for chatbot_eval_results_reader_v2.jsonl; the first run has none."""
    return os.path.basename(path)[:-len(".jsonl")].removeprefix(prefix).lstrip("_") or "first"


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _model_results(calls: list[dict]) -> list:
    return [c.get("result") for c in calls if c.get("by") != "harness"]


def recorded_flags(eval_dir: str = EVAL_DIR) -> list[str]:
    """One line per gold-set run: the answers whose figure or citation flags now
    differ from those recorded when the run was made."""
    named = [os.path.join(eval_dir, f"chatbot_eval_results_{t}.jsonl") for t in SEVEN]
    paths = named + sorted(p for p in glob.glob(os.path.join(eval_dir, "chatbot_eval_results_*_v2*.jsonl"))
                           if p not in named)
    lines = []
    for path in paths:
        tag = _name(path, "chatbot_eval_results")
        if not os.path.exists(path):
            lines.append(f"{tag}: missing")
            continue
        rows = [r for r in load_results(path) if r.get("model_answer") is not None]
        if not rows:
            lines.append(f"{tag}: not compared (recorded before the model's own text was kept)")
            continue
        figures, citations = [], []
        for r in rows:
            answer, calls = r["model_answer"], r.get("tool_calls") or []
            now = unverified_numbers(answer.split(EVIDENCE_FOUND_HEADING)[0], _model_results(calls),
                                     r.get("question", ""))
            if now != (r.get("unverified_numbers") or []):
                figures.append((r["id"], r.get("unverified_numbers"), now))
            flagged = _ToolCallTracker.from_calls(calls).answer_has_unverified_citation(answer)
            if flagged != bool(r.get("citation_fabricated")):
                citations.append((r["id"], r.get("citation_fabricated"), flagged))
        lines.append(f"{tag}: {len(rows)} answers; figure flags changed {figures or 'none'}; "
                     f"citation flags changed {citations or 'none'}")
    return lines


def _answers(eval_dir: str):
    """(key, question, answer, calls, earlier searches) for every answer a model wrote in a recorded run."""
    for path in sorted(glob.glob(os.path.join(eval_dir, "chatbot_eval_results*.jsonl"))):
        run = _name(path, "chatbot_eval_results")
        for r in load_results(path):
            if not r.get("error") and not r.get("input_guard") and model_answer(r):
                yield f"{run}/{r['id']}", r.get("question", ""), model_answer(r), r.get("tool_calls") or [], []
    for path in sorted(glob.glob(os.path.join(eval_dir, "chatbot_multiturn_results*.jsonl"))):
        run = _name(path, "chatbot_multiturn_results")
        searches: dict = {}         # each conversation's earlier searches, which a follow-up may quote
        for r in load_results(path):
            calls = r.get("tool_calls") or []
            if not r.get("error") and model_answer(r):
                yield (f"{run}/{r.get('scenario')}/{r.get('turn')}", r.get("question", ""), model_answer(r),
                       calls, list(searches.get(r.get("scenario"), [])))
            searches.setdefault(r.get("scenario"), []).extend(c for c in calls if c.get("name") == "search_evidence")


def loose_marks(eval_dir: str = EVAL_DIR) -> list[str]:
    """The recorded answers holding a double quote mark the checks can't place
    (chatbot.agent._QuoteSpans.loose)."""
    return [key for key, _, answer, _, _ in _answers(eval_dir) if _QUOTE_PATTERN.loose(answer)]


def snapshot(eval_dir: str = EVAL_DIR) -> dict:
    """Each recorded answer's checks, as the live path runs them in strip mode."""
    out = {}
    for key, question, answer, calls, earlier in _answers(eval_dir):
        results = _model_results(calls)
        tracker = _ToolCallTracker.from_calls(calls, earlier)
        stripped, still = enforce_evidence(answer, tracker, question, "strip")
        body = stripped.split(EVIDENCE_FOUND_HEADING)[0]     # as answer_turn checks the figures after strip
        checked = _BARE_MARK.sub(lambda m: " " + re.sub(r"\D+", " ", m.group(0)) + " ", body)
        checked += "".join("\n" + re.sub(r"\D+", " ", g) for g in tracker.dropped_marks)
        out[key] = {
            "cited": _ToolCallTracker.from_calls(calls, earlier).answer_has_unverified_citation(answer),
            "figures": unverified_numbers(answer.split(EVIDENCE_FOUND_HEADING)[0], results, question),
            "quotes": _digest("\x00".join(m.group(0) for m in _QUOTE_PATTERN.finditer(answer))),
            "strip": _digest(stripped),
            "strip_cited": still,
            "strip_figures": unverified_numbers(checked, results, question),
        }
    return out


def snapshot_at(commit: str, eval_dir: str = EVAL_DIR, repo: str = ROOT) -> dict:
    """The snapshot of the answers in eval_dir as the chatbot code of `commit`
    makes it: the commit's tracked files go into a temporary directory (git
    archive, which changes no branch, worktree or index), this script runs
    there in a subprocess, importing that code, and the directory is removed."""
    tmp = tempfile.mkdtemp(prefix="replay_checks_")
    try:
        archive = subprocess.Popen(["git", "-C", repo, "archive", commit], stdout=subprocess.PIPE)
        untar = subprocess.run(["tar", "-x", "-C", tmp], stdin=archive.stdout)
        archive.stdout.close()
        if archive.wait() or untar.returncode:
            raise SystemExit(f"could not extract {commit} from {repo}")
        script = os.path.join(tmp, "scripts", "replay_checks.py")
        os.makedirs(os.path.dirname(script), exist_ok=True)
        shutil.copyfile(os.path.abspath(__file__), script)     # this script, that commit's checks
        saved = os.path.join(tmp, "snapshot.json")
        subprocess.run([sys.executable, script, "--save", saved, "--snapshot-only",
                        "--eval-dir", os.path.abspath(eval_dir)],
                       env={**os.environ, "PYTHONPATH": tmp}, cwd=tmp, check=True, stdout=subprocess.DEVNULL)
        with open(saved) as f:
            return json.load(f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def compare(before: dict, now: dict) -> list[str]:
    """One line per answer whose checks differ from the snapshot: what changed."""
    lines = []
    for key in sorted(set(before) | set(now)):
        if key not in now or key not in before:
            lines.append(f"{key}: only in the {'snapshot' if key in before else 'recorded runs now'}")
            continue
        changed = []
        for field in ("cited", "figures", "strip_cited", "strip_figures"):
            if before[key][field] != now[key][field]:
                changed.append(f"{field} {before[key][field]} -> {now[key][field]}")
        changed += [field for field in ("quotes", "strip") if before[key][field] != now[key][field]]
        if changed:
            lines.append(f"{key}: " + "; ".join(changed))
    return lines


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--save", help="write a snapshot of every recorded answer's checks to this file")
    p.add_argument("--compare", help="a snapshot saved before a change: print the answers that differ from it")
    p.add_argument("--against", metavar="COMMIT",
                   help="a commit: print the answers whose checks differ from those of that commit's code")
    p.add_argument("--eval-dir", default=EVAL_DIR, help=argparse.SUPPRESS)
    p.add_argument("--repo", default=ROOT, help=argparse.SUPPRESS)                     # the repository --against reads
    p.add_argument("--snapshot-only", action="store_true", help=argparse.SUPPRESS)    # as --against runs it
    args = p.parse_args(argv)
    if not args.snapshot_only:
        print("Gold-set runs, flags now against those recorded when the run was made:")
        for line in recorded_flags(args.eval_dir):
            print("  " + line)
    now = snapshot(args.eval_dir)
    print(f"Every recorded answer: {len(now)}")
    if not args.snapshot_only:          # an older commit's code may have no such check
        loose = loose_marks(args.eval_dir)
        print(f"  holding a quote mark the checks can't place: {len(loose)}")
        for key in loose:
            print("    " + key)
    if args.save:
        with open(args.save, "w") as f:      # one answer a line, so two snapshots diff line by line
            f.write("{\n" + ",\n".join(f"{json.dumps(k)}: {json.dumps(v, sort_keys=True)}"
                                       for k, v in sorted(now.items())) + "\n}\n")
        print(f"  saved to {args.save}")
    if args.compare:
        with open(args.compare) as f:
            differ = compare(json.load(f), now)
        print(f"  differing from {args.compare}: {len(differ)}")
        for line in differ:
            print("    " + line)
    if args.against:
        differ = compare(snapshot_at(args.against, args.eval_dir, args.repo), now)
        print(f"  differing from the checks of {args.against}: {len(differ)}")
        for line in differ:
            print("    " + line)


if __name__ == "__main__":
    main()
