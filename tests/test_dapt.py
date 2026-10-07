"""
The domain-adaptive pretraining corpus (train/dapt.py) leaves out every
labelled sentence and its near-copies, so no test text informs training.
Synthetic data only: a temporary database and labels file.
"""

import sqlite3

import pandas as pd

from train.dapt import build_corpus, norm


def _setup(tmp_path):
    db = tmp_path / "plp.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sentences (sentence_id TEXT, text TEXT, source TEXT)")
    conn.executemany("INSERT INTO sentences VALUES (?, ?, ?)", [
        ("a", "DBS raised its dividend to 54 cents in 2Q25.", "earnings"),     # labelled (test)
        ("b", "DBS raised its dividend to 60 cents in 3Q25.", "earnings"),     # same sentence, new figures
        ("c", "UOB One nerf again lol", "arctic_shift"),                       # labelled (train)
        ("d", "OCBC 360 interest is higher if you meet all the conditions.", "arctic_shift"),
        ("e", "  UOB ONE   nerf again LOL ", "arctic_shift"),                  # same text, other case and spaces
    ])
    conn.commit()
    conn.close()
    labels = tmp_path / "candidates.csv"
    pd.DataFrame([{"sentence_id": "a", "text": "DBS raised its dividend to 54 cents in 2Q25.", "split": "test"},
                  {"sentence_id": "c", "text": "UOB One nerf again lol", "split": "train_dev"}]).to_csv(labels, index=False)
    return str(db), str(labels)


def test_labelled_sentences_and_their_near_copies_are_left_out(tmp_path):
    db, labels = _setup(tmp_path)
    texts, stats = build_corpus(db, labels)
    assert texts == ["OCBC 360 interest is higher if you meet all the conditions."]
    assert stats["dropped_labelled_id"] == 2
    assert stats["dropped_matching_labelled_text"] == 2
    assert stats["kept_by_source"] == {"arctic_shift": 1}


def test_norm_ignores_figures_case_and_spacing():
    assert norm("Profit rose 12.5% to S$1,234m in 2Q25") == norm("profit  rose 9% to s$987m in 3q24")
    assert norm("DBS is up") != norm("DBS is down")


def test_a_near_copy_with_a_word_changed_or_a_stray_mark_is_left_out(tmp_path):
    db, labels = _setup(tmp_path)
    conn = sqlite3.connect(db)
    conn.executemany("INSERT INTO sentences VALUES (?, ?, ?)", [
        ("f", "Higher NPLs and recessionary risks could unwind expectations for credit cost declines, posing risks to earnings.",
         "sgx_research"),
        ("g", "Higher NPLs and recession ary risks could unwind expectations for credit cost declines, posing risks to Fed cuts. •",
         "sgx_research"),
        ("h", "UOB Kay Hian reported a quarterly brokerage commission figure today.", "news"),
    ])
    conn.commit()
    conn.close()
    rows = pd.read_csv(labels)
    pd.concat([rows, pd.DataFrame([{"sentence_id": "x", "split": "test", "text": "Higher NPLs and recession ary risks "
                                    "could unwind expectations for credit cost declines, posing risks to Fed cuts."}])]
              ).to_csv(labels, index=False)
    texts, stats = build_corpus(db, labels)
    assert not any(t.startswith("Higher NPLs") for t in texts)
    assert "UOB Kay Hian reported a quarterly brokerage commission figure today." in texts
    assert stats["dropped_near_copy_of_labelled_text"] >= 2
