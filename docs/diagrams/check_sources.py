"""
Checks every diagram page's sources table against the repository: each
`path:line` must exist and that line must contain the "symbol checked" text.
Rows whose source is not a `path:line` (a DESIGN decision, the schema dump)
are checked for the file's existence only.

  .venv-plp/bin/python3 docs/diagrams/check_sources.py
Exits non-zero, listing every failure, if anything doesn't match.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
ROW = re.compile(r"^\|\s*(?P<el>.+?)\s*\|\s*`(?P<src>[^`]+)`\s*\|\s*`(?P<sym>[^`]*)`\s*\|\s*$")


def check() -> list[str]:
    failures, checked = [], 0
    for page in sorted(HERE.glob("[0-9][0-9]-*.md")):
        for n, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
            m = ROW.match(line)
            if not m:
                continue
            checked += 1
            src, sym = m["src"], m["sym"]
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
