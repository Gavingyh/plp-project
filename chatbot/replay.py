"""
Replay recorded gold-set answers through CHATBOT_ENFORCE_EVIDENCE, without
calling the model.

Enforcement (chatbot/agent.py) only changes an answer the model has already
written, so its effect can be measured on the answers a run recorded: same
questions, same model output, only the post-processing differs. That is a
cleaner comparison than a fresh run, where sampling at temperature 0.2
changes the answers too. `search` mode runs the harness's evidence search
for real, against the database and the embedding cache (no Ollama needed).

Writes data/eval/replay_<run>_<mode>.jsonl and .md (with `_aspectquery` added
when CHATBOT_ASPECT_QUERY=1 ranks the harness's searches); changes nothing else.

USAGE:
  HF_HUB_OFFLINE=1 python -m chatbot.replay --results data/eval/chatbot_eval_results_llama8b_v2_idle.jsonl --mode strip
"""

import argparse
import json
import os

from chatbot.agent import _ToolCallTracker, enforce_evidence
from chatbot.guards import unverified_numbers
from chatbot.judge import EVAL_DIR, load_results, model_answer


def replay(results: list[dict], mode: str) -> list[dict]:
    """One row per answer that reached the model: the checks before and after enforcement."""
    out = []
    for r in results:
        if r.get("error") or r.get("input_guard"):
            continue
        before = model_answer(r)
        tracker = _ToolCallTracker.from_calls(r.get("tool_calls", []))
        after, flagged = enforce_evidence(before, tracker, r["question"], mode)
        out.append({
            "id": r["id"], "question": r["question"], "changed": after != before,
            "citation_flag_before": bool(r.get("citation_fabricated")), "citation_flag_after": flagged,
            "figures_before": r.get("unverified_numbers", []),
            "figures_after": unverified_numbers(after, [c.get("result") for c in tracker.calls], r["question"]),
            "answer_after": after,
            "harness_evidence": [item for c in tracker.calls if c.get("by") == "harness"
                                 for item in (c.get("result") or {}).get("results", [])],
        })
    return out


def summary(rows: list[dict], source: str, mode: str) -> str:
    n = len(rows)
    count = lambda key: sum(1 for r in rows if r[key])  # noqa: E731
    lines = [f"# Evidence enforcement replayed: `{mode}`", "",
             f"Run: `{source}`; {n} answers that reached the model.", "",
             "| | before | after |", "|---|---|---|",
             f"| citation warning | {count('citation_flag_before')} | {count('citation_flag_after')} |",
             f"| answer with a figure no tool returned | {count('figures_before')} | {count('figures_after')} |",
             "", f"Answers changed: {count('changed')}.", ""]
    for r in rows:
        if not r["changed"]:
            continue
        lines += [f"## {r['id']}: {r['question']}", "", "```", r["answer_after"], "```", ""]
        if r["figures_after"]:
            lines += [f"Figures still unverified: {', '.join(r['figures_after'])}", ""]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--results", required=True)
    p.add_argument("--mode", choices=["strip", "search"], required=True)
    args = p.parse_args()
    rows = replay(load_results(args.results), args.mode)
    run = os.path.basename(args.results).replace("chatbot_eval_results_", "").replace(".jsonl", "")
    from chatbot.retrieval import aspect_query_enabled
    flag = "_aspectquery" if args.mode == "search" and aspect_query_enabled() else ""  # CHATBOT_ASPECT_QUERY=1
    base = os.path.join(EVAL_DIR, f"replay_{run}_{args.mode}{flag}")
    with open(base + ".jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    with open(base + ".md", "w") as f:
        f.write(summary(rows, os.path.basename(args.results), args.mode))
    print(summary(rows, os.path.basename(args.results), args.mode).split("\n\nAnswers changed")[0])
    print(f"-> {base}.md")


if __name__ == "__main__":
    main()
