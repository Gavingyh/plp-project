"""Before and after the rehearsal: the stored index in data/plp.db against the
rescored copy. Reads both, writes nothing but the tables it prints. Run from
the repository root; the copy's path may be given as the first argument."""
import os, sqlite3, sys
import pandas as pd

REAL = "data/plp.db"
COPY = sys.argv[1] if len(sys.argv) > 1 else "data/run/rescore-2026-10-12/plp_rescored.db"
BASE = "finbert-base-zeroshot-v1"
NEW = "finbert-adapted-finetuned-2026-10-11-3seed-m0"
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)


def ro(path):
    return sqlite3.connect(f"file:{os.path.realpath(path)}?mode=ro", uri=True)


def index(conn, version):
    return pd.read_sql("SELECT bank, aspect, window, source, score, n, pos_n, neu_n, neg_n FROM sentiment_index "
                       "WHERE model_version = ?", conn, params=(version,))


real, copy = ro(REAL), ro(COPY)
cols = {"before": index(real, BASE), "llm_aspects_base": index(copy, BASE), "llm_aspects_new_model": index(copy, NEW)}
key = ["bank", "aspect", "window", "source"]
wide = None
for name, df in cols.items():
    d = df.set_index(key)[["score", "n", "pos_n", "neu_n", "neg_n"]].add_suffix(f"|{name}")
    wide = d if wide is None else wide.join(d, how="outer")
wide = wide.reset_index()

print("## Counts")
for name, conn in (("data/plp.db", real), ("copy", copy)):
    q = lambda s: conn.execute(s).fetchall()  # noqa: E731
    print(name, "| sentences", q("SELECT COUNT(*) FROM sentences")[0][0], "| assigned pairs",
          q("SELECT COUNT(*) FROM sentence_aspects")[0][0], "| scores", dict(q(
              "SELECT model_version, COUNT(*) FROM aspect_sentiment GROUP BY 1")), "| index rows", dict(q(
                  "SELECT model_version, COUNT(*) FROM sentiment_index GROUP BY 1")))


def show(title, frame, names=("before", "llm_aspects_base", "llm_aspects_new_model")):
    print(f"\n## {title}")
    out = frame[[c for c in key if frame[c].nunique() > 1]].copy()
    for n in names:
        out[f"score {n}"] = frame[f"score|{n}"].round(3)
        out[f"n {n}"] = frame[f"n|{n}"]
    for n in names:
        tot = frame[f"n|{n}"]
        out[f"pos/neu/neg % {n}"] = [
            "" if pd.isna(t) or not t else f"{100*p/t:.0f}/{100*u/t:.0f}/{100*g/t:.0f}"
            for p, u, g, t in zip(frame[f"pos_n|{n}"], frame[f"neu_n|{n}"], frame[f"neg_n|{n}"], tot)]
    print(out.to_string(index=False))


head = wide[(wide.aspect == "ALL") & (wide.source == "ALL")]
show("Headline per bank and window (all sources, all aspects)", head.sort_values(["window", "bank"]))
show("Headline per bank and source (all time)",
     wide[(wide.aspect == "ALL") & (wide.window == "all_time") & (wide.source != "ALL")].sort_values(["source", "bank"]))
show("Per aspect, all time, all sources",
     wide[(wide.aspect != "ALL") & (wide.window == "all_time") & (wide.source == "ALL")].sort_values(["aspect", "bank"]))

print("\n## Aspect of each sentence: centroid pairs before, one LLM aspect after")
a = pd.read_sql("SELECT aspect, COUNT(*) AS pairs_before FROM sentence_aspects GROUP BY 1", real).set_index("aspect")
b = pd.read_sql("SELECT aspect, COUNT(*) AS sentences_after FROM sentence_aspects GROUP BY 1", copy).set_index("aspect")
print(a.join(b, how="outer").fillna(0).astype(int).to_string())

print("\n## Label of each sentence: base FinBERT against the chosen model, same LLM aspect")
lab = pd.read_sql("""SELECT b.label AS base, n.label AS new_model, COUNT(*) AS sentences
                     FROM aspect_sentiment b JOIN aspect_sentiment n USING (sentence_id, aspect)
                     WHERE b.model_version = ? AND n.model_version = ? GROUP BY 1, 2""", copy, params=(BASE, NEW))
print(lab.pivot(index="base", columns="new_model", values="sentences").fillna(0).astype(int).to_string())
print("changed:", int(lab[lab.base != lab.new_model].sentences.sum()), "of", int(lab.sentences.sum()))
