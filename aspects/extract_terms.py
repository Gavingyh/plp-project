"""
Aspect-term and opinion-term extraction (ABSA subtask: which words name the
thing being discussed, and which words give the opinion about it).

Aspect CATEGORISATION (already built, aspects/llm_classify.py) says a sentence is
about "dividends_capital_returns". Extraction goes one level finer, pointing at
the words: in "DBS raised its dividend but the payout ratio looks thin",
the aspect term is "payout ratio" and the opinion term is "looks thin".

Method: a local model (Ollama, structured JSON) lists pairs from the sentence.
Every returned span is then checked to occur verbatim in the sentence
(case-insensitive); a pair with an invented span is dropped and counted. The
model is not trusted on wording, only on which spans to pick.

Evaluation is against people: --export-gold writes a sheet with the model's
pairs hidden from a first pass (blank gold column) so annotators mark pairs
without anchoring on the model; --evaluate scores the model's pairs against the
filled sheet with exact and relaxed span matching, precision, recall and F1.
No accuracy is reported without that gold sheet.

Reads the database read-only (PLP_DB_PATH overrides the path); writes nothing
to it. Answers are cached in data/term_extraction/<model>.<prompt>.jsonl.

USAGE:
  python -m aspects.extract_terms --sample 300 --export-gold data/eval/terms/gold_sheet.csv
  python -m aspects.extract_terms --evaluate data/eval/terms/gold_sheet_filled.csv
  python -m aspects.extract_terms --summary --sample 3000      # top opinion terms by bank and aspect
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict

import pandas as pd
import requests

from config import aspect_taxonomy

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("PLP_DB_PATH") or os.path.join(BASE_DIR, "data", "plp.db")
CACHE_DIR = os.path.join(BASE_DIR, "data", "term_extraction")
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MAX_SPAN_WORDS = 6
POLARITIES = ["positive", "negative", "neutral"]

SCHEMA = {"type": "object", "properties": {"pairs": {"type": "array", "maxItems": 5, "items": {
    "type": "object",
    "properties": {"aspect_term": {"type": "string"}, "opinion_term": {"type": "string"},
                   "polarity": {"type": "string", "enum": POLARITIES}},
    "required": ["aspect_term", "opinion_term", "polarity"]}}}, "required": ["pairs"]}

EXAMPLES = [
    ("DBS raised its dividend but the payout ratio looks thin.",
     [("dividend", "raised", "positive"), ("payout ratio", "looks thin", "negative")]),
    ("The OCBC app keeps crashing when I try to transfer.",
     [("OCBC app", "keeps crashing", "negative")]),
    ("UOB net interest margin was stable at 2.0%.",
     [("net interest margin", "stable", "neutral")]),
]


def build_messages(sentence: str, aspect: str) -> list[dict]:
    ex = "\n".join(f'Sentence: "{s}"\nAnswer: ' + json.dumps({"pairs": [
        {"aspect_term": a, "opinion_term": o, "polarity": p} for a, o, p in pairs]}) for s, pairs in EXAMPLES)
    system = (
        "You extract opinion pairs from a sentence about a Singapore bank (DBS, OCBC or UOB).\n"
        "An aspect_term is the short phrase naming the thing being discussed (for example 'dividend', "
        "'net interest margin', 'app'). An opinion_term is the short phrase expressing the opinion "
        "or change about it (for example 'looks thin', 'raised'). polarity is the opinion's sentiment "
        "toward the aspect term.\n"
        f"Rules: copy both phrases exactly as they appear in the sentence; each is at most "
        f"{MAX_SPAN_WORDS} words; return at most 5 pairs; return an empty list if the sentence "
        "states no opinion about a specific aspect. Answer with JSON only.\n\nExamples:\n" + ex)
    return [{"role": "system", "content": system},
            {"role": "user", "content": f'Topic of the sentence: {aspect.replace("_", " ")}\n'
                                        f'Sentence: "{sentence}"\nAnswer:'}]


def prompt_fingerprint() -> str:
    blob = json.dumps(build_messages("{s}", "{a}"), sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:8]


def ollama_chat(model: str, messages: list[dict]) -> str:
    resp = requests.post(f"{OLLAMA_URL}/api/chat", timeout=300, json={
        "model": model, "messages": messages, "stream": False, "format": SCHEMA,
        "options": {"temperature": 0}})
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower().strip(".,;:!?\"'()"))


def valid_span(span: str, sentence: str) -> bool:
    s = norm(span)
    return bool(s) and len(s.split()) <= MAX_SPAN_WORDS and s in norm(sentence)


def validate_pairs(raw: str, sentence: str) -> tuple[list[dict], int]:
    """(pairs whose spans occur in the sentence, number dropped)."""
    try:
        pairs = json.loads(raw).get("pairs", [])
    except (json.JSONDecodeError, AttributeError, TypeError):
        return [], 1
    kept, dropped, seen = [], 0, set()
    for p in pairs:
        if not isinstance(p, dict):
            dropped += 1
            continue
        a, o, pol = p.get("aspect_term", ""), p.get("opinion_term", ""), p.get("polarity")
        key = (norm(a), norm(o))
        if (valid_span(a, sentence) and valid_span(o, sentence) and pol in POLARITIES
                and norm(a) != norm(o) and key not in seen):
            seen.add(key)
            kept.append({"aspect_term": norm(a), "opinion_term": norm(o), "polarity": pol})
        else:
            dropped += 1
    return kept, dropped


def sample_sentences(n: int, seed: int = 42, path: str = DB_PATH) -> pd.DataFrame:
    """n sentences spread evenly over aspects, one aspect per sentence, read-only."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        df = pd.read_sql_query(
            "SELECT s.sentence_id, s.text, s.bank, s.source, a.aspect FROM sentences s "
            "JOIN sentence_aspects a ON a.sentence_id = s.sentence_id "
            "WHERE length(s.text) BETWEEN 30 AND 400", conn)
    finally:
        conn.close()
    df = df[df["aspect"] != "other"].drop_duplicates("sentence_id")
    per = max(1, n // max(1, df["aspect"].nunique()))
    out = pd.concat([g.sample(min(len(g), per), random_state=seed) for _, g in df.groupby("aspect")])
    return out.sample(frac=1, random_state=seed).head(n).reset_index(drop=True)


def cache_path(model: str) -> str:
    return os.path.join(CACHE_DIR, re.sub(r"[^A-Za-z0-9._-]", "_", model) + f".{prompt_fingerprint()}.jsonl")


def extract(rows: pd.DataFrame, model: str, chat=ollama_chat, cache: str | None = None) -> pd.DataFrame:
    cache = cache or cache_path(model)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    done = {}
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                done[r["key"]] = r
    out = []
    with open(cache, "a", encoding="utf-8") as f:
        for row in rows.itertuples():
            key = f"{row.sentence_id}|{row.aspect}"
            if key not in done:
                pairs, dropped = validate_pairs(chat(model, build_messages(row.text, row.aspect)), row.text)
                done[key] = {"key": key, "pairs": pairs, "dropped": dropped}
                f.write(json.dumps(done[key], ensure_ascii=False) + "\n")
                f.flush()
            out.append({**row._asdict(), "pairs": done[key]["pairs"], "dropped": done[key]["dropped"]})
    return pd.DataFrame(out)


def export_gold(rows: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    sheet = rows[["sentence_id", "bank", "aspect", "text"]].copy()
    sheet["gold_pairs"] = ""      # "aspect term => opinion term ; aspect term => opinion term"
    sheet["annotator"] = ""
    sheet.to_csv(path, index=False)


def parse_gold(cell) -> list[tuple[str, str]]:
    if not isinstance(cell, str) or not cell.strip():
        return []
    pairs = []
    for part in cell.split(";"):
        if "=>" in part:
            a, o = part.split("=>", 1)
            if norm(a) and norm(o):
                pairs.append((norm(a), norm(o)))
    return pairs


def span_match(x: str, y: str, relaxed: bool) -> bool:
    if x == y:
        return True
    return relaxed and (x in y or y in x)


def match_counts(pred: list[tuple[str, str]], gold: list[tuple[str, str]], relaxed: bool) -> tuple[int, int, int]:
    """(true positives, predicted, gold), each gold pair matched at most once."""
    used, tp = set(), 0
    for pa, po in pred:
        for j, (ga, go) in enumerate(gold):
            if j not in used and span_match(pa, ga, relaxed) and span_match(po, go, relaxed):
                used.add(j)
                tp += 1
                break
    return tp, len(pred), len(gold)


def prf(tp: int, n_pred: int, n_gold: int) -> dict:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0}


def evaluate(extracted: pd.DataFrame, gold_df: pd.DataFrame) -> dict:
    gold = gold_df[gold_df["annotator"].fillna("").astype(str).str.strip() != ""]   # only annotated rows
    pred_by = {r.sentence_id: [(p["aspect_term"], p["opinion_term"]) for p in r.pairs] for r in extracted.itertuples()}
    result = {"n_sentences": len(gold)}
    for name, relaxed in (("exact", False), ("relaxed", True)):
        tp = npred = ngold = 0
        for r in gold.itertuples():
            a, b, c = match_counts(pred_by.get(r.sentence_id, []), parse_gold(r.gold_pairs), relaxed)
            tp, npred, ngold = tp + a, npred + b, ngold + c
        result[name] = {**prf(tp, npred, ngold), "tp": tp, "n_pred": npred, "n_gold": ngold}
    return result


def summarise(extracted: pd.DataFrame, top: int = 8) -> str:
    by = defaultdict(Counter)
    for r in extracted.itertuples():
        for p in r.pairs:
            by[(r.aspect, p["polarity"])][p["opinion_term"]] += 1
    lines = ["# Opinion terms by topic", ""]
    for aspect in sorted({a for a, _ in by}):
        lines.append(f"## {aspect.replace('_', ' ')}")
        for pol in ("positive", "negative"):
            terms = ", ".join(f"{t} ({c})" for t, c in by[(aspect, pol)].most_common(top))
            lines.append(f"- {pol}: {terms or '-'}")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--model", default=aspect_taxonomy.load()["llm_model"])
    ap.add_argument("--export-gold")
    ap.add_argument("--evaluate", help="a gold sheet filled in by annotators")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--out", default=os.path.join(BASE_DIR, "data", "eval", "terms"))
    a = ap.parse_args()
    if a.evaluate:
        gold = pd.read_csv(a.evaluate)
        extracted = extract(gold[["sentence_id", "text", "bank", "aspect"]].drop_duplicates("sentence_id"), a.model)
        result = evaluate(extracted, gold)
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, "evaluation.json"), "w") as f:
            json.dump(result, f, indent=1)
        print(json.dumps(result, indent=1))
        return
    rows = sample_sentences(a.sample)
    if a.export_gold:                        # no model output goes in the sheet
        export_gold(rows, a.export_gold)
        print(f"wrote {len(rows)} sentences to {a.export_gold}; fill gold_pairs and annotator")
        return
    extracted = extract(rows, a.model)
    os.makedirs(a.out, exist_ok=True)
    extracted.to_json(os.path.join(a.out, "extracted.jsonl"), orient="records", lines=True)
    print(f"{len(extracted)} sentences, {sum(len(p) for p in extracted.pairs)} pairs kept, "
          f"{int(extracted.dropped.sum())} dropped (span not in sentence or invalid)")
    if a.summary:
        with open(os.path.join(a.out, "opinion_terms.md"), "w", encoding="utf-8") as f:
            f.write(summarise(extracted))


if __name__ == "__main__":
    main()
