"""
The provider comparison report: one markdown file from the saved evaluation results.

Reads data/eval/chatbot_eval_results_<arm>-<set>.jsonl (and the multi-turn files)
that chatbot/provider_eval.py wrote, and puts the arms side by side. Every figure is
computed here from those files; nothing is typed in. If an arm stopped early for a
rate limit, the report says how far it got instead of hiding the gap.

USAGE:
  python -m chatbot.provider_report                       # all arms found, today's date
  python -m chatbot.provider_report --arms ollama openai --out docs/evidence/x.md
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone

from chatbot import settings
from chatbot.eval_gold_set import GOLD_SET_V2, MULTI_TURN, MULTI_TURN_SCOPE, SCOPE_SET

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(BASE_DIR, "data", "eval")
DEFAULT_ARMS = ["ollama", "openai"]
ARM_ORDER = [*DEFAULT_ARMS, "groq"]
SINGLE_SETS = {"v2": ("Gold set", GOLD_SET_V2), "scope": ("Scope set", SCOPE_SET)}
MULTI_SETS = {"multi": ("Multi-turn conversations", MULTI_TURN), "multiscope": ("Multi-turn scope conversations", MULTI_TURN_SCOPE)}


def _read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_status(eval_dir: str = EVAL_DIR) -> dict:
    """{arm: {"state": "done" | "stopped" | "skipped", "note": why}} as chatbot/provider_eval.py last saw it."""
    path = os.path.join(eval_dir, "provider_eval_status.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def single_results(arm: str, key: str, eval_dir: str = EVAL_DIR) -> list[dict]:
    return _read_jsonl(os.path.join(eval_dir, f"chatbot_eval_results_{arm}-{key}.jsonl"))


def multi_results(arm: str, key: str, eval_dir: str = EVAL_DIR) -> list[dict]:
    return _read_jsonl(os.path.join(eval_dir, f"chatbot_multiturn_results_{arm}-{key}.jsonl"))


def model_of(arm: str, eval_dir: str = EVAL_DIR) -> str:
    """The model line the harness wrote into the arm's first summary file."""
    for key in list(SINGLE_SETS):
        path = os.path.join(eval_dir, f"chatbot_eval_summary_{arm}-{key}.md")
        if os.path.exists(path):
            m = re.search(r"^Model: `(.+?)`", open(path, encoding="utf-8").read(), re.M)
            if m:
                return m.group(1)
    return "not run"


def _ratio(done: int, total: int) -> str:
    return f"{done}/{total}" if total else "n/a"


def single_metrics(results: list[dict], planned: int) -> dict:
    ok = [r for r in results if not r.get("error")]

    def checked(field):
        rows = [r for r in results if r.get(field, {}).get("applicable")]
        return sum(1 for r in rows if r[field].get("correct")), len(rows)

    secs = [r["seconds"] for r in results if r.get("seconds") is not None]
    return {
        "answered": len(results), "planned": planned, "errors": len(results) - len(ok),
        "tool": checked("tool_selection_check"), "behavior": checked("behavior_check"),
        "guard": checked("guard_check"),
        "fabricated": sum(1 for r in results if r.get("citation_fabricated")),
        "unverified": sum(1 for r in results if r.get("unverified_numbers")),
        "by_guard": sum(1 for r in results if r.get("input_guard")),
        "no_intent": sum(1 for r in ok if r.get("intent") is None),
        "mean_seconds": (sum(secs) / len(secs)) if secs else None,
        "requests": sum(r.get("model_requests") or 0 for r in results),
        "seconds_total": sum(secs),
    }


def multi_metrics(results: list[dict], scenarios: list[dict]) -> dict:
    by = {}
    for r in results:
        by.setdefault(r["scenario"], []).append(bool(r.get("correct")))
    turns = sum(len(s["turns"]) for s in scenarios)
    return {"turns_done": len(results), "turns": turns, "turns_ok": sum(1 for r in results if r.get("correct")),
            "scen_done": len(by), "scen": len(scenarios), "scen_ok": sum(1 for v in by.values() if all(v)),
            "errors": sum(1 for r in results if r.get("error")),
            "requests": sum(r.get("model_requests") or 0 for r in results),
            "seconds_total": sum(r.get("seconds") or 0 for r in results)}


def _status(item_result: dict | None) -> str:
    """pass / FAIL / n/a for one question under one arm, over the checks that apply to it."""
    if item_result is None:
        return "not run"
    if item_result.get("error"):
        return "error"
    checks = [item_result.get(k, {}) for k in ("tool_selection_check", "behavior_check", "guard_check")]
    checks = [c for c in checks if c.get("applicable")]
    if not checks:
        return "n/a"
    return "pass" if all(c.get("correct") for c in checks) else "FAIL"


