"""
The Opus 5.5 labeller (DESIGN decision 22): merge its answers, score them
against the human labels, write review queues, and audit that the raters
saw no other labels. Reads only; never changes candidates.csv.

The raters themselves were Claude Code subagents, each given one
instructions file and one batch under data/labeled/claude/ (see
docs/evidence/opus-labeller-2026-10-01.md).

The same procedure rated two sheets people hadn't labelled yet (the top-up
sheet and the bank-NER gold sheet): the `extra` commands, with batches under
data/labeled/claude/topup/ and ner/.

USAGE:
  python -m train.opus_labels merge                  # pilot/ + batches/ -> opus_labels.csv
  python -m train.opus_labels score [--centroid]     # agreement tables, review_*.csv
  python -m train.opus_labels audit --transcripts DIR
  python -m train.opus_labels extra batches|merge|score topup|ner
"""

import argparse
import glob
import json
import os
import re
import shutil

import pandas as pd
from sklearn.metrics import cohen_kappa_score, f1_score

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
CLAUDE_DIR = os.path.join(BASE_DIR, "data", "labeled", "claude")
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
    from aspects.llm_classify import answer_cache_path
    for col, path in (("llama3.1_8b_aspect", answer_cache_path("llama3.1:8b")),
                      ("qwen3_4b_aspect", answer_cache_path("qwen3:4b", no_think=True))):
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


# --- Later rounds on unlabelled sheets (2026-10-02) --------------------------------
# The top-up sheet (aspect and not_about_bank, the same task and instructions as
# the first round) and the bank-NER gold sheet (which banks a sentence is about).
# The NER batches leave out the sheet's `case` column, the sampling stratum,
# which hints at the answer. These answers replace no one's labels: they give an
# agreement figure once people finish, and a provisional reference before.

TOPUP_SHEET = os.path.join(BASE_DIR, "data", "labeled", "topup", "topup_sheet.csv")
TOPUP_LLM = os.path.join(BASE_DIR, "data", "labeled", "topup", "llm_aspects.csv")
NER_SHEET = os.path.join(BASE_DIR, "data", "labeled", "ner", "gold_sheet.csv")
BANKS = ("DBS", "OCBC", "UOB")
SEED = 2026
SHEETS = {
    "topup": {"sheet": TOPUP_SHEET, "columns": ["sentence_id", "bank", "source", "text"], "prefix": "aspect",
              "batches": 4, "instructions": "instructions_aspect.md"},
    "ner": {"sheet": NER_SHEET, "columns": ["sentence_id", "source", "text"], "prefix": "ner",
            "batches": 4, "instructions": "instructions_ner.md"},
}

NER_INSTRUCTIONS = """# Rater instructions: which banks a sentence is about

You are labelling sentences for a study of Singapore's three listed banks
(DBS, OCBC, UOB). For each sentence, decide which of the three it is about
as a bank. The rules are the project's (`data/labeled/ner/README.md`,
PLAN section 7, DESIGN decision 18), quoted.

## Rules for this task

- Read only this file and the input file named in your task. Do not open
  any other file in the repository: other files hold labels or model
  predictions for these sentences.
- Judge each sentence yourself. Do not write code to classify, and do not call
  any model, API or search.
- Every row gets an answer.

## The rules

- POSB counts as DBS. Bank of Singapore and Great Eastern count as OCBC.
- DBS Vickers counts as DBS. UOB Kay Hian is a separate broker: it does NOT count as UOB.
- "Aston Martin DBS" and medical DBS (deep brain stimulation) are not banks.
- A bank named only as a place or a payment rail ("paid via DBS PayNow")
  still counts: this task is about which bank is named, not about relevance.
- A sentence can name none, one, two or all three.

## Output

Write the output file named in your task: one line per input row, in
input order, exactly

{"sentence_id": "<id>", "banks": ["DBS", "OCBC", "UOB"]}

listing only the banks the sentence is about, in that order, or `[]` for
none. No other fields, no commentary lines.
"""


def sheet_dir(name: str) -> str:
    return os.path.join(CLAUDE_DIR, name)


