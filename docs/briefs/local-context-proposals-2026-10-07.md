# Local context: proposed answers for the team to confirm

7 Oct 2026. `docs/local-context-questions.md` has 23 questions; one (DBS
Vickers is DBS, UOB Kay Hian is not UOB) was decided on 4 Oct 2026 and is
in PLAN section 2 and `preprocess/bank_ner.py`. This page proposes answers to
the other 22. **Nothing here is decided**: each answer is a proposal for the
team to confirm or change, and the "Team answer:" lines in the questions file
are left blank for the team to fill.

## How the evidence was gathered

- **Corpus counts**: `data/run/upstream/local_context_counts.py`, run on
  7 Oct 2026 against `data/plp.db` opened read-only. The counts run over
  42,901 of the database's 44,345 sentences: the 41,923 that
  `train.dapt.build_corpus` leaves once every labelled sentence and its
  near-copies are removed, plus the 978 database sentences that are
  `train_dev` rows of the labels sheet. So no test sentence, and no
  near-copy of one, is counted. Case-insensitive word matches over
  `sentences.text` unless marked "capitals". The full output, with every
  pattern, is in `data/run/upstream/local_context_counts.json`. Some counts
  differ from the 2 Oct counts in the questions file because the patterns
  differ (for example "IBKR" here also matches "Interactive Brokers") and
  because those counts were over every sentence.
- **How people labelled matching sentences**: only the 1,258 `train_dev`
  rows of `data/labeled/combined/candidates.csv` (split `train_dev`).
  No test row was read for counting, quoting or choosing anything. Cross-tabs
  by source, aspect and sentiment: `data/run/upstream/local_context_crosstabs.py`.
- **Example sentences** are taken only from corpus sentences left after
  `train.dapt.build_corpus` (every labelled sentence, in every sheet, and its
  near-copies removed: 41,923 of 44,345 kept) and never from CNA articles.
  Quotes from the earnings reports are labelled with the bank.
- The 41,923 were counted with the 58 labelling files that existed before
  the active-learning sheet (`data/labeled/active/`) was made on 7 Oct 2026;
  `train.dapt.labelled_files()` now returns 59. The counts script leaves
  `data/labeled/active/` out so it reproduces them.
- **The banks' own product naming** comes from the earnings sentences in the
  database (the same script, "bank product naming").
- Where the train_dev rows that match a term number five or fewer, the
  people's labels are reported but are too few to show a pattern.

Throughout, "train_dev rows" means rows with split `train_dev` in that sheet.
Their overall sentiment split is 483 neutral, 473 positive, 302 negative;
the 433 Reddit rows among them are 186 neutral, 142 negative, 105 positive.

---

## Singapore banking products and names

### A rate cut on a savings account is retail banking, and negative?

**Proposed answer.** Yes on the aspect: a customer savings product (UOB One,
OCBC 360, DBS Multiplier, UOB Stash) and its rate, cap or bonus conditions
are `retail_banking_sentiment`, never NIM or dividends. On the sentiment, a
reported cut ("nerf") is negative; a bare statement of the current rate
follows whatever rule the team picks in the product-feature paper
(`docs/briefs/proposal-product-features-2026-10-07.md`).

**Evidence.**
- Corpus: UOB One 2,864 sentences (2,839 Reddit); OCBC 360 652; DBS
  Multiplier 727; UOB Stash 240; "bonus interest" 168; "salary credit" 246;
  "nerf" 149 (123 Reddit).
- People already file these under retail: every one of the 45 train_dev rows
  naming UOB One is `retail_banking_sentiment` (16 negative, 19 neutral, 10
  positive), as are all 12 naming OCBC 360 and all 12 naming DBS Multiplier.
  Of the 119 train_dev rows naming a savings product or a customer rate,
  86 of the 92 Reddit rows are retail; the only Reddit NIM row in the whole
  train_dev set is one negative row (crosstabs script).
- The banks' own reports never name UOB One or OCBC 360 (0 earnings
  sentences). They discuss deposits as "Casa" (206 earnings sentences) and
  fixed deposits (70), as funding that drives margin, e.g. [DBS] "As Casa
  flows out, it is a deliberate choice whether we want to replace it with
  fixed deposits." So a bank talking about its deposit mix is NIM; a customer
  talking about their account is retail.
