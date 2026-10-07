# Local banking terms: a draft glossary

Drafted on 7 Oct 2026. Not yet checked by a person.

`local-terms.csv` lists 79 Singapore banking and investing terms found in the
corpus: the three banks' products, programmes, apps and group companies, the
competitors and market names they are compared with, and the local and chat
slang asked about in `docs/local-context-questions.md`. Rows are sorted by
how often the term occurs, most frequent first.

## What it is for

Idea 2 of the improvement list: a lookup that can be attached to a sentence
before classification, so a model that was trained on general English reads
"UOB EVOL" as a credit card and "Premier Dividend+" as a deposit account
rather than the bank's dividend. A sentence's matching rows (term and
definition) would be added to its input. Nothing in the pipeline uses the
file yet.

## Columns

| column | meaning |
|---|---|
| term | the name as it is usually written |
| aliases | other spellings and short forms, separated by semicolons |
| bank | DBS, OCBC or UOB; `all` for a word used of every bank; `none (competitor)` or `none (separate company)` or `none (national)` otherwise |
| category | product, programme, app, brand, slang or investing |
| definition | one plain sentence |
| sentiment_note | whether the word itself carries tone; usually `none` |
| corpus_count | corpus sentences holding the term or an alias (see below) |
| source | where the definition comes from (see below) |

## How it was built

Script: `data/run/upstream/glossary_mine.py` (under `data/run/`, which is
gitignored, so it stays on the machine that built it).

1. **Corpus.** The pretraining corpus from `train.dapt.build_corpus`, with its
   default labels (all 58 labelling sheets under `data/labeled/`). It leaves
   out every labelled sentence, in any split, and every near-copy of one. Of
   the 44,345 sentences in `data/plp.db`, 41,923 remain (the script's
   printed corpus stats, 7 Oct 2026). These counts were taken before the
   active-learning sheet (`data/labeled/active/active_sheet.csv`) existed;
   `train.dapt.labelled_files()` now returns 59 files, so to reproduce them,
   leave `data/labeled/active/` out of the labels (the cached corpus,
   `data/run/upstream/corpus_cache.pkl`, already holds the 58-file corpus).
   The database was opened read-only. No
   labelled row was read for anything else, so no test text informed which
   terms were picked or how they were defined.
2. **Mining** (`glossary_mine.py mine`, output in
   `data/run/upstream/glossary_candidates.csv`). Two candidate lists, each
   counted on that corpus:
   - a bank name (DBS, OCBC, UOB, POSB) followed by one or two words
     starting with a capital letter or a digit ("UOB One", "OCBC 360",
     "UOB PPV"), skipping common words such as "Bank" or "Group";
   - a seed list of 130 names: the products and names in
     `docs/local-context-questions.md`, its slang tables, the slang pattern
     of `scripts/slang_share.py`, and other local product names.
3. **Choosing rows** (by hand). From the candidates, product, app,
   programme, brand, investing and slang terms were kept; place names,
   job titles and company suffixes ("DBS CEO", "UOB Malaysia", "DBS GROUP")
   were not. Spellings of one name were merged into one row as aliases.
   Ninety rows were drafted; the 79 with 23 or more sentences were kept, to
   stay within 80. Left out for frequency: DBS Cashline 22, Bank of Singapore
   22, liao 20, UOB Mighty 19, FIRE 16, kena 15, DBS Insignia 14, leh 14,
   whack 12, huat 12, buff 9, meh 9. Their drafted rows were not kept, so
   these counts were recounted on 7 Oct 2026 with the count step's word
   match on the cached corpus, using these aliases: Cashline; BOS; Mighty
   app; Insignia; whacked; buffed and buffs (the others alone). Without the
   aliases the counts are lower (Bank of Singapore 10, UOB Mighty 18, whack
   10, buff 4). "sia" was dropped because most of its
   97 matches are SIA, Singapore Airlines, not the particle.
4. **Counting** (`glossary_mine.py count`). A sentence counts for a row
   when it contains the term or any alias, ignoring case, as a whole word
   (no letter or digit touching the match on either side). The step writes
   `corpus_count` back into the CSV, sorts the rows, and saves up to eight
   example sentences per row to `data/run/upstream/glossary_examples.txt`
   for checking definitions.

## Reading the counts

- They are counts on the pretraining corpus, not on the whole database, so
  they are lower than the 2 Oct counts in `docs/local-context-questions.md`
  (UOB One: 2,852 here, 2,908 there).
- Ignoring case brings in other meanings: "miles" includes distance, "Tiger"
  can be the animal, "MCA" and "multi-currency account" include other banks'
  accounts, "Private Bank" covers all three banks, "lol" includes "LOL" in
  capitals, which is the same word. "UOB One" also counts the UOB One credit
  and debit cards.
- A sentence can count for several rows.

## Sources and what needs a person

- `corpus: sentence <id>`: a corpus sentence (a `sentence_id` in
  `data/plp.db`) that shows the term used in the meaning given. It supports
  the core meaning; details in the definition that the sentence does not
  state (who owns a brand, card network, tiers) still come from general
  knowledge. 61 rows.
- `docs: <file>`: the meaning is stated in a repository file. 8 rows,
  plus 5 corpus rows that also cite a doc.
- `general knowledge, to check`: neither the corpus examples nor the docs
  state it. 10 rows: DBS Multiplier, CPF, SSB, PayNow, DBS digiPortfolio,
  imo, iirc, OCBC Blue Chip Investment Plan, tbh, OCBC RoboInvest.

**Every row marked "to check" needs a person to confirm or correct it**, and
so does every `sentiment_note`, which records the assumption in
`docs/local-context-questions.md` or Claude's own reading, not a team
decision. Product terms change (rates, minimum spends, caps), so the
definitions avoid figures. Where a row touches an open team question
(priority banking as wealth or retail, DCA as a buying signal), the
`sentiment_note` says so; the glossary does not settle those questions.
