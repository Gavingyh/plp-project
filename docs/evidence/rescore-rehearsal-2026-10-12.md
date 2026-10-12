# Re-score rehearsal on a copy (12 Oct 2026)

**What this is.** The index served today is built from base FinBERT's
scores and the centroid method's aspects. The team has chosen a fine-tuned
model (the adapted encoder trained on the LLM's labels, three seeds averaged,
neutral margin 0; see [model-rerun-2026-10-11.md](model-rerun-2026-10-11.md))
and decided the re-score applies the LLM's aspects. This note records a
rehearsal of that re-score on a copy of the database, so the team can see
what every figure becomes before `data/plp.db` is changed.

**Result in one paragraph.** The step runs cleanly and passes its own checks.
Changing the aspect method alone leaves every headline figure exactly as it
is; changing the model moves them. All three banks' all-time headlines rise
(DBS 0.122 to 0.155, OCBC 0.136 to 0.143, UOB 0.074 to 0.117), DBS overtakes
OCBC, and the share of sentences labelled neutral falls from about
two-thirds to about half. The rise comes from Reddit; news from CNA turns
negative for all three banks. The per-aspect figures change far more than
the headlines, because each sentence now has one aspect where it had about
six.

`data/plp.db` was not touched: its SHA-256 after the run is
`97370949124341fe49e118058aff688b400903051260216e08dea031885914e3`, the same
as before.

## What was run

All of it on 12 Oct 2026, in under two hours. Scripts and the full output
are in `data/eval/rescore-rehearsal-2026-10-12/`.

1. **LLM aspects for the sentences that had none.** The answer cache held
   44,345 of the 45,844 sentences; the other 1,499 came in with the 11 Oct
   merge. `aspects.llm_classify --corpus --model llama3.1:8b` classified
   them. No answer needed the fallback to `other`.
2. **Scores from the chosen model.** The three models in
   `models/experiments-2026-10-11/dapt/seed_{42,1,7}/final` scored each
   (sentence, LLM aspect) pair on the CPU and their probabilities were
   averaged (`prescore.py`, then `scripts/rescore.py`).
3. **The re-score, on a copy.** `scripts/rescore.py --fresh-copy --aspects
   llm --finetuned --margin 0 --cpu --apply` on
   `data/run/rescore-2026-10-12/plp_rescored.db`, under the version tag
   `finbert-adapted-finetuned-2026-10-11-3seed-m0`. It removed 291,508
   aspect assignments and wrote 45,844, one per sentence; kept base
   FinBERT's score for every pair; added the chosen model's 45,844 scores;
   and deleted 254,132 scores for pairs that no longer exist.
4. **The index.** Rebuilt with the 7- and 30-day windows counted back from
   30 Sep 2026, the moment the stored index was computed, so the windows
   mean the same before and after. The copy holds 419 index rows for each
   model (the real database has 580 for base FinBERT; fewer cells are
   filled when a sentence has one aspect).

The copy therefore holds two models side by side on the same aspects, which
separates the two changes: "before" against "LLM aspects, base FinBERT"
shows the aspect method's effect, and "LLM aspects, base FinBERT" against
"LLM aspects, chosen model" shows the model's.

## Headline figures

Each cell is the index score, with the share of sentences labelled positive
/ neutral / negative. All sources, all aspects.

| Window | Bank | Sentences | Before | LLM aspects, base FinBERT | LLM aspects, chosen model |
|---|---|---|---|---|---|
| All time | DBS | 24,978 | 0.122 (22/67/10) | 0.122 (22/67/10) | **0.155** (33/51/16) |
| All time | OCBC | 7,774 | 0.136 (23/67/11) | 0.136 (23/67/11) | **0.143** (32/50/18) |
| All time | UOB | 13,092 | 0.074 (15/76/9) | 0.074 (15/76/9) | **0.117** (30/53/17) |
| 30 days | DBS | 312 | 0.012 (18/66/15) | 0.012 | **0.053** (30/49/20) |
| 30 days | OCBC | 105 | 0.213 (31/58/10) | 0.213 | **0.268** (41/46/13) |
| 30 days | UOB | 116 | 0.215 (28/65/7) | 0.215 | **0.202** (32/57/11) |
| 7 days | DBS | 40 | 0.204 | 0.204 | **0.180** |
| 7 days | OCBC | 14 | -0.109 | -0.109 | **-0.058** |
| 7 days | UOB | 7 | 0.244 | 0.244 | **0.052** |

