"""
A top-up labelling sheet for the aspects with too few labelled rows (PLAN
section 6: about 80 per aspect). Reads the database and the labels; writes
only the sheet.

1. Targets: every aspect with fewer than `--floor` rows in
   data/labeled/candidates.csv.
2. Pool: per target, the unlabelled sentences most similar to its centroid,
   taken evenly from Reddit, earnings and news so no source dominates, with
   PDF debris (preprocess.fragments) and duplicate texts removed.
3. Check: the LLM aspect classifier (aspects.llm_classify) reads each pooled
   sentence; a sentence is kept for the target the LLM gives it, if that is
   a target aspect.
4. Sheet: up to the quota per target, spread over sources and banks. The
   sheet is blind (no model answer in it), because the 27 Sep labels
   followed the model's suggestion on 92% of rows; the LLM's aspect is kept
   in a separate file for comparing afterwards.

USAGE:
  HF_HUB_OFFLINE=1 python -m preprocess.export_topup                # writes data/labeled/topup/
  HF_HUB_OFFLINE=1 python -m preprocess.export_topup --dry-run      # targets and pool sizes only
"""

import argparse
import os
from collections import Counter

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")
OUT_DIR = os.path.join(BASE_DIR, "data", "labeled", "topup")
SOURCE_GROUP = {"arctic_shift": "reddit", "earnings": "earnings"}   # every other source is news
FLOOR = 80
MARGIN = 20        # rows over the shortfall, since annotators will reject some
MIN_QUOTA = 30
POOL_FACTOR = 3    # pooled sentences per quota row, before the LLM check


def quotas(labels: pd.DataFrame, floor: int = FLOOR) -> dict[str, int]:
    """Rows to add per aspect below the floor: the shortfall plus a margin, at least MIN_QUOTA."""
    counts = labels["aspect"].value_counts()
    return {a: max(MIN_QUOTA, floor - int(n) + MARGIN) for a, n in counts.items() if a != "other" and n < floor}


def _group(source: str) -> str:
    return SOURCE_GROUP.get(source, "news")


def pool_for(candidates: pd.DataFrame, size: int) -> pd.DataFrame:
    """The `size` most similar sentences, taken in turn from each source group."""
    c = candidates.sort_values("similarity", ascending=False).assign(group=lambda d: d["source"].map(_group))
    by_group = {g: list(df.index) for g, df in c.groupby("group", sort=True)}
    picked = []
    while len(picked) < size and any(by_group.values()):
        for g in sorted(by_group):
            if by_group[g] and len(picked) < size:
                picked.append(by_group[g].pop(0))
    return c.loc[picked]


def spread(rows: pd.DataFrame, n: int) -> pd.DataFrame:
    """Up to n rows, round-robin over (source group, bank) so none dominates; most similar first."""
    r = rows.sort_values("similarity", ascending=False).assign(cell=lambda d: d["source"].map(_group) + "/" + d["bank"])
    queues = {k: list(df.index) for k, df in r.groupby("cell", sort=True)}
    picked = []
    while len(picked) < n and any(queues.values()):
        for k in sorted(queues):
            if queues[k] and len(picked) < n:
                picked.append(queues[k].pop(0))
    return r.loc[picked].drop(columns="cell")


def build_pool(conn, labels: pd.DataFrame, targets: dict[str, int]) -> pd.DataFrame:
    from preprocess.fragments import fragment_reason
    taken = set(labels["sentence_id"])
    seen_text, parts = set(), []
    for aspect, quota in targets.items():
        df = pd.read_sql("""SELECT s.sentence_id, s.bank, s.source, s.text, sa.similarity
                            FROM sentence_aspects sa JOIN sentences s ON s.sentence_id = sa.sentence_id
                            WHERE sa.aspect = ?""", conn, params=(aspect,))
        df = df[~df["sentence_id"].isin(taken)]
        df = df[[fragment_reason(t, s) is None for t, s in zip(df["text"], df["source"])]]
        df = df.assign(norm=df["text"].str.lower().str.split().str.join(" "))
        df = df[~df["norm"].isin(seen_text)].drop_duplicates("norm")
        part = pool_for(df, quota * POOL_FACTOR).assign(pooled_for=aspect)
        taken.update(part["sentence_id"])
        seen_text.update(part["norm"])
        parts.append(part.drop(columns="norm"))
    return pd.concat(parts, ignore_index=True)


