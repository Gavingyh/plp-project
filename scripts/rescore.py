"""
Apply the team's aspect and sentiment decisions to a database: the re-score
step planned for 12-18 Oct (team to-do). Build and check it on a copy;
applying it to data/plp.db is the team's decision.

  1. Aspects (--aspects llm): every sentence's centroid assignments are
     replaced by the LLM's one aspect, read from the classifier's cache for
     the current prompt (aspects/llm_classify.py). Every sentence must have
     an answer; nothing is classified here.
  2. Base FinBERT rows for the new pairs: base FinBERT never sees the aspect,
     so each sentence's existing label is copied to its new pair.
  3. Fine-tuned rows (--finetuned): the three seeds' averaged probabilities
     with the neutral margin, for every assigned pair, under their own
     model_version. Probabilities come from aggregate.preview's scores cache,
     so pairs the full-corpus preview scored are not scored again (on the
     same device: pass --cpu to reuse the CPU run).
  4. Scores of pairs no longer assigned are deleted; the index ignores them
     anyway.
  5. Checks: every sentence has an aspect (exactly one with --aspects llm),
     and every assigned pair has a row for every model version present.
  6. The index is recomputed (aggregate.index.rebuild).

Steps 1-6 are one transaction: if a check fails or anything raises, nothing
is written. On data/plp.db (--real-db) a backup copy is made first, in
data/snapshots/. Readers serve the version named in config/model_version.py;
switching it, and setting `assignment_method: llm` in config/aspects.yaml,
are the follow-up changes it prints. The headlines it prints should match
the preview (docs/evidence/index-preview-2026-10-01.md).

Dry run unless --apply. Refuses data/plp.db unless --real-db is given too.

USAGE:
  HF_HUB_OFFLINE=1 .venv-plp/bin/python3 scripts/rescore.py --db /tmp/plp-rescore.db --fresh-copy \\
      --aspects llm --finetuned --margin 0.13 --cpu            # dry run on a fresh copy
  ... add --apply to write the copy
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

import ingest.db  # noqa: E402

BASE_VERSION = "finbert-base-zeroshot-v1"
REAL_DB = ingest.db.DB_PATH
BACKUP_DIR = os.path.join(os.path.dirname(REAL_DB), "snapshots")


class CheckFailed(Exception):
    """A check after steps 1-4 failed; the transaction is rolled back."""


def finetuned_version(model_dirs: list[str], margin: float) -> str:
    """A tag naming the models' experiment folder, their number and the
    margin, e.g. finbert-finetuned-2026-10-01-3seed-m0.13."""
    parts = os.path.normpath(model_dirs[0]).split(os.sep)
    exp = next((p for p in parts if p.startswith("experiments-")), "custom").removeprefix("experiments-")
    return f"finbert-finetuned-{exp}-{len(model_dirs)}seed-m{margin:g}"


def fresh_copy(dst: str, src: str = REAL_DB) -> None:
    """Copy the database through SQLite's backup API, read-only on the source,
    so rows still in its write-ahead log are included."""
    for path in (dst, dst + "-wal", dst + "-shm"):    # a stale log would replay onto the new copy
        if os.path.exists(path):
            os.remove(path)
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    s.backup(d)
    d.close()
    s.close()


def llm_aspects(conn, model: str, cache_path: str | None = None) -> dict[str, str]:
    """Every sentence's aspect from the classifier's cache for the current
    prompt. Refuses if any sentence has no answer or an unknown aspect."""
    from aspects.llm_classify import answer_cache_path, aspect_keys
    keys = set(aspect_keys())
    path = cache_path or answer_cache_path(model)
    answers = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                answers[r["sentence_id"]] = r["aspect"]
    ids = [r[0] for r in conn.execute("SELECT sentence_id FROM sentences")]
    missing = [i for i in ids if i not in answers]
    if missing:
        raise SystemExit(f"{len(missing)} of {len(ids)} sentences have no answer in {path}; "
                         f"run `python -m aspects.llm_classify --corpus` first")
    unknown = {answers[i] for i in ids} - keys
    if unknown:
        raise SystemExit(f"unknown aspects in {path}: {sorted(unknown)}")
    return {i: answers[i] for i in ids}


def check_base_is_per_sentence(conn) -> None:
    """Base FinBERT scores a sentence once, so all its pairs must carry the
    same label and confidence; copying them to a new pair relies on it."""
    n = conn.execute("""SELECT COUNT(*) FROM (SELECT sentence_id FROM aspect_sentiment WHERE model_version = ?
                        GROUP BY sentence_id HAVING COUNT(DISTINCT label) > 1 OR COUNT(DISTINCT confidence) > 1)""",
                     (BASE_VERSION,)).fetchone()[0]
    if n:
        raise SystemExit(f"{n} sentences have different base FinBERT labels or confidences on different "
                         f"pairs; can't copy one to a new pair")


def assigned_pairs(conn, aspects: dict[str, str] | None) -> pd.DataFrame:
    """(sentence_id, aspect, text) for the pairs that will be assigned."""
    texts = pd.read_sql("SELECT sentence_id, text FROM sentences", conn)
    if aspects is not None:
        pairs = pd.DataFrame({"sentence_id": list(aspects), "aspect": list(aspects.values())})
    else:
        pairs = pd.read_sql("SELECT sentence_id, aspect FROM sentence_aspects", conn)
    return pairs.merge(texts, on="sentence_id")


def problems(conn, one_aspect_each: bool) -> list[str]:
    """What must hold before the step may commit; empty when all is well."""
    q = lambda sql, *p: conn.execute(sql, p).fetchone()[0]  # noqa: E731
    out = []
    n = q("SELECT COUNT(*) FROM sentences s WHERE NOT EXISTS "
          "(SELECT 1 FROM sentence_aspects a WHERE a.sentence_id = s.sentence_id)")
    if n:
        out.append(f"{n} sentences have no aspect")
    if one_aspect_each:
        n = q("SELECT COUNT(*) FROM (SELECT sentence_id FROM sentence_aspects GROUP BY 1 HAVING COUNT(*) > 1)")
        if n:
            out.append(f"{n} sentences have more than one aspect")
    for (version,) in conn.execute("SELECT DISTINCT model_version FROM aspect_sentiment").fetchall():
        n = q("""SELECT COUNT(*) FROM sentence_aspects a WHERE NOT EXISTS (
                     SELECT 1 FROM aspect_sentiment ase WHERE ase.sentence_id = a.sentence_id
                       AND ase.aspect = a.aspect AND ase.model_version = ?)""", version)
        if n:
            out.append(f"{n} assigned pairs have no {version} score"
                       + ("" if version == BASE_VERSION else " (rescore it too: --finetuned with its models)"))
    return out


def apply(conn, aspects: dict[str, str] | None, finetuned: pd.DataFrame | None, version: str | None,
          now: str) -> dict:
    """Steps 1-6 in one transaction. `finetuned` holds (sentence_id, aspect,
    label, confidence) for every assigned pair. Raises CheckFailed, writing
    nothing, if a check fails."""
    import aggregate.index
    aggregate.index._ensure_schema(conn)        # it commits, so before the transaction starts
    out = {}
    with conn:
        if aspects is not None:
            out["assignments_removed"] = conn.execute("DELETE FROM sentence_aspects").rowcount
            conn.executemany("INSERT INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) "
                             "VALUES (?, ?, 1.0, ?)", [(s, a, now) for s, a in aspects.items()])
            out["assignments_written"] = len(aspects)
            out["base_rows_copied"] = conn.execute("""
                INSERT OR IGNORE INTO aspect_sentiment
                    (sentence_id, aspect, label, confidence, model_version, scored_at)
                SELECT asg.sentence_id, asg.aspect, b.label, b.confidence, ?, ?
                FROM sentence_aspects asg
                JOIN (SELECT sentence_id, MIN(label) AS label, MAX(confidence) AS confidence
                      FROM aspect_sentiment WHERE model_version = ? GROUP BY sentence_id) b
                  ON b.sentence_id = asg.sentence_id""", (BASE_VERSION, now, BASE_VERSION)).rowcount
        if finetuned is not None:
            conn.executemany("INSERT OR REPLACE INTO aspect_sentiment "
                             "(sentence_id, aspect, label, confidence, model_version, scored_at) "
                             "VALUES (?, ?, ?, ?, ?, ?)",
                             [(r.sentence_id, r.aspect, r.label, round(float(r.confidence), 4), version, now)
                              for r in finetuned.itertuples(index=False)])
            out["finetuned_rows_written"] = len(finetuned)
        out["stale_scores_deleted"] = conn.execute("""
            DELETE FROM aspect_sentiment WHERE NOT EXISTS (
                SELECT 1 FROM sentence_aspects asg
                WHERE asg.sentence_id = aspect_sentiment.sentence_id AND asg.aspect = aspect_sentiment.aspect)
        """).rowcount
        found = problems(conn, one_aspect_each=aspects is not None)
        if found:
            raise CheckFailed("; ".join(found))
        out["index_rows"] = aggregate.index.rebuild(conn)
    return out


def summary(conn) -> dict:
    """Counts and each version's headline per bank, for the record."""
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    rows = conn.execute("SELECT model_version, bank, score, n FROM sentiment_index WHERE aspect = 'ALL' "
                        "AND source = 'ALL' AND window = 'all_time' ORDER BY 1, 2").fetchall()
    return {
        "sentences": q("SELECT COUNT(*) FROM sentences"),
        "assigned_pairs": q("SELECT COUNT(*) FROM sentence_aspects"),
        "scored_pairs_per_version": dict(conn.execute(
            "SELECT model_version, COUNT(*) FROM aspect_sentiment GROUP BY 1").fetchall()),
        "headline": {f"{v} {b}": (s, n) for v, b, s, n in rows},
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--db", required=True, help="the database to change (a copy, unless --real-db)")
    p.add_argument("--fresh-copy", action="store_true", help=f"first copy {REAL_DB} to --db")
    p.add_argument("--aspects", choices=["keep", "llm"], default="keep")
    p.add_argument("--llm-model", default="llama3.1:8b")
    p.add_argument("--finetuned", action="store_true", help="add the fine-tuned models' scores")
    p.add_argument("--models", nargs="+", default=None, help="fine-tuned model folders (default: the 1 Oct seeds)")
    p.add_argument("--margin", type=float, default=0.13)
    p.add_argument("--version", default=None, help="model_version tag for the fine-tuned rows")
    p.add_argument("--cpu", action="store_true", help="score on the CPU (and reuse the CPU preview's cache)")
    p.add_argument("--apply", action="store_true", help="write; without it, only report")
    p.add_argument("--real-db", action="store_true", help=f"allow --db to be {REAL_DB}")
    args = p.parse_args(argv)

    db = os.path.realpath(args.db)
    real = db == os.path.realpath(REAL_DB)
    if real and not args.real_db:
        print(f"refusing to change {REAL_DB}: work on a copy (--fresh-copy), or add --real-db once the "
              f"team has decided", file=sys.stderr)
        return 2
    if args.fresh_copy:
        if real:
            print("--fresh-copy can't copy the database onto itself", file=sys.stderr)
            return 2
        fresh_copy(db)
    if not os.path.exists(db):
        print(f"no database at {db}", file=sys.stderr)
        return 2
    ingest.db.DB_PATH = db                     # every module below reads this
    if args.cpu:
        import train.evaluate
        train.evaluate.best_device = lambda: "cpu"

    conn = sqlite3.connect(db)
    aspects = None
    if args.aspects == "llm":
        aspects = llm_aspects(conn, args.llm_model)
        check_base_is_per_sentence(conn)
    pairs = assigned_pairs(conn, aspects)
    print(f"database: {db}\nsentences: {pairs['sentence_id'].nunique()}; pairs after the step: {len(pairs)}")

    finetuned, version = None, None
    if args.finetuned:
        import aggregate.preview as pv
        from config.model_version import FINETUNED
        models = args.models or pv.DEFAULT_MODELS
        version = args.version or finetuned_version(models, args.margin)
        if version not in FINETUNED:
            print(f"note: {version} is not in FINETUNED in config/model_version.py; add it before serving "
                  f"it, or new sentences won't get its scores")
        cache = pv.scores_cache_path(models)
        if not args.apply:
            done = set()
            if os.path.exists(cache):
                with open(cache) as f:
                    done = {(r["sentence_id"], r["aspect"]) for r in map(json.loads, f)}
            todo = sum((s, a) not in done for s, a in zip(pairs["sentence_id"], pairs["aspect"]))
            print(f"fine-tuned: {version}; {len(pairs) - todo} pairs already scored in {cache}, {todo} to score")
        else:
            finetuned = pv.finetuned_labels(pairs, models, cache, args.margin)

    if not args.apply:
        conn.close()
        print("dry run: nothing written (add --apply)")
        return 0

    if real:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup = os.path.join(BACKUP_DIR, f"plp-before-rescore-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.db")
        fresh_copy(backup, src=db)
        print(f"backup: {backup} (to undo: stop the API, then copy it over {db})")

    from ingest.db import now_iso
    try:
        print(json.dumps(apply(conn, aspects, finetuned, version, now_iso()), indent=2))
    except CheckFailed as e:
        print(f"check failed, nothing written: {e}", file=sys.stderr)
        return 1
    print(json.dumps(summary(conn), indent=2))
    conn.close()
    if version:
        print(f"\nTo serve the new scores: MODEL_VERSION = \"{version}\" in config/model_version.py")
    if args.aspects == "llm":
        print("So new sentences get the LLM's aspect: assignment_method: llm in config/aspects.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
