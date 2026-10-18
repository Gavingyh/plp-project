"""
Opinion summarisation: for one bank and topic, a short, cited summary of what
investors praise and what they criticise.

Why this exists: the chatbot quotes evidence but never summarises it, and the
course's opinion-summarisation topic (NMSM) asks for a short summary of many
opinions. This is the contrastive form: positive points and negative points,
each tied to the sentences that support it.

How it stays honest (the same stance as the chatbot's grounding rules):
  1. The model sees only retrieved sentences, each with an id (E1, E2, ...).
  2. Its answer is constrained to JSON: points, each with a claim and the ids
     that support it.
  3. Deterministic checks then drop any point that cites no id, cites an id it
     was not given, cites a sentence of the wrong polarity, states a number
     that is in none of its cited sentences, or is too long. Dropped points are
     counted and reported, not hidden.
  4. A rating sheet is exported so people, not the code, judge faithfulness and
     usefulness. The report may only claim what that sheet shows.

It writes nothing to the database.

USAGE (on the machine with Ollama running):
  python -m chatbot.summarise --banks DBS OCBC UOB --aspects dividends_capital_returns --k 6
  python -m chatbot.summarise --all-aspects --out data/eval/summaries
  python -m chatbot.summarise --model llama3.1:8b --limit 3        # a quick try
"""

import argparse
import csv
import json
import os
import re
import time

import requests

from config import aspect_taxonomy

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
BANKS = ["DBS", "OCBC", "UOB"]
MAX_WORDS = 30          # a point is one short sentence
MIN_EVIDENCE = 3        # fewer sentences of a polarity than this: no points for that side
NUMBER = re.compile(r"\d+(?:\.\d+)?")

SCHEMA = {
    "type": "object",
    "properties": {side: {"type": "array", "maxItems": 3, "items": {
        "type": "object",
        "properties": {"claim": {"type": "string"},
                       "evidence_ids": {"type": "array", "items": {"type": "string"}}},
        "required": ["claim", "evidence_ids"]}} for side in ("positive_points", "negative_points")},
    "required": ["positive_points", "negative_points"],
}


def build_messages(bank: str, topic: str, positive: list[dict], negative: list[dict]) -> list[dict]:
    def block(items):
        return "\n".join(f'{e["evidence_id"]} ({e["source"]}): "{e["text"]}"' for e in items) or "(none)"
    system = (
        "You summarise what investors say about a Singapore bank for a retail-investor dashboard.\n"
        "Write only from the sentences given. Do not use outside knowledge.\n"
        "Return JSON with positive_points and negative_points (at most 3 each). Each point is one "
        f"plain sentence of at most {MAX_WORDS} words, with the ids of the sentences that support it. "
        "Positive points may cite only sentences from the positive list; negative points only from "
        "the negative list. Do not state a number unless it appears in a sentence you cite. If a "
        "list is empty or says too little, return an empty array for that side. Group sentences that "
        "make the same point into one point; do not copy a sentence."
    )
    user = (f"Bank: {bank}\nTopic: {topic}\n\nPOSITIVE sentences:\n{block(positive)}\n\n"
            f"NEGATIVE sentences:\n{block(negative)}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def ollama_chat(model: str, messages: list[dict]) -> str:
    resp = requests.post(f"{OLLAMA_URL}/api/chat", timeout=300, json={
        "model": model, "messages": messages, "stream": False, "format": SCHEMA,
        "options": {"temperature": 0}})
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def parse(content: str) -> dict:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"positive_points": [], "negative_points": []}
    return {s: [p for p in data.get(s, []) if isinstance(p, dict)] for s in ("positive_points", "negative_points")}


def check_point(point: dict, side: str, given: dict[str, dict]) -> str | None:
    """None if the point passes, otherwise the reason it fails."""
    claim = (point.get("claim") or "").strip()
    ids = point.get("evidence_ids") or []
    want = "positive" if side == "positive_points" else "negative"
    if not claim:
        return "empty"
    if len(claim.split()) > MAX_WORDS:
        return "too long"
    if not ids:
        return "no citation"
    if any(i not in given for i in ids):
        return "cites an id it was not given"
    if any(given[i].get("sentiment") != want for i in ids):
        return "cites a sentence of the other polarity"
    cited = " ".join(given[i]["text"] for i in ids)
    cited_numbers = set(NUMBER.findall(cited))
    if any(n not in cited_numbers for n in NUMBER.findall(claim)):
        return "number not in cited sentences"
    return None


def validate(parsed: dict, evidence: list[dict]) -> tuple[dict, list[dict]]:
    given = {e["evidence_id"]: e for e in evidence}
    kept, dropped = {"positive_points": [], "negative_points": []}, []
    for side in kept:
        for point in parsed.get(side, []):
            reason = check_point(point, side, given)
            if reason:
                dropped.append({"side": side, "claim": point.get("claim"), "reason": reason})
            else:
                kept[side].append(point)
    return kept, dropped


def renumber(positive: list[dict], negative: list[dict]) -> list[dict]:
    """One id space across both lists, so a point's ids are unambiguous."""
    out = []
    for i, e in enumerate(positive + negative, start=1):
        out.append({**e, "evidence_id": f"E{i}"})
    return out


def gather(bank: str, aspect: str | None, k: int) -> tuple[list[dict], list[dict]]:
    from chatbot import tools        # imported here: it loads the embedding model's libraries
    query = aspect.replace("_", " ") if aspect else f"{bank} sentiment"
    pos = tools.search_evidence(query, bank=bank, aspect=aspect, sentiment="positive", k=k)["results"]
    neg = tools.search_evidence(query, bank=bank, aspect=aspect, sentiment="negative", k=k)["results"]
    return pos, neg


