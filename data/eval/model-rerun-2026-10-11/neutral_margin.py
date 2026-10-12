"""Choose the averaged model's neutral margin on held-out training rows, then score the test
rows once with it. A sentence is called neutral unless the stronger of positive and negative
beats neutral by more than the margin (train.error_analysis.apply_margin).

The three seeds each held out their own dev slice, so there is no dev row that none of them
trained on. As on 4 Oct (docs/evidence/ensemble-margin-2026-10-04.md) each dev row is scored
by the average of only the seeds that held it out, and the margin with the highest macro-F1
on those rows is chosen (ties to the smaller) before any test row is scored.

  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 data/eval/model-rerun-2026-10-11/neutral_margin.py <model root> <out.json>
"""
import json, os, sys
sys.path.insert(0, os.getcwd())
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, f1_score
import train.evaluate as ev
from train.error_analysis import MARGINS, apply_margin, dev_split
from train.labels import LABELS

root, out_path = sys.argv[1], sys.argv[2]
df = pd.read_csv("data/labeled/llm_rater/rules-2026-10-10/training_set.csv")
train = df[df.split == "train_dev"].reset_index(drop=True)
first = df[df.split == "test"][["sentence_id", "aspect", "text", "bank", "source", "label"]].assign(scope="first")
broker = pd.read_csv("data/labeled/sgx_research/resolved_test_blind.csv")[["sentence_id", "aspect", "text", "bank", "source", "label"]].assign(scope="broker")
test = pd.concat([first, broker], ignore_index=True)
dirs = {s: f"{root}/seed_{s}/final" for s in (42, 1, 7)}

# out-of-fold dev probabilities
acc = {}
for seed, d in dirs.items():
    dev = dev_split(train, seed, d)
    p = ev.finetuned_probs(d, dev)
    for (sid, asp, lab), row in zip(dev[["sentence_id", "aspect", "label"]].itertuples(index=False), p):
        acc.setdefault((sid, asp, lab), []).append(row)
gold = [k[2] for k in acc]
oof = np.array([np.mean(v, axis=0) for v in acc.values()])
held = pd.Series([len(v) for v in acc.values()]).value_counts().sort_index().to_dict()
dev_curve = {f"{m:.2f}": float(f1_score(gold, apply_margin(oof, m), labels=LABELS, average="macro", zero_division=0)) for m in MARGINS}
best = max(dev_curve.items(), key=lambda kv: (kv[1], -float(kv[0])))
margin = float(best[0])

avg = sum(ev.finetuned_probs(d, test) for d in dirs.values()) / 3


def report(y, pred):
    rep = classification_report(y, pred, labels=LABELS, output_dict=True, zero_division=0)
    m = confusion_matrix(y, pred, labels=LABELS)
    n = int(m.sum()); called = m.sum(axis=0); truth = m.sum(axis=1)
    r = {"accuracy": rep["accuracy"], "macro_f1": rep["macro avg"]["f1-score"], "confusion": m.tolist(),
         "net_called": float((called[2] - called[0]) / n), "net_labels": float((truth[2] - truth[0]) / n),
         "share_called_polar": float((called[0] + called[2]) / n), "share_labels_polar": float((truth[0] + truth[2]) / n)}
    for l in LABELS:
        r[l] = {"precision": rep[l]["precision"], "recall": rep[l]["recall"], "f1": rep[l]["f1-score"]}
    return r


res = {"model_root": root, "dev_rows": len(acc), "dev_rows_by_seeds_holding_out": {str(k): int(v) for k, v in held.items()},
       "dev_curve": dev_curve, "chosen_margin": margin, "dev_macro_f1_at_margin": best[1], "dev_macro_f1_at_zero": dev_curve["0.00"], "test": {}}
for scope, mask in (("first", (test.scope == "first").values), ("broker", (test.scope == "broker").values), ("all", np.ones(len(test), bool))):
    y = test.label[mask].tolist()
    res["test"][scope] = {"n": int(mask.sum()), "argmax": report(y, apply_margin(avg[mask], 0.0)), "with_margin": report(y, apply_margin(avg[mask], margin)),
                          "curve": {f"{m:.2f}": float(f1_score(y, apply_margin(avg[mask], m), labels=LABELS, average="macro", zero_division=0)) for m in MARGINS}}
json.dump(res, open(out_path, "w"), indent=1)
print("dev rows", len(acc), held, "| dev curve", {k: round(v, 3) for k, v in dev_curve.items()})
print("chosen margin", margin)
for scope, r in res["test"].items():
    a, w = r["argmax"], r["with_margin"]
    print(f"{scope:6} n={r['n']}: macro-F1 {a['macro_f1']:.3f} -> {w['macro_f1']:.3f} | accuracy {a['accuracy']:.3f} -> {w['accuracy']:.3f} | "
          f"negative P/R {a['negative']['precision']:.2f}/{a['negative']['recall']:.2f} -> {w['negative']['precision']:.2f}/{w['negative']['recall']:.2f} | "
          f"net {a['net_called']:+.3f} -> {w['net_called']:+.3f} (labels {a['net_labels']:+.3f}) | polar share {a['share_called_polar']:.2f} -> {w['share_called_polar']:.2f} (labels {a['share_labels_polar']:.2f})")
