"""
LLM aspect classification (DESIGN decision 16, taxonomy from decision 21):
a local model reads one sentence and returns exactly one aspect key from
config/aspects.yaml, the ten aspects or `other`.

The prompt follows the course's zero-shot ABSA pattern (NMSM Day 2): role,
task, the schema of categories with definitions, constraints, a few worked
examples, then the input. Ollama's structured output constrains the answer to
JSON whose `aspect` is one of the keys; an answer that still fails validation
is retried once and then recorded as `other` and counted.

This module only classifies and evaluates. It writes nothing to the
database: applying it to the corpus is a separate, approved step. Answers are
cached in data/aspect_llm/<model>.jsonl (gitignored) so a run resumes.

USAGE:
  python -m aspects.llm_classify --eval                    # the 1,277 labelled sentences
  python -m aspects.llm_classify --corpus                  # every sentence into the cache only
  python -m aspects.llm_classify --eval --model qwen3:4b --no-think --limit 50

`--no-think` turns off a reasoning model's hidden thinking (Ollama's `think`
option): on 1 Oct qwen3:4b took 92-216 s a sentence thinking, against about
2 s for llama3.1:8b, which doesn't think.
"""

import argparse
import functools
import json
import os
import re
import time
from collections import Counter

import pandas as pd
import requests
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "aspects.yaml")
LABELS_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
CACHE_DIR = os.path.join(BASE_DIR, "data", "aspect_llm")
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = "llama3.1:8b"
OTHER = "other"

# One line per aspect, from docs/evidence/aspect-taxonomy-2026-09-25.md.
DEFINITIONS = {
    "asset_quality": "loan quality: non-performing loans, allowances and provisions, credit costs, exposure to troubled borrowers",
    "capital_liquidity": "capital and liquidity: CET1 and capital ratios, leverage, LCR/NSFR, Basel rules, capital instruments, bond issuance",
    "dividend_policy": "dividends declared or expected, dividend per share, payout ratio, dividend yield, capital returned to shareholders",
    "net_interest_margin": "net interest margin and net interest income, loan and deposit growth as their driver, effect of interest-rate moves on the bank's earnings",
    "management_guidance": "forward-looking statements by the bank: targets, outlook, guidance, strategy, earnings-call answers",
    "income_profit_results": "reported income and profit: total income, net profit, fee and trading income, quarterly or annual results",
    "wealth_business": "wealth management and private or premier banking: assets under management, wealth fee income, wealth targets",
    "investor_stock_sentiment": "the bank's stock: buy, sell or hold views, share price, valuation, analyst target prices, returns against alternatives",
    "retail_banking_sentiment": "products and service as customers experience them: cards, cashback, savings accounts, fees, app or service outages, scams, applications",
    "macro_market_environment": "GDP, interest-rate cuts and hikes, geopolitics and trade, the macro outlook as it affects the banks",
    OTHER: "anything else: appointments and pay, awards, M&A and partnerships, CSR, careers, regulatory boilerplate, or no clear investment topic",
}

# Invented sentences, so none can appear in the evaluation set.
EXAMPLES = [
    ("The bank set aside more allowances as bad loans rose in its SME book.", "asset_quality"),
    ("Its CET1 ratio stayed comfortably above the regulatory minimum.", "capital_liquidity"),
    ("They declared a final dividend of 60 cents a share.", "dividend_policy"),
    ("Margins narrowed as interest rates fell, weighing on net interest income.", "net_interest_margin"),
    ("Management expects mid-single-digit loan growth next year.", "management_guidance"),
    ("Quarterly net profit rose 8% on higher fee income.", "income_profit_results"),
    ("Wealth management fees hit a record as assets under management grew.", "wealth_business"),
    ("I'm holding the shares for the yield; the price looks fair at 1.5x book.", "investor_stock_sentiment"),
    ("The app has been down all morning and I can't transfer money.", "retail_banking_sentiment"),
    ("Rate cuts by the Fed will squeeze all three Singapore banks.", "macro_market_environment"),
    ("The bank named a new chief technology officer.", OTHER),
]


def aspect_keys(config_path: str = CONFIG_PATH) -> list[str]:
    with open(config_path) as f:
        return list(yaml.safe_load(f)["aspects"].keys())