- Both train_dev "nerf" rows are retail and negative.

**Confidence.** High on the aspect; medium on the sentiment of a bare rate
statement (it depends on the product-feature rule).

**If the team answers differently.** If customer rates were NIM, the 86
Reddit retail rows above would move aspect and the NIM aspect would fill with
customer chatter the earnings-based NIM rows don't resemble. The top-up sheet
rows the LLM called NIM would stay as the LLM put them: per
`docs/evidence/labelling-topup-2026-10-01.md`, 19 of its 42 NIM rows came
from Reddit, and a reading of those 19 found 16 to be customer rates (Opus,
labelling blind, called 19 of the 42 retail banking).
Rule: the `net_interest_margin` and `retail_banking_sentiment` rows of the
aspect table in `docs/annotation-guideline.md`.

### Mortgage repricing (FHR, SORA, "fixed for 2Y") is retail banking too?

**Proposed answer.** Yes when a customer discusses a package, rate or
repricing offer: `retail_banking_sentiment`. When the bank or an analyst
discusses SORA as a driver of the bank's earnings, it is
`net_interest_margin`.

**Evidence.**
- Corpus: SORA 92 (68 earnings, 20 Reddit); FHR 4 (all Reddit, word match;
  the 15 in the questions file was a looser match over every sentence);
  "mortgage" or "home loan" 170; "fixed rate/for/package" 56.
- Reddit uses are package quotes: "DBS repriced my loan to 3.15% fixed for 2
  years."; "OCBC gave me 2.8% for 1st year with conversion to 3m + 0.4% sora
  after 1 year." Earnings uses are about margin: [DBS] "We are now using
  assumptions of 1% for Sora and no US rate cuts."
- train_dev: the 9 SORA rows split the same way. The 4 earnings rows and 2
  of the 3 broker research rows are NIM (the third is macro); the 2 Reddit
  rows are retail and investor stock (one each).
- FHR as "Fixed Deposit Home Rate" is not confirmed by any text in the
  repository; a Reddit sentence says "DBS can change the FHR rate but not the
  spread", which fits a bank-set reference rate.

**Confidence.** High on the split by speaker; low on what FHR stands for (a
local reader should confirm; it doesn't change the aspect).

**If the team answers differently.** Few labels move (2 Reddit train_dev
rows). The rule matters more for the LLM and keyword aspect methods, which
see "SORA" and lean NIM. Rule: same two rows of the guideline's aspect table.

### OCBC's "Premier Dividend+" and "Dividend+" are deposit accounts?

**Proposed answer.** Yes: they are savings accounts, so
`retail_banking_sentiment`, never `dividend_policy`.

**Evidence.**
- Corpus: 47 sentences, all Reddit, e.g. "OCBC Premier Dividend+ Savings
  Account cutting interest rates again."; "For savings acct, OCBC Premier
  Dividend+ Savings Accounts gives 3.7% interest with no cap on the amt."
- The sentences themselves name it a savings account, quote an interest rate
  and a cap, and talk of transfers in from another OCBC account. None of the
  earnings sentences mentions it.
- No train_dev row mentions it, so no human label moves.

**Confidence.** High.

**If the team answers differently.** Nothing in the human labels changes;
the risk is entirely in automatic methods (keyword and embedding aspects read
"dividend"). Worth an explicit line in the guideline's `dividend_policy`
"not here" column, and a check in whichever aspect method the team picks.

### Priority and private banking products: wealth or retail?

**Proposed answer.** Follow the banks' own segment definitions. DBS Treasures
(and Treasures Private Client), OCBC Premier Banking and Premier Private
Client, UOB Privilege Banking and Privilege Reserve, and the private banks
(including Bank of Singapore) are `wealth_business`. A card or plain account
that a priority customer happens to hold (the DBS Insignia card, a
Premier-tier savings account such as Dividend+) is retail, because the
sentence is about a card or deposit product. This is a **team judgment**; the
banks' definitions are the strongest evidence available, but where the line
falls for a retail customer's brokerage or fund purchases is still open (see
below).

