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

## The wealth rule's extension to four more products

The team's wealth rule names loans, mortgages and unit trusts as products
that are not wealth by themselves. The raters' instructions applied the same
to brokerage accounts, regular savings plans, insurance and robo-advisers.
Checked on 11 Oct and confirmed by the owner the same day.

- **How the banks define a wealth customer:** by tier. DBS's earnings text
  says the wealth management segment "comprises Treasures, Treasures Private
  Client, and Private Bank"; UOB's footnotes say "Privilege Banking,
  Privilege Reserve and Private Bank". Comparison sites put entry at about
  S$200,000 for OCBC Premier and S$350,000 for DBS Treasures and UOB
  Privilege.
- **Whether the four products are for those customers only:** no. OCBC's
  Blue Chip Investment Plan starts "from just S$100/month" (its own page),
  and DBS Invest-Saver is sold from S$100 a month to any adult.
- **How the banks book the income:** as wealth income. OCBC's wealth
  management income covers "private banking, premier private client, premier
  banking, insurance, asset management and stockbroking"; DBS's first-quarter
  2026 release reports wealth management fees "driven by higher investment
  product sales and bancassurance".
- **Who is speaking, in the corpus** (45,844 sentences, keyword counts):
  brokerage 1,803 sentences, 1,754 of them Reddit; robo-advisers 539, 531
  Reddit; regular savings plans 138, 136 Reddit; insurance 779, of which 322
  Reddit and 307 the banks' reports. Sentences that also name a wealth tier:
  25, 3, 0 and 54.
- **How the rows were labelled** (74 rows outside the test split). Reddit:
  Opus filed 53 of 54 under retail banking; people, on the 34 they labelled,
  20 under retail and 13 under wealth. Bank and news rows: Opus filed 11 of
  20 under income results and 2 under wealth, the same as its 1 Oct run and
  as people on every row but one, a footnote that defines wealth management
  income.

So the extension follows the banks' own split: the customers are retail,
the income line is wealth. The guideline now says both halves. No row needs
relabelling beyond that one footnote.

Sources: [DBS first-quarter 2026 results](https://www.dbs.com/newsroom/First_quarter_net_profit_rises_to_SGD_2_93_billion_as_total_income_reaches_a_new_high_led_by_record_wealth_management_performance_ROE_at_17_0pct);
[OCBC Blue Chip Investment Plan](https://www.ocbc.com/personal-banking/investments/blue-chip-investment-plan);
[OCBC wealth management income, first half 2026 (Pulse 2.0)](https://pulse2.com/ocbc-wealth-management-income-reaches-record-s3-29-billion-and-41-of-total-revenue/);
[Regular savings plans in Singapore (MoneySmart)](https://blog.moneysmart.sg/invest/regular-savings-plans/);
[Priority banking accounts compared (SingSaver)](https://www.singsaver.com.sg/banking/comparison/priority-banking).
The DBS and UOB tier definitions are from the banks' earnings text in the
corpus. Only the first two pages were opened; the others are as the search
reported them.

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
