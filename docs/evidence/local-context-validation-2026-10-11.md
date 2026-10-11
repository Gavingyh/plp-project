# The seven recommended local-context answers, checked (2026-10-11)

On 11 Oct 2026 a web research pass answered the 23 questions in
[local-context-questions.md](../local-context-questions.md). Seven of the
answers are recommendations: judgment calls no web page settles. This note
checks each of the seven three ways and gives a verdict. Nothing in the
database, the labels or the guideline was changed.

## How each was checked

1. **Against the labelled rows.** The 1,676 sentences of the four labelling
   sheets that are not in a test split (978 of them labelled by people),
   with people's labels from `data/labeled/candidates.csv` and Opus's from
   `data/labeled/llm_rater/rules-2026-10-10/rater_labels.csv`. Test rows
   were left out on purpose: test text must not shape a labelling rule.
2. **Against the corpus.** The 45,844 sentences of `data/plp.db` as it
   stands after the 11 Oct merge and repairs, matched by word patterns, with
   base FinBERT's label for each. The patterns are rough: they count what a
   keyword finds, which is not always the thing meant.
3. **Against the sources.** Each cited page was fetched again and the
   quoted fact looked for.

## Results

| recommendation | labelled rows (no test rows) | corpus | sources | verdict |
|---|---|---|---|---|
| A bank economist's forecast is not about the bank | 6 rows; 1 labelled by people. Opus flagged the 3 pure forecasts as not about the bank and kept the 3 tied to the bank's own business | 29 sentences (0.06%); the model scores 25 positive or negative | both quotes confirmed | holds |
| An impersonation scam is not the bank's outage | outages: people negative on 7 of 7. Scams blaming the bank's handling: people and Opus negative on 5 of 5. Scams the bank did not cause: Opus neutral on 3 of 3, people on 1 of 3 | 345 scam sentences (0.75%), 153 scored negative; 19 with impersonation wording; 288 outage sentences, 193 negative | MAS and framework facts confirmed | holds |
| Annotators flag sarcasm | none of the rows carries "/s" | 7 marked sentences; the model calls 5 neutral | best system F1 of 0.71 confirmed | sources hold; not worth adding |
| A regular monthly purchase of a bank's shares is neutral | 6 rows; people 3 neutral and 1 negative of 4 labelled; Opus matches people on 4 of 4 | 154 sentences, 147 scored neutral; all 23 short ones neutral | a quoted phrase was not in the article; corrected | holds |
| "lol" and similar words do not change the label | 10 rows; people and Opus agree on 9 of 9 labelled | 300 sentences; 85% scored neutral, 12% negative (Reddit overall: 6.7% negative) | confirmed | holds |
| A "buy" beside a tiny upside is not a bullish view | not a labelling question | stored consensus: DBS "buy" with +0.9%, OCBC "buy" with -0.9%, UOB "hold" with +1.9% | thresholds confirmed after a correction (buy above about 15%, not 10% to 15%) | holds; no change needed |
| Report boilerplate stays out of the sentiment evidence | not checked on labels | 26 disclaimer sentences and 162 footnotes that define a term (0.41% together); the model scores 50 of the 188 positive or negative | confirmed; the source is about United States law | holds, as an evidence filter |

## What the checks add

- **Opus already follows the first two.** On economists' forecasts and on
  scams the bank did not cause, the Opus labels made on 10 Oct match the
  recommendation without having been told it. Since the models train on
  Opus's labels (decided 10 Oct), adopting the two changes no training label.
  People were not consistent on the scam rows (1 neutral, 2 negative).
- **A row flagged "not about the bank" is still trained on.** Opus flags 134
  of the 2,075 rows, including 32 of the 84 it calls macro, but each flagged
  row still has an aspect and a sentiment, and `train/finetune.py` reads no
  such flag. The economists recommendation only takes effect if those rows
  are left out, or the flag is carried into the training file.
- **The sarcasm flag would be an empty column.** Seven marked sentences in
  the corpus, none in the labelled rows, and people no longer label the
  sheets. The honest alternative is one sentence in the report: errors on
  sarcasm were not measured.
- **The model may under-read sentences with "lol".** People called 5 of the
  9 such rows negative, while the model calls 85% of the corpus's 300 such
  sentences neutral. Nine rows are too few to claim it.
- **The consensus wording is already right.** In six recent answers (the
  two consensus questions in three gold-set runs) the chatbot gave the
  rating and the implied upside as stored and called neither a bullish view.
  One answer misdescribed the analysts: "17 analysts who have rated the bank
  as 'buy' or 'strong buy'", where 17 is everyone who rated it.
- **Boilerplate barely touches the index.** About 188 sentences of 45,844.
  It matters in the chatbot's evidence, where a disclaimer line was returned
  for a target-price question on 11 Oct. Filter at evidence search, after
  someone reads the 188, since the patterns that counted them are rough.

## Two corrections made to the answers

- The dollar-cost averaging answer quoted "regardless of price" from an
  article that does not contain the phrase. It now quotes what the article
  says: the same number of dollars each month or each quarter.
- The broker ratings answer gave "buy" as a return above about 10% to 15%.
  The page lists above 15% at three brokers and above 20% at a fourth, with
  "hold" from about flat up to 10% or 15%.

## Limits

- Six to ten labelled rows stand behind most rows of the table. They show
  that a recommendation matches how the rows were labelled, not how often it
  would matter.
- The corpus counts come from keyword patterns and were not read sentence by
  sentence.
- Only the pages behind the seven recommendations were fetched again, and
  the check was for the quoted fact, not for everything the answer says.
- Two of the seven rest on a single source each (broker ratings, with
  Australian brokers; boilerplate, with United States law), as the answers
  themselves say.