**Evidence.**
- Corpus: Treasures 228 (175 Reddit, 40 earnings); Premier 189; Insignia 14
  (all Reddit); Bank of Singapore 10 (leaving out "Development Bank of
  Singapore"); "private bank" 256; "priority bank" 12; "Privilege" 53.
- The banks' own naming, from their earnings text:
  - [DBS] "The wealth management segment comprises Treasures, Treasures
    Private Client, and Private Bank."
  - [OCBC] "The Group's wealth management income, comprising income from
    private banking, premier private client, premier banking, insurance,
    asset management and stockbroking, ..." (21 earnings sentences use this
    definition).
  - [UOB] footnotes: "Refers to Privilege Banking, Privilege Reserve and
    Private Bank." (10 earnings sentences).
- OCBC's definition counts **stockbroking** and **insurance** as wealth. That
  bears on the open part of this question: of the 48 Reddit train_dev rows
  people labelled `wealth_business`, 9 mention brokerage, trading, Vickers or
  CDP, 9 a unit trust, fund, ETF or robo-adviser, 4 SRS or CPF, 2 regular
  savings plans and 2 gold; 5 mention a priority or private tier.
- Opus disagreed with people on wealth against retail in 37 train_dev rows
  of `data/labeled/llm_rater/review_aspect.csv`, all Reddit; in 36 people said
  wealth and Opus said retail. So people lean "investment products are
  wealth" and Opus leans "anything a retail customer does is retail".
- But people are split, not consistent: 21 of the 303 Reddit train_dev rows
  they labelled `retail_banking_sentiment` match the same product-type
  patterns (12 a unit trust, fund, ETF or robo-adviser; 6 SRS or CPF; 4
  insurance or ILP; 1 brokerage and 1 a priority tier; a row can match more
  than one), against 29 of the 48 wealth rows (crosstabs script). So the lean
  towards wealth for investment products is weaker than the Opus
  disagreements alone suggest.

**Proposed wording for the guideline** (team to choose): "`wealth_business`
covers the banks' wealth segments as they define them: priority and private
banking tiers, and investment products sold to customers (brokerage, unit
trusts, robo-advisers, regular savings plans, insurance sold as investment).
A card, savings account or deposit is `retail_banking_sentiment` whoever
holds it."

**Confidence.** High that the named tiers are wealth (the banks say so);
medium on investment products (OCBC's definition supports wealth; the other
reading is defensible, and people's own labels are split: 29 of the 48 Reddit
wealth rows and 21 of the 303 Reddit retail rows match the product-type
patterns); the card and deposit carve-out is a team judgment.

**If the team answers differently.** If retail customers' investment products
go to retail instead, at most about 24 of the 48 Reddit wealth train_dev rows
would move to retail: 29 of the 48 match one of the product-type patterns in
the crosstabs script, but 5 of those 29 name a priority or private tier and
stay wealth either way. Reddit would then contribute little to
`wealth_business`, and the 21 retail rows that mention investment products
would already fit. Opus's 36 disagreements would
then mostly be resolved in Opus's favour. Rule: the `wealth_business` and
`retail_banking_sentiment` rows of the aspect table; must be settled before
the top-up round.

### Subsidiaries and apps count as the parent?

**Proposed answer.** Yes for POSB, PayLah!, digibank and UOB TMRW: they are
the bank's own brands and apps. Yes for Bank of Singapore (OCBC's private
bank). Great Eastern as OCBC is a **team judgment**; the proposal is yes,
because OCBC reports it inside its own results and counts insurance as
wealth income, but its news is about an insurer and it moves OCBC's index.

**Evidence.**
- Corpus: POSB 500; PayLah 156; digibank 49; TMRW 93; OCBC Securities 62;
  Great Eastern 110 (42 Google News, 42 CNA, 12 Reddit, 13 earnings); Bank of
  Singapore 10.
- The banks' own text: [DBS] "Our roots as the Development Bank of Singapore
  and our ownership of POSB ..."; [UOB] "our mobile-only digital bank, TMRW";
  [OCBC] "Its brokerage subsidiary, OCBC Securities, ..."; [OCBC] "We deployed
  capital to increase our stake in Great Eastern Holdings ("GEH") to 93.72%."
  OCBC's results slides report a "Profit contribution from GEH".
