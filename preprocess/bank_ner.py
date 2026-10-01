"""
Bank entity recognition and resolution (DESIGN decision 18, PLAN section 7):
find the organisations a sentence mentions and resolve each to DBS, OCBC,
UOB or "not the bank".

Alias matching (`ingest.base.detect_banks`) treats any "DBS", "OCBC" or "UOB"
as the bank. That is wrong for the cases this module exists for:

- POSB is DBS's retail brand, and alias matching never sees it;
- Bank of Singapore and Great Eastern are OCBC subsidiaries;
- UOB Kay Hian and DBS Vickers are brokers, not the bank's own business
  (PLAN section 7; see RESOLUTION for the one line that decides this);
- "Aston Martin DBS" and "deep brain stimulation (DBS)" are not banks.

Recognition is spaCy's pretrained English pipeline with an entity ruler in
front of its statistical NER, plus a gazetteer fallback for names the
tokenizer glues to punctuation. On its own the pretrained model misses
lowercase "dbs" in Reddit text, tags "Kay Hian" as a person and keeps only
"Vickers" of "DBS Vickers"; the ruler marks those names first, and the
statistical model finds the rest. Resolution is a table, so changing what a
name counts as is one edit.

USAGE:
  python -m preprocess.bank_ner export-gold            # blank ~200-sentence gold sheet
  python -m preprocess.bank_ner evaluate --gold data/labeled/ner/gold_sheet.csv
  python -m preprocess.bank_ner corpus-diff            # where NER and alias matching disagree
"""

import argparse
import os
import re

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD_DIR = os.path.join(BASE_DIR, "data", "labeled", "ner")
BANKS = ("DBS", "OCBC", "UOB")
NOT_BANK = "NOT_BANK"

# Longest names first: the first rule whose pattern is found in a mention
# decides it. A mention matching none is not a bank mention at all.
RESOLUTION = [
    (r"aston\s+martin", NOT_BANK),
    (r"deep\s+brain|brain\s+stimulation", NOT_BANK),
    (r"kay\s*hian|\buobkh\b", NOT_BANK),          # UOB Kay Hian: a separate broker
    (r"vickers", NOT_BANK),                         # DBS Vickers: PLAN section 7 treats brokers as not the bank
    (r"bank\s+of\s+singapore", "OCBC"),             # OCBC's private bank
    (r"great\s+eastern", "OCBC"),                   # OCBC's insurer
    (r"\bposb\b", "DBS"),                           # DBS's retail brand
    (r"\bdbs\b|\bd05\b", "DBS"),
    (r"\bocbc\b|oversea-chinese|\bo39\b", "OCBC"),
    (r"\buob\b|united\s+overseas\s+bank|\bu11\b", "UOB"),
]
_RESOLUTION = [(re.compile(p, re.IGNORECASE), target) for p, target in RESOLUTION]

# Names the ruler marks before the statistical model runs. Token patterns
# with LOWER match any casing.
_RULER_PHRASES = [
    ("ORG", ["uob", "kay", "hian"]), ("ORG", ["kay", "hian"]), ("ORG", ["uobkh"]),
    ("ORG", ["dbs", "vickers"]), ("ORG", ["bank", "of", "singapore"]), ("ORG", ["great", "eastern"]),
    ("ORG", ["posb"]), ("ORG", ["dbs"]), ("ORG", ["ocbc"]), ("ORG", ["uob"]),
    ("ORG", ["united", "overseas", "bank"]), ("ORG", ["oversea", "-", "chinese"]),
    ("PRODUCT", ["aston", "martin", "dbs"]),
    ("PRODUCT", ["deep", "brain", "stimulation"]),
]
_LABELS = {"ORG", "PRODUCT"}

_nlp = None


def nlp():
    """spaCy's small English model with the bank ruler before its NER. Loaded once."""
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm", disable=["lemmatizer"])
        ruler = _nlp.add_pipe("entity_ruler", before="ner")
        ruler.add_patterns([{"label": label, "pattern": [{"LOWER": t} for t in toks]}
                            for label, toks in _RULER_PHRASES])
    return _nlp


def resolve(mention: str) -> str | None:
    """DBS, OCBC, UOB, NOT_BANK, or None if the mention is no bank-like name."""
    for pattern, target in _RESOLUTION:
        if pattern.search(mention):
            return target
    return None


def mentions(doc) -> list[tuple[str, str, str]]:
    """(text, entity label, resolution) for each organisation-like entity that resolves."""
    out = []
    for ent in doc.ents:
        if ent.label_ in _LABELS:
            target = resolve(ent.text)
            if target is not None:
                out.append((ent.text, ent.label_, target))
    return out


