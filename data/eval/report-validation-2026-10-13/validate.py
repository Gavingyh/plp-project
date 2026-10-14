"""Recompute the figures of docs/report/report.html from primary data (the
database, the label files, the models' stored test results, the chatbot
transcripts) and compare each with the value the report gives. Reads only.

  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 data/eval/report-validation-2026-10-13/validate.py
"""
import json, os, re, sqlite3, statistics, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
import pandas as pd
from scipy import stats
from sklearn.metrics import cohen_kappa_score

ROWS = []
def check(section, what, report, got, tol=0.0005, source=""):
    ok = (report == got) if isinstance(report, (str, tuple, list)) or isinstance(got, str) else abs(float(report) - float(got)) <= tol
    ROWS.append((section, what, report, got, "ok" if ok else "DIFFERS", source))

V = "finbert-adapted-finetuned-2026-10-11-3seed-m0"; B = "finbert-base-zeroshot-v1"
c = sqlite3.connect("file:data/plp.db?mode=ro", uri=True)
q = lambda sql, *p: c.execute(sql, p).fetchall()

# ---- 2.1 corpus
src = "data/plp.db"
check("2.1", "documents", 28852, q("SELECT COUNT(*) FROM documents")[0][0], source=src)
n_sent = q("SELECT COUNT(*) FROM sentences")[0][0]
check("2.1", "sentences", 45844, n_sent, source=src)
check("2.1", "first and last date", ("2020-01-06", "2026-09-25"), q("SELECT MIN(substr(published_at,1,10)), MAX(substr(published_at,1,10)) FROM sentences")[0], source=src)
docs = dict(q("SELECT source, COUNT(*) FROM documents GROUP BY 1")); sents = dict(q("SELECT source, COUNT(*) FROM sentences GROUP BY 1"))
for s, (d, n) in {"arctic_shift": (22630, 25533), "earnings": (178, 12254), "google_news": (5685, 5447), "cna": (207, 1599),
                  "sgx_research": (25, 641), "yahoo_news": (114, 344), "newsapi": (13, 26)}.items():
    check("Table 1", f"{s} documents / sentences", (d, n), (docs[s], sents[s]), source=src)
bank = dict(q("SELECT bank, COUNT(*) FROM sentences GROUP BY 1"))
check("2.1", "sentences DBS / UOB / OCBC", (24978, 13092, 7774), (bank["DBS"], bank["UOB"], bank["OCBC"]), source=src)
earn = dict(q("SELECT bank, COUNT(*) FROM sentences WHERE source='earnings' GROUP BY 1"))
check("2.1", "earnings sentences DBS / OCBC / UOB", (9093, 1561, 1600), (earn["DBS"], earn["OCBC"], earn["UOB"]), source=src)
check("2.1", "Reddit share of sentences, %", 56, round(100 * sents["arctic_shift"] / n_sent), source=src)
check("2.1", "earnings share of sentences, %", 27, round(100 * sents["earnings"] / n_sent), source=src)
check("2.1", "late additions: Reddit documents, broker reports", (825, 25),
      (q("SELECT COUNT(*) FROM documents WHERE source='arctic_shift' AND ingested_at > '2026-09-27'")[0][0], docs["sgx_research"]), source=src)
red = dict(q("SELECT bank, COUNT(*) FROM sentences WHERE source='arctic_shift' GROUP BY 1"))
check("4.4", "Reddit share of UOB's / DBS's sentences, %", (72, 49), (round(100 * red["UOB"] / bank["UOB"]), round(100 * red["DBS"] / bank["DBS"])), source=src)

