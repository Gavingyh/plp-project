"""
An LLM judge for faithfulness, and the human ratings that calibrate it
(PLAN section 3: "faithfulness via an LLM judge calibrated on human ratings").

Faithfulness: is everything the answer states supported by what the tools
returned for that question? The judge scores each answer 1-3; people score
the same answers on the same scale; `calibrate` reports how far the judge
can be trusted (agreement and weighted kappa) before it is used alone.

  3  every figure and claim is supported by the tool results
  2  supported overall, with a minor unsupported detail or loose wording
  1  states something the tool results contradict, or invents a figure,
     quote or source

Both the judge and the people see the model's own answer, without the
warnings the harness appends (citation and number checks), so neither is
told what the automated checks concluded.

Two judge prompts: `full` asks for one score on the scale above; `checklist`
asks the judge to list every quote, cited source or link, and figure that the
tool data doesn't contain, and every other unsupported claim, and derives the
score from those lists in code (1 if any quote, source or figure is invented,
2 if only a claim is unsupported, else 3). On 1 Oct the `full` prompt scored
every answer 3, invented evidence included: it read the opening figures and
not the evidence section.

Reads a results file from chatbot.run_eval; writes nothing else.

USAGE:
  python -m chatbot.judge sheet  --results data/eval/chatbot_eval_results_v2.jsonl   # blank sheet for people
  python -m chatbot.judge judge  --results data/eval/chatbot_eval_results_v2.jsonl --model qwen3:4b --no-think
  python -m chatbot.judge judge  --results ... --model gemma3:4b --prompt checklist --tag checklist
  python -m chatbot.judge calibrate --ratings data/eval/ratings_sheet.csv --judged data/eval/judge_qwen3_4b.jsonl
  python -m chatbot.judge checks --results data/eval/chatbot_eval_results_v2.jsonl --judged data/eval/judge_qwen3_4b.jsonl

`checks` needs no people: answers the harness flagged for citing evidence no
search returned should score 1 on the judge's own scale, so the judge's
scores on them are a floor on how much it misses.
"""

import argparse
import json
import os

import pandas as pd
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(BASE_DIR, "data", "eval")
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MAX_RESULT_CHARS = 4000
SCALE = {3: "supported", 2: "minor unsupported detail", 1: "contradicted or invented"}

JUDGE_SYSTEM = """You check a chatbot's answers about bank sentiment for faithfulness.

You get the user's question, the exact data the chatbot's tools returned, and
the chatbot's answer. Judge ONLY whether the answer is supported by that
data. Do not use your own knowledge, and do not judge style or helpfulness.

Score:
3 = every figure and claim in the answer is supported by the tool data
2 = supported overall, but with a minor unsupported detail or loose wording
1 = the answer states something the tool data contradicts, or invents a
    figure, quote, sentence id or source the data does not contain

An answer that declines (no data, out of scope, not financial advice) and
claims nothing is 3. Answer with JSON only: {"score": 1|2|3, "reason": "<one sentence>"}"""

JUDGE_CHECKLIST_SYSTEM = """You check a chatbot's answer about bank sentiment against the
exact data its tools returned. Do not use your own knowledge.

Read the whole answer, including any "evidence" or "supporting evidence"
section, and list:
- quotes_not_in_data: every quoted sentence, headline or excerpt presented as
  what someone said that does not appear in the tool data
- sources_not_in_data: every sentence id, article, outlet or URL the answer
  cites that does not appear in the tool data
- figures_not_in_data: every number the answer states that is in neither the
  tool data nor the question
- claims_not_supported: every other statement of fact the tool data does not
  support

Copy each item briefly. Use an empty list when there is nothing to list. An
answer that declines or says there is no data has empty lists. Answer with
JSON only."""

CHECKLIST_FIELDS = ("quotes_not_in_data", "sources_not_in_data", "figures_not_in_data",
                    "claims_not_supported")
