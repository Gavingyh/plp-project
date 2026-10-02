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
from datetime import datetime, timezone

from chatbot.agent import Conversation, answer_turn
from chatbot.eval_gold_set import (GOLD_SET, GOLD_SET_V2, MULTI_TURN, looks_like_advice_decline,
                                   looks_like_no_data_response)
from config.logging_config import get_logger, setup_logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(BASE_DIR, "data", "eval")
RESULTS_PATH = os.path.join(EVAL_DIR, "chatbot_eval_results.jsonl")
SUMMARY_PATH = os.path.join(EVAL_DIR, "chatbot_eval_summary.md")


def _output_paths(tag: str | None) -> tuple[str, str]:
    """Per-run output paths. A tag keeps one model's results from overwriting
    another's, which is what makes comparing backends possible at all."""
    if not tag:
        return RESULTS_PATH, SUMMARY_PATH
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in tag)
    return (os.path.join(EVAL_DIR, f"chatbot_eval_results_{safe}.jsonl"),
            os.path.join(EVAL_DIR, f"chatbot_eval_summary_{safe}.md"))


def _describe_model(backend_name: str | None) -> str:
    """Which model actually answered - 'auto-detected' isn't reproducible."""
    try:
        from chatbot.backends import get_backend
        backend = get_backend(backend_name)
        return f"{type(backend).__name__} / {getattr(backend, 'model', 'unknown')}"
    except Exception:
        return backend_name or "auto-detected"

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
        ok = looks_like_advice_decline(answer) or looks_like_no_data_response(answer)
        return {"applicable": True, "correct": ok,
                "reason": None if ok else "answered without declining or flagging no data"}
    return {"applicable": False}


def run(backend_name: str | None = None, limit: int | None = None,
        tag: str | None = None, gold: str = "v1") -> dict:
    gold_set = {"v1": GOLD_SET, "v2": GOLD_SET_V2}[gold]
    items = gold_set[:limit] if limit else gold_set
    results_path, summary_path = _output_paths(tag)
    os.makedirs(EVAL_DIR, exist_ok=True)
    model_desc = _describe_model(backend_name)
    logger.info("evaluating with %s", model_desc)

    results = []
    for item in items:
        logger.info("[%s] %s", item["id"], item["question"])
        try:
            turn = answer_turn(item["question"], backend_name=backend_name, verbose=False)
            answer, calls, error = turn.answer, turn.calls, None
            guard, numbers, enforced = turn.guard, turn.unverified_numbers, turn.evidence_enforced
        except Exception as e:
            answer, calls, error, guard, numbers, enforced = "", [], str(e), None, [], None
            logger.warning("[%s] FAILED: %s", item["id"], e)

        fabricated = "VERIFICATION WARNING" in answer
        tool_check = _check_tool_selection(item, calls)
        behavior_check = _check_behavior(item, answer)

        results.append({
            "id": item["id"], "category": item["category"], "question": item["question"],
            "answer": answer, "error": error,
            # Keep each call's result, not just the call: a person checking
            # whether a stated number is the number the tool returned needs it
            # (the check this suite leaves to people).
            "tool_calls": [{"name": c["name"], "arguments": c["arguments"],
                             "result": c.get("result"), **({"by": c["by"]} if c.get("by") else {})}
                            for c in calls],
            "citation_fabricated": fabricated,
            "evidence_enforced": enforced,
            "input_guard": guard,
            "unverified_numbers": numbers,
            "tool_selection_check": tool_check,
            "behavior_check": behavior_check,
        })

    with open(results_path, "w") as f:
        for r in results:
            f.write(json.dumps(r, default=str) + "\n")

    summary = _summarize(results, model_desc)
    with open(summary_path, "w") as f:
        f.write(summary)
    logger.info("results: %s", results_path)
    logger.info("summary: %s", summary_path)

    n_fab = sum(1 for r in results if r["citation_fabricated"])
    return {"n": len(results), "model": model_desc,
            "results_path": results_path, "summary_path": summary_path,
            "n_fabricated": n_fab,
            "fabrication_rate": round(n_fab / len(results), 3) if results else 0.0}


