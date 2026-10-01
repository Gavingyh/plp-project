# A top-up labelling sheet for the five thin aspects

PLAN section 6 asks for about 80 labelled rows per aspect. After the 27 Sep
round, five aspects are below that. This exports a blind sheet of 268
unlabelled sentences for them. Run 2026-10-01, 21:04–22:54 (it shared Ollama
with the chatbot evaluation for most of that time). Nothing was written to the
database, and nothing has been labelled yet.

```bash
HF_HUB_OFFLINE=1 .venv-plp/bin/python3 -m preprocess.export_topup
```

Output: `data/labeled/topup/topup_sheet.csv` (the sheet),
`llm_aspects.csv` (the LLM's aspect per row, kept apart from the sheet) and
`README.md` (instructions for the annotators).

## Targets

| aspect | labelled on 27 Sep | rows asked for (shortfall to 80, plus 20, at least 30) | in the sheet |
|---|---|---|---|
| asset_quality | 78 | 30 | 30 |
| net_interest_margin | 58 | 42 | 42 |
| capital_liquidity | 49 | 51 | 51 |
| dividend_policy | 33 | 67 | 67 |
| macro_market_environment | 22 | 78 | 78 |
| **total** | | **268** | **268** |

The margin of 20 allows for rows the annotators move to another aspect or
mark `not_about_bank`.

## How the rows were chosen

1. **Pool.** For each target, the unlabelled sentences with the highest
   centroid similarity to it, three per row asked for, taken in turn from
   Reddit, earnings and news. PDF debris (`preprocess.fragments`) and
   repeated texts were removed. Each sentence is pooled once, for the first
   target that reached it. Result: 804 sentences (268 earnings, 268 Reddit,
   268 news).
2. **Check.** `llama3.1:8b` gave each pooled sentence one aspect
   (`aspects.llm_classify`, temperature 0). It agreed with the target the
   sentence was pooled for on 35% of the pool. That fits the centroid
   method's known weakness (top-1 0.413 on the human labels,
   [llm-aspect-classifier-2026-10-01.md](llm-aspect-classifier-2026-10-01.md)).
3. **Select.** A sentence counts towards a target if the LLM gave it that
   target, whichever target's pool it came from. Up to the quota per target,
   taken in turn from each (source group, bank) cell. 211 of the 268 (79%)
   were pooled for the aspect the LLM gave them. The rest came from another
   target's pool: 22 of the 42 NIM rows came from the macro pool.

| LLM aspect | earnings | news | Reddit | DBS | OCBC | UOB |
|---|---|---|---|---|---|---|
| asset_quality | 26 | 4 | 0 | 19 | 3 | 8 |
| capital_liquidity | 35 | 15 | 1 | 25 | 5 | 21 |
| dividend_policy | 28 | 22 | 17 | 28 | 26 | 13 |
| macro_market_environment | 29 | 31 | 18 | 36 | 27 | 15 |
| net_interest_margin | 13 | 10 | 19 | 20 | 11 | 11 |
| **total** | 131 | 82 | 55 | 128 | 72 | 68 |

**The sheet is blind.** It shows no model answer, although the guideline
shows suggestions on train/dev rows. On 27 Sep the annotators kept the
model's suggestion on 92% of rows. A blind sheet makes their aspect a
measurement of the LLM instead of a copy of it. Every row is `train_dev`.

## Checked before committing

- 268 rows, every `sentence_id` unique, none already in
  `data/labeled/candidates.csv`, no two texts the same after lowercasing
  and spacing.
- `aspect`, `label`, `not_about_bank`, `annotator` and `notes` are blank;
  no model output is in the sheet; `llm_aspects.csv` covers the same 268
  ids.
- Two rows per aspect read, and every Reddit row for NIM, dividend
  and macro, plus every news and earnings row for NIM.

## What the reading found: NIM may end near the floor

The guideline's own boundary says rates offered to customers belong under
`retail_banking_sentiment`, not NIM. Earnings and news sentences about NIM
are mostly about NIM. The Reddit rows the LLM called NIM mostly aren't. My
reading, which is not a label:

- 16 of the 19 Reddit NIM rows are customer rates: mortgage repricing
  ("1.2M loan with DBS (3.1%), able to reprice to 2.7%"), UOB One and Stash
  deposit rates. Three are about the bank's margin ("59% of DBS revenue
  still came from net interest income").
- 3 of the 23 news and earnings NIM rows are deposit-rate revisions
  announced to customers.
- 5 of the 17 Reddit dividend rows are about OCBC's "Premier Dividend+"
  deposit account, not the bank's dividend.

If the annotators agree, NIM gains about 23 rows and reaches about 81, just
over the floor. The other four aspects stay well over 80. The cause is the
selection, not the pool alone. Each target takes rows from each
(source, bank) cell in turn, so Reddit gets about a third of the slots,
and more where earnings and news run short (19 of 42 for NIM), even for an
aspect that is mostly written in earnings text. On Reddit the closest matches to NIM are posts about rates,
and `llama3.1:8b` calls rate talk NIM. On the labelled sentences its NIM
precision is 0.69, and only 5 of its 64 NIM answers were retail. This pool
was skewed towards that confusion.

The sheet is left as is. The mislabelled rows still get labelled, under
retail banking. If NIM ends below 80, a second pass should draw NIM from
earnings and news only.

## For the people labelling

`data/labeled/topup/README.md`: label as in the 27 Sep round
(guideline version 2). Two people label the same 40 rows first and check
aspect agreement:

```bash
.venv-plp/bin/python3 -m train.agreement --a sheet_a.csv --b sheet_b.csv --field aspect
```

Don't open `llm_aspects.csv` until labelling is done; afterwards it gives the
LLM's accuracy on a second, blind sample. Merging the labelled rows into
`candidates.csv` needs `url` and `published_at` from the database; no merge
script exists yet.

## Code

`preprocess/export_topup.py`; tests in `tests/test_export_topup.py` (quotas,
pooling in turn across sources, selection up to quota across banks, and the
pool's removal of labelled sentences, PDF debris and repeated texts).
