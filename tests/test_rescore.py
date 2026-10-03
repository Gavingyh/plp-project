"""Tests for scripts/rescore.py: applying the aspect and sentiment decisions to a copy."""

import importlib.util
import json
import os

import numpy as np
import pytest

from config.model_version import MODEL_VERSION
from ingest.db import now_iso

_spec = importlib.util.spec_from_file_location(
    "rescore", os.path.join(os.path.dirname(__file__), "..", "scripts", "rescore.py"))
rescore = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rescore)

SENTENCES = {"s1": ("DBS", "dividends up"), "s2": ("DBS", "fees too high"), "s3": ("OCBC", "nim held")}
CENTROID = {"s1": ["dividend_policy", "income_profit_results"], "s2": ["retail_banking_sentiment", "wealth_business"],
            "s3": ["net_interest_margin"]}
LLM = {"s1": "dividend_policy", "s2": "retail_banking_sentiment", "s3": "macro_market_environment"}
BASE = {"s1": ("positive", 0.9), "s2": ("negative", 0.8), "s3": ("neutral", 0.7)}


@pytest.fixture
def db(temp_db, tmp_path, monkeypatch):
    conn = temp_db.get_connection()
    for sid, (bank, text) in SENTENCES.items():
        conn.execute("INSERT INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, norm_hash, "
                     "processed_at) VALUES (?, 'd', ?, ?, '2026-01-01T00:00:00+00:00', 'arctic_shift', 'u', ?, ?)",
                     (sid, bank, text, f"h{sid}", now_iso()))
        for aspect in CENTROID[sid]:
            conn.execute("INSERT INTO sentence_aspects VALUES (?, ?, 0.7, ?)", (sid, aspect, now_iso()))
            conn.execute("INSERT INTO aspect_sentiment VALUES (?, ?, ?, ?, ?, ?)",
                         (sid, aspect, *BASE[sid], MODEL_VERSION, now_iso()))
    conn.commit()
    conn.close()
    cache = tmp_path / "answers.jsonl"
    cache.write_text("".join(json.dumps({"sentence_id": s, "aspect": a}) + "\n" for s, a in LLM.items()))
    import aspects.llm_classify as llm
    monkeypatch.setattr(llm, "answer_cache_path", lambda *a, **k: str(cache))
    import train.evaluate
    probs = {"dividends up": [0.1, 0.2, 0.7], "fees too high": [0.8, 0.1, 0.1], "nim held": [0.3, 0.6, 0.1]}
    monkeypatch.setattr(train.evaluate, "finetuned_probs",
                        lambda d, df: np.array([probs[t] for t in df["text"]]))
    import aggregate.preview as pv
    monkeypatch.setattr(pv, "scores_cache_path", lambda models: str(tmp_path / "scores.jsonl"))
    monkeypatch.setattr(rescore, "REAL_DB", str(tmp_path / "real.db"))
    import ingest.db
    return ingest.db.DB_PATH


def _rows(path, sql):
    import sqlite3
    conn = sqlite3.connect(path)
    out = conn.execute(sql).fetchall()
    conn.close()
    return out


def test_dry_run_writes_nothing(db):
    before = _rows(db, "SELECT * FROM sentence_aspects ORDER BY 1, 2")
    assert rescore.main(["--db", db, "--aspects", "llm", "--finetuned", "--models", "m/a", "m/b"]) == 0
    assert _rows(db, "SELECT * FROM sentence_aspects ORDER BY 1, 2") == before