# ---- 2.2 labels
L = "data/labeled/llm_rater/rules-2026-10-10/"
r = pd.read_csv(L + "rater_labels.csv")
check("2.2", "labelled sentences", 2075, len(r), source=L + "rater_labels.csv")
check("Table 2", "first round / top-up / active / broker", (1277, 268, 150, 380), tuple(int((r.sheet == s).sum()) for s in ("first_round", "topup", "active", "broker_research")), source=L + "rater_labels.csv")
vc = r.rater_label.value_counts()
check("2.2", "LLM labels positive / neutral / negative", (757, 879, 439), (int(vc["positive"]), int(vc["neutral"]), int(vc["negative"])), source=L + "rater_labels.csv")
check("2.2", "flagged as not about the bank", 134, int(r.rater_not_about_bank.astype(str).str.lower().eq("true").sum()), source=L + "rater_labels.csv")
ts = pd.read_csv(L + "training_set.csv"); tr = ts[ts.split == "train_dev"]; te = ts[ts.split == "test"]
check("2.2", "training rows", 1563, len(tr), source=L + "training_set.csv")
check("2.2", "training positive / neutral / negative", (616, 586, 361), tuple(int((tr.label == x).sum()) for x in ("positive", "neutral", "negative")), source=L + "training_set.csv")
check("2.2", "first-round test neutral / positive / negative", (166, 94, 39), tuple(int((te.label == x).sum()) for x in ("neutral", "positive", "negative")), source=L + "training_set.csv")
bt = pd.read_csv("data/labeled/sgx_research/test_blind.csv", keep_default_na=False)
check("2.2", "broker test positive / neutral / negative", (42, 35, 23), tuple(int((bt.label == x).sum()) for x in ("positive", "neutral", "negative")), source="data/labeled/sgx_research/test_blind.csv")
cand = pd.read_csv("data/labeled/candidates.csv", keep_default_na=False)
check("Table 2", "first round train / test", (978, 299), (int((cand.split == "train_dev").sum()), int((cand.split == "test").sum())), source="data/labeled/candidates.csv")
m = cand.merge(r[r.sheet == "first_round"], on="sentence_id")
check("2.2", "LLM rater against people, aspect kappa", 0.80, round(cohen_kappa_score(m.aspect, m.rater_aspect), 2), tol=0.005, source="candidates.csv x rater_labels.csv")
check("2.2", "LLM rater against people, sentiment kappa", 0.79, round(cohen_kappa_score(m.label, m.rater_label), 2), tol=0.005, source="candidates.csv x rater_labels.csv")
check("Table 5", "LLM rater right aspect, %", 84.2, round(100 * (m.aspect == m.rater_aspect).mean(), 1), tol=0.05, source="candidates.csv x rater_labels.csv")
check("2.2", "first-round labels matching the shown suggestion, %", 91.6, round(100 * (cand.label == cand.llm_prelabel).mean(), 1), tol=0.05, source="data/labeled/candidates.csv")

# ---- 3.5 / 4.1 the models
R = "data/eval/model-rerun-2026-10-11/"
d = json.load(open(R + "report_data.json"))
pre = d["pretraining"]
check("3.5", "pretraining sentences kept; epochs", (42822, 3), (pre["kept"], pre["epochs"]), source=R + "report_data.json")
check("3.5", "left out: labelled / same text / containing / sharing words", (2270, 37, 147, 568),
      (pre["dropped_labelled_id"], pre["dropped_matching_labelled_text"], pre["dropped_holding_or_held_in_labelled_text"], pre["dropped_sharing_most_words_with_labelled_text"]), source=R + "report_data.json")
cv = d["cv"]
check("4.1", "cross-validation lead; folds better; p", (0.014, 11, 0.016), (round(cv["diff_mean"], 3), cv["better"], round(cv["p"], 3)), source=R + "report_data.json")
folds = [json.loads(l) for l in open(R + "cv_results.jsonl") if l.strip()]
piv = pd.DataFrame(folds).pivot_table(index=["seed", "fold"], columns="base", values="dev_macro_f1")
diff = piv["dapt"] - piv["finbert"]
check("4.1", "the same, recomputed from the 30 fold results", (0.014, 11, 0.016), (round(diff.mean(), 3), int((diff > 0).sum()), round(stats.ttest_rel(piv["dapt"], piv["finbert"]).pvalue, 3)), source=R + "cv_results.jsonl")
w = pd.DataFrame([json.loads(l) for l in open(R + "cv_weighting.jsonl") if l.strip()])
wd = {v: round((g.set_index(["seed", "fold"]).dev_macro_f1 - piv["dapt"]).mean(), 3) for v, g in w.groupby("variant")}
check("4.1", "weighting variants against the chosen model, lowest and highest", (-0.004, -0.002), (min(wd.values()), max(wd.values())), source=R + "cv_weighting.jsonl")
mg = json.load(open(R + "margin_adapted.json"))
best = max(mg["dev_curve"], key=mg["dev_curve"].get)
check("3.5", "held-out rows; threshold chosen", (601, 0.0), (mg["dev_rows"], float(best)), source=R + "margin_adapted.json")
print("model sets in report_data.json:", {k: list(v["sets"].keys()) for k, v in d["scopes"].items()})
print("one entry:", json.dumps(d["scopes"]["first"]["sets"][list(d["scopes"]["first"]["sets"])[0]])[:900])
bs = d["by_source"]["opus_adapted"]
check("Table 4 note", "accuracy earnings / broker / Reddit / Google News, %", (81, 77, 68, 68), tuple(round(100 * bs[s]["accuracy"]) for s in ("earnings", "sgx_research", "arctic_shift", "google_news")), source=R + "report_data.json")
check("Table 4 note", "rows earnings / broker / Reddit / Google News", (79, 100, 184, 34), tuple(bs[s]["n"] for s in ("earnings", "sgx_research", "arctic_shift", "google_news")), source=R + "report_data.json")

