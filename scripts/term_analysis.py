"""
Which words set one group of sentences apart from another.

The Text Analytics module's data-understanding step (term weighting, word
clouds, contrasting two groups) applied to the corpus. It answers questions the
report's data section only states: how Reddit differs from the banks' own
earnings text, what is distinctive about each bank, and which words mark
negative against positive sentences within a source.

Method: the log-odds ratio with an informative Dirichlet prior (Monroe,
Colaresi and Quinn, 2008). Each word's difference in use between two groups is
turned into a z-score, with the whole corpus as the prior, so rare words are not
mistaken for distinctive ones and common words are not drowned out. A
z-score above about 2 is a difference unlikely to be chance.

It reads the database read-only (set PLP_DB_PATH to use a copy) and writes
nothing to it.

USAGE:
  python -m scripts.term_analysis                      # all comparisons, tables only
  python -m scripts.term_analysis --charts             # also bar charts (needs matplotlib)
  python -m scripts.term_analysis --model-version finbert-base-zeroshot-v1
Output goes to data/eval/term_analysis/ (term_analysis.md plus one CSV per
comparison). Run it on the database that is submitted: every figure in the
report must come from that file.
"""

import argparse
import csv
import math
import os
import re
import sqlite3
from collections import Counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(BASE_DIR, "data", "eval", "term_analysis")

_WORD = re.compile(r"[a-z][a-z'&-]{2,}")
# Words that name the banks or the subject of every sentence say nothing about
# one group against another.
_SUBJECT_WORDS = {"dbs", "ocbc", "uob", "bank", "banks", "banking", "singapore", "sg", "group", "posb"}
_URLISH = re.compile(r"https?://\S+|www\.\S+")


def _stop_words() -> frozenset:
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    return frozenset(ENGLISH_STOP_WORDS) | _SUBJECT_WORDS


def tokenize(text: str, stop: frozenset | None = None) -> list[str]:
    """Lower-case words of three letters or more, without links or stop words."""
    stop = stop if stop is not None else _stop_words()
    return [w for w in _WORD.findall(_URLISH.sub(" ", str(text).lower())) if w not in stop]


def count_words(texts, stop: frozenset | None = None) -> Counter:
    counts: Counter = Counter()
    for t in texts:
        counts.update(tokenize(t, stop))
    return counts


def log_odds(group_a: Counter, group_b: Counter, prior: Counter, alpha0: float = 1000.0,
             min_count: int = 5) -> list[tuple[str, float, int, int]]:
    """Words ranked by how much more group A uses them than group B.

    Returns (word, z, count in A, count in B), highest z first (most A-like);
    the lowest z values are the most B-like words. `prior` is the background
    count of every word, scaled to alpha0 pseudo-counts in total. Words used
    fewer than `min_count` times across both groups are left out.
    """
    n_a, n_b = sum(group_a.values()), sum(group_b.values())
    total = sum(prior.values()) or 1
    out = []
    for w in set(group_a) | set(group_b):
        y_a, y_b = group_a.get(w, 0), group_b.get(w, 0)
        if y_a + y_b < min_count:
            continue
        a_w = alpha0 * prior.get(w, 0) / total
        if a_w <= 0:
            a_w = alpha0 / total   # a word the prior lacks still gets a floor
        delta = (math.log((y_a + a_w) / (n_a + alpha0 - y_a - a_w))
                 - math.log((y_b + a_w) / (n_b + alpha0 - y_b - a_w)))
        var = 1.0 / (y_a + a_w) + 1.0 / (y_b + a_w)
        out.append((w, delta / math.sqrt(var), y_a, y_b))
    out.sort(key=lambda r: r[1], reverse=True)
    return out


def top_both_ways(result: list, k: int = 15) -> tuple[list, list]:
    """The k most A-like words, and the k most B-like (most negative z first)."""
    return result[:k], sorted(result[-k:], key=lambda r: r[1])


# --- data ----------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    from ingest.db import DB_PATH
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def load_sentences(conn) -> list[dict]:
    rows = conn.execute("SELECT sentence_id, bank, source, text FROM sentences").fetchall()
    return [{"sentence_id": r[0], "bank": r[1], "source": r[2], "text": r[3]} for r in rows]


def load_labels(conn, model_version: str) -> dict[str, str]:
    """One sentiment label per sentence: the pair with the highest confidence,
    as the headline index counts each sentence once."""
    rows = conn.execute("SELECT sentence_id, label, confidence FROM aspect_sentiment "
                        "WHERE model_version = ?", (model_version,)).fetchall()
    best: dict[str, tuple] = {}
    for sid, label, conf in rows:
        if sid not in best or conf > best[sid][1]:
            best[sid] = (label, conf)
    return {sid: v[0] for sid, v in best.items()}


def load_aspects(conn) -> dict[str, set]:
    out: dict[str, set] = {}
    for sid, aspect in conn.execute("SELECT sentence_id, aspect FROM sentence_aspects"):
        out.setdefault(sid, set()).add(aspect)
    return out


# --- comparisons -----------------------------------------------------------------------

