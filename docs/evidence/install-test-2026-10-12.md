# Clean-copy install test, third run (12 Oct 2026)

**What this is.** The marker installs the project from the README. This run
repeats the test of 1 Oct ([install-test-2026-10-01.md](install-test-2026-10-01.md))
on the system as it stands after the re-score: a fresh clone of `main` at
commit `f444577`, the README's steps in order, a plain shell PATH with Python
3.14 first, and the 12 Oct snapshot. Run on the MacBook Air (M1) while a
local-model job was using the GPU. The temporary copy was deleted afterwards.

**Result.** The README works end to end and the API serves the re-scored
index. Two things were wrong and are fixed: the documented test counts were
the development Mac's, six higher than a fresh clone's, and one training
test failed in one of the two test runs.

| step | result | time |
|---|---|---|
| `git clone` | ok; the repository is private, so the clone needs GitHub credentials | under a minute |
| `python3 -m venv .venv-plp` | ok, Python 3.14.0 | seconds |
| `pip install -r requirements.txt` | ok | about 2 minutes |
| `python -m spacy download en_core_web_sm` | ok | under a minute |
| `cp .env.example .env` | ok | |
| restore `plp-2026-10-12.db.gz` | ok; SHA-256 matches the README table; 101.6 MB unpacked, as the README says | seconds |
| `pytest tests/ -q` | **2471 passed**, 2 skipped, 46 expected failures: 2519 collected, where the README said 2525 | about 4 minutes |
| `pytest -q` from the root | 2517 passed, **1 failed**, 2 skipped, 46 expected failures: 2566 collected, where the README said 2572 | about 3 minutes |
| `PLP_DASHBOARD_PORT=8601 PLP_API_PORT=8101 scripts/start.sh` | ok | about 20 seconds |
| API `/health`, `/docs`; dashboard `/` | HTTP 200, 200, 200 | |
| API `/sentiment?bank=DBS` | score 0.1552 on 24,978 sentences, served model `finbert-adapted-finetuned-2026-10-11-3seed-m0`, `data_as_of` 2026-09-25: the stored index | |
| API `/sentiment?bank=UOB&window=7d` | score 0.3093 on 60 sentences, with the note that the window ends at the newest data | |
| `scripts/stop.sh` | stopped both | |

The model weights and the sentence embeddings are not in git and were not
copied in, so this is what a marker with only the repository and the
snapshot sees: every test passes without them, and the API serves the index
from the scores the snapshot already holds.

## The two findings

**The test counts were six too high.** One test runs once per gold-set
results file in `data/eval/`. Six of those files are kept out of git because
they quote CNA text, so only the development Mac collects their six cases.
RUNBOOK already said the documented counts are a fresh checkout's, but the
figures written on 11 and 12 Oct were the Mac's. README, STATUS, RUNBOOK and
the technical spec now say 2519 and 2566, and RUNBOOK names the Mac's 2525
and 2572.

**A training test failed once, and the cause was the GPU, not the code.**
`test_weighted_training_and_ensemble_run` failed in the root run with
"probabilities don't sum to 1: the device returned garbage", after passing
in the `tests/` run minutes earlier. Repeating the two training test files
in the clone, one run of two failed. The tests train a tiny model on the
Mac's GPU, which the local model was also using; short of memory, the GPU
leaves the weights as garbage, and evaluation refuses them, as it is meant
to. With only the evaluation moved to the CPU, two runs of four still
failed in the repository, on other tests of the same files, which showed
the garbage comes from training. The tests that train now do so on the CPU
(`train_on_the_cpu` in `tests/conftest.py`): four runs of both files passed
with the GPU still busy. Real training is unchanged; the rule for it stays
in `CLAUDE.md` (rerun with `--cpu` when this message appears).

## Not covered

- The chatbot was not asked a question: it needs Ollama with `llama3.1:8b`,
  which a marker must install separately (README).
- The dashboard page loaded (HTTP 200), but its figures were not read. It
  has no model-version filter yet, so it shows both models' rows (to-do).