json.dump({"rows": ROWS}, open(os.path.join(os.path.dirname(__file__), "part1.json"), "w"), default=str)
for row in ROWS:
    if row[4] != "ok": print("DIFFERS:", row)
print(len(ROWS), "checks so far;", sum(r[4] == "ok" for r in ROWS), "ok")

# ======================= part 2 =======================
import numpy as np
from sklearn.metrics import classification_report
import train.evaluate as ev
import sentiment.score as sc
from train.labels import LABELS
ev.best_device = lambda: "cpu"; sc.best_device = lambda: "cpu"

def metrics(y, pred):
    rep = classification_report(y, pred, labels=LABELS, output_dict=True, zero_division=0)
    return {"accuracy": rep["accuracy"], "macro_f1": rep["macro avg"]["f1-score"], **{l: (rep[l]["precision"], rep[l]["recall"]) for l in LABELS}}

first = te[["sentence_id", "aspect", "text", "bank", "source", "label"]].assign(scope="first")
broker = pd.read_csv("data/labeled/sgx_research/resolved_test_blind.csv")[["sentence_id", "aspect", "text", "bank", "source", "label"]].assign(scope="broker")
test = pd.concat([first, broker], ignore_index=True)
y = test.label.values
base_pred = np.array([l for l, _ in sc.classify_sentences(test.text.tolist())])
probs = [ev.finetuned_probs(f"models/experiments-2026-10-11/dapt/seed_{s}/final", test) for s in (42, 1, 7)]
seed_pred = [np.array([LABELS[i] for i in p.argmax(axis=1)]) for p in probs]
avg_pred = np.array([LABELS[i] for i in (sum(probs) / 3).argmax(axis=1)])
live = "models re-scored on the test sentences"
def row(name, rep, pred, mask):
    mt = metrics(y[mask], pred[mask])
    got = (round(mt["accuracy"], 3), round(mt["macro_f1"], 3)) + tuple(round(x, 2) for l in ("negative", "neutral", "positive") for x in mt[l])
    check("Table 3" if len(rep) > 2 else "Table 4", name, rep, got[:len(rep)], source=live)
F = (test.scope == "first").values; Bk = (test.scope == "broker").values; A = np.ones(len(test), bool)
row("FinBERT, no fine-tuning: accuracy, macro-F1, P/R negative, neutral, positive", (0.699, 0.571, 0.53, 0.21, 0.68, 0.91, 0.79, 0.53), base_pred, F)
row("model in use (three averaged): the same", (0.716, 0.670, 0.48, 0.59, 0.81, 0.73, 0.69, 0.73), avg_pred, F)
ms = [metrics(y[F], p[F]) for p in seed_pred]
check("Table 3", "adapted encoder, mean of 3 seeds: accuracy, macro-F1, sd", (0.689, 0.649, 0.018),
      (round(np.mean([m["accuracy"] for m in ms]), 3), round(np.mean([m["macro_f1"] for m in ms]), 3), round(np.std([m["macro_f1"] for m in ms], ddof=1), 3)), source=live)
check("Table 3", "the same: mean P/R negative, neutral, positive", (0.48, 0.61, 0.77, 0.71, 0.67, 0.68),
      tuple(round(float(np.mean([m[l][i] for m in ms])), 2) for l in ("negative", "neutral", "positive") for i in (0, 1)), source=live)
