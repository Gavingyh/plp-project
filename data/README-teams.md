# PLP data: read this first

The project's dataset is one file, `data.zip`, beside this note. It holds
everything the project needs that isn't in git: the database, both sets of
sentence vectors, the CNA cache and the aspect model's answers. The models
are not in it; setup downloads them. This `data.zip` matches the code on
`main` from 25 Oct 2026 and replaces every earlier upload.

## Use it

1. **Update your code:** `git pull` on `main`.
2. **Put `data.zip` at `data/data.zip`** in your checkout. Don't unpack it by
   hand, and don't replace your `data/` folder: `labeled/`, `eval/` and the
   PDF folders are in git, and `git pull` gives you the right versions.
3. **Restore it:**
   - with Docker, `docker compose up --build` restores it on first start
     (README, "Run with Docker");
   - natively, from the project root:
     `.venv-plp/bin/python3 -m docker.bootstrap --data-only`.

Either way the restore checks the database's integrity, that it holds the
served model's scores, and that the vectors match its sentences, and it never
overwrites a file you already have. To replace an older database, move your
`data/plp.db` aside first.

Check the download first: `shasum -a 256 -c SHA256SUMS`. With Docker, set
`PLP_DATA_SHA256` in `.env` to the checksum in `SHA256SUMS`, and setup refuses
a different file.

## What is in it

Under `data/`:

| file | what it is | size |
|---|---|---|
| `plp.db` | The database: 28,852 documents, 45,844 sentences to 25 Sep 2026, one aspect each, both models' scores, the index. The 14 Oct snapshot, decompressed. | 101.4 MB |
| `search_embeddings.npz` | The chatbot's evidence search, from a model built for search (all-MiniLM-L6-v2). Setup rebuilds it if it's missing, in about 5 minutes. | 66 MB |
| `sentence_embeddings.npz` | FinBERT's vectors, for aspect discovery; the chatbot doesn't read them. | 132 MB |
| `cna/articles.jsonl`, `cna/candidates.json` | The CNA cache: needed only to rebuild the CNA part of the database. | 2 MB |
| `aspect_llm/llama3.1_8b.eef9b342.jsonl` | The aspect model's answer for every sentence (sentence ids and aspects only). Keep the name: `eef9b342` ties it to the current prompt, and a changed prompt starts a new file and a run of about a day. | 5 MB |

The models come from the public Hugging Face repo
`plp-bank-sentiment/plp-finbert-absa`: Docker setup downloads them and checks
their SHA-256; natively, follow the README ("Sharing the data and models").
They are needed only to score new sentences or reproduce the results; the
database already holds their scores.

## Rules

- **`data.zip` goes to the team and the assessors only.** It holds Reddit
  posts, CNA articles and broker reports: never commit it (git ignores it),
  publish it or upload it anywhere else.
- **Never commit anything from `data/` that git ignores.** After restoring,
  `git status` should show nothing new under `data/`.
- **API keys (`.env`) are never shared.** Get your own; see `API_KEYS.md`.

## If your feature reads the database

- **Read through the API.** It returns only the served model's rows. Reading
  the database directly, add `AND model_version = ?` with
  `config.model_version.MODEL_VERSION`, or every sentence is counted twice:
  `aspect_sentiment` and `sentiment_index` hold base FinBERT's rows too.
- **One aspect a sentence** means small counts: some bank and aspect cells
  hold under 100 sentences all time and a handful in a 30-day window. Show
  the count (`n`) beside a score, and treat a cell with `insufficient_data`
  as empty.
- **Recent means "as of 25 Sep 2026".** The API returns the date as
  `data_as_of`; show it beside any 7-day or 30-day figure.

## If your feature adds data or changes scoring

Ask first. Every evaluation in the report describes this corpus, and a change
to `data/plp.db` (new sentences, new aspects, new scores) is a team decision,
rehearsed on a copy (`scripts/rescore.py`, RUNBOOK):

```bash
cp data/plp.db /tmp/plp-feature.db
PLP_DB_PATH=/tmp/plp-feature.db PLP_API_PORT=8100 scripts/start.sh api
```

## Check that it works

```bash
curl "http://127.0.0.1:8000/sentiment?bank=DBS"
```

It should return a score of 0.143 on 24,978 sentences, with the served
model's name and `data_as_of` 2026-09-25. With different ports, use the API
port you set.
