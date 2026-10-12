import json, os, sys
sys.path.insert(0, os.getcwd())
import numpy as np, pandas as pd
from scipy import stats
from sklearn.metrics import classification_report, confusion_matrix
import train.evaluate as ev
from train.labels import LABELS
df = pd.read_csv("data/labeled/llm_rater/rules-2026-10-10/training_set.csv")
train = df[df.split == "train_dev"]
first = df[df.split == "test"][["sentence_id", "aspect", "text", "bank", "source", "label"]].assign(scope="first")
broker = pd.read_csv("data/labeled/sgx_research/resolved_test_blind.csv")[["sentence_id", "aspect", "text", "bank", "source", "label"]].assign(scope="broker")
test = pd.concat([first, broker], ignore_index=True)
SETS = [("people_1oct", "models/experiments-2026-10-01/label"), ("people_4oct", "models/experiments-2026-10-03/label"),
        ("people_7oct", "models/experiments-2026-10-07/finbert-combined"),
        ("opus_finbert", "models/experiments-2026-10-11/finbert"), ("opus_adapted", "models/experiments-2026-10-11/dapt")]
SCOPES = {"first": (test.scope == "first").values, "broker": (test.scope == "broker").values, "all": np.ones(len(test), bool)}
def metrics(y, pred):
    rep = classification_report(y, pred, labels=LABELS, output_dict=True, zero_division=0)
    r = {"accuracy": rep["accuracy"], "macro_f1": rep["macro avg"]["f1-score"]}
    for l in LABELS:
        r[l] = {"precision": rep[l]["precision"], "recall": rep[l]["recall"], "f1": rep[l]["f1-score"], "support": int(rep[l]["support"])}
    return r
lab = lambda p: [LABELS[i] for i in p.argmax(axis=1)]
from sentiment.score import classify_sentences
preds = {"base": np.array([l for l, _ in classify_sentences(test.text.tolist())])}
seedpreds = {}
for sid, root in SETS:
    ps = [ev.finetuned_probs(f"{root}/seed_{s}/final", test) for s in (42, 1, 7)]
    seedpreds[sid] = [np.array(lab(p)) for p in ps]
    preds[sid] = np.array(lab(sum(ps) / 3))
y_all = test.label.values
out = {"labels": LABELS, "scopes": {}, "paired": {}, "by_source": {}, "confusion": {}}
for sc, m in SCOPES.items():
    y = y_all[m]; o = {"n": int(m.sum()), "label_counts": {l: int((y == l).sum()) for l in LABELS}, "sets": {}}
    o["sets"]["base"] = {"single": metrics(y, preds["base"][m])}
    for sid, _ in SETS:
        seeds = [metrics(y, p[m]) for p in seedpreds[sid]]
        mean = {"accuracy": float(np.mean([s["accuracy"] for s in seeds])), "macro_f1": float(np.mean([s["macro_f1"] for s in seeds]))}
        for l in LABELS:
            mean[l] = {k: float(np.mean([s[l][k] for s in seeds])) for k in ("precision", "recall", "f1")}
        o["sets"][sid] = {"seeds": {"42": seeds[0], "1": seeds[1], "7": seeds[2]}, "mean": mean,
                          "sd_macro_f1": float(np.std([s["macro_f1"] for s in seeds], ddof=1)),
                          "sd_accuracy": float(np.std([s["accuracy"] for s in seeds], ddof=1)),
                          "averaged": metrics(y, preds[sid][m])}
    out["scopes"][sc] = o
    out["confusion"][sc] = {k: confusion_matrix(y, preds[k][m], labels=LABELS).tolist() for k in ("base", "people_4oct", "opus_finbert", "opus_adapted")}
    pr = {}
    for other in ("base", "people_4oct", "opus_finbert"):
        a = preds["opus_adapted"][m] == y; b = preds[other][m] == y
        only_a, only_b = int((a & ~b).sum()), int((~a & b).sum())
        p = float(stats.binomtest(only_a, only_a + only_b, 0.5).pvalue) if only_a + only_b else 1.0
        pr[other] = {"both_right": int((a & b).sum()), "only_adapted": only_a, "only_other": only_b, "both_wrong": int((~a & ~b).sum()), "mcnemar_exact_p": p}
    out["paired"][sc] = pr
src = test.source.values
for k in ("base", "people_4oct", "opus_finbert", "opus_adapted"):
    out["by_source"][k] = {s: {"accuracy": float((preds[k][src == s] == y_all[src == s]).mean()), "n": int((src == s).sum())} for s in pd.Series(src).value_counts().index}
cv = pd.DataFrame([json.loads(l) for l in open("data/eval/model-rerun-2026-10-11/cv_results.jsonl")]).pivot_table(index=["seed", "fold"], columns="base", values="dev_macro_f1")
d = cv["dapt"] - cv["finbert"]; t = stats.ttest_rel(cv["dapt"], cv["finbert"]); w = stats.wilcoxon(cv["dapt"], cv["finbert"])
ci = stats.t.interval(0.95, len(d) - 1, loc=d.mean(), scale=d.std(ddof=1) / np.sqrt(len(d)))
out["cv"] = {"folds": [{"seed": int(s), "fold": int(f), "finbert": float(r["finbert"]), "adapted": float(r["dapt"])} for (s, f), r in cv.iterrows()],
             "finbert_mean": float(cv["finbert"].mean()), "adapted_mean": float(cv["dapt"].mean()), "diff_mean": float(d.mean()), "diff_sd": float(d.std(ddof=1)),
             "better": int((d > 0).sum()), "n": int(len(d)), "t": float(t.statistic), "p": float(t.pvalue), "wilcoxon_p": float(w.pvalue), "ci": [float(ci[0]), float(ci[1])]}
out["train"] = {"rows": int(len(train)), "by_sheet": train.sheet.value_counts().to_dict(), "labels": train.label.value_counts().to_dict(), "by_source": train.source.value_counts().to_dict()}
out["pretraining"] = {k: v for k, v in json.load(open("data/eval/model-rerun-2026-10-11/pretraining_stats.json")).items() if not isinstance(v, (list, dict))}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print("ok", {sc: round(out["scopes"][sc]["sets"]["opus_adapted"]["mean"]["macro_f1"], 3) for sc in SCOPES}, out["paired"]["first"])