def extra_batches(name: str) -> list[str]:
    """Shuffled input batches and the instructions, under data/labeled/claude/<name>/."""
    spec = SHEETS[name]
    rows = pd.read_csv(spec["sheet"], keep_default_na=False)[spec["columns"]].sample(frac=1, random_state=SEED)
    out_dir = sheet_dir(name)
    os.makedirs(out_dir, exist_ok=True)
    if name == "topup":
        shutil.copy(os.path.join(CLAUDE_DIR, "instructions_aspect.md"), os.path.join(out_dir, spec["instructions"]))
    else:
        with open(os.path.join(out_dir, spec["instructions"]), "w") as f:
            f.write(NER_INSTRUCTIONS)
    paths, n = [], spec["batches"]
    size = -(-len(rows) // n)
    for i in range(n):
        path = os.path.join(out_dir, f"{spec['prefix']}_{i + 1:02d}.csv")
        rows.iloc[i * size:(i + 1) * size].to_csv(path, index=False)
        paths.append(path)
    return paths


def merge_extra(name: str, valid_aspects: set[str] | None = None) -> pd.DataFrame:
    """Every batch's answers, checked against its input's ids and order."""
    spec, out = SHEETS[name], []
    inputs = sorted(glob.glob(os.path.join(sheet_dir(name), f"{spec['prefix']}_[0-9][0-9].csv")))
    if not inputs:
        raise FileNotFoundError(f"no batches in {sheet_dir(name)}; run `batches {name}` first")
    for inp in inputs:
        ans = os.path.join(os.path.dirname(inp), "opus_" + os.path.basename(inp)[:-4] + ".jsonl")
        rows = _jsonl(ans)
        if [r["sentence_id"] for r in rows] != pd.read_csv(inp)["sentence_id"].tolist():
            raise ValueError(f"{ans}: sentence ids or order differ from {inp}")
        for r in rows:
            if name == "topup":
                ok = set(r) == {"sentence_id", "aspect", "not_about_bank"} and isinstance(r["not_about_bank"], bool) \
                    and (valid_aspects is None or r["aspect"] in valid_aspects)
            else:
                ok = set(r) == {"sentence_id", "banks"} and isinstance(r["banks"], list) and set(r["banks"]) <= set(BANKS)
            if not ok:
                raise ValueError(f"{ans}: invalid answer {r}")
        out += rows
    df = pd.DataFrame(out)
    if name == "ner":
        df["banks"] = [";".join(b for b in BANKS if b in r) for r in df["banks"]]
        df = df.rename(columns={"banks": "opus_banks"})
    else:
        df = df.rename(columns={"aspect": "opus_aspect", "not_about_bank": "opus_not_about_bank"})
    return df


def score_topup(opus: pd.DataFrame, llm: pd.DataFrame) -> dict:
    from sklearn.metrics import cohen_kappa_score
    m = opus.merge(llm, on="sentence_id")
    return {"n": len(m), "agree": float((m["opus_aspect"] == m["llm_aspect"]).mean()),
            "kappa": float(cohen_kappa_score(m["opus_aspect"], m["llm_aspect"])),
            "not_about_bank": int(m["opus_not_about_bank"].sum()),
            "by_llm_aspect": m.groupby("llm_aspect")["opus_aspect"].value_counts().unstack(fill_value=0)}


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("merge")
    sc = sub.add_parser("score")
    sc.add_argument("--centroid", action="store_true", help="also score seed-centroid assignment (loads embeddings)")
    au = sub.add_parser("audit")
    au.add_argument("--transcripts", required=True, help="folder of subagent transcripts (*.output)")
    xt = sub.add_parser("extra", help="the later rounds on the top-up and NER sheets")
    xt.add_argument("action", choices=["batches", "merge", "score"])
    xt.add_argument("sheet", choices=list(SHEETS))
    args = p.parse_args()
    if args.cmd == "extra":
        return extra(args.action, args.sheet)
    if args.cmd == "merge":
        from aspects.llm_classify import aspect_keys
        out = merge(batch_pairs(), aspect_keys())
        out.to_csv(f"{CLAUDE_DIR}/opus_labels.csv", index=False)
        print(f"merged {len(out)} sentences -> data/labeled/claude/opus_labels.csv")
    elif args.cmd == "score":
        score(args.centroid)
    else:
        audit(args.transcripts)


def extra(action: str, sheet: str) -> None:
    out_csv = os.path.join(sheet_dir(sheet), f"opus_{sheet}.csv")
    if action == "batches":
        for path in extra_batches(sheet):
            print(path, len(pd.read_csv(path)))
    elif action == "merge":
        from aspects.llm_classify import aspect_keys
        df = merge_extra(sheet, set(aspect_keys()))
        df.to_csv(out_csv, index=False)
        print(f"merged {len(df)} answers -> {out_csv}")
    elif sheet == "topup":
        r = score_topup(pd.read_csv(out_csv), pd.read_csv(TOPUP_LLM))
        print({k: v for k, v in r.items() if k != "by_llm_aspect"})
        print(r["by_llm_aspect"].to_string())
    else:
        from preprocess.bank_ner import evaluate
        gold = pd.read_csv(NER_SHEET, keep_default_na=False).drop(columns=["gold_banks", "annotator"])
        ref = gold.merge(pd.read_csv(out_csv, keep_default_na=False), on="sentence_id") \
            .rename(columns={"opus_banks": "gold_banks"}).assign(annotator="opus (provisional reference)")
        print(evaluate(ref).to_string(index=False))


if __name__ == "__main__":
    main()