**The aspect method does not move the headline.** The second and third
columns are identical. The headline counts each sentence once, and base
FinBERT gives a sentence the same score whatever its aspect, so reassigning
aspects only reshapes the per-aspect figures.

**The model does.** It changes the label of 13,154 of the 45,844 sentences
(29%). Most of the movement is out of neutral: 10,219 sentences that base
FinBERT called neutral become positive (6,896) or negative (3,323), and
1,874 go the other way. This is the behaviour the model was chosen for: on
the 299 test rows base FinBERT finds 21% of the negative sentences and the
chosen model 59%, at the cost of neutral recall (0.91 to 0.73).

**The order of the banks changes.** All time, OCBC led DBS by 0.014; now DBS
leads OCBC by 0.012. UOB stays last but closes most of the gap. Over 30
days OCBC is now clearly first and UOB second; before, the two were level.
The 7-day figures rest on 7 to 40 sentences and should not be read as a
ranking either way.

## Where the change comes from: by source

All time, all aspects. Score, with positive / neutral / negative shares.

| Source | Bank | Sentences | Base FinBERT | Chosen model |
|---|---|---|---|---|
| Reddit | DBS | 12,226 | -0.004 (6/88/6) | 0.067 (25/58/17) |
| Reddit | OCBC | 3,936 | -0.031 (4/88/8) | 0.002 (22/57/20) |
| Reddit | UOB | 9,371 | -0.022 (4/89/7) | 0.066 (26/57/17) |
| CNA | DBS | 915 | -0.013 (31/37/32) | -0.154 (27/33/40) |
| CNA | OCBC | 435 | 0.128 (34/44/21) | -0.017 (27/44/29) |
| CNA | UOB | 249 | 0.052 (31/43/26) | -0.126 (23/43/34) |
| Earnings reports | DBS | 9,093 | 0.286 (40/48/12) | 0.287 (41/46/13) |
| Earnings reports | OCBC | 1,561 | 0.375 (49/39/12) | 0.344 (46/40/14) |
| Earnings reports | UOB | 1,600 | 0.406 (52/36/12) | 0.335 (47/38/15) |
| Google News | DBS | 2,510 | 0.172 (33/53/14) | 0.204 (38/47/16) |
| Google News | OCBC | 1,446 | 0.218 (34/54/12) | 0.252 (41/46/14) |
| Google News | UOB | 1,491 | 0.201 (34/54/12) | 0.201 (36/50/14) |
| Broker research | DBS | 151 | 0.503 (63/24/13) | 0.557 (65/24/11) |
| Broker research | OCBC | 251 | 0.228 (45/33/22) | 0.189 (40/39/21) |
| Broker research | UOB | 239 | 0.236 (47/28/25) | -0.026 (31/37/33) |

Yahoo News and NewsAPI (fewer than 150 sentences a bank) are in
`rehearsal.txt`.

- **Reddit drives the headline rise.** Base FinBERT, trained on formal
  financial news, called 88 to 89% of Reddit sentences neutral. The chosen
  model calls 57 to 58% neutral, about a quarter positive and a sixth
  negative. Reddit is 56% of all sentences (25,533 of 45,844), so this one
  source moves the blended figure. It also explains why UOB gains most:
  72% of UOB's sentences are from Reddit (9,371 of 13,092), against 49% of
  DBS's and 51% of OCBC's.
- **CNA turns negative for all three banks**, by 0.14 to 0.18. The model
  moves 103 sentences from neutral to negative and 47 from positive to
  negative; in the 16 of them read, these were mostly reports of outages,
  regulatory action and scams.
- **Earnings reports barely move for DBS** and fall a little for OCBC and
  UOB. This is the formal financial language base FinBERT was built for, so
  there was least to correct.
- **UOB's broker research falls from 0.236 to -0.026**, on 239 sentences.
  This is the largest single change and the one most worth a person reading
  before the figures go live.

## Per aspect

All time, all sources; the full table is in `rehearsal.txt`. The change in
the number of sentences matters as much as the change in score.