for name, mask, rep_base, rep_model in (("first round", F, 0.571, (0.670, 0.716)), ("broker research", Bk, 0.687, (0.770, 0.770)), ("both", A, 0.648, (0.709, 0.729))):
    check("Table 4", f"{name}: FinBERT macro-F1", rep_base, round(metrics(y[mask], base_pred[mask])["macro_f1"], 3), source=live)
    mm = metrics(y[mask], avg_pred[mask]); check("Table 4", f"{name}: model in use macro-F1, accuracy", rep_model, (round(mm["macro_f1"], 3), round(mm["accuracy"], 3)), source=live)
S = d["scopes"]["first"]["sets"]
def stored(k):
    m = S[k]["mean"]; return (round(m["accuracy"], 3), round(m["macro_f1"], 3), round(S[k]["sd_macro_f1"], 3)) + tuple(round(m[l][x], 2) for l in ("negative", "neutral", "positive") for x in ("precision", "recall"))
check("Table 3", "fine-tuned on people's labels, mean of 3: accuracy, macro-F1, sd, P/R", (0.693, 0.621, 0.027, 0.51, 0.41, 0.73, 0.81, 0.70, 0.61), stored("people_4oct"), source=R + "report_data.json")
check("Table 3", "fine-tuned on LLM labels, mean of 3: the same", (0.682, 0.631, 0.020, 0.49, 0.49, 0.77, 0.72, 0.62, 0.70), stored("opus_finbert"), source=R + "report_data.json")
check("4.1", "steps: fine-tuning, LLM labels, pretraining, averaging", (0.050, 0.010, 0.018, 0.021),
      (round(0.621 - 0.571, 3), round(0.631 - 0.621, 3), round(0.649 - 0.631, 3), round(0.670 - 0.649, 3)), source="Table 3")

# ---- 4.4 the index
src = "data/plp.db"
def head(v, w="all_time"):
    return {b: (round(s, 3), n, round(100 * p / n), round(100 * u / n), round(100 * g / n)) for b, s, n, p, u, g in q(
        "SELECT bank, score, n, pos_n, neu_n, neg_n FROM sentiment_index WHERE aspect='ALL' AND source='ALL' AND window=? AND model_version=?", w, v)}
hb, hv = head(B), head(V)
for b, rb, rv in (("DBS", (0.122, 24978, 22, 67, 10), (0.155, 24978, 33, 51, 16)), ("OCBC", (0.136, 7774, 23, 67, 11), (0.143, 7774, 32, 50, 18)), ("UOB", (0.074, 13092, 15, 76, 9), (0.117, 13092, 30, 53, 17))):
    check("Table 6", f"{b} FinBERT: score, sentences, % pos/neu/neg", rb, hb[b], source=src); check("Table 6", f"{b} model in use: the same", rv, hv[b], source=src)
for w, rep in (("30d", {"DBS": (0.054, 371), "OCBC": (0.281, 115), "UOB": (0.196, 136)}), ("7d", {"DBS": (0.171, 90), "OCBC": (0.151, 42), "UOB": (0.309, 60)})):
    h = head(V, w); check("Table 6 note", f"{w} DBS, OCBC, UOB: score, sentences", tuple(rep[b] for b in ("DBS", "OCBC", "UOB")), tuple(h[b][:2] for b in ("DBS", "OCBC", "UOB")), source=src)
lab = q("""SELECT b.label, n.label, COUNT(*) FROM aspect_sentiment b JOIN aspect_sentiment n USING (sentence_id, aspect)
           WHERE b.model_version=? AND n.model_version=? GROUP BY 1,2""", B, V)
changed = sum(k for a, b_, k in lab if a != b_); from_neu = sum(k for a, b_, k in lab if a == "neutral" and b_ != "neutral")
check("4.4", "labels changed; of them from neutral; % changed", (13154, 10219, 29), (changed, from_neu, round(100 * changed / n_sent)), source=src)
def bysrc(v, s):
    return {b: (round(sc_, 3), round(100 * u / n)) for b, sc_, n, u in q("SELECT bank, score, n, neu_n FROM sentiment_index WHERE aspect='ALL' AND window='all_time' AND source=? AND model_version=?", s, v)}