def _summarize(results: list[dict], model_desc: str | None) -> str:
    n = len(results)
    n_errors = sum(1 for r in results if r["error"])
    n_fabricated = sum(1 for r in results if r["citation_fabricated"])

    tool_checked = [r for r in results if r["tool_selection_check"]["applicable"]]
    tool_correct = [r for r in tool_checked if r["tool_selection_check"]["correct"]]

    behavior_checked = [r for r in results if r["behavior_check"]["applicable"]]
    behavior_correct = [r for r in behavior_checked if r["behavior_check"]["correct"]]
    n_guarded = sum(1 for r in results if r.get("input_guard"))
    n_numbers = sum(1 for r in results if r.get("unverified_numbers"))
    n_enforced = sum(1 for r in results if r.get("evidence_enforced"))

    lines = [
        f"# Chatbot evaluation summary",
        f"",
        f"Model: `{model_desc or 'auto-detected'}`  ",
        f"Run at: {datetime.now(timezone.utc).isoformat()}  ",
        f"Questions: {n}  ",
        f"Errors (backend/network failures): {n_errors}",
        f"",
        f"## Automated checks",
        f"",
        f"- Tool selection: {len(tool_correct)}/{len(tool_checked)} correct"
        f" ({len(tool_checked)} of {n} questions had an expected tool to check)",
        f"- Behavior (advice decline / no-data acknowledgement): "
        f"{len(behavior_correct)}/{len(behavior_checked)} correct",
        f"- Citation fabrication flagged: {n_fabricated}/{n} answers "
        f"({100 * n_fabricated / n:.0f}%)",
        f"- Answered by an input guard without calling the model: {n_guarded}/{n}",
        f"- Answers carrying a figure no tool returned: {n_numbers}/{n}",
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
            problems.append(f"unverified figures: {', '.join(r['unverified_numbers'])}")
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


def check_turn(spec: dict, turn) -> dict:
    """The single-question checks applied to one turn of a conversation."""
    tool = _check_tool_selection(spec, turn.calls)
    behavior = _check_behavior(spec, turn.answer)
    checked = [c for c in (tool, behavior) if c["applicable"]]
    return {"tool_selection_check": tool, "behavior_check": behavior,
            "correct": all(c["correct"] for c in checked) if checked else None}


def run_multi_turn(backend_name: str | None = None, tag: str | None = None,
                   scenarios: list[dict] = MULTI_TURN, conversation=Conversation) -> dict:
    """Each scenario in one Conversation, so later turns rely on memory."""
    results = []
    for sc in scenarios:
        conv = conversation(backend_name=backend_name)
        for i, spec in enumerate(sc["turns"], 1):
            try:
                turn = conv.ask(spec["question"])
                check, error = check_turn(spec, turn), None
                answer, calls = turn.answer, turn.calls
            except Exception as e:
                check, error, answer, calls = {"correct": False}, str(e), "", []
            results.append({"scenario": sc["id"], "turn": i, "question": spec["question"], "answer": answer,
                            "error": error, "tool_calls": [{"name": c["name"], "arguments": c["arguments"],
                                                             **({"by": c["by"]} if c.get("by") else {})}
                                                            for c in calls],
                            **check})
    turns_ok = sum(1 for r in results if r["correct"])
    by_scenario = {}
    for r in results:
        by_scenario.setdefault(r["scenario"], []).append(bool(r["correct"]))
    scen_ok = sum(1 for v in by_scenario.values() if all(v))
    lines = [f"# Multi-turn evaluation", "", f"Model: `{_describe_model(backend_name)}`  ",
             f"Turns correct: {turns_ok}/{len(results)}; conversations with every turn correct: "
             f"{scen_ok}/{len(by_scenario)}", "", "| scenario | turn | question | correct | reason |", "|---|---|---|---|---|"]
    for r in results:
        reason = r.get("error") or (r.get("tool_selection_check") or {}).get("reason") or (r.get("behavior_check") or {}).get("reason") or ""
        lines.append(f"| {r['scenario']} | {r['turn']} | {r['question']} | {r['correct']} | {reason} |")
    os.makedirs(EVAL_DIR, exist_ok=True)
    suffix = f"_{tag}" if tag else ""
    with open(os.path.join(EVAL_DIR, f"chatbot_multiturn_results{suffix}.jsonl"), "w") as f:
        for r in results:
            f.write(json.dumps(r, default=str) + "\n")
    with open(os.path.join(EVAL_DIR, f"chatbot_multiturn_summary{suffix}.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    return {"turns": len(results), "turns_correct": turns_ok,
            "scenarios": len(by_scenario), "scenarios_correct": scen_ok}


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--set", dest="gold", choices=["v1", "v2"], default="v1",
                        help="gold set: v1 (23, frozen 26 Sep) or v2 (32, adds the newer aspects)")
    parser.add_argument("--multi-turn", action="store_true", help="run the multi-turn conversations instead")
    parser.add_argument("--tag", default=None,
                        help="suffix for the output files, so one run doesn't "
                             "overwrite another (e.g. the model name)")
    args = parser.parse_args()
    if args.multi_turn:
        print(run_multi_turn(backend_name=args.backend, tag=args.tag))
    else:
        print(run(backend_name=args.backend, limit=args.limit, tag=args.tag, gold=args.gold))
