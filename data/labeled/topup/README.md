# Top-up labelling sheet

Sentences for the aspects with fewer than 80 labelled rows on 2026-10-01:
- `asset_quality`: 78 labelled
- `net_interest_margin`: 58 labelled
- `capital_liquidity`: 49 labelled
- `dividend_policy`: 33 labelled
- `macro_market_environment`: 22 labelled

Label them exactly as the 27 Sep round, following
`docs/annotation-guideline.md` (version 2): fill `aspect`, `label`,
`not_about_bank` and `annotator`. Every row is train/dev; none goes to the
test split.

The sheet is blind: it shows no model answer. The sentences were found by
centroid similarity and checked by `llama3.1:8b`, whose aspect is kept in
`llm_aspects.csv` for comparison after labelling; don't open it first. The
annotators of the 27 Sep round kept the model's suggestion on 92% of rows,
which is why it isn't shown here.

Two people should label the same 40 rows first and check aspect agreement:

    .venv-plp/bin/python3 -m train.agreement --a sheet_a.csv --b sheet_b.csv --field aspect
