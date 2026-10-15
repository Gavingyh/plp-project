# PLP data files: read this first

These are the files the project needs that are not in git: the database, the
sentence embeddings and the aspect model's answers. The sentiment model's
weights are on Hugging Face (below). This set matches the code on `main` from 14 Oct 2026 and replaces
every earlier upload. Private to the team.

## What changed since the last upload

The database was re-scored twice, and the code now depends on it:

- **One aspect a sentence.** Each sentence has exactly one aspect, chosen by
  the local LLM, where it used to have about six. The aspect model's prompt
  follows the wealth rule of 10 Oct: wealth means the priority and private
  banking tiers; unit trusts, brokerage accounts, insurance and the like are
  retail.
- **Two models' scores side by side.** Every sentence has a score from the
  fine-tuned model the product serves
  (`finbert-adapted-finetuned-2026-10-11-3seed-m0`) and one from base
  FinBERT, kept for comparison.
- **Recent windows end at the newest sentence**, 25 Sep 2026, not at today.
- **Links to PDFs are relative paths** (`data/earnings_pdfs/...`,
  `data/sgx_research/...`), so no one's home folder is in the database.

With an older database the API finds no rows for the served model and
returns empty tables, so restore this one together with `git pull`.

## Before you start

1. **Update your code:** `git pull` on `main`.
2. **Copy only the files below** into the same place under your checkout.
   Do **not** replace your whole `data/` folder: `labeled/`, `eval/`, `logs/`
   and `earnings_pdfs/` are in git, and `git pull` gives you the right
   versions.

## What each file is

| file in this upload | goes to | what it is | size |
|---|---|---|---|
| `plp-2026-10-14.db.gz` | unpack to `data/plp.db` | The database: 28,852 documents, 45,844 sentences, one aspect each, both models' scores, the index. The only snapshot you need. | 26.2 MB (101.4 MB unpacked) |
| `sentence_embeddings.npz` | `data/sentence_embeddings.npz` | Needed for the chatbot's evidence search. Without it, search falls back to matching words. Unchanged since 11 Oct. | 132 MB |
| `aspect_llm/llama3.1_8b.eef9b342.jsonl` | `data/aspect_llm/` | The aspect model's answer for every sentence (sentence ids and aspects only, no text). Needed only to re-run the re-score, or to compare with the earlier answers. | 5 MB |
| `SHA256SUMS` | nowhere | Checksums of every file above: `shasum -a 256 -c SHA256SUMS` | |

### Unpacking and checking the snapshot

```bash
gunzip -c plp-2026-10-14.db.gz > data/plp.db
shasum -a 256 plp-2026-10-14.db.gz
```

The checksum must be:
`2e42aafeaa9d1e219b00359e8b31e7219b0fe1824f0aaaf9b3d2598607a857f0`

Keep the aspect file's name exactly as it is: the code finds it by name, and
`eef9b342` ties it to the current prompt. If you change an aspect's
definition or an example in `config/aspects.yaml`, the code starts a new file
and classifies the whole corpus again, which takes about a day.

## If your feature reads the database

- **Filter on the model.** `aspect_sentiment` and `sentiment_index` hold two
  models' rows. Add `AND model_version = ?` with
  `config.model_version.MODEL_VERSION`, as the API and the chatbot do, or
  every sentence is counted twice. Using the API instead avoids this: it
  returns only the served model's rows.
- **One aspect a sentence** means small counts: some bank and aspect cells
  hold under 100 sentences all time and a handful in a 30-day window. Show
  the count (`n`) beside a score, and treat a cell with `insufficient_data`
  as empty.
- **Recent means "as of 25 Sep 2026".** The API returns the date as
  `data_as_of`; show it beside any 7-day or 30-day figure.

## If your feature adds data or changes scoring

Ask first. Collection is frozen so that every evaluation in the report
describes the same corpus, and a change to `data/plp.db` (new sentences, new
aspects, new scores) is a team decision that is rehearsed on a copy
(`scripts/rescore.py`, RUNBOOK). Build and test on a copy:

```bash
cp data/plp.db /tmp/plp-feature.db
PLP_DB_PATH=/tmp/plp-feature.db PLP_API_PORT=8100 scripts/start.sh api
```

## Not in this upload

- **The fine-tuned models:** in the private Hugging Face repo
  `plp-bank-sentiment/plp-finbert-absa`, folder `adapted-2026-10-11/` (ask to
  be added to the organisation). **Needed only if your feature scores new
  sentences**, or to reproduce the results: the database already holds their
  scores. Download and place them as the project README says ("Sharing the
  data and models"); the model card is the repo's README.
- **Raw CNA articles (`data/cna/`):** unchanged; use the copy already in the
  team folder. Needed only to rebuild the CNA part of the database.
- **API keys (`.env`):** never shared. Get your own; see `API_KEYS.md`.
- **Base FinBERT** downloads by itself on first use. **Local models** come
  from Ollama: `ollama pull llama3.1:8b`.

## Rules

- **Never commit anything from `data/` that git ignores.** After copying,
  `git status` should show nothing new under `data/`.
- **Keep the database, `cna/` and broker research within the team.** They
  hold Reddit posts, CNA articles and broker reports: never commit them,
  share them outside the team, or upload them anywhere else.

## Check that it works

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m pytest tests/ -q
```

2,523 tests in a fresh clone; 2 are skipped and 46 are expected failures
that record known limits.

```bash
scripts/start.sh
curl "http://127.0.0.1:8000/sentiment?bank=DBS"
```

Starts the API (port 8000) and the dashboard (port 8501); the call should
return a score of 0.143 on 24,978 sentences with the served model's name.
If those ports are taken:

```bash
PLP_API_PORT=8100 PLP_DASHBOARD_PORT=8502 scripts/start.sh
```

The dashboard does not yet filter on the model, so until its owner adds that
its figures can differ from the API's.
