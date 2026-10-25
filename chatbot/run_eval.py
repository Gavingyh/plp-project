"""
Runs chatbot/eval_gold_set.py against a live chatbot backend and writes a
transcript plus a summary of what could be checked automatically.

Automated checks:
  - tool selection: did the model call the tool (and, where specified, the
    bank/aspect) the question actually calls for?
  - advice questions: does the answer contain a decline, per
    chatbot/prompts.py rule 5?
  - out-of-scope questions: does the answer indicate no data / no coverage,
    rather than answering from general knowledge?
  - citation fabrication rate: how often chatbot/agent.py's verification
    check fired.
  - the harness (docs/DESIGN.md decision 19): which input guard answered, if
    any, and how many answers carried a figure no tool returned. The number
    check is a strict detector, not a grade: a flagged figure still needs a
    person to read it.

NOT automated, and left in the transcript for a human to grade: whether a
stated number is correct, and whether cited evidence is actually relevant.
Free-text number extraction is unreliable enough that a wrong automated
check would be worse than a plain "read this yourself".

USAGE:
  python -m chatbot.run_eval                       # default backend, gold set v1 (23)
  python -m chatbot.run_eval --backend ollama --set v2 --tag llama8b-v2   # v2 (32)
  python -m chatbot.run_eval --multi-turn --backend ollama               # the conversations
  python -m chatbot.run_eval --limit 5              # smoke test
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from chatbot import ratelimit, settings
from chatbot.agent import Conversation, answer_turn
from chatbot.ratelimit import DailyBudgetExhausted
from chatbot.eval_gold_set import (GOLD_SET, GOLD_SET_V2, MULTI_TURN, looks_like_advice_decline,
                                   looks_like_no_data_response,
                               SCOPE_SET, MULTI_TURN_SCOPE, looks_like_declining_unrelated_part)
from config.logging_config import get_logger, setup_logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(BASE_DIR, "data", "eval")
RESULTS_PATH = os.path.join(EVAL_DIR, "chatbot_eval_results.jsonl")
SUMMARY_PATH = os.path.join(EVAL_DIR, "chatbot_eval_summary.md")


def _shown(turn) -> dict:
    """The flags as the reader saw them. Since the answer is verified before it is
    shown, a first draft that failed a check may have been rewritten or trimmed;
    TurnResult.shown_flags() gives the flags of the answer shown. A turn without
    that method (an older result, or a stand-in in a test) shows its first draft."""
    if hasattr(turn, "shown_flags"):
        return turn.shown_flags()
    return {"citation_unverified": turn.citation_unverified, "unverified_numbers": turn.unverified_numbers}


def _output_paths(tag: str | None) -> tuple[str, str]:
    """Per-run output paths. A tag keeps one model's results from overwriting
    another's, which is what makes comparing backends possible at all."""
    if not tag:
        return RESULTS_PATH, SUMMARY_PATH
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in tag)
    return (os.path.join(EVAL_DIR, f"chatbot_eval_results_{safe}.jsonl"),
            os.path.join(EVAL_DIR, f"chatbot_eval_summary_{safe}.md"))


def _describe_model(backend_name: str | None) -> str:
    """Which model actually answered - 'the configured default' isn't reproducible."""
    try:
        from chatbot.backends import get_backend
        backend = get_backend(backend_name)
        return f"{type(backend).__name__} / {getattr(backend, 'model', 'unknown')}"
    except Exception:
        return backend_name or "the configured default"

logger = get_logger(__name__)


def _check_tool_selection(item: dict, calls: list[dict]) -> dict:
    expected_tool = item.get("expected_tool")
    if not expected_tool:
        return {"applicable": False}
    calls = [c for c in calls if c.get("by", "model") == "model"]  # not a search the harness made
    matching = [c for c in calls if c["name"] == expected_tool]
    if not matching:
        return {"applicable": True, "correct": False, "reason": "expected tool never called"}

    call = matching[0]
    args = call["arguments"]
    if "expected_bank" in item and item["expected_bank"] is not None:
        if args.get("bank") != item["expected_bank"]:
            return {"applicable": True, "correct": False,
                    "reason": f"wrong bank: got {args.get('bank')!r}, expected {item['expected_bank']!r}"}
    if "expected_aspect" in item and item["expected_aspect"] is not None:
        if args.get("aspect") != item["expected_aspect"]:
            return {"applicable": True, "correct": False,
                    "reason": f"wrong aspect: got {args.get('aspect')!r}, expected {item['expected_aspect']!r}"}
    return {"applicable": True, "correct": True}


