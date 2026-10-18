"""
Baselines and fine-tuned FinBERT on the extended test set: the 299 frozen
random test rows plus the 100 broker research (sgx_research) test rows, 399 in all.

The baselines train on the same 1,563 labelled pairs as before (which already
include 275 broker research rows) and are scored on the 399. The fine-tuned model's
labels are read from the database (read-only), where they are the three seeds
combined; they were never trained on any test row. The paired bootstrap is
macro-F1(FinBERT) minus macro-F1(baseline) on the same rows.

The extended rows come from data/labeled/combined/candidates.csv (split = test,
source = sgx_research); the script refuses to run if any of them is in the training set.

USAGE:
  HF_HUB_OFFLINE=1 python -m train.baselines_extended_test
Output: data/eval/baselines_extended/ (results.json, results.md, predictions.csv).
"""

import json
import os
import sqlite3

import numpy as np
import pandas as pd

from train.baselines_classical import (DEFAULT_LABELS, load_split, macro_f1_interval, model_input, models,
                                       paired_bootstrap)
from train.labels import LABELS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMBINED = os.path.join(BASE_DIR, "data", "labeled", "combined", "candidates.csv")
OUT_DIR = os.path.join(BASE_DIR, "data", "eval", "baselines_extended")
SEEDS = [42, 43, 44]


def extended_test(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    c = pd.read_csv(COMBINED)
    sgx = c[(c["split"] == "test") & (c["source"] == "sgx_research") & c["label"].isin(LABELS)]
    if sgx["sentence_id"].isin(train["sentence_id"]).any() or sgx["text"].isin(train["text"]).any():
        raise SystemExit("an SGX test row is in the training set")
    both = pd.concat([test.assign(group="original_299"), sgx.assign(group="sgx_100")], ignore_index=True)
    return both.drop_duplicates("sentence_id").reset_index(drop=True)


def finbert_labels(ids: list[str]) -> pd.Series:
    from config.model_version import MODEL_VERSION
    from ingest.db import DB_PATH
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        db = pd.read_sql_query("SELECT sentence_id, aspect AS db_aspect, label AS finbert FROM aspect_sentiment "
                               "WHERE model_version = ?", conn, params=(MODEL_VERSION,))
    finally:
        conn.close()
    db = db.drop_duplicates("sentence_id").set_index("sentence_id")
    return db.reindex(ids)


def scope_rows(df: pd.DataFrame, preds: pd.DataFrame, scope: str) -> pd.DataFrame:
    return df if scope == "all_399" else df[df["group"] == scope]


def main():
    train, test = load_split(DEFAULT_LABELS)
    ext = extended_test(train, test)
    fb = finbert_labels(ext["sentence_id"].tolist())
    ext["finbert"] = fb["finbert"].values
    ext["db_aspect"] = fb["db_aspect"].values
    if ext["finbert"].isna().any():
        raise SystemExit(f"{int(ext['finbert'].isna().sum())} test sentences have no stored FinBERT label")
    print(f"extended test set: {len(ext)} rows ({(ext.group == 'original_299').sum()} + {(ext.group == 'sgx_100').sum()})")

    Xtr, ytr, Xte = model_input(train), train["label"].tolist(), model_input(ext)
    preds = ext[["sentence_id", "group", "aspect", "label", "finbert"]].copy()
    for name, pipe in models(42).items():
        preds[name] = pipe.fit(Xtr, ytr).predict(Xte)

    from train.bilstm_baseline import train_one
    for arch in ("bilstm", "cnn"):
        runs = [train_one(arch, s, train, ext, None) for s in SEEDS]
        votes = np.array([r["pred"] for r in runs])
        majority = [int(np.bincount(votes[:, j], minlength=len(LABELS)).argmax()) for j in range(votes.shape[1])]
        preds[arch] = [LABELS[i] for i in majority]
        preds[f"{arch}_seed_f1"] = None
        print(arch, "per-seed test macro-F1 on the 399:", [round(r["test_macro_f1"], 3) for r in runs])
    out = {"n_train": len(train), "n_test": len(ext), "scopes": {}}
    methods = ["finbert", "naive_bayes", "complement_nb", "linear_svm", "logistic_regression", "bilstm", "cnn"]
    for scope in ("all_399", "original_299", "sgx_100"):
        d = scope_rows(preds, preds, scope)
        y = d["label"].tolist()
        res = {"n": len(d), "macro_f1": {}, "paired_vs_finbert": {}}
        for m in methods:
            f, lo, hi = macro_f1_interval(y, d[m].tolist())
            res["macro_f1"][m] = {"f1": f, "lo": lo, "hi": hi}
        for m in methods[1:]:
            res["paired_vs_finbert"][m] = paired_bootstrap(y, d["finbert"].tolist(), d[m].tolist())
        out["scopes"][scope] = res
    # how often the stored FinBERT aspect differs from the human aspect on these rows
    out["aspect_mismatch"] = {"rows": int((ext["aspect"] != ext["db_aspect"]).sum()), "of": len(ext)}
    os.makedirs(OUT_DIR, exist_ok=True)
    preds.drop(columns=[c for c in preds.columns if c.endswith("_seed_f1")]).to_csv(
        os.path.join(OUT_DIR, "predictions.csv"), index=False)
    with open(os.path.join(OUT_DIR, "results.json"), "w") as f:
        json.dump(out, f, indent=1, default=float)
    with open(os.path.join(OUT_DIR, "results.md"), "w", encoding="utf-8") as f:
        f.write(render(out, methods))
    print(render(out, methods))


def render(out: dict, methods: list[str]) -> str:
    lines = ["# Baselines and fine-tuned FinBERT on the extended test set", "",
             f"Baselines trained on {out['n_train']:,} labelled pairs; scored on {out['n_test']} test rows "
             "(299 frozen random rows plus 100 broker research rows). 95% bootstrap intervals over rows.", ""]
    for scope, r in out["scopes"].items():
        lines += [f"## {scope} ({r['n']} rows)", "", "| model | macro-F1 (95% interval) | FinBERT minus this model (95% interval) |",
                  "|---|---|---|"]
        for m in methods:
            s = r["macro_f1"][m]
            p = r["paired_vs_finbert"].get(m)
            diff = f"{p['diff']:+.3f} ({p['lo']:+.3f} to {p['hi']:+.3f})" if p else ""
            lines.append(f"| {m} | {s['f1']:.3f} ({s['lo']:.3f} to {s['hi']:.3f}) | {diff} |")
        lines.append("")
    a = out["aspect_mismatch"]
    lines.append(f"The stored FinBERT label was made under the pipeline's aspect, which differs from the human aspect on "
                 f"{a['rows']} of {a['of']} rows.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
