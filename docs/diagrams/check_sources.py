"""
Checks every diagram page's sources table against the repository: each
`path:line` must exist and that line must contain the "symbol checked" text.
Rows whose source is not a `path:line` (a DESIGN decision, the schema dump)
are checked for the file's existence only. A row inside a sources table that
can't be parsed is itself a failure, so no row is skipped silently.

  .venv-plp/bin/python3 docs/diagrams/check_sources.py
Exits non-zero, listing every failure, if anything doesn't match.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
# The symbol is a code span: `text`, or `` text `` when the text itself has backticks.
ROW = re.compile(r"^\|\s*(?P<el>.+?)\s*\|\s*`(?P<src>[^`]+)`\s*\|\s*"
                 r"(?:`` (?P<sym2>.*?) ``|`(?P<sym>[^`]*)`)\s*\|\s*$")
HEADER = "| element | source | symbol checked |"


def check() -> list[str]:
    failures, checked = [], 0
    for page in sorted(HERE.glob("[0-9][0-9]-*.md")):
        in_table = False
        for n, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip() == HEADER:
                in_table = True
                continue
            if not in_table or line.startswith("|---"):
                continue
            if not line.startswith("|"):
                in_table = False
                continue
            m = ROW.match(line)
            if not m:
                failures.append(f"{page.name}:{n}: sources row not parsed: {line[:120]!r}")
                continue
            checked += 1
            src = m["src"]
            sym = m["sym2"] if m["sym2"] is not None else m["sym"]
            path, _, lineno = src.partition(":")
            f = ROOT / path
            where = f"{page.name}:{n} ({src})"
            if not f.exists():
                failures.append(f"{where}: file not found")
                continue
            if not lineno:
                if sym and sym not in f.read_text(encoding="utf-8"):
                    failures.append(f"{where}: {sym!r} not found in file")
                continue
            lines = f.read_text(encoding="utf-8").splitlines()
            i = int(lineno)
            if i < 1 or i > len(lines):
                failures.append(f"{where}: line {i} out of range")
            elif sym not in lines[i - 1]:
                failures.append(f"{where}: line {i} is {lines[i - 1].strip()!r}, expected {sym!r}")
    print(f"checked {checked} source rows", file=sys.stderr)
    return failures


if __name__ == "__main__":
    fails = check()
    for f in fails:
        print(f)
    sys.exit(1 if fails else 0)