def _write_csv(path: str, result: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["word", "z", "count_a", "count_b"])
        for word, z, a, b in result:
            w.writerow([word, round(z, 3), a, b])


def _table(title: str, name_a: str, name_b: str, n_a: int, n_b: int, result: list, k: int) -> str:
    top_a, top_b = top_both_ways(result, k)
    lines = [f"### {title}", "",
             f"{name_a}: {n_a:,} sentences. {name_b}: {n_b:,} sentences. "
             "Words with a z-score above 2 or below -2 differ more than chance would give.", "",
             f"| rank | more {name_a} (z) | more {name_b} (z) |", "|---|---|---|"]
    for i in range(k):
        a = f"{top_a[i][0]} ({top_a[i][1]:.1f})" if i < len(top_a) else ""
        b = f"{top_b[i][0]} ({top_b[i][1]:.1f})" if i < len(top_b) else ""
        lines.append(f"| {i + 1} | {a} | {b} |")
    return "\n".join(lines) + "\n"


def _chart(path: str, title: str, name_a: str, name_b: str, result: list, k: int = 12) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    top_a, top_b = top_both_ways(result, k)
    rows = list(reversed(top_b)) + list(reversed(top_a))
    fig, ax = plt.subplots(figsize=(7, 0.28 * len(rows) + 1.2))
    ax.barh([r[0] for r in rows], [r[1] for r in rows],
            color=["#c0504d" if r[1] < 0 else "#4f81bd" for r in rows])
    ax.axvline(0, color="#444", lw=0.8)
    ax.set_xlabel(f"log-odds z-score  (left: more {name_b}, right: more {name_a})")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def run(out_dir: str, model_version: str, k: int, charts: bool, min_count: int) -> str:
    os.makedirs(out_dir, exist_ok=True)
    stop = _stop_words()
    conn = _connect()
    try:
        sentences = load_sentences(conn)
        labels = load_labels(conn, model_version)
        aspects = load_aspects(conn)
    finally:
        conn.close()

    prior = count_words((s["text"] for s in sentences), stop)
    sections = [f"# Distinctive terms\n\n{len(sentences):,} sentences; sentiment labels from "
                f"`{model_version}`; words seen fewer than {min_count} times are left out.\n"]

    def compare(slug, title, name_a, name_b, group_a, group_b):
        if len(group_a) < 30 or len(group_b) < 30:
            sections.append(f"### {title}\n\nSkipped: fewer than 30 sentences in a group.\n")
            return
        result = log_odds(count_words((s["text"] for s in group_a), stop),
                          count_words((s["text"] for s in group_b), stop), prior, min_count=min_count)
        _write_csv(os.path.join(out_dir, f"{slug}.csv"), result)
        sections.append(_table(title, name_a, name_b, len(group_a), len(group_b), result, k))
        if charts:
            _chart(os.path.join(out_dir, f"{slug}.png"), title, name_a, name_b, result)

    reddit = [s for s in sentences if s["source"] == "arctic_shift"]
    earnings = [s for s in sentences if s["source"] == "earnings"]
    compare("reddit_vs_earnings", "Reddit against the banks' earnings text",
            "Reddit", "earnings", reddit, earnings)

    for bank in ("DBS", "OCBC", "UOB"):
        mine = [s for s in reddit if s["bank"] == bank]
        rest = [s for s in reddit if s["bank"] != bank]
        compare(f"reddit_{bank.lower()}_vs_other_banks", f"{bank} on Reddit against the other two banks",
                bank, "the other two", mine, rest)

    for source_name, group in (("Reddit", reddit), ("earnings", earnings)):
        neg = [s for s in group if labels.get(s["sentence_id"]) == "negative"]
        pos = [s for s in group if labels.get(s["sentence_id"]) == "positive"]
        compare(f"{source_name.lower()}_negative_vs_positive", f"{source_name}: negative against positive sentences",
                "negative", "positive", neg, pos)

    in_reddit_with_aspect = {a for a in {x for v in aspects.values() for x in v}}
    for aspect in sorted(in_reddit_with_aspect):
        mine = [s for s in sentences if aspect in aspects.get(s["sentence_id"], ())]
        rest = [s for s in sentences if aspect not in aspects.get(s["sentence_id"], ())]
        compare(f"aspect_{aspect}", f"Aspect {aspect} against all other sentences",
                aspect, "the rest", mine, rest)

    report = "\n".join(sections)
    with open(os.path.join(out_dir, "term_analysis.md"), "w", encoding="utf-8") as f:
        f.write(report)
    return report


def main():
    from config import model_version as mv
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--model-version", default=mv.MODEL_VERSION,
                   help="whose sentiment labels to contrast (default: the model the index serves)")
    p.add_argument("--top", type=int, default=15, help="words shown per side")
    p.add_argument("--min-count", type=int, default=5)
    p.add_argument("--charts", action="store_true", help="write a bar chart per comparison (matplotlib)")
    args = p.parse_args()
    report = run(args.out, args.model_version, args.top, args.charts, args.min_count)
    print(report[:3000])
    print(f"\nFull output in {args.out}")


if __name__ == "__main__":
    main()