# The fallback: bank names glued to punctuation ("DBS/", "OCBC+", "UOB$",
# "D05.SI", "www.ocbc.com") become one token that neither the ruler nor the
# statistical model sees. Any such name outside an entity already resolved
# still counts, unless it sits inside a not-the-bank entity ("DBS Vickers").
_FALLBACK = re.compile(r"\b(?:posb|dbs|d05|ocbc|o39|uob|u11)\b", re.IGNORECASE)
# Not-the-bank names found in the raw text for the same reason: "DBS Vickers/"
# tokenizes as "DBS" + "Vickers/", so the ruler never sees the broker.
_NOT_BANK_TEXT = re.compile(r"\bdbs\W{0,2}vickers|\buob\W{0,2}kay\W{0,2}hian|\bkay\W{0,2}hian|\buobkh\b"
                            r"|aston\W+martin\W+dbs|deep\W+brain\W+stimulation", re.IGNORECASE)


def banks_from_doc(doc) -> list[str]:
    blocked = [m.span() for m in _NOT_BANK_TEXT.finditer(doc.text)]
    inside = lambda pos, spans: any(s <= pos < e for s, e in spans)
    found, covered = set(), []
    for ent in doc.ents:
        if ent.label_ in _LABELS and not inside(ent.start_char, blocked):
            target = resolve(ent.text)
            if target is not None:
                covered.append((ent.start_char, ent.end_char))
                if target != NOT_BANK:
                    found.add(target)
    for m in _FALLBACK.finditer(doc.text):
        if not inside(m.start(), covered) and not inside(m.start(), blocked):
            found.add(resolve(m.group()))
    return [b for b in BANKS if b in found]


def banks_in(text: str) -> list[str]:
    """The banks a sentence is about, in the order DBS, OCBC, UOB."""
    return banks_from_doc(nlp()(text or ""))


def banks_in_many(texts: list[str], batch_size: int = 256) -> list[list[str]]:
    return [banks_from_doc(doc) for doc in nlp().pipe((t or "" for t in texts), batch_size=batch_size)]


# --- the gold sheet ----------------------------------------------------------

# Strata for the gold set, weighted to the cases alias matching gets wrong
# (DESIGN decision 18), plus random sentences as the ordinary case.
GOLD_STRATA = [
    ("posb", "text LIKE '%POSB%'", 30),
    ("kay_hian", "text LIKE '%Kay Hian%'", 30),
    ("vickers", "text LIKE '%Vickers%'", 30),
    ("bank_of_singapore", "text LIKE '%Bank of Singapore%'", 20),
    ("great_eastern", "text LIKE '%Great Eastern%'", 30),
    ("lowercase_dbs", "text GLOB '*dbs*' AND text NOT GLOB '*DBS*'", 20),
    ("aston_martin", "text LIKE '%Aston Martin%'", 5),
    ("random", "1 = 1", 40),
]

GOLD_README = """# Bank NER gold set

For each sentence, write in `gold_banks` which of DBS, OCBC and UOB the
sentence is about as a bank, separated by `;` (e.g. `DBS;UOB`), or leave it
empty if it is about none of them. Then put your role in `annotator`.

Rules (PLAN section 7, DESIGN decision 18):

- POSB counts as DBS. Bank of Singapore and Great Eastern count as OCBC.
- UOB Kay Hian and DBS Vickers are brokers: they do NOT count as the bank.
  If the team decides DBS Vickers should count as DBS, change the `vickers`
  line in `preprocess/bank_ner.py` RESOLUTION and say so in `notes`.
- "Aston Martin DBS" and medical DBS (deep brain stimulation) are not banks.
- A bank named only as a place or a payment rail ("paid via DBS PayNow")
  still counts: this task is about which bank is named, not about relevance.

`case` is the sampling stratum, not a hint about the answer. Don't look at
what any tool predicts before you finish.

Score it with:

    .venv-plp/bin/python3 -m preprocess.bank_ner evaluate --gold data/labeled/ner/gold_sheet.csv
"""


