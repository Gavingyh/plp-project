"""
Where the fine-tuned models go wrong, and whether a neutral threshold chosen
on dev cuts the commonest error (neutral sentences called positive or
negative).

The threshold rule: predict neutral unless the most likely polar class
beats neutral by more than `margin` in probability. margin = 0 is the
plain argmax. Each seed's margin is chosen on that seed's own dev split (the
same 85/15 shuffle train/finetune.py used), never on test; test is scored
once with the chosen margin. Reads only.

USAGE:
  HF_HUB_OFFLINE=1 python -m train.error_analysis
  HF_HUB_OFFLINE=1 python -m train.error_analysis --cpu --models models/experiments-2026-10-01/label/seed_{42,1,7}/final
"""

import argparse
import json
import os
import re

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from config.model_version import DEFAULT_FINETUNED, FINETUNED
from train.labels import LABELS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODELS = [os.path.join(BASE_DIR, d) for d in FINETUNED[DEFAULT_FINETUNED]["models"]]
MARGINS = np.round(np.arange(0.0, 0.61, 0.05), 2)


# The default models predate dev_ids.json; they were trained on this many
# train_dev rows, and a reshuffle reproduces their dev rows only at that size.
TRAIN_DEV_ROWS_AT_TRAINING = 978


def dev_split(train_dev: pd.DataFrame, seed: int, model_dir: str | None = None) -> pd.DataFrame:
    """The dev rows train/finetune.py held out for this seed: read from the
    model's dev_ids.json when it has one, else rebuilt by the same reshuffle,
    which is only right while train_dev is the size it was at training."""
    path = os.path.join(model_dir, "dev_ids.json") if model_dir else None
    if path and os.path.exists(path):
        with open(path) as f:
            keys = [tuple(k) for k in json.load(f)]
        indexed = train_dev.set_index(["sentence_id", "aspect"])
        missing = [k for k in keys if k not in indexed.index]
        if missing:
            raise KeyError(f"{len(missing)} dev rows of {model_dir} are no longer in train_dev, first: {missing[:2]}")
        return indexed.loc[keys].reset_index()
    if len(train_dev) != TRAIN_DEV_ROWS_AT_TRAINING:
        raise ValueError(f"train_dev has {len(train_dev)} rows, not the {TRAIN_DEV_ROWS_AT_TRAINING} this model "
                         "was trained on, so reshuffling no longer gives its dev rows; retrain to get dev_ids.json")
    shuffled = train_dev.sample(frac=1, random_state=seed).reset_index(drop=True)
    return shuffled[int(len(shuffled) * 0.85):]


def apply_margin(probs: np.ndarray, margin: float) -> list[str]:
    """Neutral unless the stronger polar class beats neutral by more than `margin`."""
    neg, neu, pos = probs[:, 0], probs[:, 1], probs[:, 2]
    polar = np.where(pos >= neg, 2, 0)
    polar_p = np.maximum(pos, neg)
    pick = np.where(polar_p - neu > margin, polar, 1)
    return [LABELS[i] for i in pick]


def best_margin(probs: np.ndarray, gold: list[str]) -> tuple[float, float]:
    """The margin with the highest dev macro-F1 (ties go to the smaller margin)."""
    scores = [(f1_score(gold, apply_margin(probs, m), labels=LABELS, average="macro", zero_division=0), -m)
              for m in MARGINS]
    f1, neg_m = max(scores)
    return -neg_m, f1


def error_types(gold: list[str], pred: list[str]) -> dict:
    g, p = np.array(gold), np.array(pred)
    return {"errors": int((g != p).sum()),
            "neutral_called_polar": int(((g == "neutral") & (p != "neutral")).sum()),
            "polar_called_neutral": int(((g != "neutral") & (p == "neutral")).sum()),
            "pos_neg_swapped": int(((g != "neutral") & (p != "neutral") & (g != p)).sum())}


def by_group(df: pd.DataFrame, pred: list[str], col: str) -> pd.DataFrame:
    d = df.assign(pred=pred, ok=lambda x: x["label"] == x["pred"])
    out = d.groupby(col).agg(n=("ok", "size"), accuracy=("ok", "mean"),
                             neutral_called_polar=("pred", lambda s: int(((d.loc[s.index, "label"] == "neutral") & (s != "neutral")).sum())))
    return out.sort_values("n", ascending=False)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    p.add_argument("--cpu", action="store_true", help="run on the CPU (e.g. while the GPU is busy)")
    args = p.parse_args()

    import train.evaluate as ev
    if args.cpu:
        ev.best_device = lambda: "cpu"
    full = pd.read_csv(ev.CANDIDATES_PATH)
    train_dev = full[(full["split"] == "train_dev") & full["label"].isin(LABELS)]
    test = ev._load_test_set().reset_index(drop=True)

    test_probs, rows = [], []
    for d in args.models:
        seed = int(re.search(r"seed_(\d+)", d).group(1))
        dev = dev_split(train_dev, seed, d).reset_index(drop=True)
        dev_probs = ev.finetuned_probs(d, dev)
        margin, dev_f1 = best_margin(dev_probs, dev["label"].tolist())
        tp = ev.finetuned_probs(d, test)
        test_probs.append(tp)
        for name, m in (("argmax", 0.0), ("dev-chosen margin", margin)):
            pred = apply_margin(tp, m)
            rows.append({"seed": seed, "rule": name, "margin": m,
                         "dev_macro_f1": f1_score(dev["label"], apply_margin(dev_probs, m), labels=LABELS, average="macro"),
                         "test_macro_f1": f1_score(test["label"], pred, labels=LABELS, average="macro"),
                         "test_accuracy": float(np.mean(np.array(pred) == test["label"].values)),
                         **error_types(test["label"].tolist(), pred)})
    res = pd.DataFrame(rows)
    print("Per seed, test split (n=299):")
    print(res.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    avg = np.mean(test_probs, axis=0)
    mean_margin = float(res[res["rule"] == "dev-chosen margin"]["margin"].mean())
    print(f"\nAverage of the models, argmax and the seeds' mean dev-chosen margin ({mean_margin:.2f}):")
    for name, m in (("argmax", 0.0), ("mean margin", mean_margin)):
        pred = apply_margin(avg, m)
        print(f"  {name:12s} macro-F1 {f1_score(test['label'], pred, labels=LABELS, average='macro'):.3f} "
              f"accuracy {np.mean(np.array(pred) == test['label'].values):.3f} {error_types(test['label'].tolist(), pred)}")

    pred = apply_margin(avg, 0.0)
    print("\nAverage of the models (argmax), by source:")
    print(by_group(test, pred, "source").to_string(float_format=lambda v: f"{v:.2f}"))
    print("\nBy human aspect:")
    print(by_group(test, pred, "aspect").to_string(float_format=lambda v: f"{v:.2f}"))
    words = test["text"].str.split().str.len()
    test = test.assign(length=pd.cut(words, [0, 10, 20, 35, 1000], labels=["1-10", "11-20", "21-35", "36+"]))
    print("\nBy sentence length (words):")
    print(by_group(test, pred, "length").to_string(float_format=lambda v: f"{v:.2f}"))

    d = test.assign(pred=pred)
    wrong = d[(d["label"] == "neutral") & (d["pred"] != "neutral")]
    print(f"\nNeutral sentences called polar ({len(wrong)}), first 12 by source:")
    for r in wrong.sort_values("source").head(12).itertuples():
        print(f"  [{r.source}] {r.pred:8s} | {r.aspect} | {r.text[:110]}")


if __name__ == "__main__":
    main()