- Reddit readers treat Great Eastern as OCBC: "Great Eastern is under OCBC so
  not much difference."
- train_dev: 12 POSB rows (9 retail), 4 PayLah rows (all retail), 3 TMRW, 3
  Great Eastern (income, guidance, other), 2 Bank of Singapore (both wealth).
- This is already the rule in `preprocess/bank_ner.py` (PLAN section 7);
  the team is confirming it, not changing it.

**Confidence.** High for POSB, PayLah!, digibank, TMRW and Bank of
Singapore; medium for Great Eastern.

**If the team answers differently.** If Great Eastern is not OCBC, the
`great eastern` line of `RESOLUTION` in `preprocess/bank_ner.py` becomes
not-a-bank, and the 110 counted sentences (most of them news), and more
in the full database, leave OCBC's index
when NER is applied. Few labels move (3 train_dev rows).

### Tickers and market names, and other local terms

**Proposed answer.** Yes: D05, O39 and U11 resolve to DBS, OCBC and UOB; STI,
SGX and CDP are market infrastructure, not a bank. Other local terms a reader
would recognise and a model may not: "the 3 local banks" or "big 3" (a
sentence about all three), "BCIP" (OCBC's Blue Chip Investment Plan), "KF"
(KrisFlyer, as in UOB KF card), "SIA" (Singapore Airlines, in card and miles
talk), "OA/SA/MA" (CPF accounts), "HYSA" (high-yield savings account).

**Evidence.**
- Corpus: D05/O39/U11 126; STI 172; SGX 230; CDP 174 (173 Reddit); "big 3",
  "3 local banks" or "local banks" 85; SIA in capitals 74 (63 Reddit, mostly
  miles cards: "UOB KF Mastercard offers 3mpd if you send at least $800/yr in
  SIA group"); OA in capitals 72.
- Examples: "I bought D05 instead of putting my money in DBS, 4-5% dividends
  a year + capital growth"; "OCBC BCIP , poems Sharebuilder allow you to buy
  SGX that famous 3 local bank stocks at a fraction of their cost."
- train_dev: 4 ticker rows, 7 STI rows (all investor stock), 5 SGX rows.

**Confidence.** High on the tickers (the NER already does it); medium on
the list of extra terms (taken from the corpus, not checked by a local
reader).

**If the team answers differently.** Only NER and the keyword lists change.
Open for the team: should a "3 local banks" sentence count once for each
bank? NER currently needs a bank's name, so it counts for none.

### A bank's economists forecasting the economy

**Proposed answer.** Not sentiment about the bank. A forecast or warning by a
bank's economists or research desk about the economy, an index or another
company is `not_about_bank` (the bank is the source, not the subject). It
becomes macro sentiment only when the sentence ties the outlook to the bank's
own business ("rate cuts will squeeze our margin" is NIM; "slower trade will
hurt our loan growth" is macro). This is a **team judgment** with a clear
consequence for the macro aspect.

**Evidence.**
- Corpus: 137 sentences name a bank's economists, research desk or "DBS
  warns/expects/raises/..."; 110 are Google News. Examples: "DBS Group
  Research has raised its year-end target for the Straits Times Index (STI)
  to 5,850 ..."; "... DBS Group Research said." about AI computing demand.
  Some matches are about the bank itself ("DBS raises full-year outlook as
  record Q2 profit beats estimates"), so the pattern overcounts.
- train_dev: 5 rows match; people labelled them capital, guidance, other and
  investor stock, none macro.
- Two other train_dev rows, which the pattern misses, cut against the
  proposal: a bank's economists speak about the economy and people labelled
  both `macro_market_environment` (neutral). [earnings] "Our economists refer
  to this as 'TOTUS' ... trade outside the United States ..."; [Google News]
  "De-dollarisation will be a slow grind, says DBS India economist ahead of
  Brics summit". Under the proposal both would become `not_about_bank`. So
  the annotators so far have treated this as macro, not as not-about-bank.
- The whole train_dev set has 38 `macro_market_environment` rows (0 Reddit,
  13 earnings, 6 Google News, 18 broker research, 1 Yahoo).
- The questions file reports that Opus called 25 of the 52 top-up rows the
  LLM called macro not about the bank; that count was not rerun here.

**Confidence.** Low to medium. The rule is clean, but it leaves macro
small, and the two train_dev rows found (by searching for "economist") where
a bank's economists speak about the economy were labelled macro, not
not-about-bank. Two rows are too few to show a pattern, but they are the
only direct evidence of how people label this case.

**If the team answers differently.** If bank economists' forecasts count as
macro sentiment toward that bank, macro gains rows quickly from news, but the
index would move with the bank's forecasts about Vietnam or the STI rather
than with views about the bank. If the proposal stands, macro stays near its
38 train_dev rows and the team should decide whether macro is evaluated at
all or merged into `other`. Rule: the `macro_market_environment` row of the
aspect table and step 1 ("Is it about the bank?") of the guideline.

### Comparisons with brokers and robo-advisers

**Proposed answer.** About the bank when the bank's own product is judged or
compared ("For amounts above 10k, UOB's spread is more than the IBKR
commission." is negative for UOB); not about the bank when the bank is only
where the money comes from ("I made a USD transfer from DBS MCA to IBKR").
The aspect is the bank product compared: brokerage or funds go to wealth
under the proposal above, FX, transfers and accounts to retail.

**Evidence.**
- Corpus: IBKR or Interactive Brokers 806; moomoo or Tiger 338; Endowus,
  Syfe or StashAway 330; all Reddit.
- train_dev: 20 rows; 18 are retail (7 negative, 6 neutral, 5 positive), 1
  wealth, 1 investor stock. The sheet has no `not_about_bank` column, so
  "only the funding account" rows may simply have been labelled neutral.

**Confidence.** Medium: the rule is the guideline's step 1 applied; whether
a funding-account mention is neutral or not-about-bank is the team's call.

**If the team answers differently.** If any mention counts, the neutral class
grows with funding-account chatter. If brokerage comparisons go to retail
rather than wealth, it follows the wealth-or-retail answer above.

### Products that compete with bank deposits (SSB, T-bills, CPF, SRS)

**Proposed answer.** "T-bills beat UOB One now" is negative for the bank's
product (retail). A mention of SSB, T-bills, CPF or SRS with the bank only
as the channel ("I bought t-bills thru dbs") is neutral, or not about the
bank if it adds nothing about the bank. When the bank's report talks of
customers moving to T-bills, it is NIM (deposit outflows): [DBS] "Casa
deposits declined during the quarter as customers switched to higher
yielding instruments such as T-bills and fixed deposits."

**Evidence.**
- Corpus: SSB 214; T-bills 176 (9 earnings); CPF 261; SRS 256.
- train_dev: 17 rows; 11 retail (7 neutral), 4 wealth, 1 investor stock, 1
  Google News retail.

**Confidence.** Medium (same reasoning as the broker comparisons).

**If the team answers differently.** Few labels move; the main effect is on
the neutral share of retail.

### Scams and outages

**Proposed answer.** An outage, failed payment or security flaw that is the
bank's own is negative `retail_banking_sentiment`. An impersonation scam the
bank did not cause is neutral toward the bank, or not about the bank, unless
the sentence blames or praises the bank's handling ("Interest rate is
attractive but is OCBC safe given the scammers were able to bypass their
security features?" judges the bank). This is a **team judgment**: the
guideline files scams under retail but doesn't say whether a scam the bank
suffered is sentiment toward it.

**Evidence.**
- Corpus: scam 210 (89 Reddit, 63 Google News, 57 CNA); phishing 34;
  outage, "down again" or disruption 196 (82 CNA, 83 Google News).
- train_dev: scam 6 rows (5 retail negative, 1 retail neutral); outage 5
  rows (2 retail negative, 2 other negative, 1 capital negative).
- The banks' own report text treats outages as a regulatory and capital
  matter: [DBS] "... additional penalties on the CET-1 beyond the 40 basis
  points that was imposed for the first outage".

**Confidence.** High that the bank's own outages are negative retail; medium
on scams.

**If the team answers differently.** If every scam sentence is negative
retail, the news flow of scam warnings drives retail sentiment down without
anything the bank did. Rule: the guideline's `retail_banking_sentiment` and
`asset_quality` rows ("scams against customers"), and a sentence in step 1.

### MAS rules and notices: which aspect?

**Proposed answer.** Keep the assumed rule: prudential rules (capital,
liquidity, operational-risk capital, dividend guidance) go to the aspect they
affect, mostly `capital_liquidity`; customer-facing rules (cooling-off,
anti-scam measures, account rules) go to retail; regulatory boilerplate and
licensing mentions are `other` or not about the bank.

**Evidence.**
- Corpus: MAS in capitals 268 (99 earnings, 72 CNA, 51 Reddit, 45 Google
  News).
- Earnings uses are prudential: [UOB] "... NSFR is calculated based on MAS
  Notice 652 ..."; [DBS] "And any update from MAS on the operational risk
  multiplier?". Reddit uses are customer rules or licensing: "This free-look
  period is mandated by MAS so DBS would definitely abide."
- train_dev: 5 rows (other, retail twice, dividend, investor stock).

**Confidence.** High; it follows the existing aspect table.

**If the team answers differently.** Almost no labels move (5 rows).

---

## Singlish and local expressions

### Particles carry tone, not sentiment?

**Proposed answer.** Agreed: lah, leh, lor, meh, liao and sia mark tone. Label
the sentence's content. A particle can signal doubt ("meh") or resignation
("lor"), which can soften but not reverse the content.

**Evidence.**
- Corpus: lah 24, leh 14, lor 30, meh 9, liao 21, sia (lower case) 21, all
  Reddit apart from 6 "sia" in Google News, which are likely the airline in
  lower case. Examples: "DBS shares now very high leh"; "Just buy DBS lah.";
  "OCBC 360 at 1.45% when you cant hit the $500 spend is kinda meh ." (here
  "meh" is an English word meaning unimpressive, which is negative).
- train_dev: one row in all (a "liao" row, retail neutral).

**Confidence.** High. Note "meh" has an English sense (unimpressive) that
does carry sentiment.

**If the team answers differently.** Nothing in the labels moves; the answer
matters only for the error analysis of slang.

### Sentiment words: are these readings right?

**Proposed answer.** The table's readings look right to a non-native reader,
with three corrections from the corpus. A local reader must still check it.
- **heng**: of 8 sentences, 7 are Google News, where it is likely a surname;
  only 1 Reddit sentence uses the Hokkien word. Treat as a surname in news.
- **kena**: "got hit by" is right, but the object carries the sentiment:
  "I kena stolen card before in China, called UOB on the spot and all
  reversed." is positive about UOB overall.
- **divvy**: 3 word matches now (the questions file's 5 likely included
  "divvies"); two are in a valuation table ("Divvy: 5.49%"), neutral.
- **power**: of 34, 6 are Reddit and one is the slang ("Buy DBS, power
  ah!"); news uses ("pricing power") are the English word.
- **confirm**: of 50, most are the English verb ("could I confirm that ...").

**Evidence.** Counts by the counts script: huat 12, heng 8, jialat 2, sian 3,
shiok 2, kena 15, atas 1, paiseh 3, kiasu 1, kiasi 2, "die die" 3, "gone case"
1, kpkb 1, chio 2, lobang 3, ownself 6, whack 11, divvy 3, power 34, confirm
50. In train_dev: heng 1, whack 1, confirm 6; no other word appears.

**Confidence.** Medium overall; the table needs a local reader.

**If the team answers differently.** Almost nothing moves in the labels (8
train_dev rows contain any of these words). It matters for the report's
slang discussion and any slang list a preprocessing step uses.

### What do these mean? (xmm, Lobang Sis, the "DBS uncle" poster)

**Proposed answer.** **Claude cannot answer these; a local reader must.**
What the corpus does show:
- "xmm" occurs once in the corpus. Whether the sentence is positive about
  DBS depends on its meaning.
- "Lobang Sis" occurs twice, both as a source of card rules ("apparently
  Lobang Sis says cannot use DBS Woman's"). It reads as a deals source the
  writer trusts, not a bank.
- The poster's signed series appears in 9 sentences, each in a different
  post (9 documents, 13 counted sentences in those posts). Proposal: no
  special weight either way. Thirteen of the 24,260 counted Reddit sentences
  can't move an index.

**Evidence.** Counts script ("unknowns" and "poster_series" in its
output): 9 counted sentences carry the series' signature, in 9 documents,
and the counted sentences in those documents number 13.

**Confidence.** Low on meanings (not answered); high that the poster's
weight doesn't matter.

**If the team answers differently.** No label moves; none of these
sentences is in train_dev.

---

## Internet and investing slang

### "nerf" and "buff": always about the product?

**Proposed answer.** Agreed: a nerf is a product made worse for the customer
(a rate cut, a cap, a perk removed), a buff the reverse. The aspect is the
product's (retail for accounts and cards). A nerf is negative and a buff
positive for that product, whatever the stock does.

**Evidence.**
- Corpus: nerf 149 (123 Reddit); buff 10 (8 Google News). "Currently on UOB
  One but losing dollars there as they nerfed interest rates."; "the recent
  buff in the Lady's Card is very attractive."
- train_dev: both nerf rows retail negative; the one buff row retail
  positive.
- The questions file reports llama filing 11 of 37 nerf sentences as
  investor stock sentiment; that count was not rerun here.

**Confidence.** High.

**If the team answers differently.** Few human labels move; the LLM aspect
prompt would need an example either way.

### Do "lol", "lmao", "tbh", "sigh" or a laughing emoji change sentiment?

**Proposed answer.** No on their own. They mark tone or sarcasm. When they
mark sarcasm, label the intended meaning (the guideline's existing sarcasm
rule); otherwise ignore them. "I worked at a local SME once and they only
accepted DBS accounts lol." stays what its content says.

**Evidence.**
- Corpus: lol 166, lmao 14, haha 78, tbh 36, imo 56, iirc 60, sigh 2,
  laughing emoji 38 (all Reddit).
- train_dev: lol 3, lmao 1, haha 2, tbh 1, iirc 1, sigh 1, emoji 1; too few
  to show a pattern.

**Confidence.** High on the rule; it is already the guideline's sarcasm rule.

**If the team answers differently.** Almost nothing moves in the labels.

### Investing stance words (DCA, diamond hands, to the moon, stonks, FOMO, YOLO)

**Proposed answer.** A plan to keep buying the bank's stock ("Monthly DCA dbs
stock.") is mildly positive `investor_stock_sentiment`: the writer is
choosing to own more. A DCA plan through the bank's product ("DCA via OCBC
BCIP") is about the product, not the stock. FOMO about the stock is
ambiguous: "we are witnessing people fomo into dbs in real time" warns of a
bubble and reads negative. This is a **team judgment**; the guideline is
silent, and it is close to the product-feature question.

**Evidence.**
- Corpus: DCA 148; diamond hands 1; to the moon 1; stonks 4; FOMO 5; YOLO 7
  (4 of the 7 YOLO sentences are the UOB YOLO card, a product name, read by
  hand).
- train_dev: 4 DCA rows (2 retail neutral, 1 investor stock neutral, 1
  wealth negative); none of the other words.

**Confidence.** Medium on DCA of the stock; low on FOMO.

**If the team answers differently.** If a buying plan is neutral, the one
investor stock DCA row stays neutral; few labels move. Note for any keyword
list: "YOLO" is mostly a UOB card.

### "FIRE" and other acronyms with two readings

**Proposed answer.** FIRE in capitals is financial independence; "fire
insurance" is a home insurance product (retail). Other two-way terms found in
the corpus:
- **SIA**: Singapore Airlines (capitals, 74) against the particle "sia"
  (lower case, 21).
- **PayLah** against the particle "lah": a word match on "lah" doesn't hit
  "PayLah", but a tokenizer might.
- **YOLO**: the UOB YOLO card against the slang.
- **SA**: mostly the CPF Special Account, but also a savings account ("OCBC
  premier dividend+ SA", "UOB Gold SA") and once a French company suffix
  ("BNP Paribas SA"); 16 matches, read by hand.
- **PR**: permanent resident in 8 of 9 matches, public relations in 1 (read
  by hand).
- **Multiplier**: the DBS account in Reddit, but the operational-risk
  capital multiplier in DBS's earnings ("The operational risk multiplier was
  increased from 1.5 to 1.8 times ...").

**Evidence.** Counts script ("two readings", "savings rate cut"): FIRE in
capitals 9, fire insurance 4, SA 16, OA 72, PR 9, SIA 74.

**Confidence.** Medium; the list is what the corpus shows, not complete.

**If the team answers differently.** No labels move; the list matters for
keyword aspect rules ("multiplier" would send DBS capital sentences to retail).

---

## Sarcasm, jokes and questions

### Sarcastic expansions of a bank's name

**Proposed answer.** Yes: negative toward the bank named, and not about
OCBC. "Bank of Singapore" inside such an expansion is not OCBC's private
bank. The corpus has two more: "UOB = Use Other Banks" (negative about UOB)
and "DBS = Dont Be Scared" (encouraging, read in context).

**Evidence.** The counts script searched every counted sentence for
capitalised words whose initials spell DBS, UOB or OCBC, leaving out the real
names. The example in the question is not among the counted sentences (it is
a labelled sentence, or a near-copy of one, outside train_dev). Real
expansions occur once each: "Use Other Banks" and "Dont Be Scared". The rest are ordinary phrases
("Digital Banking Services", "Development Bank of Seychelles"). Neither of
the two is a labelled sentence.

**Confidence.** High on the reading; the expansions are rare (two in the
42,901 counted sentences, besides the question's own example).

**If the team answers differently.** No train_dev labels move. NER should
not add OCBC for "Bank of Singapore" in this pattern; that is a small fix in
`preprocess/bank_ner.py` if the team wants it.

### Contrarian jokes ("when the aunties buy, it's the top")

**Proposed answer.** Negative `investor_stock_sentiment` about the stock: the
writer is warning that the price has peaked. A local reader should confirm
the joke's reading.

**Evidence.** "auntie" or "uncle" occurs in 24 sentences; this joke once.
No train_dev row. Similar crowd-signal warnings appear in plain English ("If
even grab drivers are talking about DBS, then it seems like fomo investing.").

**Confidence.** Medium.

**If the team answers differently.** No labels move; it is a guideline
example for the investor stock aspect.

### Should annotators flag sarcasm?

**Proposed answer.** Yes, as an optional yes/no column on the sheet, filled
only when the annotator thinks the sentence is sarcastic. It costs a second
per row and lets the report count model errors on sarcasm, which can't be
measured now. Whether the extra column is worth it is a **team judgment**.

**Evidence.** "/s" marks 7 corpus sentences, all Reddit ("UOB is so
thoughtful and kind to us /s"); no train_dev row has one, so marked sarcasm
alone can't be measured.

**Confidence.** Medium.

**If the team answers differently.** Without the flag, sarcasm errors stay
unmeasured; the report should then say so.

### A question is not evidence?

**Proposed answer.** Agreed. A question is neutral unless it states a view
("Is OCBC safe given the scammers were able to bypass their security
features?" carries doubt and reads negative), and the chatbot should never
quote a question as supporting evidence.

**Evidence.**
- Corpus: 3,381 sentences end with "?" once trailing spaces are removed
  (counts script), and 2,757 of the 24,260 counted Reddit sentences end with
  "?" as stored ("reddit_questions" in its output).
- train_dev: 52 rows end with "?"; people labelled 45 neutral, 5 negative
  and 2 positive.

**Confidence.** High; people already label this way.

**If the team answers differently.** Few labels move. The chatbot's evidence
search would keep returning questions; the fix there is a filter that drops
sentences ending in "?" from quoted evidence (not made here).

---

## Notes

- The last section of the questions file ("What Claude Code assumed in its
  own analysis") lists judgements for people to check rather than questions;
  they have no "Team answer:" line and are not proposed on here, except that
  the customer-rates-as-NIM judgement is the first question above.
- The answers that change the most labels are the wealth-or-retail boundary
  (at most about 24 Reddit train_dev rows), and the bank economists question
  (whether macro survives as an aspect). The rest change few or no human
  labels but matter for NER and for keyword or LLM aspect methods.
- Scripts: `data/run/upstream/local_context_counts.py` (database and corpus
  counts, examples, the banks' naming, the expansions search, Opus's wealth
  and retail disagreements) and `data/run/upstream/local_context_crosstabs.py`
  (train_dev labels by source, aspect and sentiment). Both read only; the
  first writes `data/run/upstream/local_context_counts.json`.