rb, rv = bysrc(B, "arctic_shift"), bysrc(V, "arctic_shift")
check("4.4", "Reddit neutral %, FinBERT (lowest, highest)", (88, 89), (min(x[1] for x in rb.values()), max(x[1] for x in rb.values())), source=src)
check("4.4", "Reddit neutral %, model in use (lowest, highest)", (57, 58), (min(x[1] for x in rv.values()), max(x[1] for x in rv.values())), source=src)
check("4.4", "Reddit score, model in use (lowest, highest)", (0.00, 0.07), (round(min(x[0] for x in rv.values()), 2), round(max(x[0] for x in rv.values()), 2)), tol=0.005, source=src)
eb, evv = bysrc(B, "earnings"), bysrc(V, "earnings")
check("4.4", "earnings DBS, OCBC, UOB: FinBERT to model in use", ((0.286, 0.287), (0.375, 0.344), (0.406, 0.335)), tuple((eb[b][0], evv[b][0]) for b in ("DBS", "OCBC", "UOB")), source=src)
check("4.4", "earnings score, model in use (lowest, highest)", (0.29, 0.34), (round(min(x[0] for x in evv.values()), 2), round(max(x[0] for x in evv.values()), 2)), tol=0.005, source=src)
cb, cv_ = bysrc(B, "cna"), bysrc(V, "cna")
falls = [round(cb[b][0] - cv_[b][0], 2) for b in ("DBS", "OCBC", "UOB")]
check("4.4", "CNA fall (smallest, largest); all below zero after", (0.14, 0.18, True), (min(falls), max(falls), all(cv_[b][0] < 0 for b in cv_)), source=src)
asp = {(b, a): (round(s, 3), n) for b, a, s, n in q("SELECT bank, aspect, score, n FROM sentiment_index WHERE window='all_time' AND source='ALL' AND model_version=?", V)}
T7 = {"retail_banking_sentiment": ((-0.046, 8747), (-0.060, 3288), (0.040, 7649)), "wealth_business": ((0.489, 2154), (0.476, 913), (0.368, 1292)),
      "dividend_policy": ((0.452, 456), (0.446, 136), (0.350, 71)), "income_profit_results": ((0.390, 2257), (0.447, 744), (0.255, 671)),
      "net_interest_margin": ((0.150, 1047), (-0.034, 170), (-0.033, 190))}
for a, rep in T7.items():
    check("Table 7", f"{a}: DBS, OCBC, UOB score and sentences", rep, tuple(asp[(b, a)] for b in ("DBS", "OCBC", "UOB")), source=src)
n_retail = q("SELECT COUNT(*) FROM sentence_aspects WHERE aspect='retail_banking_sentiment'")[0][0]
check("4.4", "retail banking share of sentences, %", 43, round(100 * n_retail / n_sent), source=src)
check("3.3", "aspects per sentence under similarity matching", 6.4, round(291508 / 45844, 1), tol=0.05, source="README snapshot table (291,508 pairs)")

# ---- 4.2 aspects
ans = pd.read_csv("data/eval/wealth-definition-trial-2026-10-12/answers.csv")
o, nw = ans.old == ans.rater_aspect, ans.new == ans.rater_aspect
check("4.2 box", "agreement old, new wording, %", (75.5, 79.4), (round(100 * o.mean(), 1), round(100 * nw.mean(), 1)), source="wealth trial answers.csv")
check("4.2 box", "newly right, newly wrong", (148, 67), (int((~o & nw).sum()), int((o & ~nw).sum())), source="wealth trial answers.csv")
def pr(col):
    called = (ans[col] == "wealth_business"); right = called & (ans.rater_aspect == "wealth_business"); ref = (ans.rater_aspect == "wealth_business").sum()
    return (int(called.sum()), int(right.sum()), round(right.sum() / called.sum(), 2), round(right.sum() / ref, 2))
check("4.2", "wealth, old wording: called, right, precision, recall", (176, 63, 0.36, 0.76), pr("old"), source="wealth trial answers.csv")
check("4.2 box", "wealth, new wording: precision, recall", (0.70, 0.46), pr("new")[2:], source="wealth trial answers.csv")
import aspects.llm_classify as llm
cache = {}
for line in open("data/aspect_llm/llama3.1_8b.96efe244.jsonl"):   # the wording Table 5 measured
    x = json.loads(line); cache[x["sentence_id"]] = x["aspect"]
