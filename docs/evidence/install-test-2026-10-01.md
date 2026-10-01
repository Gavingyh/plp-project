# Clean-copy install test

Can someone who has only the repository and the README get the system
running? Tested 2026-10-01 on this MacBook Air (M1, macOS) from a fresh clone
of commit `606dde4`, following the README's Quick start and "Getting the
database" steps exactly, with a plain shell PATH (no project venv active).
The temporary copy was deleted afterwards.

## Attempt 1: the default `python3` on a Mac

With the system PATH, `python3` is Apple's built-in **Python 3.9.6**
(`/usr/bin/python3`).

| step | result |
|---|---|
| `python3 -m venv .venv-plp` | succeeds, silently, on 3.9 |
| `pip install -r requirements.txt` | **fails**: `ERROR: No matching distribution found for torch>=2.9.0` |
| everything after | fails (no packages); `scripts/start.sh` stops with a clear message: the codebase needs Python 3.10+ |

The README never says which Python is needed, and pip's error doesn't say
the Python is the problem.

## Attempt 2: Python 3.14 from python.org first on PATH

| step | result | time |
|---|---|---|
| `python3 -m venv .venv-plp` | ok | seconds |
| `pip install -r requirements.txt` | ok | ~3 min |
| `python -m spacy download en_core_web_sm` | ok | ~4 min |
| `cp .env.example .env` | ok | — |
| restore `plp-2026-09-30.db.gz` | ok; SHA-256 matches the README table | seconds |
| `pytest tests/ -q` | **421 passed** (the README says 379) | 2.6 min |
| `pytest -q` from the root | 462 passed (adds the diagram and notebook checks) | 46 s |
| `scripts/start.sh` (default ports) | **refused**: port 8000 is held by another project on this Mac; the script says why and how to choose another port | — |
| `PLP_DASHBOARD_PORT=8601 PLP_API_PORT=8100 scripts/start.sh` | ok | ~10 s |
| API `/health`, `/docs`; dashboard `/` | HTTP 200, 200, 200 | — |
| API `/sentiment?bank=DBS` | `"score":0.122, "n":24431`, the stored index value | — |
| `scripts/stop.sh` | stopped both | — |

So with a recent Python the README works end to end, and the snapshot and
checksum are right.

## Suggested README fixes (not made in this run)

1. **State the Python requirement** before the venv step: Python 3.10 or
   newer (tested on 3.14); check with `python3 --version`; on a Mac, install
   from python.org or Homebrew, or create the venv with an explicit
   interpreter (`python3.14 -m venv .venv-plp`). This was the only blocking
   problem.
2. **Order the Quick start for a newcomer**: install, restore the snapshot,
   start the services. Today the pipeline commands come first, before
   "Getting the database", although a teammate restoring the snapshot never
   runs them.
3. **Mention the port overrides** (`PLP_DASHBOARD_PORT`, `PLP_API_PORT`): the
   defaults, 8501 and 8000, are common enough to be taken.
4. **Update stale figures**: the database is 118 MB uncompressed, not "about
   103MB"; `tests/` holds 421 tests, not 379 (the same 379 appears in RUNBOOK,
   STATUS and the technical spec).
