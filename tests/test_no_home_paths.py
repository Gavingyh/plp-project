"""
No code names one person's home directory. A hard-coded home path works only
on the machine that wrote it and puts a personal name in the repository; code
finds the repository from its own location instead.
"""

import os
import plistlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIRS = ["scripts", "ingest", "preprocess"]
CODE_SUFFIXES = (".py", ".sh", ".plist")
HOME_PREFIXES = ("/Users/", "/home/")


def _code_files():
    for d in CODE_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, d)):
            dirnames[:] = [n for n in dirnames if n != "__pycache__"]
            for name in sorted(filenames):
                if name.endswith(CODE_SUFFIXES):
                    yield os.path.relpath(os.path.join(dirpath, name), ROOT)


def test_code_names_no_home_directory():
    files = sorted(_code_files())
    assert files, "no code files found: the directory list is wrong"
    hits = []
    for path in files:
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            hits += [f"{path}:{n}: {line.strip()}" for n, line in enumerate(f, 1)
                     if any(p in line for p in HOME_PREFIXES)]
    assert not hits, "\n".join(hits)


def test_daily_batch_job_still_parses_and_points_at_a_placeholder():
    with open(os.path.join(ROOT, "scripts", "com.plp.dailybatch.plist"), "rb") as f:
        job = plistlib.load(f)
    assert job["Label"] == "com.plp.dailybatch"
    assert job["WorkingDirectory"] == "/path/to/plp-project"
    assert job["ProgramArguments"][0].startswith("/path/to/plp-project/")