def _check_behavior(item: dict, answer: str) -> dict:
    expected = item.get("expected_behavior")
    if not expected:
        return {"applicable": False}
    if expected == "decline_advice":
        ok = looks_like_advice_decline(answer)
        return {"applicable": True, "correct": ok,
                "reason": None if ok else "no advice-decline language found"}
    if expected == "decline_or_no_data":
        # "I can't help with that" declines too: the check once missed it.
        ok = (looks_like_advice_decline(answer) or looks_like_no_data_response(answer)
              or looks_like_declining_unrelated_part(answer))
        return {"applicable": True, "correct": ok,
                "reason": None if ok else "answered without declining or flagging no data"}
    if expected == "decline_unrelated_part":
        ok = looks_like_declining_unrelated_part(answer)
        return {"applicable": True, "correct": ok,
                "reason": None if ok else "didn't say it can't help with the unrelated part"}
    return {"applicable": False}


def _check_guard(item: dict, guard: str | None) -> dict:
    """Whether the right input guard answered: `expected_guard` names it, or is
    None for a question that must reach the model."""
    if "expected_guard" not in item:
        return {"applicable": False}
    ok = guard == item["expected_guard"]
    return {"applicable": True, "correct": ok,
            "reason": None if ok else f"guard {guard!r}, expected {item['expected_guard']!r}"}


def _load_done(results_path: str) -> dict[str, dict]:
    """Results already written by an earlier, stopped run: those that were not a failure."""
    done = {}
    if os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    if not r.get("error"):
                        done[r["id"]] = r
    return done


def _write_results(results_path: str, results: list[dict]) -> None:
    """Rewritten after every question, so a stop or a crash loses nothing already answered."""
    with open(results_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, default=str) + "\n")


def run(backend_name: str | None = None, limit: int | None = None,
        tag: str | None = None, gold: str = "v1", resume: bool = False) -> dict:
    """Run a gold set against a backend. Each answer is saved as it arrives. With `resume`, questions
    already answered in this tag's results file are kept and not asked again. If a hosted provider's
    budget runs out (chatbot/ratelimit.py) the run stops there, saves what it has, and says so in
    the summary; rerun with resume once the budget is back."""
    gold_set = {"v1": GOLD_SET, "v2": GOLD_SET_V2, "scope": SCOPE_SET}[gold]
    items = gold_set[:limit] if limit else gold_set
    results_path, summary_path = _output_paths(tag)
    os.makedirs(EVAL_DIR, exist_ok=True)
    model_desc = _describe_model(backend_name)
    logger.info("evaluating with %s", model_desc)

    done = _load_done(results_path) if resume else {}
    if done:
        logger.info("resuming: %d of %d questions already answered", len(done), len(items))
    results, stopped = [], None
    for item in items:
        if item["id"] in done:
            results.append(done[item["id"]])
            continue
        logger.info("[%s] %s", item["id"], item["question"])
        started, requests_before = time.monotonic(), ratelimit.session_requests()
        try:
            turn = answer_turn(item["question"], backend_name=backend_name, verbose=False)
            answer, calls, error = turn.answer, turn.calls, None
            guard, numbers, enforced = turn.guard, turn.unverified_numbers, turn.evidence_enforced
            shown, repaired = _shown(turn), getattr(turn, "repaired", None)
        except DailyBudgetExhausted as e:
            stopped = str(e)
            logger.warning("[%s] stopping: %s", item["id"], e)
            break
        except Exception as e:
            answer, calls, error, guard, numbers, enforced = "", [], str(e), None, [], None
            shown, repaired = {}, None
            logger.warning("[%s] FAILED: %s", item["id"], e)

        fabricated = bool(turn.citation_unverified) if error is None else False
        tool_check = _check_tool_selection(item, calls) if not guard or "expected_tool" in item else {"applicable": False}
        behavior_check = _check_behavior(item, answer)
        guard_check = _check_guard(item, guard)

        results.append({
            "id": item["id"], "category": item["category"], "question": item["question"],
            "answer": answer, "model_answer": (turn.model_answer if error is None else None), "error": error,
            # Keep each call's result, not just the call: a person checking
            # whether a stated number is the number the tool returned needs it
            # (the check this suite leaves to people).
            "tool_calls": [{"name": c["name"], "arguments": c["arguments"],
                             "result": c.get("result"), **({"by": c["by"]} if c.get("by") else {})}
                            for c in calls],
            "citation_fabricated": fabricated,
            "evidence_enforced": enforced,
            "input_guard": guard,
            "intent": (turn.intent if error is None else None),
            # The checks' flags on the model's first draft, and on the answer the
            # reader saw after verification rewrote or trimmed a failing draft.
            "unverified_numbers": numbers,
            "shown_unverified_numbers": list(shown.get("unverified_numbers") or []),
            "shown_citation_unverified": bool(shown.get("citation_unverified")),
            "repaired": repaired,
            "tool_selection_check": tool_check,
            "behavior_check": behavior_check,
            "guard_check": guard_check,
            # What a run cost: wall-clock seconds, and requests sent to a hosted provider (0 for a local model).
            "seconds": round(time.monotonic() - started, 1),
            "model_requests": ratelimit.session_requests() - requests_before,
        })
        _write_results(results_path, results)

    _write_results(results_path, results)
    summary = _summarize(results, model_desc, stopped=stopped, planned=len(items))
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    logger.info("results: %s", results_path)
    logger.info("summary: %s", summary_path)

    n_fab = sum(1 for r in results if r["citation_fabricated"])
    return {"n": len(results), "planned": len(items), "stopped": stopped, "model": model_desc,
            "results_path": results_path, "summary_path": summary_path,
            "n_fabricated": n_fab,
            "fabrication_rate": round(n_fab / len(results), 3) if results else 0.0}


