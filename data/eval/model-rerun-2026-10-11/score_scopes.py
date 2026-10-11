"""Score the model sets on three test scopes: the first round's 299 rows, the broker research
round's 100 blind rows (annotator recorded on 11 Oct), and both together. Same measures as
score.py. Reads only.

  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 data/run/rerun-2026-10-11/score_scopes.py
"""
import json, os, sys
sys.path.insert(0, os.getcwd())
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import classification_report
import train.evaluate as ev
from train.labels import LABELS, near_test_copies

R = "data/run/rerun-2026-10-11"
df = pd.read_csv("data/labeled/llm_rater/rules-2026-10-10/training_set.csv")
train = df[df.split == "train_dev"]
first = df[df.split == "test"][["sentence_id", "aspect", "text", "bank", "source", "label"]].assign(scope="first round 299")
broker = pd.read_csv("data/labeled/sgx_research/resolved_test_blind.csv")[["sentence_id", "aspect", "text", "bank", "source", "label"]].assign(scope="broker research 100")
test = pd.concat([first, broker], ignore_index=True)
assert test.label.isin(LABELS).all() and not set(test.sentence_id) & set(train.sentence_id)
assert not near_test_copies(train.text.tolist(), test.text.tolist())
SETS = {
    "FinBERT fine-tuned on people's labels (4 Oct retrain)": "models/experiments-2026-10-03/label",
    "FinBERT fine-tuned on people's labels, broker rows included (7 Oct)": "models/experiments-2026-10-07/finbert-combined",
    "FinBERT fine-tuned on Opus's labels (11 Oct)": "models/experiments-2026-10-11/finbert",
    "Adapted encoder fine-tuned on Opus's labels (11 Oct)": "models/experiments-2026-10-11/dapt",
}
SCOPES = {"first round 299": test.scope == "first round 299", "broker research 100": test.scope == "broker research 100",
          "all 399": test.scope.notna()}


def metrics(y, pred):
    rep = classification_report(y, pred, labels=LABELS, output_dict=True, zero_division=0)
    row = {"accuracy": rep["accuracy"], "macro_f1": rep["macro avg"]["f1-score"]}
    for l in LABELS:
        row[f"{l}_precision"], row[f"{l}_recall"] = rep[l]["precision"], rep[l]["recall"]
    return row


def labels_of(p):
    return [LABELS[i] for i in p.argmax(axis=1)]


from sentiment.score import classify_sentences
base = [l for l, _ in classify_sentences(test.text.tolist())]
probs = {}
for name, root in SETS.items():
    dirs = [f"{root}/seed_{s}/final" for s in (42, 1, 7)]
    if all(os.path.isdir(d) for d in dirs):
        probs[name] = [ev.finetuned_probs(d, test) for d in dirs]
out = {}
lines = []
for scope, mask in SCOPES.items():
    m = mask.values
    y = test.label[m].tolist()
    lines += ["", f"### {scope} ({dict(pd.Series(y).value_counts())})", "",
              "| model | accuracy | macro-F1 | negative P / R | neutral P / R | positive P / R |", "|---|---|---|---|---|---|"]
    fmt = lambda r: f"{r['accuracy']:.3f} | {r['macro_f1']:.3f} | " + " | ".join(f"{r[l + '_precision']:.2f} / {r[l + '_recall']:.2f}" for l in LABELS)
    b = metrics(y, [x for x, k in zip(base, m) if k]); out[f"{scope} | base"] = b
    lines.append(f"| Base FinBERT, no fine-tuning | {fmt(b)} |")
    for name, ps in probs.items():
        seeds = [metrics(y, labels_of(p[m])) for p in ps]
        mean = {k: float(np.mean([s[k] for s in seeds])) for k in seeds[0]}
        sd = float(np.std([s["macro_f1"] for s in seeds], ddof=1))
        avg = metrics(y, labels_of(sum(ps)[m] / 3))
        out[f"{scope} | {name}"] = {"per_seed_macro_f1": [s["macro_f1"] for s in seeds], "mean": mean, "sd_macro_f1": sd, "three_averaged": avg}
        lines.append(f"| {name}: mean of three seeds (macro-F1 sd {sd:.3f}) | {fmt(mean)} |")
        lines.append(f"| {name}: the three averaged | {fmt(avg)} |")
    # accuracy by source for the two new sets, the three averaged
    if scope == "all 399":
        for name in list(probs)[-2:]:
            pred = labels_of(sum(probs[name]) / 3)
            g = pd.DataFrame({"ok": [a == b for a, b in zip(test.label, pred)], "source": test.source}).groupby("source").ok.agg(["mean", "size"])
            lines += ["", f"Accuracy by source, {name}, the three averaged: " + ", ".join(f"{s} {r['mean']:.2f} (n={int(r['size'])})" for s, r in g.sort_values('size', ascending=False).iterrows())]

cv = pd.DataFrame([json.loads(l) for l in open(f"{R}/cv_results.jsonl")]).pivot_table(index=["seed", "fold"], columns="base", values="dev_macro_f1")
d = cv["dapt"] - cv["finbert"]
t = stats.ttest_rel(cv["dapt"], cv["finbert"]); w = stats.wilcoxon(cv["dapt"], cv["finbert"])
ci = stats.t.interval(0.95, len(d) - 1, loc=d.mean(), scale=d.std(ddof=1) / np.sqrt(len(d)))
lines += ["", "### Cross-validation, adapted encoder against FinBERT (15 paired folds, dev macro-F1 against Opus's labels)", "",
          f"FinBERT {cv['finbert'].mean():.3f}, adapted {cv['dapt'].mean():.3f}; difference {d.mean():+.3f} (sd {d.std(ddof=1):.3f}), "
          f"better in {(d > 0).sum()} of {len(d)}; paired t = {t.statistic:.2f}, p = {t.pvalue:.3f}; Wilcoxon p = {w.pvalue:.3f}; "
          f"95% interval {ci[0]:+.3f} to {ci[1]:+.3f}.",
          "By seed: " + "; ".join(f"seed {s}: {g['finbert'].mean():.3f} against {g['dapt'].mean():.3f}" for s, g in cv.groupby("seed"))]
json.dump(out, open(f"{R}/test_results_scopes.json", "w"), indent=1)
open(f"{R}/results_scopes.md", "w").write("\n".join(lines).strip() + "\n")
print("\n".join(lines))
