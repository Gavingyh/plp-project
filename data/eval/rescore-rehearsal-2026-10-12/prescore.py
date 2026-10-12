"""Score ahead, on the CPU, every (sentence, LLM aspect) pair whose aspect is
already in the classifier's cache, into the same cache scripts/rescore.py
--cpu reads. Reads data/plp.db only; writes data/preview/scores.<key>.jsonl."""
import json, os, sqlite3, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
import pandas as pd
import train.evaluate
train.evaluate.best_device = lambda: "cpu"
import aggregate.preview as pv
from aspects.llm_classify import answer_cache_path

MODELS = [os.path.realpath(f"models/experiments-2026-10-11/dapt/seed_{s}/final") for s in (42, 1, 7)]
answers = {}
with open(answer_cache_path("llama3.1:8b")) as f:
    for line in f:
        r = json.loads(line)
        answers[r["sentence_id"]] = r["aspect"]
conn = sqlite3.connect("file:data/plp.db?mode=ro", uri=True)
texts = pd.read_sql("SELECT sentence_id, text FROM sentences", conn)
conn.close()
pairs = texts[texts["sentence_id"].isin(answers)].copy()
pairs["aspect"] = pairs["sentence_id"].map(answers)
cache = pv.scores_cache_path(MODELS)
print("cache:", cache, "| pairs:", len(pairs), flush=True)
pv.averaged_probs(pairs, MODELS, cache)
print("done", flush=True)
