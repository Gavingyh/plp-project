"""
Inter-annotator agreement (Cohen's kappa) for the labelling task.

docs/annotation-guideline.md asks two annotators to independently label the
same ~150-row sample and to compute Cohen's kappa before dividing up the rest,
targeting kappa >= 0.6. This is the tool that guideline refers to.

WHY KAPPA AND NOT RAW AGREEMENT: with three classes and a skewed
distribution, two annotators who both label almost everything `neutral` will
agree ~80% of the time while carrying no shared understanding of the hard
cases. Kappa subtracts the agreement you would expect from chance given each
annotator's own label distribution, so it collapses toward 0 exactly in that
situation. Both numbers are reported, because a large gap between them is
itself diagnostic: it means the label distribution is doing the work.

WHAT A LOW SCORE MEANS: below 0.6, the guideline is ambiguous somewhere
rather than the annotators being careless. Use --show-disagreements to find
where, tighten the guideline, and re-label the sample.

USAGE:
  # Two annotators' sheets, matched on (sentence_id, aspect)
  python -m train.agreement --a labels_alice.csv --b labels_bob.csv

  # Aspect agreement: the sheets' `aspect` columns, matched on sentence_id
  python -m train.agreement --a sheet_a.csv --b sheet_b.csv --field aspect

  # Two label columns inside one file
  python -m train.agreement --file candidates.csv --col-a label --col-b llm_prelabel

  # How often did the human change the model's proposal?
  python -m train.agreement --file data/labeled/candidates.csv \
      --col-a label --col-b llm_prelabel --show-disagreements 20
"""

import argparse

import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix

from config.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

LABELS = ["negative", "neutral", "positive"]
KEY = ["sentence_id", "aspect"]
ASPECT_KEY = ["sentence_id"]   # aspect agreement: the aspect is the thing compared

# From Landis & Koch (1977), "The Measurement of Observer Agreement for
# Categorical Data", Biometrics 33(1):159-174 - the thresholds the course's
# Text Analytics module cites. They are a convention for describing a number,
# not a statistical test; docs/annotation-guideline.md sets this project's own
# target at 0.6.
_LANDIS_KOCH = [
    (0.00, "poor (< 0.00)"),
    (0.20, "slight (0.00-0.20)"),
    (0.40, "fair (0.21-0.40)"),
    (0.60, "moderate (0.41-0.60)"),
    (0.80, "substantial (0.61-0.80)"),
    (1.01, "almost perfect (0.81-1.00)"),
]

TARGET_KAPPA = 0.6  # docs/annotation-guideline.md


def interpret(kappa: float) -> str:
    for upper, label in _LANDIS_KOCH:
        if kappa <= upper:
            return label
    return "almost perfect (0.81-1.00)"