def build_messages(sentence: str, keys: list[str]) -> list[dict]:
    schema = "\n".join(f"- {k}: {DEFINITIONS.get(k, '')}" for k in keys)
    examples = "\n".join(f'Sentence: "{s}"\nAnswer: {{"aspect": "{a}"}}' for s, a in EXAMPLES if a in keys)
    system = (
        "You are an analyst classifying sentences about Singapore's three listed banks, "
        "DBS, OCBC and UOB, for an investor sentiment study.\n\n"
        "Task: choose the ONE aspect the sentence is mainly about. If it touches two, choose "
        "the one its sentiment is about. Judge the topic only, not whether it is positive or "
        "negative.\n\nAspects:\n" + schema + "\n\n"
        "Constraints: answer with JSON only, exactly {\"aspect\": \"<key>\"}, using one of the "
        "keys above. No explanation.\n\nExamples:\n" + examples
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": f'Sentence: "{sentence}"\nAnswer:'}]


def parse_answer(content: str, keys: list[str]) -> str | None:
    """The aspect key from a model answer, or None if it isn't a valid one."""
    if not content:
        return None
    try:
        value = json.loads(content).get("aspect")
    except (json.JSONDecodeError, AttributeError):
        m = re.search(r'"aspect"\s*:\s*"([a-z_]+)"', content)
        value = m.group(1) if m else None
    return value if value in keys else None


def ollama_chat(model: str, messages: list[dict], keys: list[str], think: bool | None = None) -> str:
    """One deterministic call, with the answer constrained to the aspect keys.
    `think` is sent only when given, so models without thinking are untouched."""
    payload = {
        "model": model, "messages": messages, "stream": False,
        "format": {"type": "object", "properties": {"aspect": {"type": "string", "enum": keys}},
                   "required": ["aspect"]},
        "options": {"temperature": 0},
    }
    if think is not None:
        payload["think"] = think
    resp = requests.post(f"{OLLAMA_URL}/api/chat", timeout=300, json=payload)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def classify(sentence: str, keys: list[str], model: str = DEFAULT_MODEL, chat=ollama_chat) -> tuple[str, int]:
    """(aspect, attempts used). After two invalid answers, `other`, attempts 0."""
    messages = build_messages(sentence, keys)
    for attempt in (1, 2):
        aspect = parse_answer(chat(model, messages, keys), keys)
        if aspect is not None:
            return aspect, attempt
    return OTHER, 0


def _cache_path(model: str) -> str:
    return os.path.join(CACHE_DIR, re.sub(r"[^A-Za-z0-9._-]", "_", model) + ".jsonl")


def classify_rows(rows: pd.DataFrame, model: str = DEFAULT_MODEL, chat=ollama_chat,
                  cache_path: str | None = None) -> pd.DataFrame:
    """Classify each (sentence_id, text) row, reusing and appending to the cache."""
    keys = aspect_keys()
    cache_path = cache_path or _cache_path(model)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    cached = {}
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            for line in f:
                r = json.loads(line)
                cached[r["sentence_id"]] = r
    out = []
    with open(cache_path, "a") as f:
        for i, (sid, text) in enumerate(zip(rows["sentence_id"], rows["text"]), 1):
            if sid not in cached:
                t = time.time()
                aspect, attempts = classify(text, keys, model, chat)
                cached[sid] = {"sentence_id": sid, "aspect": aspect, "attempts": attempts,
                               "seconds": round(time.time() - t, 3)}
                f.write(json.dumps(cached[sid]) + "\n")
                f.flush()
                if i % 100 == 0:
                    print(f"classified {i}/{len(rows)}", flush=True)
            out.append(cached[sid])
    return pd.DataFrame(out)


def corpus_rows(conn, seed: int = 2026, limit: int | None = None) -> pd.DataFrame:
    """Every corpus sentence in a fixed random order: a run stopped early has
    covered a random sample, and the first n rows are aggregate.preview's
    sample of n (same seed, same draw)."""
    df = pd.read_sql("SELECT sentence_id, text FROM sentences ORDER BY sentence_id", conn)
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    return df.head(limit) if limit else df


def evaluate(pred: list[str], gold: list[str]) -> dict:
    from sklearn.metrics import f1_score
    keys = sorted(set(gold) | set(pred))
    return {"top1_accuracy": sum(p == g for p, g in zip(pred, gold)) / len(gold),
            "macro_f1": f1_score(gold, pred, labels=keys, average="macro", zero_division=0),
            "n": len(gold)}


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--eval", action="store_true", help="classify the labelled sentences and score them")
    p.add_argument("--corpus", action="store_true",
                   help="classify every corpus sentence into the answer cache (random order, resumable); "
                        "writes nothing to the database")
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--no-think", action="store_true", help="turn off a reasoning model's thinking")
    args = p.parse_args()
    if not (args.eval or args.corpus):
        p.error("use --eval or --corpus: writing aspects to the database is a separate, approved step")
    if args.corpus:
        from ingest.db import get_connection
        conn = get_connection()
        try:
            rows = corpus_rows(conn, args.seed, args.limit)
        finally:
            conn.close()
        chat = functools.partial(ollama_chat, think=False) if args.no_think else ollama_chat
        cache = _cache_path(args.model + ("-nothink" if args.no_think else ""))
        t = time.time()
        res = classify_rows(rows, args.model, chat, cache)
        print(f"corpus: {len(res)} of {len(rows)} sentences in the cache ({time.time() - t:.0f}s this run); "
              f"aspects {dict(Counter(res['aspect']).most_common())}")
        return

    labels = pd.read_csv(LABELS_PATH).drop_duplicates("sentence_id")
    if args.limit:
        labels = labels.head(args.limit)
    t = time.time()
    chat = functools.partial(ollama_chat, think=False) if args.no_think else ollama_chat
    cache = _cache_path(args.model + ("-nothink" if args.no_think else ""))
    res = classify_rows(labels[["sentence_id", "text"]], args.model, chat, cache)
    elapsed = time.time() - t
    gold, pred = labels["aspect"].tolist(), res["aspect"].tolist()
    m = evaluate(pred, gold)
    from sklearn.metrics import classification_report
    print(f"\nmodel {args.model}{' (no thinking)' if args.no_think else ''}: n={m['n']} top-1 accuracy {m['top1_accuracy']:.3f} macro-F1 {m['macro_f1']:.3f}")
    print(f"invalid after retry (recorded as other): {int((res['attempts'] == 0).sum())}; "
          f"needed a retry: {int((res['attempts'] == 2).sum())}")
    print(f"seconds per sentence (classified this run): {res['seconds'].mean():.2f}; wall time {elapsed:.0f}s")
    print("\n" + classification_report(gold, pred, zero_division=0))
    print(pd.crosstab(pd.Series(gold, name="human"), pd.Series(pred, name="llm")).to_string())
    print("\npredicted distribution:", dict(Counter(pred).most_common()))


if __name__ == "__main__":
    main()
