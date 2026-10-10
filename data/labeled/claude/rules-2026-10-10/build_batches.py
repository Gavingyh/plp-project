"""Inputs for the Opus labelling round under the rules of 10 Oct 2026.

Every sentence of the four sentiment sheets, once: the first round
(data/labeled/candidates.csv), the top-up sheet, the active-learning sheet and
the broker research round. Columns given to the rater: sentence_id, bank,
source, text. No human or model label is copied. A 50-row pilot (seed 2026),
the rest shuffled (seed 2026) into batches of about 122.

  .venv-plp/bin/python3 data/labeled/claude/rules-2026-10-10/build_batches.py            # aspect inputs
  .venv-plp/bin/python3 data/labeled/claude/rules-2026-10-10/build_batches.py sentiment  # after the aspect answers are in
"""
import glob, json, os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LABELED = os.path.dirname(os.path.dirname(HERE))
SHEETS = [("first_round", "candidates.csv"), ("topup", "topup/topup_sheet.csv"),
          ("active", "active/active_sheet.csv"), ("broker_research", "sgx_research/candidates.csv")]
COLS = ["sentence_id", "bank", "source", "text"]
SEED, PILOT, SIZE = 2026, 50, 122


def rows() -> pd.DataFrame:
    parts = [pd.read_csv(os.path.join(LABELED, path))[COLS].assign(sheet=name) for name, path in SHEETS]
    d = pd.concat(parts, ignore_index=True)
    dup = d[d.duplicated("sentence_id", keep="first")]
    if len(dup):
        print(f"{len(dup)} sentences are on two sheets; kept once, under the first sheet: "
              + dup.groupby('sheet').size().to_dict().__repr__())
    return d.drop_duplicates("sentence_id", keep="first").reset_index(drop=True)


def split(d: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    pilot = d.sample(n=PILOT, random_state=SEED)
    rest = d.drop(pilot.index).sample(frac=1, random_state=SEED).reset_index(drop=True)
    n = -(-len(rest) // SIZE)
    out = [("pilot/input", pilot.reset_index(drop=True))]
    out += [(f"batches/{i + 1:02d}", rest.iloc[i * len(rest) // n:(i + 1) * len(rest) // n]) for i in range(n)]
    return out


def main():
    d = rows()
    d[["sentence_id", "sheet"]].to_csv(os.path.join(HERE, "sheets.csv"), index=False)
    task = sys.argv[1] if len(sys.argv) > 1 else "aspect"
    answers = {}
    if task == "sentiment":
        for path in glob.glob(os.path.join(HERE, "pilot", "opus_aspect.jsonl")) + glob.glob(os.path.join(HERE, "batches", "opus_aspect_*.jsonl")):
            for line in open(path):
                if line.strip():
                    r = json.loads(line)
                    answers[r["sentence_id"]] = r["aspect"]
        missing = set(d["sentence_id"]) - set(answers)
        if missing:
            raise SystemExit(f"{len(missing)} sentences have no aspect answer yet")
    for name, part in split(d):
        folder, stem = name.split("/")
        out = os.path.join(HERE, folder, f"input_{task}.csv" if folder == "pilot" else f"{task}_{stem}.csv")
        part = part[COLS].copy()
        if task == "sentiment":
            part["aspect"] = part["sentence_id"].map(answers)     # Opus's own aspect from pass 1
        part.to_csv(out, index=False)
        print(f"{os.path.relpath(out, HERE)}: {len(part)} rows")
    print(f"{len(d)} sentences: " + d.groupby('sheet').size().to_dict().__repr__())


if __name__ == "__main__":
    main()
