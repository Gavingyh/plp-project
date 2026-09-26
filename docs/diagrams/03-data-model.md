# Data model

The six tables in `data/plp.db`, their columns and keys, and how they relate. For anyone querying the database or reading the report's data section.

**Legend.** Solid shapes and arrows are built and running. Dashed shapes and arrows labelled *planned* are decided but not yet built, with the DESIGN.md decision that records them. Shapes marked *not installed* exist in the repository but aren't running anywhere.

```mermaid
erDiagram
  accTitle: Data model of plp.db
  accDescr: Six SQLite tables. Documents split into sentences; sentences get aspects and sentiment; the index is derived from sentiment; analyst consensus stands alone.

  documents {
    TEXT doc_id PK
    TEXT source
    TEXT source_detail
    TEXT bank
    TEXT doc_type
    TEXT title
    TEXT body
    TEXT published_at
    TEXT url
    TEXT ingested_at
    TEXT raw
    INTEGER has_analyst_view "added later by ingest/analyst_tag.py"
  }
  sentences {
    TEXT sentence_id PK
    TEXT doc_id FK
    TEXT bank
    TEXT text
    INTEGER char_start
    INTEGER char_end
    TEXT published_at
    TEXT source
    TEXT url
    TEXT norm_hash
    TEXT processed_at
  }
  sentence_aspects {
    TEXT sentence_id PK, FK
    TEXT aspect PK
    REAL similarity
    TEXT assigned_at
  }
  aspect_sentiment {
    TEXT sentence_id PK, FK
    TEXT aspect PK
    TEXT label
    REAL confidence
    TEXT model_version PK
    TEXT scored_at
  }
  sentiment_index {
    TEXT bank PK
    TEXT aspect PK
    TEXT window PK
    TEXT source PK
    REAL score
    INTEGER n
    INTEGER pos_n
    INTEGER neu_n
    INTEGER neg_n
    REAL confidence_mean
    TEXT model_version PK
    TEXT computed_at
  }
  analyst_consensus {
    TEXT bank PK
    TEXT as_of_date PK
    TEXT ticker
    INTEGER n_analysts
    TEXT recommendation_key
    REAL recommendation_mean
    REAL target_mean
    REAL target_median
    REAL target_high
    REAL target_low
    REAL current_price
    INTEGER strong_buy
    INTEGER buy
    INTEGER hold
    INTEGER sell
    INTEGER strong_sell
    TEXT fetched_at
  }

  documents ||--o{ sentences : "doc_id, declared key"
  sentences ||--o{ sentence_aspects : "sentence_id, declared key"
  sentences ||--o{ aspect_sentiment : "sentence_id, declared key"
  sentence_aspects ||..o{ aspect_sentiment : "sentence_id and aspect, joined by convention"
  aspect_sentiment }o..o{ sentiment_index : "derived: aggregated by bank, aspect, window, source"
```

Rendered for the report: [SVG](img/03-data-model.svg) · [PNG](img/03-data-model.png)

## What this shows and doesn't show

Solid lines are the three foreign keys the schema declares. They are **not
enforced**: SQLite checks foreign keys only when `PRAGMA foreign_keys=ON`, and no code
turns it on. Dashed lines are relationships the code relies on without a key: sentiment
rows match aspect rows on `(sentence_id, aspect)`, and `sentiment_index` is recomputed
from `aspect_sentiment` joined to `sentences` each time the index runs.
`analyst_consensus` has no relationship; it shares only the bank name with the rest.

Columns are exactly those of the live database (`schema-2026-09-26.txt`). One differs
from the code's `CREATE TABLE`: `documents.has_analyst_view` is added afterwards by
`ingest/analyst_tag.py` with `ALTER TABLE`, so a database built from `ingest/db.py` alone
lacks it.

Rows in the schema dump, taken on 2026-09-26 before CNA was loaded: documents 27,795;
sentences 42,746; sentence_aspects 90,117; aspect_sentiment 90,117; sentiment_index 257;
analyst_consensus 14. Loading CNA the same day added rows but changed no table or column;
current counts are in `docs/STATUS.md`.

## Sources

Each row names the file and line an element comes from, and the text that line must contain; `check_sources.py` verifies them.

| element | source | symbol checked |
|---|---|---|
| documents, created | `ingest/db.py:20` | `CREATE TABLE IF NOT EXISTS documents (` |
| sentences, created | `ingest/db.py:41` | `CREATE TABLE IF NOT EXISTS sentences (` |
| sentences key to documents | `ingest/db.py:43` | `doc_id         TEXT NOT NULL REFERENCES documents(doc_id)` |
| analyst_consensus, created | `ingest/db.py:61` | `CREATE TABLE IF NOT EXISTS analyst_consensus (` |
| sentence_aspects, created | `aspects/assign.py:40` | `CREATE TABLE IF NOT EXISTS sentence_aspects (` |
| aspect_sentiment, created | `sentiment/score.py:43` | `CREATE TABLE IF NOT EXISTS aspect_sentiment (` |
| sentiment_index, created | `aggregate/index.py:78` | `CREATE TABLE IF NOT EXISTS sentiment_index (` |
| has_analyst_view added later | `ingest/analyst_tag.py:77` | `ALTER TABLE documents ADD COLUMN has_analyst_view` |
| join by sentence_id and aspect | `sentiment/score.py:100` | `ase.sentence_id = sa.sentence_id AND ase.aspect = sa.aspect` |
| index derived from aspect_sentiment | `aggregate/index.py:100` | `FROM aspect_sentiment ase` |
| index joins sentences | `aggregate/index.py:101` | `JOIN sentences sa ON sa.sentence_id = ase.sentence_id` |
| foreign keys not enforced | `docs/diagrams/schema-2026-09-26.txt:114` | `PRAGMA foreign_keys (enforcement on this connection): 0` |
| sentence_aspects key to sentences | `aspects/assign.py:41` | `sentence_id  TEXT NOT NULL REFERENCES sentences(sentence_id)` |
| aspect_sentiment key to sentences | `sentiment/score.py:44` | `sentence_id   TEXT NOT NULL REFERENCES sentences(sentence_id)` |