def draw_gold(conn, seed: int = 2026) -> pd.DataFrame:
    rows, taken = [], set()
    for case, where, n in GOLD_STRATA:
        df = pd.read_sql(f"SELECT sentence_id, source, text FROM sentences WHERE {where} ORDER BY sentence_id", conn)
        df = df[~df["sentence_id"].isin(taken)].drop_duplicates("text")
        df = df.sample(n=min(n, len(df)), random_state=seed)
        taken.update(df["sentence_id"])
        rows.append(df.assign(case=case))
    out = pd.concat(rows, ignore_index=True)
    out = out.sample(frac=1, random_state=seed).reset_index(drop=True)   # strata mixed, so order hints nothing
    return out.assign(gold_banks="", annotator="", notes="")[
        ["sentence_id", "case", "source", "text", "gold_banks", "annotator", "notes"]]


# --- evaluation --------------------------------------------------------------

def parse_banks(cell) -> set[str]:
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return set()
    parts = {p.strip().upper() for p in str(cell).replace(",", ";").split(";") if p.strip()}
    unknown = parts - set(BANKS)
    if unknown:
        raise ValueError(f"unknown bank(s) {sorted(unknown)} in gold cell {cell!r}")
    return parts


def prf(gold: list[set], pred: list[set]) -> dict:
    """Micro precision, recall and F1 over (sentence, bank) pairs, plus exact-set accuracy."""
    tp = sum(len(g & p) for g, p in zip(gold, pred))
    fp = sum(len(p - g) for g, p in zip(gold, pred))
    fn = sum(len(g - p) for g, p in zip(gold, pred))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    exact = sum(g == p for g, p in zip(gold, pred)) / len(gold) if gold else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "exact": exact, "n": len(gold)}


def evaluate(gold_df: pd.DataFrame) -> pd.DataFrame:
    """Alias matching and NER against the gold sets, overall and per stratum."""
    from ingest.base import detect_banks
    labelled = gold_df[gold_df["annotator"].fillna("").astype(str).str.strip() != ""].copy()
    if labelled.empty:
        raise ValueError("no labelled rows: fill `gold_banks` and `annotator` first")
    gold = [parse_banks(c) for c in labelled["gold_banks"]]
    alias = [set(detect_banks(t)) for t in labelled["text"]]
    ner = [set(b) for b in banks_in_many(labelled["text"].tolist())]
    rows = []
    for case in ["ALL"] + sorted(labelled["case"].unique()):
        idx = [i for i, c in enumerate(labelled["case"]) if case == "ALL" or c == case]
        for name, pred in (("alias matching", alias), ("NER", ner)):
            m = prf([gold[i] for i in idx], [pred[i] for i in idx])
            rows.append({"case": case, "method": name, **m})
    return pd.DataFrame(rows)


def corpus_diff(conn) -> pd.DataFrame:
    """Every sentence where NER and alias matching name different banks (reads only)."""
    from ingest.base import detect_banks
    df = pd.read_sql("SELECT sentence_id, source, bank, text FROM sentences", conn)
    df["alias"] = [";".join(detect_banks(t)) for t in df["text"]]
    df["ner"] = [";".join(b) for b in banks_in_many(df["text"].tolist())]
    return df[df["alias"] != df["ner"]]


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export-gold")
    ex.add_argument("--seed", type=int, default=2026)
    ev = sub.add_parser("evaluate")
    ev.add_argument("--gold", default=os.path.join(GOLD_DIR, "gold_sheet.csv"))
    sub.add_parser("corpus-diff")
    args = p.parse_args()

    if args.cmd == "evaluate":
        res = evaluate(pd.read_csv(args.gold, keep_default_na=False))
        print(res.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
        return

    from ingest.db import get_connection
    conn = get_connection()
    try:
        if args.cmd == "export-gold":
            os.makedirs(GOLD_DIR, exist_ok=True)
            path = os.path.join(GOLD_DIR, "gold_sheet.csv")
            if os.path.exists(path):
                raise SystemExit(f"{path} exists; it may hold labels. Move it before exporting a new one.")
            sheet = draw_gold(conn, args.seed)
            sheet.to_csv(path, index=False)
            with open(os.path.join(GOLD_DIR, "README.md"), "w") as f:
                f.write(GOLD_README)
            print(f"{len(sheet)} sentences -> {path}")
            print(sheet["case"].value_counts().to_string())
        else:
            diff = corpus_diff(conn)
            path = os.path.join(BASE_DIR, "data", "preview", "ner_corpus_diff.csv")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            diff.to_csv(path, index=False)
            print(f"{len(diff)} sentences where NER and alias matching differ -> {path}")
            print(pd.crosstab(diff["alias"].replace("", "(none)"), diff["ner"].replace("", "(none)")).to_string())
    finally:
        conn.close()


if __name__ == "__main__":
    main()
