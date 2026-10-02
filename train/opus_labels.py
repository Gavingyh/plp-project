"""
The Opus 5.5 labeller (DESIGN decision 22): merge its answers, score them
against the human labels, write review queues, and audit that the raters
saw no other labels. Reads only; never changes candidates.csv.

The raters themselves were Claude Code subagents, each given one
instructions file and one batch under data/labeled/claude/ (see
docs/evidence/opus-labeller-2026-10-01.md).

USAGE:
  python -m train.opus_labels merge                  # pilot/ + batches/ -> opus_labels.csv
  python -m train.opus_labels score [--centroid]     # agreement tables, review_*.csv
  python -m train.opus_labels audit --transcripts DIR
"""

import argparse
import glob
import json
import os
import re

import pandas as pd
from sklearn.metrics import cohen_kappa_score, f1_score

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
CLAUDE_DIR = os.path.join(BASE_DIR, "data", "labeled", "claude")
LLM_CACHE = os.path.join(BASE_DIR, "data", "aspect_llm")
RATER = "claude-opus-5-5"
SENTIMENTS = ("negative", "neutral", "positive")


def _jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def batch_pairs(root: str = CLAUDE_DIR) -> list[tuple[str, str, str]]:
    """(input csv, answer jsonl, task) for the pilot and every batch."""
    pairs = [(f"{root}/pilot/input_{t}.csv", f"{root}/pilot/opus_{t}.jsonl", t) for t in ("aspect", "sentiment")]
    for inp in sorted(glob.glob(f"{root}/batches/aspect_*.csv")) + sorted(glob.glob(f"{root}/batches/sentiment_*.csv")):
        name = os.path.basename(inp)[:-4]
        pairs.append((inp, f"{root}/batches/opus_{name}.jsonl", name.split("_")[0]))
    return pairs


def merge(pairs: list[tuple[str, str, str]], keys: list[str]) -> pd.DataFrame:
    """One row per sentence; fails if any answer file differs from its input in ids or order, or holds an invalid value."""
    aspect, sentiment = [], []
    for inp, out, task in pairs:
        ids = pd.read_csv(inp)["sentence_id"].tolist()
        rows = _jsonl(out)
        if [r["sentence_id"] for r in rows] != ids:
            raise ValueError(f"{out}: sentence ids or order differ from {inp}")
        if task == "aspect":
            if not all(set(r) == {"sentence_id", "aspect", "not_about_bank"} and r["aspect"] in keys
                       and isinstance(r["not_about_bank"], bool) for r in rows):
                raise ValueError(f"{out}: invalid aspect answer")
            aspect += rows
        else:
            if not all(set(r) == {"sentence_id", "label"} and r["label"] in SENTIMENTS for r in rows):
                raise ValueError(f"{out}: invalid sentiment answer")
            sentiment += rows
    a = pd.DataFrame(aspect).rename(columns={"aspect": "opus_aspect", "not_about_bank": "opus_not_about_bank"})
    s = pd.DataFrame(sentiment).rename(columns={"label": "opus_label"})
    if not (a["sentence_id"].is_unique and s["sentence_id"].is_unique and set(a["sentence_id"]) == set(s["sentence_id"])):
        raise ValueError("aspect and sentiment answers don't cover the same sentences exactly once")
    out = a.merge(s, on="sentence_id")
    out.insert(1, "rater", RATER)
    return out


def agreement(x: pd.Series, y: pd.Series) -> dict:
    ok = pd.concat([x, y], axis=1).dropna()
    a, b = ok.iloc[:, 0], ok.iloc[:, 1]
    return {"n": len(ok), "agreement": float((a == b).mean()), "kappa": float(cohen_kappa_score(a, b))}