def summarise_one(bank: str, aspect: str | None, k: int, model: str, chat=ollama_chat) -> dict:
    pos, neg = gather(bank, aspect, k)
    pos = pos if len(pos) >= MIN_EVIDENCE else []
    neg = neg if len(neg) >= MIN_EVIDENCE else []
    evidence = renumber(pos, neg)
    pos_e, neg_e = evidence[:len(pos)], evidence[len(pos):]
    result = {"bank": bank, "aspect": aspect, "model": model, "n_positive": len(pos), "n_negative": len(neg),
              "evidence": evidence, "positive_points": [], "negative_points": [], "dropped": []}
    if not evidence:
        return result
    topic = aspect.replace("_", " ") if aspect else "overall"
    parsed = parse(chat(model, build_messages(bank, topic, pos_e, neg_e)))
    kept, dropped = validate(parsed, evidence)
    # a side with too little evidence yields no points even if the model wrote some
    if not pos:
        dropped += [{"side": "positive_points", "claim": p.get("claim"), "reason": "too little evidence"}
                    for p in kept["positive_points"]]
        kept["positive_points"] = []
    if not neg:
        dropped += [{"side": "negative_points", "claim": p.get("claim"), "reason": "too little evidence"}
                    for p in kept["negative_points"]]
        kept["negative_points"] = []
    result.update(kept)
    result["dropped"] = dropped
    return result


def render(results: list[dict]) -> str:
    lines = ["# Opinion summaries", "",
             "Each point cites the sentences it rests on. Points that failed the checks are listed "
             "at the end of each section, not shown above.", ""]
    for r in results:
        lines += [f"## {r['bank']} - {(r['aspect'] or 'overall').replace('_', ' ')}", "",
                  f"Evidence: {r['n_positive']} positive, {r['n_negative']} negative sentences.", ""]
        by_id = {e["evidence_id"]: e for e in r["evidence"]}
        for side, title in (("positive_points", "Praised"), ("negative_points", "Criticised")):
            lines.append(f"**{title}**")
            if not r[side]:
                lines.append("- (nothing reliable to report)")
            for p in r[side]:
                cites = ", ".join(f'{by_id[i]["source"]} {by_id[i]["date"]}' for i in p["evidence_ids"])
                lines.append(f"- {p['claim']} ({cites})")
            lines.append("")
        if r["dropped"]:
            lines.append(f"Dropped by checks: {len(r['dropped'])} " + "; ".join(
                f'"{d["claim"]}" ({d["reason"]})' for d in r["dropped"]))
            lines.append("")
    return "\n".join(lines)


def rating_rows(results: list[dict]) -> list[dict]:
    rows = []
    for r in results:
        by_id = {e["evidence_id"]: e for e in r["evidence"]}
        for side in ("positive_points", "negative_points"):
            for p in r[side]:
                rows.append({"bank": r["bank"], "aspect": r["aspect"] or "overall", "side": side[:3],
                             "claim": p["claim"],
                             "cited_sentences": " || ".join(by_id[i]["text"] for i in p["evidence_ids"]),
                             "supported_0_1": "", "useful_1_5": "", "rater": "", "note": ""})
    return rows


def run(banks, aspects, k, model, out_dir, limit=None, chat=ollama_chat) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    pairs = [(b, a) for b in banks for a in aspects]
    if limit:
        pairs = pairs[:limit]
    results = []
    for bank, aspect in pairs:
        t0 = time.time()
        results.append(summarise_one(bank, aspect, k, model, chat=chat))
        print(f"{bank} {aspect or 'overall'}: {len(results[-1]['positive_points'])}+/"
              f"{len(results[-1]['negative_points'])}- points, {len(results[-1]['dropped'])} dropped "
              f"({time.time() - t0:.1f}s)")
    with open(os.path.join(out_dir, "summaries.jsonl"), "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(out_dir, "summaries.md"), "w", encoding="utf-8") as f:
        f.write(render(results))
    rows = rating_rows(results)
    with open(os.path.join(out_dir, "rating_sheet.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bank", "aspect", "side", "claim", "cited_sentences",
                                           "supported_0_1", "useful_1_5", "rater", "note"])
        w.writeheader()
        w.writerows(rows)
    kept = sum(len(r["positive_points"]) + len(r["negative_points"]) for r in results)
    dropped = sum(len(r["dropped"]) for r in results)
    print(f"{kept} points kept, {dropped} dropped by checks; rating sheet has {len(rows)} rows")
    return {"kept": kept, "dropped": dropped, "rows": len(rows)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--banks", nargs="+", default=BANKS)
    ap.add_argument("--aspects", nargs="*", default=[])
    ap.add_argument("--all-aspects", action="store_true")
    ap.add_argument("--k", type=int, default=6, help="sentences retrieved per polarity")
    ap.add_argument("--model", default=aspect_taxonomy.load()["llm_model"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default=os.path.join(BASE_DIR, "data", "eval", "summaries"))
    a = ap.parse_args()
    aspects = list(aspect_taxonomy.load()["aspects"]) if a.all_aspects else (a.aspects or [None])
    try:
        from chatbot.ollama_load import ensure_loaded
        ensure_loaded(a.model)
    except Exception:
        pass
    run(a.banks, aspects, a.k, a.model, a.out, a.limit)


if __name__ == "__main__":
    main()
