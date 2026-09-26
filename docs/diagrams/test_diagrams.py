"""
Keeps each diagram page true to its Mermaid source: the page's mermaid block
must equal docs/diagrams/src/<name>.mmd exactly, every source must have a
page, and every page must carry a sources table. Rendering is not tested here
(it needs Node); docs/diagrams/render_diagrams.sh does that.
"""

import re
from pathlib import Path

import pytest

HERE = Path(__file__).parent
PAGES = sorted(HERE.glob("[0-9][0-9]-*.md"))
SOURCES = sorted((HERE / "src").glob("*.mmd"))
_BLOCK = re.compile(r"```mermaid\n(.*?)```", re.S)


def test_every_source_has_a_page_and_every_page_a_source():
    assert {p.stem for p in PAGES} == {s.stem for s in SOURCES}


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_page_block_matches_source(page):
    blocks = _BLOCK.findall(page.read_text(encoding="utf-8"))
    assert len(blocks) == 1, "one mermaid block per page"
    assert blocks[0] == (HERE / "src" / f"{page.stem}.mmd").read_text(encoding="utf-8")


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_page_has_sources_table(page):
    assert "| element | source | symbol checked |" in page.read_text(encoding="utf-8")
