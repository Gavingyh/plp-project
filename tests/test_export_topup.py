"""Tests for preprocess/export_topup.py: quotas, pooling across sources, selection."""

import pandas as pd

import preprocess.export_topup as tu


def test_quotas_cover_the_shortfall_with_a_margin_and_skip_other():
    labels = pd.DataFrame({"aspect": ["dividend_policy"] * 33 + ["asset_quality"] * 78 + ["other"] * 5
                                     + ["retail_banking_sentiment"] * 100})
    assert tu.quotas(labels) == {"dividend_policy": 67, "asset_quality": 30}


def test_pool_takes_sources_in_turn_most_similar_first():
    c = pd.DataFrame({"sentence_id": list("abcdef"), "source": ["earnings"] * 4 + ["arctic_shift", "google_news"],
                      "similarity": [0.99, 0.98, 0.97, 0.96, 0.50, 0.40]})
    picked = tu.pool_for(c, 3)
    assert set(picked["sentence_id"]) == {"a", "e", "f"}             # one per group, not the top three earnings


def test_select_keeps_llm_confirmed_targets_up_to_quota_spread_over_banks():
    pool = pd.DataFrame({"sentence_id": [f"s{i}" for i in range(6)], "bank": ["DBS", "DBS", "DBS", "UOB", "OCBC", "DBS"],
                         "source": ["earnings"] * 6, "similarity": [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]})
    llm = pd.Series(["dividend_policy"] * 5 + ["retail_banking_sentiment"])
    out = tu.select(pool, llm, {"dividend_policy": 3})
    assert len(out) == 3 and set(out["llm_aspect"]) == {"dividend_policy"}
    assert set(out["bank"]) == {"DBS", "UOB", "OCBC"}                 # spread before a second DBS row


def test_build_pool_drops_labelled_fragments_and_repeats(temp_db):
    from ingest.db import now_iso
    from preprocess.fragments import fragment_reason
    table_row = "Dividend 1.20 3.40 5.60 7.80 9.00 1.10 2.20 3.30 4.40 5.50"
    assert fragment_reason(table_row, "earnings") == "table"
    prose = "The board raised the dividend to 60 cents a share."
    rows = [("s1", "earnings", prose, "dividend_policy", 0.9),
            ("s2", "earnings", "Already labelled dividend sentence.", "dividend_policy", 0.95),
            ("s3", "earnings", table_row, "dividend_policy", 0.8),
            ("s4", "arctic_shift", "the board  raised the DIVIDEND to 60 cents a share.", "dividend_policy", 0.7),
            ("s5", "google_news", "Provisions fell and the dividend held.", "dividend_policy", 0.6),
            ("s5", "google_news", "Provisions fell and the dividend held.", "asset_quality", 0.9),
            ("s6", "cna", prose, "asset_quality", 0.8),
            ("s7", "cna", "Bad loans rose for a second quarter.", "asset_quality", 0.7)]
    conn = temp_db.get_connection()
    for sid, source, text, aspect, sim in rows:
        conn.execute("INSERT OR IGNORE INTO sentences (sentence_id, doc_id, bank, text, published_at, source, url, "
                     "norm_hash, processed_at) VALUES (?, 'd', 'DBS', ?, '2026-01-01', ?, 'u', ?, ?)",
                     (sid, text, source, f"h-{sid}", now_iso()))
        conn.execute("INSERT INTO sentence_aspects (sentence_id, aspect, similarity, assigned_at) VALUES (?, ?, ?, ?)",
                     (sid, aspect, sim, now_iso()))
    conn.commit()
    labels = pd.DataFrame({"sentence_id": ["s2"], "aspect": ["dividend_policy"]})
    pool = tu.build_pool(conn, labels, {"dividend_policy": 10, "asset_quality": 10})
    conn.close()

    by_target = pool.groupby("pooled_for")["sentence_id"].apply(set).to_dict()
    assert len(by_target["dividend_policy"] & {"s1", "s4"}) == 1           # same text after lowercasing and spacing
    assert "s5" in by_target["dividend_policy"]
    assert by_target["asset_quality"] == {"s7"}                            # s5 already pooled, s6 repeats a text
    assert not {"s2", "s3"} & set(pool["sentence_id"])                     # labelled; a table row
    assert pool["sentence_id"].is_unique


def test_quotas_ignore_the_test_split():
    labels = pd.DataFrame({"aspect": ["capital_liquidity"] * 49, "split": ["train_dev"] * 39 + ["test"] * 10})
    assert tu.quotas(labels) == {"capital_liquidity": 61}          # 80 - 39 + 20, not 80 - 49 + 20