pred = cand.sentence_id.map(cache)
e = llm.evaluate(pred.tolist(), cand.aspect.tolist())
check("Table 5", "llama3.1:8b: right aspect %, macro-F1", (72.9, 0.679), (round(100 * e["top1_accuracy"], 1), round(e["macro_f1"], 3)), source="answer cache x candidates.csv")
common = cand.aspect.value_counts()
check("Table 5", "always the commonest aspect, %", 37.4, round(100 * common.iloc[0] / len(cand), 1), tol=0.05, source="data/labeled/candidates.csv")
from sklearn.metrics import f1_score
r1 = cand.merge(pd.read_csv("data/labeled/llm_rater/rater_labels.csv", keep_default_na=False), on="sentence_id")
check("Table 5", "LLM rater, first run: right aspect %, macro-F1", (84.2, 0.789), (round(100 * (r1.aspect == r1.rater_aspect).mean(), 1), round(f1_score(r1.aspect, r1.rater_aspect, average="macro"), 3)), source="candidates.csv x llm_rater/rater_labels.csv")
qc = {}
for line in open("data/aspect_llm/qwen3_4b-nothink.96efe244.jsonl"):
    x = json.loads(line); qc[x["sentence_id"]] = x["aspect"]
if cand.sentence_id.isin(qc).all():
    eq = llm.evaluate(cand.sentence_id.map(qc).tolist(), cand.aspect.tolist())
    check("Table 5", "qwen3:4b: right aspect %, macro-F1", (71.9, 0.671), (round(100 * eq["top1_accuracy"], 1), round(eq["macro_f1"], 3)), source="answer cache x candidates.csv")
else:
    print("qwen cache does not cover every labelled sentence:", int(cand.sentence_id.isin(qc).sum()))

# ---- 4.3 bank recognition
diffc = pd.read_csv("data/preview/ner_corpus_diff.csv", keep_default_na=False)
check("4.3", "corpus sentences where the two methods differ", 258, len(diffc), source="preprocess.bank_ner corpus-diff")
check("4.3", "of them: alias matching UOB, recogniser no bank", 145, int(((diffc.alias == "UOB") & (diffc.ner == "")).sum()), source="preprocess.bank_ner corpus-diff")

# ---- 4.5 chatbot
res = [json.loads(l) for l in open("data/eval/chatbot_eval_results_rescored_v2.jsonl")]
ts_ = [x["tool_selection_check"] for x in res if x.get("tool_selection_check") and x["tool_selection_check"].get("applicable")]
bh = [x["behavior_check"] for x in res if x.get("behavior_check") and x["behavior_check"].get("applicable")]
check("Table 8", "right tool chosen", (23, 24), (sum(1 for t in ts_ if t["correct"]), len(ts_)), source="chatbot_eval_results_rescored_v2.jsonl")
check("Table 8", "advice declined, missing data admitted", (8, 8), (sum(1 for t in bh if t["correct"]), len(bh)), source="chatbot_eval_results_rescored_v2.jsonl")
check("Table 8", "answers; citing unreturned evidence; with an unreturned figure", (32, 0, 1), (len(res), sum(bool(x.get("citation_fabricated")) for x in res), sum(bool(x.get("unverified_numbers")) for x in res)), source="chatbot_eval_results_rescored_v2.jsonl")
tm = [json.loads(l)["seconds"] for l in open("data/run/eval-2026-10-13/times_rescored_v2.jsonl") if l.strip()]
check("Table 8", "median seconds per answer", 59, round(statistics.median(tm)), source="times_rescored_v2.jsonl")
mt = [json.loads(l) for l in open("data/eval/chatbot_multiturn_results_rescored_mt.jsonl")]
print("multi-turn record keys:", list(mt[0].keys())[:12])
rl = open("data/run/eval-2026-10-13/retrieval_eval.log").read()
g = lambda name: [float(x) for x in re.search(r"^" + re.escape(name) + r"\s+([\d. ]+)$", rl, flags=re.M).group(1).split()]
check("4.5", "evidence precision at 5: by aspect name, random, by the question (all with the filter)", (0.78, 0.72, 0.69),
      (round(g("label + stored-aspect filter")[3], 2), round(g("label + stored-aspect filter (random)")[3], 2), round(g("question + stored-aspect filter")[3], 2)), tol=0.005, source="retrieval_eval.log")
check("4.5", "retrieval queries", 28, int(re.search(r"(\d+) \(bank, aspect\) queries", rl).group(1)), source="retrieval_eval.log")

