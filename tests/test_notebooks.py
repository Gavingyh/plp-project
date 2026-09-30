"""
Notebooks in notebooks/ are committed without outputs: saved outputs print
corpus text, including staff email addresses from investor-relations PDFs.
"""

import json
from pathlib import Path

import pytest

NOTEBOOKS = sorted((Path(__file__).resolve().parent.parent / "notebooks").glob("*.ipynb"))


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook_has_no_saved_outputs(path):
    nb = json.loads(path.read_text(encoding="utf-8"))
    with_output = [i for i, c in enumerate(nb["cells"]) if c.get("outputs")]
    assert not with_output, f"{path.name}: clear the outputs of cells {with_output} before committing"


def test_there_are_notebooks_to_check():
    assert NOTEBOOKS