| Aspect | Pairs before | Sentences after |
|---|---|---|
| retail_banking_sentiment | 37,301 | 19,684 |
| investor_stock_sentiment | 40,855 | 5,781 |
| wealth_business | 33,860 | 4,359 |
| other | 1,840 | 4,298 |
| income_profit_results | 10,411 | 3,672 |
| management_guidance | 36,911 | 2,154 |
| asset_quality | 32,140 | 1,632 |
| net_interest_margin | 19,223 | 1,407 |
| capital_liquidity | 34,925 | 1,252 |
| macro_market_environment | 5,422 | 942 |
| dividend_policy | 38,620 | 663 |

The centroid method gave a sentence every aspect it resembled, 6.4 on
average (291,508 pairs over 45,844 sentences), so most aspects were a
near-copy of the whole corpus and their scores sat close to the headline.
With one aspect a sentence the aspects separate:

- **Retail banking is now 43% of all sentences** and close to zero for every
  bank (DBS -0.046, OCBC -0.060, UOB 0.040), with about a quarter negative.
- **`other` stops being a complaints bin.** It was -0.93 for DBS on 971
  pairs; it is 0.044 on 2,532 sentences, about 80% neutral.
- **Income and results fall from about 0.78 to between 0.26 and 0.45.**
  Most of the fall is the aspect method, not the model: with base FinBERT
  on the LLM's aspects the three banks already score 0.50, 0.46 and 0.29.
- **Net interest margin turns slightly negative for OCBC and UOB** (-0.034
  and -0.033, from 0.486 and 0.387), on 170 and 190 sentences.
- **Wealth and dividends rise** (wealth: DBS 0.272 to 0.489; dividends: DBS
  0.198 to 0.452).

Several bank and aspect cells now rest on a few hundred sentences or fewer
all time (dividends for UOB: 71), and far fewer in the 30-day window. The
dashboard should show the count beside each per-aspect figure.

## How far to trust the new figures

- **The model is better than base FinBERT but wrong on about three test rows
  in ten.** On the 299 hand-labelled test rows, the three averaged score
  macro-F1 0.670 and accuracy 0.716 against base FinBERT's 0.571 and 0.699.
  Its precision on negative is 0.48, so on those rows about half of what it
  calls negative a person did not. That figure is measured against labels
  made under the earlier retail rule; the model was trained under the 10 Oct
  rule, under which a product's fee or feature carries sentiment, so some of
  the disagreement is the rule and not an error. How much is not measured.
- **A read of 32 changed sentences** (eight each from Reddit neutral to
  positive, Reddit neutral to negative, CNA positive to negative and CNA
  neutral to negative) found most consistent with the 10 Oct rule: card
  rewards and premier-tier perks now positive, fees and failed transactions
  now negative. A few looked wrong, for example a plain statement that a
  transfer is possible scored positive. This is a sanity check, not a
  measurement.
- **The index scale is unchanged**, but a neutral share of about half
  against two-thirds makes every figure more sensitive to the balance of
  positive and negative. Figures from before and after the re-score are not
  comparable, so a time series must use one model throughout.

## What the rehearsal did not cover

- **Bank recognition.** The two fixes approved on 11 Oct are in
  `preprocess/bank_ner.py`, but the stored bank tag of each sentence comes
  from alias matching at ingestion and no step re-tags stored sentences.
  The bank tags are the same before and after.
- **The wealth definition.** The LLM's aspects were made with the
  definition in `config/aspects.yaml` from before the 10 Oct rule (wealth
  means the priority tiers). Changing the definition starts a new answer
  cache and about a day of classification.
- **Serving.** To serve the new scores the version has to be listed in
  `FINETUNED` and named in `MODEL_VERSION` (`config/model_version.py`), and
  `assignment_method` set to `llm` in `config/aspects.yaml`, in the same
  commit as the re-score. The dashboard must filter on the model version
  first, or it will count both models' rows.

## To reproduce

```bash
data/eval/rescore-rehearsal-2026-10-12/run.sh        # waits for the two jobs, re-scores the copy, rebuilds its index
.venv-plp/bin/python3 data/eval/rescore-rehearsal-2026-10-12/compare.py > rehearsal.txt
```