def select(pool: pd.DataFrame, llm_aspect: pd.Series, targets: dict[str, int]) -> pd.DataFrame:
    """Rows whose LLM aspect is a target, up to each target's quota."""
    p = pool.assign(llm_aspect=llm_aspect.values)
    p = p[p["llm_aspect"].isin(targets)]
    return pd.concat([spread(p[p["llm_aspect"] == a], q) for a, q in targets.items()], ignore_index=True)


SHEET_README = """# Top-up labelling sheet

Sentences for the aspects with fewer than {floor} labelled rows on {date}:
{targets}

Label them exactly as the 27 Sep round, following
`docs/annotation-guideline.md` (version 2): fill `aspect`, `label`,
`not_about_bank` and `annotator`. Every row is train/dev; none goes to the
test split.

The sheet is blind: it shows no model answer. The sentences were found by
centroid similarity and checked by `llama3.1:8b`, whose aspect is kept in
`llm_aspects.csv` for comparison after labelling; don't open it first. The
annotators of the 27 Sep round kept the model's suggestion on 92% of rows,
which is why it isn't shown here.

Two people should label the same 40 rows first and check aspect agreement:

    .venv-plp/bin/python3 -m train.agreement --a sheet_a.csv --b sheet_b.csv --field aspect
"""


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--floor", type=int, default=FLOOR)
    p.add_argument("--llm", default="llama3.1:8b")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    from ingest.db import get_connection
    labels = pd.read_csv(LABELS_PATH)
    targets = quotas(labels, args.floor)
    current = labels["aspect"].value_counts()
    print("targets: " + ", ".join(f"{a} {int(current[a])} labelled -> add up to {q}" for a, q in targets.items()))
    conn = get_connection()
    try:
        pool = build_pool(conn, labels, targets)
    finally:
        conn.close()
    print(f"pool: {len(pool)} sentences; by target {dict(Counter(pool['pooled_for']))}; "
          f"by source {dict(Counter(pool['source']))}", flush=True)
    if args.dry_run:
        return

    from aspects.llm_classify import classify_rows
    llm = classify_rows(pool[["sentence_id", "text"]], args.llm).set_index("sentence_id")["aspect"]
    chosen = select(pool, pool["sentence_id"].map(llm), targets)
    confirmed = pool["sentence_id"].map(llm).eq(pool["pooled_for"]).mean()
    print(f"LLM agreed with the centroid's aspect on {confirmed:.0%} of the pool")

    os.makedirs(OUT_DIR, exist_ok=True)
    sheet_path = os.path.join(OUT_DIR, "topup_sheet.csv")
    if os.path.exists(sheet_path):
        raise SystemExit(f"{sheet_path} exists; it may hold labels. Move it before exporting a new one.")
    sheet = chosen.sample(frac=1, random_state=2026)        # mixed, so order hints nothing
    sheet[["sentence_id", "bank", "source", "text"]].assign(
        aspect="", label="", not_about_bank="", annotator="", notes="", split="train_dev").to_csv(sheet_path, index=False)
    sheet[["sentence_id", "pooled_for", "llm_aspect", "similarity"]].to_csv(
        os.path.join(OUT_DIR, "llm_aspects.csv"), index=False)
    with open(os.path.join(OUT_DIR, "README.md"), "w") as f:
        f.write(SHEET_README.format(floor=args.floor, date=pd.Timestamp.today().date(),
                                    targets="\n".join(f"- `{a}`: {int(current[a])} labelled" for a in targets)))
    got = Counter(sheet["llm_aspect"])
    print(f"sheet: {len(sheet)} rows -> {sheet_path}")
    for a, q in targets.items():
        print(f"  {a}: {got.get(a, 0)} of {q}" + ("" if got.get(a, 0) >= q else "  (short: rerun with a larger pool)"))


if __name__ == "__main__":
    main()