def _summarize(results: list[dict], model_desc: str | None, stopped: str | None = None,
               planned: int | None = None, run_at: str | None = None, note: str | None = None) -> str:
    n = len(results)
    n_errors = sum(1 for r in results if r["error"])
    n_fabricated = sum(1 for r in results if r["citation_fabricated"])

    tool_checked = [r for r in results if r["tool_selection_check"]["applicable"]]
    tool_correct = [r for r in tool_checked if r["tool_selection_check"]["correct"]]

    behavior_checked = [r for r in results if r["behavior_check"]["applicable"]]
    behavior_correct = [r for r in behavior_checked if r["behavior_check"]["correct"]]
    n_guarded = sum(1 for r in results if r.get("input_guard"))
    n_numbers = sum(1 for r in results if r.get("unverified_numbers"))
    # Results written before the shown flags were recorded have no such field: report the first draft only.
    has_shown = any("shown_unverified_numbers" in r for r in results)
    n_fab_shown = sum(1 for r in results if r.get("shown_citation_unverified"))
    n_numbers_shown = sum(1 for r in results if r.get("shown_unverified_numbers"))
    n_enforced = sum(1 for r in results if r.get("evidence_enforced"))

    lines = [
        f"# Chatbot evaluation summary",
        f"",
        f"Model: `{model_desc or 'the configured default'}`  ",
        f"Intent classifier: `{settings.get('models.intent')}`  ",
        f"Run at: {run_at or datetime.now(timezone.utc).isoformat()}  ",
        *([note + "  "] if note else []),
        f"Questions: {n}" + (f" of {planned}" if planned and planned != n else "") + "  ",
        f"Errors (backend/network failures): {n_errors}",
        *([f"", f"**Stopped early:** {stopped}"] if stopped else []),
        f"",
        f"## Automated checks",
        f"",
        f"- Tool selection: {len(tool_correct)}/{len(tool_checked)} correct"
        f" ({len(tool_checked)} of {n} questions had an expected tool to check)",
        f"- Behavior (advice decline / no-data acknowledgement): "
        f"{len(behavior_correct)}/{len(behavior_checked)} correct",
        f"- Citation fabrication flagged, in the model's first draft: {n_fabricated}/{n} answers "
        f"({100 * n_fabricated / n:.0f}%)",
        *([f"- The same, in the answer shown: {n_fab_shown}/{n}"] if has_shown else []),
        f"- Answered by an input guard without calling the model: {n_guarded}/{n}",
        f"- Answers carrying a figure no tool returned, in the model's first draft: {n_numbers}/{n}",
        *([f"- The same, in the answer shown: {n_numbers_shown}/{n}"] if has_shown else []),
        *([f"- Evidence written without a search, removed by CHATBOT_ENFORCE_EVIDENCE: {n_enforced}/{n}"]
          if n_enforced else []),
        f"",
        f"## Failures needing a look",
        f"",
    ]
    for r in results:
        problems = []
        if r["error"]:
            problems.append(f"error: {r['error']}")
        if r["tool_selection_check"].get("applicable") and not r["tool_selection_check"].get("correct"):
            problems.append(f"tool selection: {r['tool_selection_check']['reason']}")
        if r["behavior_check"].get("applicable") and not r["behavior_check"].get("correct"):
            problems.append(f"behavior: {r['behavior_check']['reason']}")
        if r["citation_fabricated"]:
            problems.append("citation fabrication flagged")
        if r.get("unverified_numbers"):
            first_only = "shown_unverified_numbers" in r and not r["shown_unverified_numbers"]
            problems.append(f"unverified figures: {', '.join(r['unverified_numbers'])}"
                            + (" (first draft only; the answer shown passes)" if first_only else ""))
        if problems:
            lines.append(f"- **{r['id']}** ({r['category']}): {'; '.join(problems)}")
    if not any(r["error"] or
               (r["tool_selection_check"].get("applicable") and not r["tool_selection_check"].get("correct")) or
               (r["behavior_check"].get("applicable") and not r["behavior_check"].get("correct")) or
               r["citation_fabricated"]
               for r in results):
        lines.append("(none)")

    lines += [
        "",
        "## Not automated: read the full transcript for these",
        "",
        "Whether stated numbers are correct, and whether cited evidence is "
        "actually relevant to the question. See the results `.jsonl` beside this file "
        "for the full transcript, including every tool call and its raw result "
        "alongside the model's final answer.",
    ]
    return "\n".join(lines)


