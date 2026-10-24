"""Would a model built for search rank the chatbot's evidence better? Each
candidate embeds the 1,277 labelled sentences and the 28 queries of
chatbot/retrieval_eval.py, and the sentences people labelled with the asked
topic are counted among the top five. Two settings: within the stored-topic
filter (the chatbot's searches that name a topic) and without it (searches
that name none). References: the ordering in use within a topic (the
question's words, then newest), FinBERT similarity (in use without a topic),
and a random draw from the same pool.

Rule fixed before running: within a topic a model replaces the ordering in
use only at precision at 5 of 0.85 or more (0.82 now); without a topic it
replaces FinBERT if it is well above FinBERT's 0.12. Each model is scored on
similarity alone and, as the search combines them, with the small bonus for
words shared with the question. Speed is measured too, since the search embeds
each question while the user waits: one question's time, and the time and
memory to embed the corpus, extrapolated from the labelled sentences.

Qwen3-Embedding-0.6B was left out: on this Mac's processor it had not finished
the labelled sentences after about 15 minutes, where all-MiniLM-L6-v2 took
under half a minute, so it could neither answer a search quickly nor embed the
corpus in the time left.

  .venv-plp/bin/python3 data/eval/search-models/compare.py      # needs the network once, to download
"""
import json, os, sqlite3, sys, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
import numpy as np, pandas as pd, torch
from transformers import AutoModel, AutoTokenizer
import chatbot.retrieval_eval as re_
from chatbot.retrieval import _LEXICAL_WEIGHT, ranking_query, _lexical_overlap, _WORD, _instant
from config import aspect_taxonomy

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = {   # name: (repo, pooling, query prefix, document prefix)
    "all-MiniLM-L6-v2": ("sentence-transformers/all-MiniLM-L6-v2", "mean", "", ""),
    "bge-small-en-v1.5": ("BAAI/bge-small-en-v1.5", "cls", "Represent this sentence for searching relevant passages: ", ""),
    "bge-base-en-v1.5": ("BAAI/bge-base-en-v1.5", "cls", "Represent this sentence for searching relevant passages: ", ""),
}

def load(repo):
    return AutoTokenizer.from_pretrained(repo), AutoModel.from_pretrained(repo).float().eval()

def embed(texts, tok, model, pooling, batch=32):
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            enc = tok(texts[i:i + batch], padding=True, truncation=True, max_length=160, return_tensors="pt")
            h = model(**enc).last_hidden_state
            if pooling == "cls":
                v = h[:, 0]
            else:
                m = enc["attention_mask"].unsqueeze(-1).float(); v = (h * m).sum(1) / m.sum(1)
            out.append(torch.nn.functional.normalize(v, dim=-1).numpy())
    return np.concatenate(out)

labels = pd.read_csv(re_.LABELS_PATH)
conn = sqlite3.connect("file:data/plp.db?mode=ro", uri=True)
stored = dict(conn.execute("SELECT sentence_id, aspect FROM sentence_aspects").fetchall())
names = aspect_taxonomy.labels()
queries = []
for bank, bp in labels.groupby("bank"):
    for aspect, n in bp.aspect.value_counts().items():
        if aspect != "other" and n >= re_.MIN_RELEVANT:
            q = f"What do people say about {bank}'s {names[aspect].lower()}?"
            queries.append((bank, aspect, q, ranking_query(q, aspect)))
print(len(queries), "queries over", len(labels), "labelled sentences", flush=True)

def p_at_5(order, rel):
    return float(rel[order][:5].mean())

def rr(order, rel):
    hits = np.flatnonzero(rel[order]); return 1.0 / (hits[0] + 1) if len(hits) else 0.0

# FinBERT vectors from the search's own cache, for the reference without a topic
from aspects.embed import embed_sentences
from aspects.embed_store import load_for_search
labels["published_at"] = labels.sentence_id.map(dict(conn.execute("SELECT sentence_id, published_at FROM sentences").fetchall())).fillna(labels.published_at)
ids, fvecs = load_for_search(); fidx = {s: i for i, s in enumerate(ids)}
fin_doc = np.stack([fvecs[fidx[s]] for s in labels.sentence_id]); fin_doc = fin_doc / np.linalg.norm(fin_doc, axis=1, keepdims=True)
fin_q = {q: (lambda v: v / np.linalg.norm(v))(embed_sentences([q])[0]) for _, _, q, _ in queries}
CORPUS = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]

