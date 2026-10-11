"""Score every model set on the test rows of the re-run's label file: accuracy, macro-F1, and
precision and recall for negative, neutral and positive. Per seed, the seeds' mean and sd, and the
three models averaged (mean probabilities, then the most likely class). Model sets that are missing
are skipped and named.

  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 data/run/rerun-2026-10-11/score.py [--cpu]
"""
import json, os, sys
sys.path.insert(0, os.getcwd())
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report
import train.evaluate as ev
from train.labels import LABELS

R = "data/run/rerun-2026-10-11"
LABEL_FILE = "data/labeled/llm_rater/rules-2026-10-10/training_set.csv"
if "--cpu" in sys.argv:
    ev.best_device = lambda: "cpu"
df = pd.read_csv(LABEL_FILE)
ev.check_splits(df)
test = df[(df.split == "test") & df.label.isin(LABELS)].reset_index(drop=True)
train = df[(df.split == "train_dev") & df.label.isin(LABELS)]
y = test.label.tolist()
SETS = {
    "FinBERT fine-tuned on people's labels (1 Oct)": "models/experiments-2026-10-01/label",
    "FinBERT fine-tuned on people's labels (4 Oct retrain)": "models/experiments-2026-10-03/label",
    "FinBERT fine-tuned on Opus's labels (11 Oct)": "models/experiments-2026-10-11/finbert",
    "Adapted encoder fine-tuned on Opus's labels (11 Oct)": "models/experiments-2026-10-11/dapt",
}


def metrics(pred):
    rep = classification_report(y, pred, labels=LABELS, output_dict=True, zero_division=0)
    row = {"accuracy": rep["accuracy"], "macro_f1": rep["macro avg"]["f1-score"]}
    for l in LABELS:
        row[f"{l}_precision"], row[f"{l}_recall"], row[f"{l}_f1"] = rep[l]["precision"], rep[l]["recall"], rep[l]["f1-score"]
    return row


def labels_of(probs):
    return [LABELS[i] for i in probs.argmax(axis=1)]


out = {"test_rows": len(test), "train_rows": len(train), "test_label_counts": test.label.value_counts().to_dict(), "rows": {}}
from sentiment.score import classify_sentences
out["rows"]["Base FinBERT, no fine-tuning"] = metrics([l for l, _ in classify_sentences(test.text.tolist())])
for name, root in SETS.items():
    dirs = [f"{root}/seed_{s}/final" for s in (42, 1, 7)]
    if not all(os.path.isdir(d) for d in dirs):
        out["rows"][name] = {"missing": [d for d in dirs if not os.path.isdir(d)]}
        continue
    probs = [ev.finetuned_probs(d, test) for d in dirs]
    seeds = [metrics(labels_of(p)) for p in probs]
    row = {"per_seed": dict(zip(("42", "1", "7"), seeds)),
           "mean": {k: float(np.mean([s[k] for s in seeds])) for k in seeds[0]},
           "sd": {k: float(np.std([s[k] for s in seeds], ddof=1)) for k in seeds[0]},
           "three_averaged": metrics(labels_of(sum(probs) / 3))}
    out["rows"][name] = row
json.dump(out, open(f"{R}/test_results.json", "w"), indent=1)

cv = [json.loads(l) for l in open(f"{R}/cv_results.jsonl")] if os.path.exists(f"{R}/cv_results.jsonl") else []
cv = pd.DataFrame([c for c in cv if c.get("dev_macro_f1") is not None])
lines = [f"Test rows: {len(test)} ({out['test_label_counts']}). Training rows: {len(train)}.", "",
         "| model | accuracy | macro-F1 | negative P / R | neutral P / R | positive P / R |", "|---|---|---|---|---|---|"]
def fmt(m): return (f"{m['accuracy']:.3f} | {m['macro_f1']:.3f} | " + " | ".join(f"{m[l + '_precision']:.2f} / {m[l + '_recall']:.2f}" for l in LABELS))
for name, row in out["rows"].items():
    if "missing" in row:
        lines.append(f"| {name} | not found | | | | |")
    elif "mean" in row:
        lines.append(f"| {name}: mean of three seeds (macro-F1 sd {row['sd']['macro_f1']:.3f}) | {fmt(row['mean'])} |")
        lines.append(f"| {name}: the three averaged | {fmt(row['three_averaged'])} |")
    else:
        lines.append(f"| {name} | {fmt(row)} |")
if len(cv):
    lines += ["", "Cross-validation on the training rows (dev macro-F1 against Opus's labels, 5 folds, seeds 42, 1 and 7):", ""]
    p = cv.pivot_table(index=["seed", "fold"], columns="base", values="dev_macro_f1")
    for base in p.columns:
        lines.append(f"- {base}: mean {p[base].mean():.3f}, sd {p[base].std():.3f}, {p[base].notna().sum()} folds")
    if {"finbert", "dapt"} <= set(p.columns):
        d = (p["dapt"] - p["finbert"]).dropna()
        lines.append(f"- adapted minus FinBERT, paired: mean {d.mean():+.3f}, sd {d.std():.3f}, better in {(d > 0).sum()} of {len(d)} folds")
open(f"{R}/results.md", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
