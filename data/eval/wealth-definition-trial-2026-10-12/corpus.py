"""Classify every corpus sentence under the wording trial.py tried, into that
wording's own answer file. Reads the database; writes only the cache
(data/aspect_llm/). Random order, resumable: rerun to continue. Applying the
answers to the database is a separate step (scripts/rescore.py), after
config/aspects.yaml is given the same wording.

  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 data/eval/wealth-definition-trial-2026-10-12/corpus.py
"""
import os, sqlite3, sys, time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))
sys.path.insert(0, HERE)
import aspects.llm_classify as llm
import trial

llm.DEFINITIONS = {**llm.DEFINITIONS, **trial.NEW_DEFINITIONS}
llm.EXAMPLES = llm.EXAMPLES + [e for e in trial.NEW_EXAMPLES if e not in llm.EXAMPLES]
cache = llm.answer_cache_path(trial.MODEL)
conn = sqlite3.connect("file:data/plp.db?mode=ro", uri=True)
rows = llm.corpus_rows(conn)
conn.close()
print(f"cache: {cache}; sentences: {len(rows)}", flush=True)
t = time.time()
res = llm.classify_rows(rows, trial.MODEL, cache_path=cache)
print(f"corpus: {len(res)} of {len(rows)} sentences in the cache ({time.time() - t:.0f}s this run); "
      f"invalid after retry: {int((res['attempts'] == 0).sum())}; aspects {dict(Counter(res['aspect']).most_common())}")