_CHECKLIST_SCHEMA = {"type": "object", "required": list(CHECKLIST_FIELDS),
                     "properties": {f: {"type": "array", "items": {"type": "string"}}
                                    for f in CHECKLIST_FIELDS}}
_SCORE_SCHEMA = {"type": "object", "properties": {"score": {"type": "integer", "enum": [1, 2, 3]},
                                                  "reason": {"type": "string"}},
                 "required": ["score", "reason"]}


def load_results(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def tool_summary(result: dict, limit: int = MAX_RESULT_CHARS) -> str:
    """The tool calls and their raw results, as the judge and the raters see them."""
    parts = [f"{c['name']}({json.dumps(c.get('arguments', {}), default=str)}) -> "
             f"{json.dumps(c.get('result'), default=str)}" for c in result.get("tool_calls", [])]
    text = "\n".join(parts) or "(no tool was called)"
    return text if len(text) <= limit else text[:limit] + " …[truncated]"


def model_answer(result: dict) -> str:
    """The answer as the model wrote it, without the warnings the harness appended."""
    return (result.get("answer") or "").split("\n\n⚠️")[0]


def build_messages(result: dict, prompt: str = "full") -> list[dict]:
    system = JUDGE_CHECKLIST_SYSTEM if prompt == "checklist" else JUDGE_SYSTEM
    ask = "List what it doesn't support." if prompt == "checklist" else "Score it."
    user = (f"Question: {result['question']}\n\nTool data:\n{tool_summary(result)}\n\n"
            f"Answer:\n{model_answer(result)}\n\n{ask}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def checklist_score(parsed: dict) -> tuple[int, str]:
    """1 if a quote, source or figure is invented, 2 if only a claim is unsupported, else 3."""
    lists = {f: [str(x) for x in (parsed.get(f) or [])] for f in CHECKLIST_FIELDS}
    invented = lists["quotes_not_in_data"] + lists["sources_not_in_data"] + lists["figures_not_in_data"]
    score = 1 if invented else 2 if lists["claims_not_supported"] else 3
    found = [f"{f}: {'; '.join(v)[:200]}" for f, v in lists.items() if v]
    return score, " | ".join(found) or "nothing unsupported listed"


def ollama_judge(model: str, messages: list[dict], think: bool | None = None,
                 schema: dict | None = None) -> str:
    """One deterministic call; `think=False` turns off a reasoning model's hidden thinking."""
    payload = {"model": model, "messages": messages, "stream": False, "options": {"temperature": 0},
               "format": schema or _SCORE_SCHEMA}
    if think is not None:
        payload["think"] = think
    resp = requests.post(f"{OLLAMA_URL}/api/chat", timeout=300, json=payload)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def judge(results: list[dict], model: str, chat=ollama_judge, prompt: str = "full") -> list[dict]:
    out = []
    for r in results:
        if r.get("error"):
            continue
        try:
            reply = chat(model, build_messages(r, prompt))
        except requests.exceptions.RequestException as e:
            # A slow or failed request is recorded for this answer; the run goes on.
            out.append({"id": r["id"], "judge_score": None, "judge_reason": f"judge request failed: {type(e).__name__}"})
            continue
        try:
            parsed = json.loads(reply)
            if prompt == "checklist":
                score, reason = checklist_score(parsed)
            else:
                score, reason = int(parsed["score"]), str(parsed.get("reason", ""))
            if score not in SCALE:
                raise ValueError(score)
        except (ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
            score, reason = None, "invalid judge answer"
        out.append({"id": r["id"], "judge_score": score, "judge_reason": reason})
    return out


def ratings_sheet(results: list[dict]) -> pd.DataFrame:
    """One row per answer for people to score blind (no judge output in it)."""
    rows = [{"id": r["id"], "question": r["question"], "tool_data": tool_summary(r), "answer": model_answer(r),
             "human_score": "", "rater": "", "notes": ""} for r in results if not r.get("error")]
    return pd.DataFrame(rows)


def calibrate(ratings: pd.DataFrame, judged: pd.DataFrame) -> dict:
    """Agreement between people and the judge on the answers both scored."""
    from sklearn.metrics import cohen_kappa_score
    r = ratings[pd.to_numeric(ratings["human_score"], errors="coerce").notna()].copy()
    r["human_score"] = r["human_score"].astype(int)
    m = r.merge(judged.dropna(subset=["judge_score"]), on="id")
    if m.empty:
        raise ValueError("no answer has both a human and a judge score")
    m["judge_score"] = m["judge_score"].astype(int)
    return {"n": len(m), "agreement": float((m["human_score"] == m["judge_score"]).mean()),
            "weighted_kappa": float(cohen_kappa_score(m["human_score"], m["judge_score"], labels=[1, 2, 3], weights="linear")),
            "judge_too_lenient": int((m["judge_score"] > m["human_score"]).sum()),
            "judge_too_harsh": int((m["judge_score"] < m["human_score"]).sum())}


def against_checks(results: list[dict], judged: pd.DataFrame) -> pd.DataFrame:
    """Judge score counts for answers the harness flagged for unverified
    citations, and for the rest (errors and guard answers left out)."""
    flag = {r["id"]: bool(r.get("citation_fabricated")) for r in results
            if not r.get("error") and not r.get("input_guard")}
    m = judged[judged["id"].isin(flag)].assign(
        harness=lambda d: d["id"].map(flag).map({True: "citation flagged", False: "not flagged"}))
    return (pd.crosstab(m["harness"], m["judge_score"].astype("Int64"))
            .reindex(columns=[1, 2, 3], fill_value=0))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet"); s.add_argument("--results", required=True)
    j = sub.add_parser("judge"); j.add_argument("--results", required=True); j.add_argument("--model", default="qwen3:4b")
    j.add_argument("--no-think", action="store_true", help="turn off a reasoning model's thinking (qwen3)")
    j.add_argument("--prompt", choices=["full", "checklist"], default="full")
    j.add_argument("--tag", default=None, help="added to the output file name, to keep variants apart")
    c = sub.add_parser("calibrate"); c.add_argument("--ratings", required=True); c.add_argument("--judged", required=True)
    k = sub.add_parser("checks"); k.add_argument("--results", required=True); k.add_argument("--judged", required=True)
    args = p.parse_args()
    os.makedirs(EVAL_DIR, exist_ok=True)
    if args.cmd == "sheet":
        path = os.path.join(EVAL_DIR, "ratings_sheet.csv")
        if os.path.exists(path):
            raise SystemExit(f"{path} exists; it may hold ratings. Move it first.")
        ratings_sheet(load_results(args.results)).to_csv(path, index=False)
        print(f"blank ratings sheet -> {path}")
    elif args.cmd == "judge":
        import functools
        chat = functools.partial(ollama_judge, think=False if args.no_think else None,
                                 schema=_CHECKLIST_SCHEMA if args.prompt == "checklist" else None)
        out = judge(load_results(args.results), args.model, chat=chat, prompt=args.prompt)
        suffix = f"_{args.tag}" if args.tag else ""
        path = os.path.join(EVAL_DIR, f"judge_{args.model.replace(':', '_')}{suffix}.jsonl")
        with open(path, "w") as f:
            for row in out:
                f.write(json.dumps(row) + "\n")
        print(f"{len(out)} answers judged -> {path}; scores {pd.Series([o['judge_score'] for o in out]).value_counts().to_dict()}")
    elif args.cmd == "checks":
        print(against_checks(load_results(args.results), pd.DataFrame(load_results(args.judged))))
    else:
        judged = pd.DataFrame(load_results(args.judged))
        print(calibrate(pd.read_csv(args.ratings, keep_default_na=False), judged))


if __name__ == "__main__":
    main()