def review_queues(d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rows where Opus and the human differ, with an empty `decision` column for a reviewer."""
    cols = ["sentence_id", "split", "source", "bank", "text"]
    extra = ["llama3.1_8b_aspect"] if "llama3.1_8b_aspect" in d else []
    qa = d[d["aspect"] != d["opus_aspect"]][cols + ["aspect", "opus_aspect"] + extra + ["opus_not_about_bank"]]
    qa = qa.rename(columns={"aspect": "human_aspect"}).assign(decision="")
    qs = d[d["label"] != d["opus_label"]][cols + ["aspect", "label", "opus_label", "llm_prelabel"]]
    qs = qs.rename(columns={"label": "human_label"}).assign(decision="")
    return qa.sort_values(["split", "human_aspect"]), qs.sort_values(["split", "aspect"])


def _fmt(m: dict) -> str:
    return f"{m['agreement']:.3f} (n={m['n']}), kappa {m['kappa']:.3f}"


def score(with_centroid: bool = False):
    labels = pd.read_csv(f"{CLAUDE_DIR}/opus_labels.csv")
    d = pd.read_csv(CANDIDATES_PATH).merge(labels, on="sentence_id")
    raters = ["opus_aspect"]
    for col, f in (("llama3.1_8b_aspect", "llama3.1_8b.jsonl"), ("qwen3_4b_aspect", "qwen3_4b-nothink.jsonl")):
        path = os.path.join(LLM_CACHE, f)
        if os.path.exists(path):
            d = d.merge(pd.DataFrame(_jsonl(path))[["sentence_id", "aspect"]].rename(columns={"aspect": col}), on="sentence_id")
            raters.append(col)
    if with_centroid:
        import numpy as np
        import aspects.assignment_eval as ae
        cents = ae._build_centroids(ae._load_config())
        names = list(cents)
        ids, vecs = ae.load_for_search()
        row = {s: i for i, s in enumerate(ids)}
        sims = ae.cosine_matrix(vecs[[row[s] for s in d["sentence_id"]]], np.stack([cents[a] for a in names]))
        d["centroid_aspect"] = ae.assign_at(sims, names, 0.65)[1]
        raters.append("centroid_aspect")
    test = d[d["split"] == "test"]

    print(f"ASPECT vs human, {len(d)} sentences")
    for r in raters:
        print(f"  {r:20s} all {_fmt(agreement(d['aspect'], d[r]))}, macro-F1 {f1_score(d['aspect'], d[r], average='macro'):.3f}"
              f" | test {_fmt(agreement(test['aspect'], test[r]))}")
    print(f"  not_about_bank: {int(d['opus_not_about_bank'].sum())}; by source "
          f"{d.groupby('source')['opus_not_about_bank'].sum().astype(int).to_dict()}")
    print("  per human aspect: rows, Opus recall, Opus precision (times used)")
    for k in sorted(d["aspect"].unique()):
        h, o = d[d["aspect"] == k], d[d["opus_aspect"] == k]
        print(f"    {k:26s} {len(h):4d}  R {(h['opus_aspect'] == k).mean():.2f}  P {(o['aspect'] == k).mean():.2f} ({len(o)})")
    pairs = d[d["aspect"] != d["opus_aspect"]].groupby(["aspect", "opus_aspect"]).size().sort_values(ascending=False)
    print("  largest disagreements (human -> Opus):\n" + pairs.head(10).to_string())
    for flag, g in d.groupby("opus_not_about_bank"):
        print(f"  not_about_bank={flag}: {_fmt(agreement(g['aspect'], g['opus_aspect']))}")
    if {"llama3.1_8b_aspect", "qwen3_4b_aspect"} <= set(d):
        print(f"  Opus vs llama3.1:8b {_fmt(agreement(d['opus_aspect'], d['llama3.1_8b_aspect']))}")
        both = d["llama3.1_8b_aspect"] == d["qwen3_4b_aspect"]
        for name, g in (("agree", d[both]), ("disagree", d[~both])):
            print(f"  where llama and qwen {name} (n={len(g)}): Opus = human {(g['aspect'] == g['opus_aspect']).mean():.3f}")
        (h, o), n = pairs.index[0], pairs.iloc[0]
        top = d[(d["aspect"] == h) & (d["opus_aspect"] == o)]
        print(f"  {h} -> {o} ({n}): llama3.1:8b also says {o} on {(top['llama3.1_8b_aspect'] == o).sum()}")

    print(f"\nSENTIMENT vs human (aspect given)")
    print(f"  Opus             all {_fmt(agreement(d['label'], d['opus_label']))}, "
          f"macro-F1 {f1_score(d['label'], d['opus_label'], average='macro'):.3f}")
    for split, g in d.groupby("split"):
        print(f"  Opus {split:11s} {_fmt(agreement(g['label'], g['opus_label']))}")
    print(f"  suggestion vs human {_fmt(agreement(d['label'], d['llm_prelabel']))}")
    print(f"  Opus vs suggestion  {_fmt(agreement(d['opus_label'], d['llm_prelabel']))}")
    print("  by source: " + "; ".join(f"{s} {(g['label'] == g['opus_label']).mean():.3f} (n={len(g)})"
                                       for s, g in d.groupby("source")))
    print(f"  label counts: human {d['label'].value_counts().to_dict()}, Opus {d['opus_label'].value_counts().to_dict()}")
    print("  confusion (rows human, columns Opus):\n" + pd.crosstab(d["label"], d["opus_label"]).to_string())
    differ = d[d["label"] != d["opus_label"]]
    print(f"  disagreements {len(differ)}: human = suggestion in {(differ['label'] == differ['llm_prelabel']).sum()}, "
          f"Opus = suggestion in {(differ['opus_label'] == differ['llm_prelabel']).sum()}")

    qa, qs = review_queues(d)
    qa.to_csv(f"{CLAUDE_DIR}/review_aspect.csv", index=False)
    qs.to_csv(f"{CLAUDE_DIR}/review_sentiment.csv", index=False)
    print(f"\nreview queues: aspect {len(qa)} ({(qa['split'] == 'test').sum()} test), "
          f"sentiment {len(qs)} ({(qs['split'] == 'test').sum()} test)")


_FORBIDDEN = re.compile(r"candidates|agreement|resolved|test_blind|aspect_llm|evidence|plp\.db|\.\./|\bls\b|\bfind\b|grep -r|curl|http")
_OWN_FILE = re.compile(r"^(.*/)?((opus_)?(aspect|sentiment|ner)_\d\d|input_(aspect|sentiment)|opus_(aspect|sentiment)"
                       r"|instructions_(aspect|sentiment|ner))\.(csv|jsonl|md)$")


def audit_call(name: str, inp: dict, root: str = CLAUDE_DIR) -> bool:
    """True if a rater's tool call stayed within its own instructions, input and output."""
    if name == "SubagentHandback":
        return True
    if name in ("Read", "Write"):
        path = inp.get("file_path", "")
        return path.startswith(root + "/") and bool(_OWN_FILE.match(path))
    if name == "Bash":
        cmd = inp.get("command", "")
        files = re.findall(r"[\w./-]+\.(?:csv|jsonl|md|json|txt|db|py)", cmd)
        return not _FORBIDDEN.search(cmd) and bool(files) and all(_OWN_FILE.match(f) for f in files)
    return False


def audit(transcripts: str):
    raters = calls = 0
    bad = []
    for f in sorted(glob.glob(os.path.join(transcripts, "*.output"))):
        with open(f) as fh:
            text = fh.read()
        if "independent annotator" not in text:
            continue
        raters += 1
        for line in text.splitlines():
            try:
                msg = json.loads(line).get("message") or {}
            except json.JSONDecodeError:
                continue
            for part in msg.get("content") if isinstance(msg.get("content"), list) else []:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    calls += 1
                    if not audit_call(part["name"], part["input"]):
                        bad.append((os.path.basename(f), part["name"], str(part["input"])[:200]))
    print(f"rater transcripts {raters}; tool calls {calls}; outside the rater's own files {len(bad)}")
    for b in bad:
        print("  ", b)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("merge")
    sc = sub.add_parser("score")
    sc.add_argument("--centroid", action="store_true", help="also score seed-centroid assignment (loads embeddings)")
    au = sub.add_parser("audit")
    au.add_argument("--transcripts", required=True, help="folder of subagent transcripts (*.output)")
    args = p.parse_args()
    if args.cmd == "merge":
        from aspects.llm_classify import aspect_keys
        out = merge(batch_pairs(), aspect_keys())
        out.to_csv(f"{CLAUDE_DIR}/opus_labels.csv", index=False)
        print(f"merged {len(out)} sentences -> data/labeled/claude/opus_labels.csv")
    elif args.cmd == "score":
        score(args.centroid)
    else:
        audit(args.transcripts)


if __name__ == "__main__":
    main()
