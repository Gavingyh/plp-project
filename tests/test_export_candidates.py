"""Tests for preprocess/export_candidates.py: it never silently replaces the labelled file."""

import pytest

import preprocess.export_candidates as ec


def test_export_refuses_to_replace_the_labelled_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "OUT_DIR", str(tmp_path))
    (tmp_path / "candidates.csv").write_text("sentence_id,label\ns1,positive\n")
    with pytest.raises(FileExistsError, match="frozen test split"):
        ec.export(800, 200)
    assert (tmp_path / "candidates.csv").read_text() == "sentence_id,label\ns1,positive\n"