def test_apply_gives_one_llm_aspect_each_and_scores_every_pair_with_both_models(db):
    assert rescore.main(["--db", db, "--aspects", "llm", "--finetuned", "--models", "x/experiments-2026-10-01/s1",
                         "x/experiments-2026-10-01/s2", "--margin", "0.13", "--apply"]) == 0
    assert dict(_rows(db, "SELECT sentence_id, aspect FROM sentence_aspects")) == LLM
    version = "finbert-finetuned-2026-10-01-2seed-m0.13"
    base = {(s, a): (lab, c) for s, a, lab, c in _rows(
        db, f"SELECT sentence_id, aspect, label, confidence FROM aspect_sentiment WHERE model_version='{MODEL_VERSION}'")}
    assert base == {(s, LLM[s]): BASE[s] for s in LLM}             # base label copied to the new pair
    ft = dict(((s, a), lab) for s, a, lab in _rows(
        db, f"SELECT sentence_id, aspect, label FROM aspect_sentiment WHERE model_version='{version}'"))
    assert ft == {("s1", "dividend_policy"): "positive", ("s2", "retail_banking_sentiment"): "negative",
                  ("s3", "macro_market_environment"): "neutral"}
    assert _rows(db, "SELECT COUNT(*) FROM aspect_sentiment WHERE aspect IN "
                     "('income_profit_results', 'wealth_business', 'net_interest_margin')") == [(0,)]
    head = dict(_rows(db, "SELECT model_version || ' ' || bank, n FROM sentiment_index WHERE aspect='ALL' "
                          "AND source='ALL' AND window='all_time'"))
    assert head == {f"{MODEL_VERSION} DBS": 2, f"{MODEL_VERSION} OCBC": 1, f"{version} DBS": 2, f"{version} OCBC": 1}


def test_refuses_the_real_database(db, monkeypatch):
    monkeypatch.setattr(rescore, "REAL_DB", db)
    assert rescore.main(["--db", db, "--aspects", "llm", "--apply"]) == 2


def test_refuses_when_a_sentence_has_no_llm_answer(db, tmp_path):
    (tmp_path / "answers.jsonl").write_text(json.dumps({"sentence_id": "s1", "aspect": "dividend_policy"}) + "\n")
    with pytest.raises(SystemExit, match="2 of 3 sentences have no answer"):
        rescore.main(["--db", db, "--aspects", "llm", "--apply"])


def test_refuses_when_base_labels_differ_within_a_sentence(db):
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("UPDATE aspect_sentiment SET label='negative' WHERE sentence_id='s1' AND aspect='dividend_policy'")
    conn.commit()
    conn.close()
    with pytest.raises(SystemExit, match="different base FinBERT labels"):
        rescore.main(["--db", db, "--aspects", "llm", "--apply"])


def test_finetuned_version_names_the_experiment_seeds_and_margin():
    dirs = [f"models/experiments-2026-10-01/label/seed_{s}/final" for s in (42, 1, 7)]
    assert rescore.finetuned_version(dirs, 0.13) == "finbert-finetuned-2026-10-01-3seed-m0.13"


def _assignments(path):
    return sorted(_rows(path, "SELECT sentence_id, aspect FROM sentence_aspects"))


def test_a_failed_check_writes_nothing(db):
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM aspect_sentiment WHERE sentence_id = 's3'")     # s3 has no base score to copy
    conn.commit()
    conn.close()
    before = _assignments(db)
    assert rescore.main(["--db", db, "--aspects", "llm", "--apply"]) == 1
    assert _assignments(db) == before


def test_new_aspects_alone_refuse_to_leave_a_fine_tuned_version_partial(db):
    args = ["--db", db, "--finetuned", "--models", "x/experiments-2026-10-01/s1", "--apply"]
    assert rescore.main(args) == 0                                            # fine-tuned rows on centroid pairs
    before = _assignments(db)
    assert rescore.main(["--db", db, "--aspects", "llm", "--apply"]) == 1      # would leave them on 2 of 3 pairs
    assert _assignments(db) == before


def test_an_index_failure_rolls_everything_back(db, monkeypatch):
    import aggregate.index

    def broken(conn):
        raise RuntimeError("index failed")
    monkeypatch.setattr(aggregate.index, "rebuild", broken)
    before = _assignments(db)
    with pytest.raises(RuntimeError, match="index failed"):
        rescore.main(["--db", db, "--aspects", "llm", "--apply"])
    assert _assignments(db) == before


def test_the_real_database_is_backed_up_first(db, tmp_path, monkeypatch):
    monkeypatch.setattr(rescore, "REAL_DB", db)
    monkeypatch.setattr(rescore, "BACKUP_DIR", str(tmp_path / "backups"))
    before = _assignments(db)
    assert rescore.main(["--db", db, "--aspects", "llm", "--apply", "--real-db"]) == 0
    backups = list((tmp_path / "backups").glob("plp-before-rescore-*.db"))
    assert len(backups) == 1 and _assignments(str(backups[0])) == before
    assert _assignments(db) == sorted(LLM.items())