def build(arms: list[str], eval_dir: str = EVAL_DIR, today: str | None = None) -> str:
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    arms = [a for a in ARM_ORDER if a in arms] + [a for a in arms if a not in ARM_ORDER]
    labels = {"ollama": "Ollama", "openai": "OpenAI", "groq": "Groq"}
    title = " / ".join(labels.get(a, a) for a in arms) or "selected providers"
    out = [f"# Chatbot evaluation across {title} ({today})", ""]

    # --- what was run
    out += ["## What was compared", "",
            "The same questions, asked through the same chatbot code (tools, prompt, evidence checks), with only the "
            "answering model changed. The questions are the project's gold sets in `chatbot/eval_gold_set.py`. "
            "The intent classifier that decides whether a question is in scope is the local Ollama model in every arm.", "",
            "| arm | model | request budget (per minute / per 24 hours) | requests sent | time spent answering |",
            "|---|---|---|---|---|"]
    for arm in arms:
        req = sec = 0
        for key in SINGLE_SETS:
            m = single_metrics(single_results(arm, key, eval_dir), len(SINGLE_SETS[key][1]))
            req, sec = req + m["requests"], sec + m["seconds_total"]
        for key, (_, scen) in MULTI_SETS.items():
            m = multi_metrics(multi_results(arm, key, eval_dir), scen)
            req, sec = req + m["requests"], sec + m["seconds_total"]
        try:
            lim = (f"{settings.get(f'rate_limits.{arm}.rpm')} / {settings.get(f'rate_limits.{arm}.rpd')}")
        except KeyError:
            lim = "local, no limit" if arm == "ollama" else "account limits (paid API)"
        local = arm == "ollama"
        out.append(f"| {arm} | `{model_of(arm, eval_dir)}` | {lim} | {'n/a (local)' if local else req} | "
                   f"{sec / 60:.1f} minutes |")
    out.append("")

    # --- summary and run status, computed from the same files
    status = read_status(eval_dir)
    out += ["## Summary", ""]
    for arm in arms:
        singles = [single_metrics(single_results(arm, k, eval_dir), len(g)) for k, (_, g) in SINGLE_SETS.items()]
        multis = [multi_metrics(multi_results(arm, k, eval_dir), sc) for k, (_, sc) in MULTI_SETS.items()]
        answered, planned = sum(m["answered"] for m in singles), sum(m["planned"] for m in singles)
        note = status.get(arm, {})
        if not answered and not any(m["turns_done"] for m in multis):
            why = note.get("note") or "no results saved"
            out.append(f"- **{arm}**: not run ({why}).")
            continue
        tool = [sum(m["tool"][i] for m in singles) for i in (0, 1)]
        beh = [sum(m["behavior"][i] for m in singles) for i in (0, 1)]
        guard = [sum(m["guard"][i] for m in singles) for i in (0, 1)]
        out.append(
            f"- **{arm}**: answered {answered} of {planned} single questions and "
            f"{sum(m['turns_done'] for m in multis)} of {sum(m['turns'] for m in multis)} conversation turns. "
            f"Right tool {tool[0]}/{tool[1]}; declines and no-data replies {beh[0]}/{beh[1]}; right input guard "
            f"{guard[0]}/{guard[1]}; {sum(m['fabricated'] for m in singles)} citations flagged; "
            f"{sum(m['unverified'] for m in singles)} answers with a figure no tool returned; "
            f"{sum(m['errors'] for m in singles) + sum(m['errors'] for m in multis)} errors.")
    out.append("")

    # --- single-question sets
    all_complete = True
    for key, (title, gold) in SINGLE_SETS.items():
        out += [f"## {title} ({len(gold)} questions)", "",
                "| arm | answered | errors | tool selection | behaviour (declines and no-data) | right input guard "
                "| citation flagged | answers with a figure no tool returned | answered by an input guard | "
                "no intent found | mean seconds |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for arm in arms:
            res = single_results(arm, key, eval_dir)
            m = single_metrics(res, len(gold))
            all_complete &= m["answered"] == m["planned"]
            ms = f"{m['mean_seconds']:.1f}" if m["mean_seconds"] is not None else "n/a"
            out.append(f"| {arm} | {_ratio(m['answered'], m['planned'])} | {m['errors']} | "
                       f"{_ratio(*m['tool'])} | {_ratio(*m['behavior'])} | {_ratio(*m['guard'])} | "
                       f"{m['fabricated']} | {m['unverified']} | {m['by_guard']} | {m['no_intent']} | {ms} |")
        out.append("")

    # --- multi-turn
    out += ["## Multi-turn conversations", "",
            "| arm | set | turns correct | conversations with every turn correct | errors |", "|---|---|---|---|---|"]
    for arm in arms:
        for key, (title, scen) in MULTI_SETS.items():
            m = multi_metrics(multi_results(arm, key, eval_dir), scen)
            all_complete &= m["turns_done"] == m["turns"]
            out.append(f"| {arm} | {title} | {m['turns_ok']}/{m['turns_done']} (of {m['turns']}) | "
                       f"{m['scen_ok']}/{m['scen_done']} (of {m['scen']}) | {m['errors']} |")
    out.append("")

    # --- where the arms differ
    out += ["## Questions where the arms differ", "",
            "A question is listed when the arms did not all pass or all fail it (over the checks that apply to it).", "",
            "| set | question | category | " + " | ".join(arms) + " |", "|---|---|---|" + "---|" * len(arms)]
    rows = 0
    for key, (_, gold) in SINGLE_SETS.items():
        by_arm = {a: {r["id"]: r for r in single_results(a, key, eval_dir)} for a in arms}
        for item in gold:
            states = [_status(by_arm[a].get(item["id"])) for a in arms]
            if len({s for s in states if s in ("pass", "FAIL", "error")}) > 1:
                out.append(f"| {key} | {item['id']}: {item['question'][:70]} | {item['category']} | " + " | ".join(states) + " |")
                rows += 1
    if not rows:
        out.append("| (none) | | | " + " | ".join("" for _ in arms) + " |")
    out.append("")

    # --- reading it
    out += ["## How to read this", "",
            "- **The checks are automatic and narrow.** They test that the right tool was called, that advice was declined, "
            "that no-data cases said so, and that no figure or quote appeared that no tool returned. They do not test "
            "that a stated number is right or that evidence is relevant; a person must read the answers in "
            "`data/eval/chatbot_eval_results_<arm>-<set>.jsonl` for that.",
            "- **The arms do not see the same evidence.** Hosted models never receive text written by "
            "members of the public (Reddit), CNA articles or broker research; those quotes are replaced by a placeholder "
            "(`chatbot/backends/base.py`, decided 4 Oct 2026). The local Ollama model sees them. A hosted model can therefore "
            "look worse on questions that need those quotes, and its tool calls and figures are the fair comparison.",
            "- **Configured limits shape the run.** Where request budgets are configured, requests are paced "
            "(`rate_limits` in `config/chatbot.yaml`, `chatbot/ratelimit.py`) and a run that reaches its budget stops and "
            "can be resumed, not retried in a loop. 'Answered' above shows how far each arm got.",
            "- **Timing includes rate-limit waits.** Configured pacing and retry waits contribute to elapsed time. "
            "OpenAI has no application pacing cap by default; account limits and network latency still apply. "
            "Record these conditions when comparing providers.",
            f"- **Sample sizes are small.** With {len(GOLD_SET_V2)} and {len(SCOPE_SET)} questions, a difference of one or two is inside what a "
            "different run of the same model can produce. Only repeated differences across sets mean much.", ""]
    if not all_complete:
        out += ["> **This report is incomplete.** At least one arm did not answer every question (see the 'answered' "
                "columns). Rerun `python -m chatbot.provider_eval --resume` when the provider's budget is back, then "
                "regenerate this report.", ""]

    out += ["## Reproduce", "",
            "```bash",
            "python -m chatbot.provider_eval --dry-run      # what is ready, and the request budget, with no calls",
            "python -m chatbot.provider_eval                # run every ready arm, resuming where one stopped",
            "python -m chatbot.provider_report              # regenerate this file from the saved results",
            "```", ""]
    return "\n".join(out)


def write_report(arms: list[str], out_path: str | None = None, eval_dir: str = EVAL_DIR) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = out_path or os.path.join(BASE_DIR, "docs", "evidence", f"chatbot-provider-eval-{today}.md")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(build(arms, eval_dir=eval_dir, today=today))
        # Notes a person wrote after reading the transcripts sit beside the generated report
        # and are appended to it, so regenerating the tables does not lose them.
        notes = os.path.join(os.path.dirname(out_path), f"chatbot-provider-eval-{today}-notes.md")
        if os.path.exists(notes):
            f.write("\n" + open(notes, encoding="utf-8").read().strip() + "\n")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--arms", nargs="+", default=DEFAULT_ARMS, choices=ARM_ORDER)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    print("wrote", write_report(args.arms, args.out))