def recheck(tag: str | None) -> dict:
    """Fill in the flags of the answer shown for a results file written before they
    were recorded, by running the checks again on each stored final answer
    (model_answer, the text before the harness's warnings). The first draft's flags
    are kept as they were; no model is asked. Rewrites the results and the summary,
    keeping the run's model and time."""
    from chatbot.agent import _ToolCallTracker, _check_answer
    results_path, summary_path = _output_paths(tag)
    with open(results_path, encoding="utf-8") as f:
        results = [json.loads(line) for line in f if line.strip()]
    old = open(summary_path, encoding="utf-8").read() if os.path.exists(summary_path) else ""
    model = re.search(r"Model: `([^`]*)`", old)
    run_at = re.search(r"Run at: (\S+)", old)
    filled = rescored = 0
    items = {i["id"]: i for i in GOLD_SET + GOLD_SET_V2 + SCOPE_SET}
    for r in results:
        if r.get("error"):
            continue
        # The refusal check reads the answer's wording, and its phrase lists grow when a
        # model is found to decline in words they missed: score each answer again.
        if r["id"] in items:
            behavior = _check_behavior(items[r["id"]], r.get("answer") or "")
            if behavior != r.get("behavior_check"):
                r["behavior_check"], rescored = behavior, rescored + 1
        if "shown_unverified_numbers" in r:
            continue
        tracker = _ToolCallTracker()
        tracker.calls.extend(r.get("tool_calls") or [])
        checked = _check_answer(r.get("model_answer") or r.get("answer") or "", tracker, r["question"], "strip", False)
        r["shown_unverified_numbers"] = list(checked.figures)
        r["shown_citation_unverified"] = bool(checked.citation)
        r["shown_rechecked"] = True
        filled += 1
    _write_results(results_path, results)
    note = (f"Rechecked on {datetime.now(timezone.utc).date().isoformat()} from each stored answer: "
            f"flags on the answer shown filled in for {filled}, refusal check changed for {rescored}")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(_summarize(results, model.group(1) if model else None,
                           run_at=run_at.group(1) if run_at else None, note=note))
    return {"rechecked": filled, "behavior_rescored": rescored, "results_path": results_path, "summary_path": summary_path,
            "shown_unverified_numbers": sum(1 for r in results if r.get("shown_unverified_numbers")),
            "first_draft_unverified_numbers": sum(1 for r in results if r.get("unverified_numbers"))}


def check_turn(spec: dict, turn) -> dict:
    """The single-question checks applied to one turn of a conversation."""
    tool = _check_tool_selection(spec, turn.calls)
    behavior = _check_behavior(spec, turn.answer)
    guard = _check_guard(spec, getattr(turn, "guard", None))
    checked = [c for c in (tool, behavior, guard) if c["applicable"]]
    return {"tool_selection_check": tool, "behavior_check": behavior, "guard_check": guard,
            "correct": all(c["correct"] for c in checked) if checked else None}


def _multi_turn_paths(tag: str | None) -> tuple[str, str]:
    suffix = f"_{tag}" if tag else ""
    return (os.path.join(EVAL_DIR, f"chatbot_multiturn_results{suffix}.jsonl"),
            os.path.join(EVAL_DIR, f"chatbot_multiturn_summary{suffix}.md"))


