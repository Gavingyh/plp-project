"""
Opus 5.5 as an extra, blind rater on two sheets people haven't labelled yet:
the top-up sheet (aspect and not_about_bank, the same task and instructions
as the 1 Oct round) and the bank-NER gold sheet (which banks a sentence is
about). DESIGN decision 22 applies: these answers never replace people's
labels; they give an agreement figure once people finish, and a provisional
reference before.

The raters are Claude Code subagents, each given one instructions file and
one batch under data/labeled/claude/<sheet>/, as in
docs/evidence/opus-labeller-2026-10-01.md. The NER batches leave out the
sheet's `case` column, the sampling stratum, which hints at the answer.

USAGE:
  python -m train.opus_extra batches topup|ner   # write inputs and instructions
  python -m train.opus_extra merge topup|ner     # answers -> opus_<sheet>.csv (validated)
  python -m train.opus_extra score topup|ner     # agreement with llama / NER against Opus
"""

import argparse
import glob
import json
import os
import shutil

import pandas as pd

from train.opus_labels import CLAUDE_DIR, _jsonl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
- UOB Kay Hian and DBS Vickers are brokers: they do NOT count as the bank.
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


def write_batches(name: str) -> list[str]:
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


def merge(name: str, valid_aspects: set[str] | None = None) -> pd.DataFrame:
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
    p.add_argument("cmd", choices=["batches", "merge", "score"])
    p.add_argument("sheet", choices=list(SHEETS))
    args = p.parse_args()
    out_csv = os.path.join(sheet_dir(args.sheet), f"opus_{args.sheet}.csv")
    if args.cmd == "batches":
        for path in write_batches(args.sheet):
            print(path, len(pd.read_csv(path)))
    elif args.cmd == "merge":
        from aspects.llm_classify import aspect_keys
        df = merge(args.sheet, set(aspect_keys()))
        df.to_csv(out_csv, index=False)
        print(f"merged {len(df)} answers -> {out_csv}")
    elif args.sheet == "topup":
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
