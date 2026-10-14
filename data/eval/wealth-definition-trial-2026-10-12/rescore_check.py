"""The condition for applying the second re-score without a person's review.
Compares the rehearsed copy with data/plp.db and exits 0 only if:
  - both hold the same sentences, and the copy has one aspect a sentence and
    both models' scores for every pair;
  - every headline row scored by base FinBERT is identical (its score does
    not depend on the aspect, so any difference is a fault);
  - each bank's all-time headline under the served model moved by no more
    than TOLERANCE (its input includes the aspect's name, so it moves a little).
Prints every per-aspect row before and after. Reads only.

  python gate.py <copy.db> [tolerance]
"""
import sqlite3, sys
from config.model_version import BASE_VERSION, MODEL_VERSION

copy_path = sys.argv[1]; TOL = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
a = sqlite3.connect("file:data/plp.db?mode=ro", uri=True); b = sqlite3.connect(f"file:{copy_path}?mode=ro", uri=True)
q = lambda c, sql, *p: c.execute(sql, p).fetchall()
problems = []
if q(a, "SELECT sentence_id FROM sentences ORDER BY 1") != q(b, "SELECT sentence_id FROM sentences ORDER BY 1"):
    problems.append("the copy does not hold the same sentences")
n = q(b, "SELECT COUNT(*) FROM sentences")[0][0]
if q(b, "SELECT COUNT(*), COUNT(DISTINCT sentence_id) FROM sentence_aspects")[0] != (n, n):
    problems.append("the copy does not have exactly one aspect a sentence")
for v in (BASE_VERSION, MODEL_VERSION):
    missing = q(b, """SELECT COUNT(*) FROM sentence_aspects s WHERE NOT EXISTS (SELECT 1 FROM aspect_sentiment x
                      WHERE x.sentence_id = s.sentence_id AND x.aspect = s.aspect AND x.model_version = ?)""", v)[0][0]
    if missing:
        problems.append(f"{missing} pairs have no {v} score in the copy")
head = "SELECT bank, window, source, score, n, pos_n, neu_n, neg_n FROM sentiment_index WHERE aspect='ALL' AND model_version=? ORDER BY 1,2,3"
if q(a, head, BASE_VERSION) != q(b, head, BASE_VERSION):
    problems.append("base FinBERT's headline rows differ, which the aspect change cannot cause")
hv = "SELECT bank, score, n FROM sentiment_index WHERE aspect='ALL' AND source='ALL' AND window=? AND model_version=? ORDER BY 1"
print("Headline under the served model (all sources):")
for w in ("all_time", "30d", "7d"):
    for (bank, s0, n0), (_, s1, n1) in zip(q(a, hv, w, MODEL_VERSION), q(b, hv, w, MODEL_VERSION)):
        print(f"  {w:8} {bank:5} {s0:+.4f} -> {s1:+.4f}  change {s1 - s0:+.4f}  ({n0} -> {n1} sentences)")
        if w == "all_time" and (abs(s1 - s0) > TOL + 1e-9 or n0 != n1):
            problems.append(f"{bank}'s all-time headline moved by {s1 - s0:+.4f}, more than {TOL}")
asp = "SELECT bank, aspect, score, n FROM sentiment_index WHERE aspect!='ALL' AND source='ALL' AND window='all_time' AND model_version=?"
x = {(r[1], r[0]): r[2:] for r in q(a, asp, MODEL_VERSION)}; y = {(r[1], r[0]): r[2:] for r in q(b, asp, MODEL_VERSION)}
print("\nPer aspect, all time, all sources, served model: score (sentences) before -> after")
for k in sorted(set(x) | set(y)):
    s0, n0 = x.get(k, (float("nan"), 0)); s1, n1 = y.get(k, (float("nan"), 0))
    print(f"  {k[0]:26} {k[1]:5} {s0:+.3f} ({n0:5}) -> {s1:+.3f} ({n1:5})")
ca = dict(q(a, "SELECT aspect, COUNT(*) FROM sentence_aspects GROUP BY 1")); cb = dict(q(b, "SELECT aspect, COUNT(*) FROM sentence_aspects GROUP BY 1"))
print("\nSentences per aspect before -> after:")
for k in sorted(set(ca) | set(cb)):
    print(f"  {k:26} {ca.get(k, 0):6} -> {cb.get(k, 0):6}")
moved = q(b, "SELECT COUNT(*) FROM sentence_aspects")[0][0] - len(set(q(a, "SELECT sentence_id, aspect FROM sentence_aspects")) & set(q(b, "SELECT sentence_id, aspect FROM sentence_aspects")))
print(f"\nSentences whose aspect changed: {moved} of {n}")
print("\nGATE:", "PASS" if not problems else "FAIL: " + "; ".join(problems))
sys.exit(0 if not problems else 1)