def run_multi_turn(backend_name: str | None = None, tag: str | None = None,
                   scenarios: list[dict] = MULTI_TURN, conversation=Conversation,
                   resume: bool = False) -> dict:
    """Each scenario in one Conversation, so later turns rely on memory. A scenario is the unit
    that is kept or redone: with `resume`, scenarios whose every turn was answered without error
    are kept; if the provider's budget runs out the scenario in progress is dropped and the run
    stops (see `run`)."""
    results_path, summary_path = _multi_turn_paths(tag)
    os.makedirs(EVAL_DIR, exist_ok=True)
    prior: dict[str, list[dict]] = {}
    if resume and os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    prior.setdefault(r["scenario"], []).append(r)
    results, stopped = [], None
    for sc in scenarios:
        old = prior.get(sc["id"], [])
        if len(old) == len(sc["turns"]) and not any(r.get("error") for r in old):
            results.extend(old)
            continue
        conv = conversation(backend_name=backend_name)
        scenario_results = []
        try:
            for i, spec in enumerate(sc["turns"], 1):
                started, before = time.monotonic(), ratelimit.session_requests()
                try:
                    turn = conv.ask(spec["question"])
                    check, error = check_turn(spec, turn), None
                    answer, calls = turn.answer, turn.calls
                except DailyBudgetExhausted:
                    raise
                except Exception as e:
                    check, error, answer, calls = {"correct": False}, str(e), "", []
                scenario_results.append({
                    "scenario": sc["id"], "turn": i, "question": spec["question"], "answer": answer,
                    "error": error, "tool_calls": [{"name": c["name"], "arguments": c["arguments"],
                                                    **({"by": c["by"]} if c.get("by") else {})}
                                                   for c in calls],
                    "seconds": round(time.monotonic() - started, 1),
                    "model_requests": ratelimit.session_requests() - before, **check})
        except DailyBudgetExhausted as e:
            stopped = str(e)
            logger.warning("[%s] stopping: %s", sc["id"], e)
            break
        results.extend(scenario_results)
        with open(results_path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, default=str) + "\n")
    turns_ok = sum(1 for r in results if r["correct"])
    by_scenario = {}
    for r in results:
        by_scenario.setdefault(r["scenario"], []).append(bool(r["correct"]))
    scen_ok = sum(1 for v in by_scenario.values() if all(v))
    planned_scen = len(scenarios)
    lines = [f"# Multi-turn evaluation", "", f"Model: `{_describe_model(backend_name)}`  ",
             f"Turns correct: {turns_ok}/{len(results)}; conversations with every turn correct: "
             f"{scen_ok}/{len(by_scenario)}" + (f" (of {planned_scen} planned)" if planned_scen != len(by_scenario) else ""),
             *([f"", f"**Stopped early:** {stopped}"] if stopped else []),
             "", "| scenario | turn | question | correct | reason |", "|---|---|---|---|---|"]
    for r in results:
        reason = (r.get("error") or (r.get("tool_selection_check") or {}).get("reason")
                  or (r.get("behavior_check") or {}).get("reason") or (r.get("guard_check") or {}).get("reason") or "")
        lines.append(f"| {r['scenario']} | {r['turn']} | {r['question']} | {r['correct']} | {reason} |")
    with open(results_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, default=str) + "\n")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    outcome = {"turns": len(results), "turns_correct": turns_ok, "scenarios": len(by_scenario),
               "scenarios_correct": scen_ok}
    if stopped:       # the shape callers and tests already rely on changes only when a run stopped early
        outcome.update({"planned_scenarios": planned_scen, "stopped": stopped})
    return outcome


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--set", dest="gold", choices=["v1", "v2", "scope"], default="v1",
                        help="gold set: v1 (23, frozen 26 Sep), v2 (32, adds the newer aspects) or scope "
                             "(small talk, off-topic, service and controls, 4 Oct; with --multi-turn, "
                             "its conversations)")
    parser.add_argument("--multi-turn", action="store_true", help="run the multi-turn conversations instead")
    parser.add_argument("--resume", action="store_true",
                        help="keep the answers already saved for this tag and ask only the rest "
                             "(after a stop for a provider's rate limit)")
    parser.add_argument("--recheck", action="store_true",
                        help="fill in the flags of the answer shown for this tag's saved results, "
                             "by checking each stored final answer again; asks no model")
    parser.add_argument("--tag", default=None,
                        help="suffix for the output files, so one run doesn't "
                             "overwrite another (e.g. the model name)")
    args = parser.parse_args()
    if args.recheck:
        print(recheck(args.tag))
        sys.exit(0)
    if args.multi_turn:
        outcome = run_multi_turn(backend_name=args.backend, tag=args.tag, resume=args.resume,
                                 scenarios=MULTI_TURN_SCOPE if args.gold == "scope" else MULTI_TURN)
    else:
        outcome = run(backend_name=args.backend, limit=args.limit, tag=args.tag, gold=args.gold,
                      resume=args.resume)
    print(outcome)
    sys.exit(3 if outcome.get("stopped") else 0)      # 3: stopped for a rate limit; rerun with --resume
