"""How much the index's own constants move the headline: the news weight
(1.5 against 1.0 for every source), the shrinkage constant (5, against 0
and 20), and weighting by the model's confidence (against none). Reads
data/plp.db only.

  .venv-plp/bin/python3 data/eval/index-uncertainty/sensitivity.py
"""
import os, sqlite3, sys
from datetime import timedelta
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
import pandas as pd
import aggregate.index as ix
from config.model_version import MODEL_VERSION

conn = sqlite3.connect("file:data/plp.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT s.bank, s.source, s.published_at, a.label, a.confidence FROM sentences s
                    JOIN aspect_sentiment a USING (sentence_id) WHERE a.model_version = ?""", conn, params=(MODEL_VERSION,))
anchor = ix.newest_sentence_time(conn); conn.close()
df["s"] = df.label.map(ix._LABEL_SCORE)
df["in_30d"] = [x is not None and x >= anchor - timedelta(days=30) for x in df.published_at.map(ix._utc)]
def score(g, news=1.5, k=ix.SHRINKAGE_K, conf=True):
    w = g.source.map(lambda s: 1.0 if ix._SOURCE_WEIGHT.get(s, 1.0) == 1.0 else news)
    cw = (g.confidence if conf else 1.0) * w
    return (g.s * cw).sum() / cw.sum() * len(g) / (len(g) + k)
rows = []
for name, kw in (("as stored: news 1.5, shrinkage 5, confidence-weighted", {}), ("every source weighted 1.0", {"news": 1.0}),
                 ("no shrinkage", {"k": 0}), ("shrinkage 20", {"k": 20}), ("no confidence weighting", {"conf": False})):
    r = {"variant": name}
    for bank, g in df.groupby("bank"):
        r[f"{bank} all time"] = round(score(g, **kw), 3); r[f"{bank} 30d"] = round(score(g[g.in_30d], **kw), 3)
    rows.append(r)
t = pd.DataFrame(rows); pd.set_option("display.width", 220); print(t.to_string(index=False))
t.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sensitivity.csv"), index=False)
