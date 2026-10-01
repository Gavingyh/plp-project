"""
Flags sentences that are extraction debris rather than prose: earnings-PDF
table rows (mostly figures) and letter-spaced text ("N e t p ro fit"). Dry
run only: it reports what it would flag and changes no data.

Deliberately narrow. On 2026-10-01 broader rules were tried and rejected:
"fewer than 6 words" would drop "Cards were strong at 17%." and "bought DBS
at $37.3 this morning" (18 of the 34 short labelled sentences carry
sentiment), and a low share of letters catches real opinions with numbers in
them ("UOB Evol is nerfing the cashback from 40/600 (6.7%) to 30/800").

USAGE:
  python -m preprocess.fragments            # dry-run report over the corpus and labelled set
"""

import argparse
import os
import re

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS_PATH = os.path.join(BASE_DIR, "data", "labeled", "candidates.csv")

_WORD = re.compile(r"[A-Za-z]{2,}")
_TOKEN = re.compile(r"\S+")
MIN_TOKENS = 8              # shorter sentences are never flagged
GARBLE_SINGLE_SHARE = 0.4   # share of one-letter tokens above which text is letter-spaced
TABLE_NUMERIC_RATIO = 1.5   # numeric tokens per word at or above which a line is a table row


PDF_SOURCES = {"earnings"}   # debris comes from PDF extraction


def fragment_reason(text: str, source: str | None = None) -> str | None:
    """'garbled', 'table', or None for prose. With a source given, only
    PDF-extracted text is checked: Reddit users write rows of figures on
    purpose ("SSB 3.3% $200k = $6.6k, UOB 4% $150k = $6k")."""
    if source is not None and source not in PDF_SOURCES:
        return None
    tokens = _TOKEN.findall(text or "")
    n = len(tokens)
    if n < MIN_TOKENS:
        return None
    single = sum(len(t) == 1 and t.isalpha() for t in tokens)
    if single / n > GARBLE_SINGLE_SHARE:
        return "garbled"
    words = len(_WORD.findall(text))
    numeric = sum(any(c.isdigit() for c in t) for t in tokens)
    if numeric >= TABLE_NUMERIC_RATIO * max(words, 1):
        return "table"
    return None


def main():
    argparse.ArgumentParser(description=__doc__.split("\n\n")[0]).parse_args()
    from ingest.db import get_connection
    conn = get_connection()
    try:
        corpus = pd.read_sql("SELECT sentence_id, source, text FROM sentences", conn)
    finally:
        conn.close()
    corpus["flag"] = [fragment_reason(t, s) for t, s in zip(corpus["text"], corpus["source"])]
    print(f"Corpus: {corpus['flag'].notna().sum()} of {len(corpus)} sentences would be flagged "
          f"({100 * corpus['flag'].notna().mean():.2f}%)")
    print(pd.crosstab(corpus["source"], corpus["flag"].fillna("kept")).to_string())
    for reason in ("table", "garbled"):
        sample = corpus[corpus["flag"] == reason]["text"].str[:90]
        print(f"\n{reason} examples:")
        for t in sample.head(5):
            print("  ", t)

    labels = pd.read_csv(LABELS_PATH)
    labels["flag"] = [fragment_reason(t, s) for t, s in zip(labels["text"], labels["source"])]
    flagged = labels[labels["flag"].notna()]
    print(f"\nLabelled set: {len(flagged)} of {len(labels)} rows would be flagged")
    for _, r in flagged.iterrows():
        print(f"   {r['flag']} | gold {r['label']} | {r['split']} | {r['text'][:100]}")


if __name__ == "__main__":
    main()