def _clean(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower()


def aspect_keys() -> list[str]:
    from config import aspect_taxonomy
    return aspect_taxonomy.keys()


def _one_row_per_pair(df: pd.DataFrame, col: str, name: str, key: list[str] = KEY) -> pd.DataFrame:
    labels = df.assign(_v=_clean(df[col])).groupby(key)["_v"].nunique()
    conflicting = labels[labels > 1]
    if not conflicting.empty:
        raise ValueError(f"{name} lists {len(conflicting)} {tuple(key)} key(s) more than "
                         f"once with different values, first: {list(conflicting.index[:3])}")
    return df.drop_duplicates(key, keep="first")


def load_pair(file_a: str, file_b: str, col: str = "label", key: list[str] = KEY) -> pd.DataFrame:
    """Two annotator sheets joined on `key`: (sentence_id, aspect) for
    sentiment, sentence_id alone for the aspect itself.

    The join is inner: rows only one annotator labelled say nothing
    about agreement, and silently treating a missing label as a disagreement
    would understate kappa.
    """
    a = pd.read_csv(file_a, keep_default_na=False)
    b = pd.read_csv(file_b, keep_default_na=False)
    for name, df in (("--a", a), ("--b", b)):
        missing = [c for c in dict.fromkeys(key + [col]) if c not in df.columns]
        if missing:
            raise ValueError(f"{name} is missing column(s): {', '.join(missing)}")

    # A pair listed twice in one sheet (an aspect correction can make two
    # candidate rows the same pair) would be joined to the other sheet twice
    # and counted twice. Keep one copy, unless the copies disagree.
    a, b = _one_row_per_pair(a, col, "--a", key), _one_row_per_pair(b, col, "--b", key)
    cols = list(dict.fromkeys(key + [col]))
    merged = a[cols].merge(b[cols], on=key, suffixes=("_a", "_b"))
    if merged.empty:
        raise ValueError(f"no {tuple(key)} rows are present in both files")
    return merged.rename(columns={f"{col}_a": "rater_a", f"{col}_b": "rater_b"})


def load_columns(path: str, col_a: str, col_b: str) -> pd.DataFrame:
    df = pd.read_csv(path, keep_default_na=False)
    for c in (col_a, col_b):
        if c not in df.columns:
            raise ValueError(f"{path} has no column '{c}'. Columns: {list(df.columns)}")
    out = df[KEY + [col_a, col_b]].copy() if all(k in df.columns for k in KEY) else df[[col_a, col_b]].copy()
    return out.rename(columns={col_a: "rater_a", col_b: "rater_b"})


def score(pairs: pd.DataFrame, labels: list[str] = LABELS) -> dict:
    """Kappa over rows where BOTH raters gave a valid label (one of `labels`)."""
    df = pairs.copy()
    df["rater_a"] = _clean(df["rater_a"])
    df["rater_b"] = _clean(df["rater_b"])

    total = len(df)
    both = df[df["rater_a"].isin(labels) & df["rater_b"].isin(labels)]
    if both.empty:
        raise ValueError(
            f"no rows where both raters gave one of {labels}. "
            f"{total} row(s) were compared - is the label column filled in?")

    kappa = float(cohen_kappa_score(both["rater_a"], both["rater_b"], labels=labels))
    observed = float((both["rater_a"] == both["rater_b"]).mean())
    return {
        "n_compared": len(both),
        "n_skipped": total - len(both),
        "cohen_kappa": round(kappa, 4),
        "observed_agreement": round(observed, 4),
        "interpretation": interpret(kappa),
        "meets_target": kappa >= TARGET_KAPPA,
        "confusion": confusion_matrix(both["rater_a"], both["rater_b"], labels=labels),
        "labels": labels,
        "pairs": both,
    }


def report(result: dict, show_disagreements: int = 0) -> str:
    lines = [
        "Inter-annotator agreement",
        "=" * 46,
        f"Rows compared:        {result['n_compared']}",
        f"Rows skipped:         {result['n_skipped']}  (a rater left it blank or non-standard)",
        f"Observed agreement:   {result['observed_agreement']:.3f}",
        f"Cohen's kappa:        {result['cohen_kappa']:.3f}  - {result['interpretation']}",
        "",
    ]

    gap = result["observed_agreement"] - result["cohen_kappa"]
    if gap > 0.3:
        lines += [
            f"NOTE: raw agreement exceeds kappa by {gap:.2f}. Much of the agreement here is",
            "explained by the label distribution rather than by shared judgement - this is",
            "what a heavily neutral corpus looks like. Trust kappa, not the raw figure.",
            "",
        ]

    if result["meets_target"]:
        lines.append(f"Meets the >= {TARGET_KAPPA} target in docs/annotation-guideline.md. "
                     "Split the remaining rows.")
    else:
        lines += [
            f"BELOW the >= {TARGET_KAPPA} target in docs/annotation-guideline.md.",
            "Per the guideline this means the guideline is ambiguous somewhere, not that an",
            "annotator was careless. Find the disagreements (--show-disagreements), tighten",
            "the guideline, and re-label this sample before dividing up the rest.",
        ]

    labels = result.get("labels", LABELS)
    lines += ["", "Confusion matrix (rows = rater A, columns = rater B):", ""]
    if labels == LABELS:
        lines.append(" " * 12 + "".join(f"{c:>12s}" for c in LABELS))
        for label, row in zip(LABELS, result["confusion"]):
            lines.append(f"{label:>10s}  " + "".join(f"{v:>12d}" for v in row))
    else:   # eleven aspects: abbreviate the columns so the table fits a terminal
        pad = max(len(l) for l in labels)
        lines.append("Columns use the first five letters of each label.")
        lines.append(" " * (pad + 2) + "".join(f"{l[:5]:>7s}" for l in labels))
        for label, row in zip(labels, result["confusion"]):
            lines.append(f"{label:>{pad}s}  " + "".join(f"{v:>7d}" for v in row))

    if show_disagreements:
        d = result["pairs"]
        d = d[d["rater_a"] != d["rater_b"]]
        lines += ["", f"Disagreements ({len(d)} total, showing up to {show_disagreements}):", ""]
        for _, r in d.head(show_disagreements).iterrows():
            sid = r.get("sentence_id", "?")
            aspect = r.get("aspect", "?")
            lines.append(f"  {sid} / {aspect}: A={r['rater_a']}  B={r['rater_b']}")

    return "\n".join(lines)


def run(file_a: str | None = None, file_b: str | None = None, path: str | None = None,
        col_a: str = "label", col_b: str = "llm_prelabel",
        show_disagreements: int = 0, field: str = "label") -> dict:
    """`field` is what the two raters chose: "label" (sentiment, per
    (sentence, aspect) pair) or "aspect" (per sentence)."""
    if field not in ("label", "aspect"):
        raise ValueError(f"field must be 'label' or 'aspect', got {field!r}")
    labels = LABELS if field == "label" else aspect_keys()
    if file_a and file_b:
        pairs = load_pair(file_a, file_b, col=field, key=KEY if field == "label" else ASPECT_KEY)
    elif path:
        pairs = load_columns(path, col_a, col_b)
    else:
        raise ValueError("provide either --a and --b, or --file with --col-a/--col-b")

    result = score(pairs, labels)
    print(report(result, show_disagreements))
    return result


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Cohen's kappa between two sets of labels.")
    parser.add_argument("--a", dest="file_a", help="first annotator's CSV")
    parser.add_argument("--b", dest="file_b", help="second annotator's CSV")
    parser.add_argument("--file", dest="path", help="one CSV holding both label columns")
    parser.add_argument("--col-a", default="label")
    parser.add_argument("--col-b", default="llm_prelabel")
    parser.add_argument("--show-disagreements", type=int, default=0, metavar="N")
    parser.add_argument("--field", choices=["label", "aspect"], default="label",
                        help="what the raters chose: sentiment `label` (default) or the `aspect`")
    args = parser.parse_args()
    run(file_a=args.file_a, file_b=args.file_b, path=args.path,
        col_a=args.col_a, col_b=args.col_b, show_disagreements=args.show_disagreements,
        field=args.field)
