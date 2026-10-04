"""
How well the intent classifier (chatbot/intent.py) sorts questions, measured
on every labelled question the project has, before any chatbot answer:

  - the gold sets' single questions (v2): advice -> advice; the uncovered
    banks -> other_bank; the weather question -> off_topic; the rest in_scope
  - the scope set (small talk, off-topic, service, injection, controls)
  - every turn of the conversations, with the bank, aspect and previous
    question the chatbot would carry at that point
  - INTENT_EXTRA: advice phrasings, non-advice controls, other languages

Reports accuracy, each intent's precision and recall, the real questions it
would wrongly block (in_scope labelled as something else: the costliest
error), the questions it would let through (the chatbot model's prompt is
then the only safeguard), how often it couldn't answer, and the time per
call. Writes data/eval/intent_eval_<tag>.{jsonl,md}.

USAGE:
  python -m chatbot.eval_intent --model llama3.1:8b --tag llama8b
  CHATBOT_INTENT_THINK=false python -m chatbot.eval_intent --model qwen3:4b --tag qwen4b
"""

import argparse
import json
import os
import statistics
import time
from collections import Counter

from chatbot.eval_gold_set import GOLD_SET_V2, INTENT_EXTRA, MULTI_TURN, MULTI_TURN_SCOPE, SCOPE_SET
from chatbot.intent import IN_SCOPE, classify_intent, intent_names

EVAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "eval")
_OTHER_BANK_GOLD = {"oos-1", "oos-2", "oos-4"}


def labelled_questions() -> list[dict]:
    """(id, question, state, previous question, intent) for every labelled question."""
    out = []
    for item in GOLD_SET_V2:
        if item["category"] == "advice":
            label = "advice"
        elif item["category"] == "out_of_scope":
            label = "other_bank" if item["id"] in _OTHER_BANK_GOLD else "off_topic"
        else:
            label = IN_SCOPE
        out.append({"id": item["id"], "question": item["question"], "state": None, "previous": None,
                    "intent": label})
    for item in SCOPE_SET:
        out.append({"id": item["id"], "question": item["question"], "state": None, "previous": None,
                    "intent": item["expected_guard"] or IN_SCOPE})
    for sc in MULTI_TURN + MULTI_TURN_SCOPE:
        state, previous = {"banks": [], "aspect": None}, None
        for i, t in enumerate(sc["turns"], 1):
            label = t.get("expected_guard") or ("advice" if t.get("expected_behavior") == "decline_advice"
                                                else IN_SCOPE)
            out.append({"id": f"{sc['id']}.{i}", "question": t["question"], "previous": previous,
                        "state": dict(state) if state["banks"] or state["aspect"] else None, "intent": label})
            if label == IN_SCOPE:            # what the conversation would carry into the next turn
                if t.get("expected_bank"):
                    state["banks"] = [t["expected_bank"]]
                if "expected_aspect" in t:
                    state["aspect"] = t["expected_aspect"]
            previous = t["question"]
    for item in INTENT_EXTRA:
        out.append({"id": item["id"], "question": item["question"], "state": None, "previous": None,
                    "intent": item["intent"]})
    return out


def evaluate(model: str, chat=None) -> list[dict]:
    rows = []
    for q in labelled_questions():
        start = time.time()
        got = classify_intent(q["question"], q["state"], q["previous"], model=model, chat=chat)
        rows.append({**q, "predicted": got, "seconds": round(time.time() - start, 3)})
    return rows


def summarize(rows: list[dict], model: str) -> str:
    names = intent_names()
    answered = [r for r in rows if r["predicted"] is not None]
    correct = sum(r["predicted"] == r["intent"] for r in rows)
    lines = [f"# Intent classifier evaluation", "", f"Model: `{model}`  ",
             f"Questions: {len(rows)}; correct {correct} ({correct / len(rows):.1%}); "
             f"no answer (classifier unavailable or invalid twice): {len(rows) - len(answered)}", ""]
    secs = [r["seconds"] for r in rows]
    lines += [f"Time per question: median {statistics.median(secs):.2f} s, "
              f"90th percentile {sorted(secs)[int(0.9 * (len(secs) - 1))]:.2f} s", ""]
    lines += ["| intent | labelled | precision | recall |", "|---|---|---|---|"]
    for name in names:
        tp = sum(r["intent"] == name and r["predicted"] == name for r in rows)
        labelled = sum(r["intent"] == name for r in rows)
        predicted = sum(r["predicted"] == name for r in rows)
        if labelled or predicted:
            lines.append(f"| {name} | {labelled} | {tp / predicted if predicted else 0:.2f} | "
                         f"{tp / labelled if labelled else 0:.2f} |")
    blocked = [r for r in rows if r["intent"] == IN_SCOPE and r["predicted"] not in (IN_SCOPE, None)]
    let_through = [r for r in rows if r["intent"] != IN_SCOPE and r["predicted"] in (IN_SCOPE, None)]
    other = [r for r in rows if r["intent"] != IN_SCOPE and r["predicted"] not in (IN_SCOPE, None, r["intent"])]
    lines += ["", f"## Real questions wrongly blocked: {len(blocked)}", ""]
    lines += [f"- {r['id']} \"{r['question']}\" -> {r['predicted']}" for r in blocked] or ["- none"]
    lines += ["", f"## Let through to the chatbot model: {len(let_through)}", ""]
    lines += [f"- {r['id']} \"{r['question']}\" ({r['intent']}) -> {r['predicted']}" for r in let_through] or ["- none"]
    lines += ["", f"## Wrong fixed reply: {len(other)}", ""]
    lines += [f"- {r['id']} \"{r['question']}\" ({r['intent']}) -> {r['predicted']}" for r in other] or ["- none"]
    confusion = Counter((r["intent"], r["predicted"]) for r in rows if r["intent"] != r["predicted"])
    lines += ["", "Confusions (labelled -> predicted): "
              + (", ".join(f"{a} -> {b} x{n}" for (a, b), n in confusion.most_common()) or "none")]
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--model", default=None, help="Ollama model (default: CHATBOT_INTENT_MODEL or llama3.1:8b)")
    p.add_argument("--tag", default=None)
    args = p.parse_args()
    from chatbot.intent import default_model
    model = args.model or default_model()
    rows = evaluate(model)
    suffix = f"_{args.tag}" if args.tag else ""
    os.makedirs(EVAL_DIR, exist_ok=True)
    with open(os.path.join(EVAL_DIR, f"intent_eval{suffix}.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = summarize(rows, model)
    with open(os.path.join(EVAL_DIR, f"intent_eval{suffix}.md"), "w") as f:
        f.write(summary)
    print(summary)


if __name__ == "__main__":
    main()
