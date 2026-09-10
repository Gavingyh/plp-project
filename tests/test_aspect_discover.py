"""
Tests for aspects/discover.py's sentence lookup.

These exist because of a real bug that only appeared once the corpus grew:
run() fetched sentence text with `WHERE sentence_id IN (?,?,?...)`, binding
one SQL variable per cached embedding. SQLite's SQLITE_MAX_VARIABLE_NUMBER is
32,766, so at 36,884 embedded sentences every run died with
`sqlite3.OperationalError: too many SQL variables`.

The failure mode is what makes it worth a test: the script was fine on the
2,888-sentence corpus it was developed against and became unrunnable exactly
when the corpus finally got big enough for clustering to be worth doing. A
size-dependent query needs a test that exercises it above the size limit.
"""

import numpy as np
import pytest

import aspects.discover as discover


def _insert_sentences(db_module, n, start=0):
    """n minimal sentence rows, ids sentence_id-<i>."""
    conn = db_module.get_connection()
    conn.executemany(
        "INSERT INTO sentences (sentence_id, doc_id, text, bank, source, published_at, "
        "char_start, char_end, url, norm_hash, processed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(f"s{i}", f"d{i}", f"Sentence number {i} about the bank's margins.", "DBS",
          "arctic_shift", "2026-01-01T00:00:00+00:00", 0, 10,
          f"https://example.test/{i}", f"h{i}", "2026-01-01T00:00:00+00:00")
         for i in range(start, start + n)],
    )
    conn.commit()
    conn.close()
    return [f"s{i}" for i in range(start, start + n)]


@pytest.mark.parametrize("n", [10, 33_000])
def test_lookup_survives_more_ids_than_sqlite_variable_limit(temp_db, monkeypatch, n):
    """The regression: 33,000 ids exceeds SQLite's 32,766-variable ceiling.

    Parametrised with a small case so a failure tells you whether the lookup
    is broken generally or only above the limit.
    """
    ids = _insert_sentences(temp_db, n)
    vectors = np.zeros((n, 4), dtype=np.float32)

    monkeypatch.setattr(discover, "load_for_search", lambda: (ids, vectors))
    monkeypatch.setattr(discover, "update_embeddings", lambda: {"total": n})

    captured = {}

    def fake_umap(**kwargs):
        class _R:
            def fit_transform(self, v):
                captured["n_rows"] = v.shape[0]
                raise _StopHere()
        return _R()

    class _StopHere(Exception):
        pass

    monkeypatch.setattr(discover.umap, "UMAP", fake_umap)

    # UMAP/HDBSCAN on 33k rows is slow and not what this test is about, so
    # stop the moment the SQL lookup has provably succeeded and handed its
    # rows onward.
    with pytest.raises(_StopHere):
        discover.run(min_cluster_size=2)

    assert captured["n_rows"] == n


def test_embedded_sentence_missing_from_table_is_dropped(temp_db, monkeypatch):
    """A vector whose row was deleted must not KeyError, and must not
    desynchronise vectors from ids."""
    ids = _insert_sentences(temp_db, 5)
    ids_with_ghost = ids + ["s-deleted"]
    vectors = np.arange(6 * 3, dtype=np.float32).reshape(6, 3)

    monkeypatch.setattr(discover, "load_for_search", lambda: (ids_with_ghost, vectors))
    monkeypatch.setattr(discover, "update_embeddings", lambda: {"total": 6})

    captured = {}

    class _StopHere(Exception):
        pass

    def fake_umap(**kwargs):
        class _R:
            def fit_transform(self, v):
                captured["vectors"] = v
                raise _StopHere()
        return _R()

    monkeypatch.setattr(discover.umap, "UMAP", fake_umap)

    with pytest.raises(_StopHere):
        discover.run(min_cluster_size=2)

    # The ghost's vector (the last row) must be gone, and the five survivors
    # must still be their original rows in their original order.
    assert captured["vectors"].shape[0] == 5
    assert np.array_equal(captured["vectors"], vectors[:5])