def one_question_ms(fn, runs=20):
    fn(); ts = []
    for _ in range(runs):
        t = time.perf_counter(); fn(); ts.append(time.perf_counter() - t)
    return round(1000 * float(np.median(ts)), 1)

speed = {"FinBERT (in use without a topic)": {
    "one question, ms": one_question_ms(lambda: embed_sentences([queries[0][2]])),
    "width": int(fin_doc.shape[1])}}
results = []
doc_vecs = {"FinBERT (in use without a topic)": (fin_doc, fin_q)}
for name, (repo, pooling, qpre, dpre) in MODELS.items():
    tok, model = load(repo)
    t = time.time()
    d = embed([dpre + x for x in labels.text], tok, model, pooling)
    secs = time.time() - t
    qv = embed([qpre + q for _, _, q, _ in queries], tok, model, pooling)
    doc_vecs[name] = (d, {q: qv[i] for i, (_, _, q, _) in enumerate(queries)})
    speed[name] = {"one question, ms": one_question_ms(lambda: embed([qpre + queries[0][2]], tok, model, pooling)),
                   "labelled sentences, s": round(secs, 1),
                   "corpus estimate, min": round(secs / len(labels) * CORPUS / 60, 1),
                   "weights in memory, MB": round(sum(p.numel() for p in model.parameters()) * 4 / 1e6),
                   "width": int(d.shape[1])}
    print(name, speed[name], flush=True)
for v in speed.values():
    v["corpus vectors, MB"] = round(CORPUS * v["width"] * 4 / 1e6)

for setting in ("within the topic filter", "without a topic"):
    for bank, aspect, q, aq in queries:
        mask = (labels.bank == bank).values
        if setting == "within the topic filter":
            mask = mask & np.array([stored.get(s) == aspect for s in labels.sentence_id])
        idx = np.flatnonzero(mask)
        if len(idx) == 0:
            continue
        rel = (labels.aspect.values[idx] == aspect)
        row = {"setting": setting, "bank": bank, "aspect": aspect, "pool": len(idx), "random": float(rel.mean())}
        words = set(_WORD.findall(aq.lower()))
        lex = np.array([_lexical_overlap(words, t) for t in labels.text.values[idx]])
        newest = np.array([_instant(p) for p in labels.published_at.values[idx]])
        o = np.lexsort((-newest, -lex)); row["words, then newest (in use within a topic)"] = p_at_5(o, rel)
        # the bonus uses the words the search would: the topic's query within a topic, else the question
        bonus_words = words if setting == "within the topic filter" else set(_WORD.findall(q.lower()))
        bonus = _LEXICAL_WEIGHT * np.array([_lexical_overlap(bonus_words, t) for t in labels.text.values[idx]])
        for name, (d, qmap) in doc_vecs.items():
            sim = d[idx] @ qmap[q]
            o = np.argsort(-sim, kind="stable"); row[name] = p_at_5(o, rel)
            o = np.argsort(-(sim + bonus), kind="stable"); row[name + " + word bonus"] = p_at_5(o, rel)
        results.append(row)
r = pd.DataFrame(results)
cols = ["random", "words, then newest (in use within a topic)"] + [c for n in doc_vecs for c in (n, n + " + word bonus")]
table = r.groupby("setting")[cols].mean().round(3).T
print("\nPrecision at 5, mean over the queries:\n" + table.to_string())
print("\nSpeed on this Mac's processor (" + str(CORPUS) + " sentences in the corpus):\n" + pd.DataFrame(speed).T.to_string())
json.dump({"speed": speed, "precision_at_5": table.to_dict(), "queries": len(queries),
           "per_query": r.to_dict("records")}, open(os.path.join(HERE, "results.json"), "w"), indent=1)