# ======================= part 3: older runs and remaining figures =======================
import subprocess
out = subprocess.run([sys.executable, "-m", "train.rater_labels", "extra", "score", "ner"], capture_output=True, text=True).stdout
ner = {mth: (float(e), float(f), int(n)) for mth, e, f, n in re.findall(r"^\s*ALL\s+(alias matching|NER)\s+[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s*$", out, flags=re.M)}
ner = {k: (round(v[1] * v[2]), v[2], round(v[0], 3)) for k, v in ner.items()}     # exact count, sheet size, F1
check("4.3", "recogniser: right of 201, F1", (201, 201, 1.0), ner.get("NER"), source="train.rater_labels extra score ner")
check("4.3", "alias matching: right of 201, F1", (161, 201, 0.89), ner.get("alias matching"), source="train.rater_labels extra score ner")
ca, cb = (pd.read_csv(f"data/labeled/agreement/candidates_coder_{x}.csv", keep_default_na=False).drop_duplicates(["sentence_id", "aspect"]) for x in "ab")
j = ca.merge(cb, on=["sentence_id", "aspect"], suffixes=("_a", "_b"))
check("2.2", "two annotators: rows compared, sentiment kappa", (1277, 0.93), (len(j), round(cohen_kappa_score(j.label_a, j.label_b), 2)), source="data/labeled/agreement/")
sg = pd.read_csv("data/labeled/sgx_research/candidates.csv", keep_default_na=False); sg = sg[sg.split == "train_dev"]; sg = sg[sg.label != ""]
check("2.2", "broker training rows; % keeping the suggested sentiment", (280, 94), (len(sg), round(100 * (sg.label == sg.llm_prelabel).mean())), source="data/labeled/sgx_research/candidates.csv")
def summ(tag):
    t = open(f"data/eval/chatbot_eval_summary_{tag}.md").read()
    g1 = lambda pat: tuple(int(x) for x in re.search(pat, t).groups())
    return g1(r"Tool selection: (\d+)/(\d+)"), g1(r"Behavior[^:]*: (\d+)/(\d+)"), g1(r"Citation fabrication flagged: (\d+)/(\d+)"), g1(r"figure no tool returned: (\d+)/(\d+)")
check("Table 8", "before the code checks: tool, behaviour, citing unreturned evidence", ((20, 24), (8, 8), (11, 32)), summ("llama8b_v2_idle")[:3], source="chatbot_eval_summary_llama8b_v2_idle.md")
check("Table 8", "after them, earlier database: tool, behaviour, citations, figures", ((23, 24), (8, 8), (0, 32), (0, 32)), summ("final3_v2"), source="chatbot_eval_summary_final3_v2.md")
check("Table 8", "re-scored database, from its summary: the same", ((23, 24), (8, 8), (0, 32), (1, 32)), summ("rescored_v2"), source="chatbot_eval_summary_rescored_v2.md")
for tag, rep in (("final3_mt", (9, 9, 4, 4)), ("rescored_mt", (9, 9, 4, 4))):
    t = open(f"data/eval/chatbot_multiturn_summary_{tag}.md").read()
    check("Table 8", f"conversation turns and conversations correct ({tag})", rep, tuple(int(x) for x in re.search(r"Turns correct: (\d+)/(\d+); conversations with every turn correct: (\d+)/(\d+)", t).groups()), source=f"chatbot_multiturn_summary_{tag}.md")
t0 = [json.loads(l)["seconds"] for l in open("data/run/overnight/times_final3_v2.jsonl") if l.strip()]
check("Table 8", "median seconds per answer, earlier database", 47, round(statistics.median(t0)), source="data/run/overnight/times_final3_v2.jsonl")
try:
    human_train = cand[cand.split == "train_dev"]; t299 = te
    lx = ev.eval_lexicon(t299.copy()); tf = ev.eval_tfidf_logreg(human_train.copy(), t299.copy())
    check("Table 3", "VADER: macro-F1", 0.427, round(lx["macro_f1"], 3), source="train.evaluate.eval_lexicon (its printed accuracy: 0.49)")
    check("Table 3", "TF-IDF with logistic regression: macro-F1", 0.515, round(tf["macro_f1"], 3), source="train.evaluate.eval_tfidf_logreg, people's labels (its printed accuracy: 0.57)")
except Exception as ex:
    print("baselines not recomputed:", repr(ex)[:300])

json.dump({"rows": ROWS}, open(os.path.join(os.path.dirname(__file__), "checks.json"), "w"), default=str, indent=1)
print("\nDIFFERENCES:")
for row_ in ROWS:
    if row_[4] != "ok": print("  ", row_[:4])
print(len(ROWS), "checks;", sum(r_[4] == "ok" for r_ in ROWS), "ok")
