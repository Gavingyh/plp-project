# Local context: questions for people

The corpus is Singaporean: Reddit's r/singaporefi and r/singapore, local
news, and the banks' own reports. The models that read it were trained on
general English: FinBERT on financial news, `llama3.1:8b`, `qwen3:4b` and
Opus 5.5 on the web at large. Claude Code, which did much of the analysis,
also made assumptions about what local words and products mean. This file
lists every such point found so far, as a question a person who knows
Singapore banking and Singlish can answer.

Each item gives the question, how often it occurs in the 44,345 corpus
sentences (counted on 2026-10-02 by a case-insensitive word match, so a
count can include another meaning; where that happens it is split), what was
assumed and by whom, and why the answer matters. Write the team's answer
under each; where it changes a rule, the item says where the rule lives.

**How much it matters, in one paragraph.** Singlish itself is rare: 121
sentences (0.3%) carry a particle such as *lah*, *lor* or *liao*, and only about
a dozen of the 1,277 labelled sentences contain any Singlish, slang or emoji
(12 by the 2 Oct word match, whose word list wasn't recorded), so how
the models handle it is barely measured (on those 12, base FinBERT gave a
different label from people on 2 and none on 3). Local **product** vocabulary is common: "UOB One" alone is in
2,908 sentences, and the aspect a product sentence belongs to (retail
banking, wealth, NIM, dividends) is where the models go wrong most (DESIGN
decision 21; the top-up and Opus evidence). The banking-products section and
Claude's own assumptions (the last section) are where answers change the
most labels.

**Adopted on 2026-10-11.** The owner adopted six of the seven recommended
answers below (economists' forecasts, scams, regular monthly purchases,
"lol", the small "buy" rating, report boilerplate) and dropped the sarcasm
flag. They are written into `docs/annotation-guideline.md`.

---

## Singapore banking products and names

**A rate cut on a savings account ("UOB One nerf", "OCBC 360 nerf") is
retail banking, not net interest margin or dividends. Right? And is it
negative sentiment toward the bank?**
- Occurs: UOB One 2,908; OCBC 360 670; DBS Multiplier 746; UOB Stash 241;
  "bonus interest" 172; "salary credit" 250; "nerf" 154.
- Assumed: retail banking, negative (the guideline's "not here" column says
  rates offered to customers are retail banking). `llama3.1:8b` filed 11 of
  the 37 "nerf" sentences it has classified as investor stock sentiment, e.g.
  "Even with the latter's recent nerf, I'm still sticking with the UOB
  ecosystem."
- Matters for: the NIM and retail banking aspects; the top-up sheet, where 19
  of the 42 rows the LLM called NIM are customer rates.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Yes on both counts. UOB One, OCBC 360, DBS Multiplier and UOB Stash are savings accounts that pay the customer bonus interest for meeting conditions (salary credit, card spend, a growing balance), so a cut to that interest is a change to a retail product; net interest margin is the bank's own measure (interest earned less interest paid, relative to its interest-earning assets) and a dividend is paid on shares. Under the team's decision of 10 October 2026 a rate cut is a feature clearly bad for the customer, so it is negative on retail banking, while a bare mention of the account stays neutral. The drafted proposal is kept; the point it left open (a plain statement of the current rate) is settled by that decision.

  **Sources.** [Revision of UOB One Account Interest Rates (UOB notice, effective 1 September 2025)](https://www.uob.com.sg/assets/web-resources/personal/pdf/save/everyday-accounts/revision-of-interest-rates-for-uob-one-account-202508.pdf); [OCBC 360 Account | High Interest Savings Account | Salary Crediting](https://www.ocbc.com/personal-banking/deposits/360-savings-account); [Open a High Interest Savings Account with DBS Multiplier](https://www.dbs.com.sg/personal/deposits/bank-earn/multiplier); [Stash Account | UOB Singapore](https://www.uob.com.sg/personal/save/savings-accounts/stash-account.page); [UOB One Account nerfing interest rates to 1.9% p.a. from December 2025 (The MileLion)](https://milelion.com/2025/11/01/uob-one-account-nerfing-interest-rates-to-1-9-p-a-from-december-2025/); [Net interest margin (Wikipedia)](https://en.wikipedia.org/wiki/Net_interest_margin).

  **Confidence.** High. The four banks' own pages call these savings accounts, and UOB's notice describes the cut as a revision of the account's rates "to align with long-term interest rate environment expectations".

  **What it changes.** No rule changes: `docs/annotation-guideline.md` already lists rates offered to customers under retail banking, and the 10 October 2026 rule makes a cut negative. The 11 "nerf" sentences `llama3.1:8b` filed as investor stock sentiment point to a missing example in `config/aspects.yaml` (`llm_examples`); adding one starts a new aspect cache file.

**Mortgage repricing (FHR, SORA, "fixed for 2Y") is retail banking too?**
- Occurs: SORA 96; FHR 15 (DBS's Fixed Deposit Home Rate, assumed).
- Assumed: retail banking; a customer comparing package rates is sentiment
  toward the bank as a lender, not toward its margin.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Yes when a customer is discussing a home loan package. FHR is confirmed: DBS's own home loan page says "FHR refers to Fixed Deposit Home Rate, a reference rate unique to DBS", and gives FHR6 as based on DBS's prevailing 6-month Singapore dollar fixed deposit rate for S$1,000 to S$9,999. SORA is the Singapore Overnight Rate Average, which MAS administers; floating home loans are pegged to 3-month compounded SORA plus the bank's spread, and "fixed for 2Y" is a package whose rate is fixed for a two-year lock-in. The drafted proposal is kept (a customer's package is retail banking; SORA as a driver of the bank's earnings is net interest margin), and its one low-confidence point, what FHR stands for, is now confirmed.

  **Sources.** [Secure your dream property with DBS Private Home Loan (DBS)](https://dbs.com.sg/personal/loans/homeloans/buy-private-property); [SORA Interest Rate Benchmark (MAS)](https://www.mas.gov.sg/monetary-policy/SORA).

  **Confidence.** High. Both are primary sources.

  **What it changes.** Nothing in the labels. The "(DBS's Fixed Deposit Home Rate, assumed)" note in this question can be read as confirmed. An aspect method that sees "SORA" and leans to net interest margin still needs the split by who is speaking.

**OCBC's "Premier Dividend+" and "Dividend+" are deposit accounts, not
the bank's dividend. Right?**
- Occurs: 52, e.g. "OCBC already nerfed their dividend+ from 3.7% to 3.3%".
- Assumed by Claude, confirmed by Opus on the top-up sheet (5 rows moved from
  dividend policy to retail banking). An embedding or keyword method will
  read them as dividend policy.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Right. OCBC's own page calls it the "Premier Dividend+ Savings Account": a savings account for OCBC Premier Banking customers who open it with at least S$50,000 in fresh funds, paying a base rate plus bonus interest for months with no withdrawals (up to 1.70% a year on the page as opened on 11 October 2026). It has nothing to do with the dividend OCBC pays its shareholders, so it is retail banking, never dividend policy. The drafted proposal is kept.

  **Sources.** [Premier Dividend+ Savings Account | OCBC Premier Banking](https://www.ocbc.com/premier-banking/our-solutions/deposits/premier-dividend-plus-savings); [Home | OCBC Premier Banking (the page behind ocbc.com/dividendplus)](https://ocbc.com/dividendplus).

  **Confidence.** High. Primary source. The older rates quoted in the corpus (3.7%, 3.3%) were not checked.

  **What it changes.** No human label moves. The account is open only to Premier Banking customers, but under the 10 October 2026 rule a savings account is retail banking unless the sentence is about the wealth tier itself. Worth naming in the `dividend_policy` "not here" column of `docs/annotation-guideline.md`, and a keyword or embedding aspect method needs a check for "Dividend+".

**Where do priority and private banking products belong: DBS Treasures,
OCBC Premier, Bank of Singapore, the DBS Insignia card?**
- Occurs: Treasures 231; Premier 206; Insignia 15; Bank of Singapore (NER
  stratum, 20 in the gold sheet).
- Assumed: unresolved. This is the wealth-versus-retail boundary that
  explains 63 of Opus's aspect disagreements with the human labels; the
  guideline draws it loosely.
- Answer goes into: `docs/annotation-guideline.md`, before the top-up round.
- Team answer:

  **Answer (decided by the team on 2026-10-10, recorded with web sources on 2026-10-11).** `wealth_business` covers the priority and private banking tiers (DBS Treasures, priority banking and the like) and the wealth segment's figures; loans, mortgages and unit trusts are retail banking unless the sentence is about a wealth tier. The web agrees on which names are tiers: DBS presents Treasures as wealth management, a Singapore comparison lists DBS Treasures, OCBC Premier Banking and UOB Privilege Banking as priority banking from S$350,000 (with UOB Wealth Banking from S$100,000), and Bank of Singapore describes itself as "a wholly-owned private banking subsidiary of OCBC". The DBS Insignia is an invitation-only credit card (S$500,000 income or a Treasures Private Client relationship, S$3,270 annual fee), so a sentence about its miles or fee is about a card and is retail banking. This differs from the drafted proposal's wording, which sent a retail customer's investment products to wealth: the team decided the reverse.

  **Sources.** [Treasury Deposit, Trading & Investment Plans | DBS Treasures Singapore](https://www.dbs.com.sg/treasures/default.page); [A Full Guide To Priority Banking In Singapore (2026) (SingSaver)](https://www.singsaver.com.sg/personal-loan/blog/priority-banking-singapore-guide); [Bank of Singapore | Asia's global private bank](https://bankofsingapore.com); [Review: DBS Insignia (The MileLion)](https://milelion.com/2026/04/25/review-dbs-insignia-credit-card/).

  **Confidence.** High on the rule (it is the team's decision) and on which names are tiers. The Insignia reading is a recommendation that follows from the rule, not part of the team's note.

  **What it changes.** Already written into `docs/annotation-guideline.md` ("Two rules decided on 2026-10-10"). Two small additions to consider there: name UOB Wealth Banking among the tiers, and give the Insignia card as an example of a card that stays retail.

**Is DBS Vickers "DBS"? Is UOB Kay Hian "UOB"?**
- Occurs: Vickers 541; Kay Hian 144.
- Assumed: both are brokers, not the bank (PLAN section 7), so NER drops 456
  DBS Vickers sentences from DBS. UOB Kay Hian is a separate listed company;
  DBS Vickers is DBS's own brokerage, which makes it the contestable one.
- Answer goes into: `preprocess/bank_ner.py`, the `vickers` line of
  `RESOLUTION`.
- Checked on the web (2 Oct): DBS Vickers Securities (Singapore) Pte Ltd is
  a DBS subsidiary, listed with its holding company in DBS Group's list of
  subsidiaries at 31 Dec 2024 ([DBS](https://www.dbs.com/iwov-resources/images/investors/other-materials/2025/list-of-subsi-and-assoc.pdf)). UOB Kay Hian Holdings is
  separately listed on SGX (U10), and UOB is its largest shareholder with
  about a third ([Simply Wall St](https://simplywall.st/stocks/sg/diversified-financials/sgx-u10/uob-kay-hian-holdings-shares/ownership)), so it is not part of UOB. Of
  the 456 DBS Vickers sentences, 451 are from Reddit: customers using it as
  their broker (fees, paying upfront, CDP, SRS, the app). None of the twelve
  that use words such as "analyst" or "recommend" is research about another
  bank. The next question's rule, that subsidiaries count as the parent,
  puts DBS Vickers in DBS.
- Suggested answer: DBS Vickers is DBS; UOB Kay Hian is not UOB.
- Decided 4 Oct 2026: DBS Vickers is DBS; UOB Kay Hian is not UOB (PLAN section 2).
- Team answer:

  **Answer (decided by the team on 2026-10-04, rechecked on the web on 2026-10-11).** The decision of 4 October 2026 stands and the web still supports it: DBS Vickers is DBS, UOB Kay Hian is not UOB. DBS Vickers trades as DBS Vickers Securities (Singapore) Pte Ltd and its own site ties it to DBS accounts (lower commission when settling through a DBS multi-currency account). UOB-Kay Hian Holdings is a separately listed broker in which UOB has a deemed interest of 33.51%, a minority, according to the substantial shareholders table of its 2024 annual report; Wikipedia's summary box lists UOB as its parent, which overstates a one-third holding.

  **Sources.** [DBS Vickers Online Trading](https://www.dbsvickers.com/vickers/default.page); [UOB-Kay Hian Holdings Limited Annual Report 2024 (SGX)](https://links.sgx.com/1.0.0/corporate-announcements/R3CRJY2XHBYM2N9L/839897_UOBKHHL%20Annual%20Report%202024.pdf); [UOB-Kay Hian (Wikipedia)](https://en.wikipedia.org/wiki/UOB-Kay_Hian).

  **Confidence.** High. Company sources for both.

  **What it changes.** Nothing. `preprocess/bank_ner.py` already resolves "vickers" to DBS and "kay hian" to not-a-bank.

**Subsidiaries and apps count as the parent: POSB, PayLah! and digibank
as DBS; Great Eastern and Bank of Singapore as OCBC. Right?**
- Occurs: POSB 535; PayLah 161; digibank 52.
- Assumed: yes (PLAN section 7). Great Eastern is an insurer OCBC controls;
  counting its news as OCBC moves OCBC's index.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Right for all of them as a matter of fact. DBS bought POSBank in 1998 and kept the brand; PayLah! is DBS Bank's payments app and digibank its banking app; UOB TMRW is UOB's mobile banking app; Bank of Singapore is OCBC's wholly owned private bank. Great Eastern is a listed insurer that OCBC controls: OCBC held close to 94% at the end of 2024, and after its delisting offer failed on 8 July 2025 the insurer was to issue new shares that take OCBC's holding to about 88%. The drafted proposal is kept with that stake updated (it quoted 93.72%); whether Great Eastern's news should move OCBC's index is still the team's choice, and OCBC itself calls the insurer "a strategic pillar of the Group's wealth management and insurance businesses".

  **Sources.** [DBS Bank to acquire POSBank (DBS press release, 24 July 1998)](https://www.dbs.com/newsroom/DBS_Bank_to_acquire_POSBank_MIGRT); [DBS PayLah! Your Ultimate Payment App | DBS Singapore](https://www.dbs.com.sg/personal/deposits/pay-with-ease/dbs-paylah); [Revision of UOB One Account Interest Rates (UOB notice, which names "UOB TMRW, the mobile banking app")](https://www.uob.com.sg/assets/web-resources/personal/pdf/save/everyday-accounts/revision-of-interest-rates-for-uob-one-account-202508.pdf); [Bank of Singapore | Asia's global private bank](https://bankofsingapore.com); [Winning as One Group (OCBC Annual Report 2024)](https://www.ocbc.com/group/investors/annual-reports/2024-annual-report/winning-as-one-group.page); [Great Eastern to resume trading as delisting bid fails (Fortune, 9 July 2025)](https://fortune.com/asia/2025/07/09/great-eastern-ocbc-delisting-bid-fails/).

  **Confidence.** High for POSB, PayLah!, digibank, TMRW and Bank of Singapore. High that Great Eastern is an OCBC subsidiary; medium on the exact stake today, because the 88% figure is from a July 2025 news report of what was planned.

  **What it changes.** No rule changes. One gap in `preprocess/bank_ner.py`: `RESOLUTION` has lines for POSB, Bank of Singapore and Great Eastern but none for PayLah, digibank or TMRW, so a sentence that names only the app resolves to no bank (checked on 11 October 2026 with three made-up sentences). Adding those lines is a team decision because it changes which sentences count for a bank.

**Tickers and market names: D05, O39 and U11 are the three banks on SGX;
the STI is the index they are in. Anything else a local reader would
recognise that the models don't?**
- Occurs: D05/O39/U11 130; STI 174; SGX 233; CDP (with brokers) common.
- Assumed: tickers resolve to the bank (`preprocess/bank_ner.py`).
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Right: D05, O39 and U11 are the SGX stock codes of DBS Group Holdings, OCBC and UOB, and the Straits Times Index is the 30-company benchmark they sit in. CDP is the Central Depository, a wholly owned SGX subsidiary that holds SGX-listed shares in the investor's own name, as opposed to a broker's custodian account. Other local terms checked on the web: BCIP is OCBC's Blue Chip Investment Plan (a monthly plan from S$100 whose counters include DBS and UOB shares), "mpd" is miles per dollar, KF is KrisFlyer as in the KrisFlyer UOB Credit Card, SIA is Singapore Airlines, and OA and SA are the CPF Ordinary and Special Accounts. The drafted proposal is kept; "HYSA" and "the big 3" from its list were not researched.

  **Sources.** [Straits Times Index (Wikipedia)](https://en.wikipedia.org/wiki/Straits_Times_Index); [What is a CDP account (Syfe)](https://www.syfe.com/magazine/what-is-cdp-account/); [OCBC Blue Chip Investment Plan (BCIP) | ETF's & Blue Chip Stocks](https://www.ocbc.com/personal-banking/investments/blue-chip-investment-plan); [KrisFlyer UOB Credit Card Review (2025) (SingSaver)](https://www.singsaver.com.sg/credit-card/blog/krisflyer-uob-credit-card-review); [The DBS Guide to Investing in T-bills](https://www.dbs.com.sg/personal/articles/nav/investing/investing-in-t-bills).

  **Confidence.** High on the tickers and the index. Medium on the extra terms as a list: each one is confirmed, but the list is what turned up, not everything a local reader knows.

  **What it changes.** Nothing for the tickers (`preprocess/bank_ner.py` already resolves them). A sentence about buying DBS or UOB shares through OCBC's BCIP names two banks for different reasons (one as the stock, one as the product), which the guideline does not yet cover.

**A bank's economists forecasting the economy ("UOB revises up
Vietnam's 2026 GDP growth forecast to 8.5%", "Malaysian SMEs face rising
costs ..., OCBC warns"): is that macro sentiment about the bank, or not
about the bank?**
- Assumed by Opus: not about the bank (25 of the 52 top-up rows it called
  macro). If people agree, macro ends near 49 labelled rows, well short of
  80.
- Matters for: whether the macro aspect can be trained and evaluated at all.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** No web page settles this; it is a recommendation for the team, not a fact. The evidence that bears on it is how published financial sentiment datasets define the task: Financial PhraseBank asked annotators whether a sentence "may have positive, negative or neutral influence on the stock price" and to use only what the sentence states, and SemEval-2017 Task 5 scored sentiment "for each of the mentioned companies/stocks", so both separate the company a sentence is about from whoever is speaking. On that reading a forecast by a bank's economists about Vietnam's GDP or another company has the bank as its source, not its subject, and is not about the bank; it becomes macro sentiment only when the sentence ties the outlook to the bank's own business. The drafted proposal is kept.

  **Sources.** [Financial PhraseBank (dataset card, Hugging Face)](https://huggingface.co/datasets/takala/financial_phrasebank); [SemEval-2017 Task 5: Fine-Grained Sentiment Analysis on Financial Microblogs and News (ACL Anthology)](https://aclanthology.org/S17-2089/).

  **Confidence.** Low to medium. The convention is clear, but it is a convention; and the two train and dev rows the proposal found where a bank's economists speak about the economy were labelled macro by people.

  **What it changes.** If the team adopts it: a sentence in step 1 ("Is it about the bank?") and the `macro_market_environment` row of `docs/annotation-guideline.md`, and those two rows are relabelled. Macro then stays small, so the team must also decide whether it is evaluated at all. No code.

  **Validated (2026-10-11).** Holds. Both sources say what is quoted. Opus already labels this way: of six such rows outside the test split it flagged the three pure forecasts as not about the bank and kept the three tied to the bank's own business. In the corpus 29 sentences match (0.06%), and the current model scores 25 of them positive or negative, so today they count as sentiment toward the bank. One gap: a row flagged as not about the bank still carries an aspect and a sentiment, and nothing leaves it out of training. Details: [local-context-validation](evidence/local-context-validation-2026-10-11.md).

**Comparisons with brokers and robo-advisers (IBKR, moomoo, Tiger,
Endowus, Syfe, StashAway): when is "IBKR is cheaper than DBS Vickers"
sentiment about the bank?**
- Occurs: IBKR 796; moomoo or Tiger 278; Endowus, Syfe or StashAway 341.
- Assumed: about the bank when the bank's product is compared unfavourably
  (negative, retail or wealth); not about the bank when it is only the
  funding account.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** The facts are settled; the labelling rule is a recommendation for the team. Interactive Brokers, moomoo and Tiger Brokers are brokers that compete with the banks' own brokerages, and the price gap customers describe is real: an October 2026 comparison lists minimum fees of about S$2 to S$2.50 per Singapore trade at those three against S$27.25 at DBS Vickers (S$10.90 for buy trades), with OCBC Securities and UOB Kay Hian at S$10 to S$25. Endowus, Syfe and StashAway are robo-advisers. Recommended: the sentence is about the bank when the bank's own product is judged or compared, and not about the bank when the bank is only the account the money came from. The drafted proposal is kept except for the aspect: under the 10 October 2026 rule a brokerage account is a product ordinary customers hold, so the comparison is retail banking, not wealth as the proposal had it.

  **Sources.** [Best Online Brokerage & Trading Platform in Singapore (Beansprout, October 2026)](https://growbeansprout.com/best-online-brokerage-singapore); [Syfe vs StashAway vs Endowus: 5 Key Differences (2026) (Dollar Bureau)](https://dollarbureau.com/blog/syfe-vs-stashaway-vs-endowus/).

  **Confidence.** High on what the firms are and on the fee gap (two comparison sites, no primary source opened). Medium on the rule: it applies step 1 of the guideline, and the retail aspect rests on an extension of the 10 October 2026 rule, which the owner confirmed on 2026-10-11.

  **What it changes.** An example for `docs/annotation-guideline.md` ("IBKR is cheaper than DBS Vickers": negative, retail banking, DBS). No code.

**Products that compete with bank deposits (SSB, T-bills, CPF, SRS):
"T-bills beat UOB One now" is negative for UOB?**
- Occurs: SSB 217; T-bills 179; CPF 268; SRS 259.
- Assumed: negative for the bank's product when it's the comparison point,
  otherwise not about the bank.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** The products are confirmed and the rule is a recommendation. Savings Bonds and T-bills are Singapore Government securities described by MAS (T-bills of 6 months or 1 year; Savings Bonds of up to 10 years, redeemable in any month, from S$500), and DBS's own guide shows customers applying for T-bills through the bank with cash, SRS or CPF money. So the three banks are both the channel for these products and the competitor that loses deposits to them. Recommended, as the proposal drafted: "T-bills beat UOB One now" is negative for the bank's product (retail banking); the bank as a mere channel ("bought T-bills through DBS") is neutral or not about the bank; a bank's report of customers moving deposits into T-bills is net interest margin.

  **Sources.** [Products for Individuals (MAS)](https://www.mas.gov.sg/bonds-and-bills/compare-products-for-individuals); [The DBS Guide to Investing in T-bills](https://www.dbs.com.sg/personal/articles/nav/investing/investing-in-t-bills).

  **Confidence.** High on the products (primary sources). Medium on the rule, which is a judgment.

  **What it changes.** Nothing in the rules; an example sentence for the retail banking row of `docs/annotation-guideline.md` would help.

**Scams and outages: an impersonation scam the bank didn't cause ("Scam
call impersonating DBS"), against a failure that is the bank's ("DBS went
down again"). Both negative retail banking sentiment?**
- Occurs: scam 212; phishing 35; outage or "down again" 100.
- Assumed: the guideline (version 2) files scams and outages under retail
  banking. Whether an impersonation scam is sentiment *toward the bank* is
  not settled.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Not both in the same way; the facts are settled and the scam half is a recommendation. An outage is treated in Singapore as the bank's own failure: on 5 May 2023 MAS raised the extra capital DBS must hold to 1.8 times its risk-weighted assets for operational risk (about S$1.6 billion in all) after its digital services failed on 29 March and 5 May 2023. For phishing scams the Shared Responsibility Framework, in force since 16 December 2024, puts the loss on the bank only if it failed set duties (real-time alerts, a cooling-off period, a kill switch), then on the telco, and otherwise on the customer. Recommended, as the proposal drafted: the bank's own outage or security lapse is negative retail banking; an impersonation scam the bank did not cause is neutral or not about the bank unless the sentence blames or praises the bank's safeguards or its handling.

  **Sources.** [MAS Imposes Further Additional Capital Requirement on DBS Bank for Disruption of Banking Services (MAS, 5 May 2023)](https://www.mas.gov.sg/news/media-releases/2023/mas-imposes-further-additional-capital-requirement-on-dbs-bank-for-disruption-of-banking-services); [Scammed In Singapore: How The Shared Responsibility Framework Helps Consumers (DollarsAndSense)](https://dollarsandsense.sg/scammed-singapore-shared-responsibility-framework-helps-consumers/).

  **Confidence.** High on outages. Medium on scams: the framework shows the regulator itself separates a scam the bank could have stopped from one it could not, but where a sentence falls is the labeller's call.

  **What it changes.** A sentence for step 1 of `docs/annotation-guideline.md` and its retail banking row, which now lists "scams" without that distinction. A sentence about the capital penalty itself belongs to capital and liquidity. No code.

  **Validated (2026-10-11).** Holds, both halves. The MAS and framework facts were confirmed on the pages cited. People labelled all 7 outage rows negative. On scam rows where the bank's handling is blamed, people and Opus are both negative (5 of 5); on the three scams the bank did not cause, Opus is neutral on all three and people on one. So this is what Opus already does, on a point where people were not consistent. In the corpus 345 sentences mention a scam (153 scored negative) and only 19 use impersonation wording, so the split has to be judged per sentence, not by keyword. Details: [local-context-validation](evidence/local-context-validation-2026-10-11.md).

**MAS rules and notices ("Is this part of some new MAS guideline or
just UOB being extra cautious?"): which aspect?**
- Occurs: MAS 282.
- Assumed: capital and liquidity for prudential rules, retail banking for
  customer-facing rules, other for boilerplate.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** The assumed split is right, and MAS's own documents fall the same way. Notice 637 sets capital adequacy and leverage requirements for banks incorporated in Singapore (prudential, so capital and liquidity); the E-Payments User Protection Guidelines set the duties of banks and customers for unauthorised and erroneous payments (customer-facing, so retail banking); and the extra capital MAS imposed on DBS for its outages shows a customer-facing failure can also be a capital matter. Label by what the sentence is about, with boilerplate and licensing mentions in `other`. The drafted proposal is kept.

  **Sources.** [Notice 637 Risk Based Capital Adequacy Requirements for Banks Incorporated in Singapore (MAS)](https://www.mas.gov.sg/regulation/notices/notice-637); [E-Payments User Protection Guidelines (MAS)](https://www.mas.gov.sg/regulation/guidelines/e-payments-user-protection-guidelines); [MAS Imposes Further Additional Capital Requirement on DBS Bank for Disruption of Banking Services (MAS, 5 May 2023)](https://www.mas.gov.sg/news/media-releases/2023/mas-imposes-further-additional-capital-requirement-on-dbs-bank-for-disruption-of-banking-services).

  **Confidence.** High. Primary sources, and the rule follows the existing aspect table.

  **What it changes.** Nothing.

## Singlish and local expressions

**Particles (lah, leh, lor, meh, liao, sia) carry tone, not sentiment.
Agreed?**
- Occurs: lah 23 (plus 161 "PayLah", the DBS app, which a model may
  confuse); leh 16; lor 30; meh 9; liao 21; sia 21 lowercase (plus 75 "SIA",
  Singapore Airlines).
- Assumed: tone only. "uob one have meh?" is a doubtful question; "Then just
  go for uob lor" is a resigned recommendation.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Agreed, with two refinements. The reference sources describe them as sentence-final particles that mark attitude, not content: lah and leh add emphasis, lor marks something as obvious or accepted, meh is tagged onto the end of a question (the doubting kind, as in the example above), sia is an exclamation, and liao simply means "already". So none of them has a polarity of its own; meh and lor can colour a sentence with doubt or resignation, and sia strengthens whatever the sentence already says. Label the content. The drafted proposal is kept.

  **Sources.** [Singlish vocabulary (Wikipedia)](https://en.wikipedia.org/wiki/Singlish_vocabulary); [Disentangling Singlish Discourse Particles with Task-Driven Representation (arXiv)](https://arxiv.org/abs/2409.20366).

  **Confidence.** High on what the particles mean. Medium that they never matter: the research paper's point is that they do carry pragmatic meaning, only not positive or negative.

  **What it changes.** Nothing in the labels. It matters for the report's slang discussion only.

**Sentiment words: are these readings right?**

| word | count | assumed meaning | assumed polarity |
|---|---|---|---|
| huat | 12 | prosper, make money ("He DBS position huat.") | positive |
| heng | — | lucky (Hokkien); also a surname ("Elaine Heng") | positive |
| jialat | 2 | terrible, in trouble | negative |
| sian | 3 | fed up, tired of it | negative |
| shiok | 2 | great, satisfying | positive |
| power | 35, mostly the English word | impressive ("Power bro u can sue ocbc") | positive |
| kena | 15 | got hit by something bad | negative |
| atas | 1 | snobbish, high-class ("act very atas") | negative |
| paiseh | 3 | embarrassed | none |
| kiasu / kiasi | 1 | afraid to lose out / afraid to die | none |
| confirm (plus chop) | 52, mostly the English word | certainly ("Confirm scam") | none on its own |
| die die | 3 | insist on, at all costs | none |
| gone case | 1 | hopeless | negative |
| kpkb | 1 | complain loudly | negative |
| chio | 2 | attractive, good | positive |
| lobang | 3 | a deal or opportunity | positive |
| ownself | 6 | by yourself | none |
| whack | 11 | buy aggressively ("whack dbs stock") | positive about the stock |
| divvy | 5 | dividend | none |

- Team answer (correct any row):

  **Answer (researched on the web, 2026-10-11).** Most rows hold against two Singlish references: huat (prosper), heng (lucky), jialat (in trouble), sian (tired or sick of it), shiok (delight), power (impressive), kena (afflicted with), paiseh (embarrassed), kiasu and kiasi, confirm plus chop (extremely sure), die die (no matter what), gone case (doomed), kpkb (complain loudly), lobang (an opportunity or deal), ownself (by oneself), and divvy, which is informal English for a dividend. Two rows need correcting. "Atas" means sophisticated or upmarket as well as snobbish, so it is negative only when it mocks ("act very atas"), not when it describes a premium card or lounge. "Chio" means good-looking, usually of a young woman, not "good" in general. Two notes: "whack" is listed as hitting, or doing something hard without planning, and no dictionary lists a "buy" sense, so "whack dbs stock" as buying aggressively is a fair extension but its positive polarity is an inference; and kpkb belittles the person complaining, so it is not automatically negative toward the bank complained about. The drafted proposal's notes on heng, kena, power and confirm are kept.

  **Sources.** [Singlish vocabulary (Wikipedia)](https://en.wikipedia.org/wiki/Singlish_vocabulary); Singlish Dictionary entries for [kpkb](https://singlishdict.app/?q=kpkb), [chio](https://singlishdict.app/?q=chio), [whack](https://singlishdict.app/?q=whack), [die die](https://singlishdict.app/?q=die+die) and [power](https://singlishdict.app/?q=power); [divvy (Wiktionary)](https://en.wiktionary.org/wiki/divvy).

  **Confidence.** Medium to high on the meanings (two independent references agree where both list a word). The polarity column stays a labeller's judgment, because most of these words take their sentiment from what they are said about.

  **What it changes.** Two rows of the table above (atas, chio). No rule, label or code; about 8 train and dev rows contain any of these words.

**What do these mean? Claude could not tell.**
- "Not chio no mood to invest liao, heng dbs give me xmm this time." What is
  *xmm*, and is the sentence positive about DBS?
- "Lobang Sis says cannot use DBS Woman's to smash that 4mpd": is *Lobang
  Sis* a deals page or person whose posts are a known source?
- "Pet10003 / Pet1003, your favourite DBS uncle" (9 sentences): a known
  Reddit persona? Should one poster's long posts count like everyone
  else's?
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Two of the three are settled.

  - **xmm** is short for "xiao mei mei" (Mandarin for little sister or little girl): Singlish slang for a young, girlish woman, often said mockingly. Read with "chio" (pretty) and "heng" (luckily), the sentence is a joke about the looks of the bank staff member the writer was given: not pretty, no mood to invest; luckily DBS gave a young woman this time. It is a remark about a person's appearance, not about DBS's products or service, so the recommended label is neutral and it should not be quoted as evidence; that label is a recommendation for the team.

  - **Lobang Sis** is a Singapore deals and personal finance site with social media channels, run by an individual content creator, covering credit card rewards (miles and cashback), bank accounts and promotions. It is a third-party source, not a bank or a bank's channel. In the sentence it is cited for a card rule: that a kind of spending does not earn the DBS Woman's World Card's 4 miles per dollar, the card's rate on online spending, which has a list of excluded transactions. Label such a sentence by its content, as a reported limit on a card benefit (retail banking).

  - **The signed "DBS uncle" posts** were not researched, because the limits for this research bar searching for a Reddit username. The drafted proposal stands: no special weight either way.

  **Sources.** [Singlish Dictionary: XMM](https://singlishdict.app/?q=XMM); [Singlish Dictionary: chio](https://singlishdict.app/?q=chio); [Find the Best Deals & Promos in Singapore | LobangSis](https://lobangsis.com); [About - Lobang Sis](https://lobangsis.com/about/); [Review: DBS Woman's World Card (The MileLion)](https://milelion.com/2026/08/11/review-dbs-womans-world-card/).

  **Confidence.** High on what xmm and Lobang Sis mean. Medium on how to label the xmm sentence. The poster question is not settled by the web.

  **What it changes.** No label: none of these sentences is in train and dev. "xmm" can join the table of words above (meaning: young woman; polarity: none).

## Internet and investing slang

**"nerf" and "buff" are gaming words for a product made worse or better.
Agreed, and always about the product?**
- Occurs: nerf 154; buff 10. See the savings-account rate-cut question (first in the banking
  products section) for what llama did with them.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Agreed. In video game slang to nerf is to change something "in order to make less efficacious" (the word comes from the Nerf brand of soft toys) and to buff is to make it stronger. Singapore finance writers use "nerf" in the same way for cuts to an account's interest or a card's rewards, as in the headline "UOB One Account nerfing interest rates". In this corpus that makes a nerf negative and a buff positive for the product named, whatever the share price does; "buff" also has ordinary English senses, so read the sentence before trusting a word match. The drafted proposal is kept.

  **Sources.** [nerf (Wiktionary)](https://en.wiktionary.org/wiki/nerf); [buff (Wiktionary)](https://en.wiktionary.org/wiki/buff); [UOB One Account nerfing interest rates to 1.9% p.a. from December 2025 (The MileLion)](https://milelion.com/2025/11/01/uob-one-account-nerfing-interest-rates-to-1-9-p-a-from-december-2025/).

  **Confidence.** High.

  **What it changes.** No rule. The aspect is the product's (retail banking for accounts and cards), which an example in `config/aspects.yaml` (`llm_examples`) would teach the local model.

**Do "lol", "lmao", "😂", "tbh", "sigh" change a sentence's sentiment?**
- Occurs: lol 169; lmao 14; tbh 36; imo 56; iirc 62.
- Assumed: they soften or mark sarcasm but don't flip it. "Don't use DBS lol
  hahah it's down again" is negative; "where else did u think DBS fund the
  accelerated miles accrual ..., lol" was labelled neutral by people and
  negative by Opus.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Not on their own; this is a recommendation backed by how linguists describe the words. "lol" is described as a pragmatic marker that sets tone, softening a statement or showing fellow feeling, and no longer reports laughter; "tbh", "imo" and "iirc" hedge in the same way. So label what the sentence says, and treat such a word as a possible sign of sarcasm, in which case the guideline's sarcasm rule (label the intended meaning) applies. The drafted proposal is kept.

  **Sources.** [Why We Use "lol" So Much (Vice)](https://www.vice.com/en/article/why-we-use-lol-so-much/); [Tone indicator (Wikipedia)](https://en.wikipedia.org/wiki/Tone_indicator).

  **Confidence.** Medium. The description of "lol" is sourced; that it never changes a label is the team's rule to make, and the example in this question (people neutral, Opus negative) shows where it is hard.

  **What it changes.** Nothing in the labels.

  **Validated (2026-10-11).** Holds. The description of "lol" was confirmed on the page cited. People and Opus gave the same sentiment on all 9 labelled rows with such a word. Those rows lean negative (5 of 9), and across the corpus the model calls 85% of the 300 such sentences neutral, so the model may under-read them; 9 rows are too few to say. Details: [local-context-validation](evidence/local-context-validation-2026-10-11.md).

**Investing stance words: DCA (150), "diamond hands", "to the moon",
"stonks", FOMO, YOLO. Is "Monthly DCA dbs stock." positive investor
sentiment, or neutral description?**
- Assumed: a plan to keep buying is mildly positive about the stock; the
  guideline doesn't say.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** The meanings are settled; the label is a recommendation, and it differs from the drafted proposal. Dollar-cost averaging is investing "the same number of dollars each month or each quarter" whatever the price, and the banks sell it as a product (OCBC's Blue Chip Investment Plan, from S$100 a month), so "Monthly DCA dbs stock." states a schedule, not a view. Recommended: neutral unless the sentence adds a reason or a judgment, which is also how people labelled the one such row in train and dev; the proposal had it as mildly positive. Of the rest, diamond hands (holding through swings) and "to the moon" (expecting a sharp rise) are positive about the stock; "stonks" is a mocking misspelling that often signals a bad decision; YOLO means going all in and was also a UOB credit card until it was renamed UOB EVOL in June 2021; FOMO said of other buyers is a warning.

  **Sources.** [Dollar-cost averaging (Wikipedia)](https://en.wikipedia.org/wiki/Dollar_cost_averaging); [OCBC Blue Chip Investment Plan (BCIP) | ETF's & Blue Chip Stocks](https://www.ocbc.com/personal-banking/investments/blue-chip-investment-plan); [Trading Lingo from Wall Street Bets Decoded (SingSaver)](https://www.singsaver.com.sg/page/blog/trading-lingo-from-wallstreetbets); [Stash's Guide to Reddit's WallStreetBets Can Help You Understand the Lingo](https://www.stash.com/learn/stashs-guide-to-reddits-wallstreetbets-can-help-you-understand-the-lingo); [Fear of missing out (Wikipedia)](https://en.wikipedia.org/wiki/Fear_of_missing_out); [UOB YOLO Is Now The UOB EVOL: What's Changed? (SingSaver)](https://www.singsaver.com.sg/page/blog/uob-yolo-relaunch-uob-evol).

  **Confidence.** High on the meanings. Low to medium on the label for a bare buying plan: the definition supports neutral, but a reader can fairly see a choice to keep buying as mild approval.

  **What it changes.** An example for the `investor_stock_sentiment` row of `docs/annotation-guideline.md`, which is silent on buying plans. Any keyword list must treat "YOLO" as a card name first.

  **Validated (2026-10-11).** Holds, with one quote corrected: the phrase "regardless of price" is not in the article cited, so the definition above now quotes what the article does say. People labelled 3 of the 4 such rows neutral and Opus matched them on all 4; the current model calls 147 of the corpus's 154 such sentences neutral, and all 23 short ones. No label changes. Details: [local-context-validation](evidence/local-context-validation-2026-10-11.md).

**"FIRE" means financial independence, retire early, except when it
means fire insurance. Any other local acronym with two readings?**
- Occurs: 9 "FIRE" in capitals, 6 "fire insurance".
- Team answer:

  **Answer (researched on the web, 2026-10-11).** FIRE in capitals is "financial independence, retire early"; fire insurance is home insurance, and the HDB Fire Insurance Scheme is compulsory for flat owners with an outstanding HDB loan. Other terms with two readings that the web confirms: YOLO (a UOB credit card until June 2021, and the slang); "Dividend+" (an OCBC savings account, not a dividend); "Multiplier" (the DBS savings account, and the capital multiplier MAS applied to DBS's operational risk); SA (the CPF Special Account, and a savings account); SIA (Singapore Airlines, against the particle sia); "Stash" (the UOB Stash Account, against the robo-adviser StashAway); and "Bank of Singapore" (OCBC's private bank, but also the last three words of "The Development Bank of Singapore", DBS's name until 21 July 2003). The drafted proposal's list is kept and the last two are added.

  **Sources.** [The "FIRE" Movement Explained (DollarsAndSense)](https://dollarsandsense.sg/fire-movement-explained-heres-need-know-latest-retirement-trend/); [Protect your home: insurance for your HDB flat (CPF Board)](https://www.cpf.gov.sg/member/infohub/educational-resources/protect-your-home-insurance-for-your-hdb-flat); [UOB YOLO Is Now The UOB EVOL: What's Changed? (SingSaver)](https://www.singsaver.com.sg/page/blog/uob-yolo-relaunch-uob-evol); [Stash Account | UOB Singapore](https://www.uob.com.sg/personal/save/savings-accounts/stash-account.page); [DBS Bank (Wikipedia)](https://en.wikipedia.org/wiki/DBS_Bank).

  **Confidence.** High on each term. Medium on the list being complete: it holds what the corpus and this search turned up.

  **What it changes.** No labels. It matters for keyword aspect rules and for `preprocess/bank_ner.py`: see the next section's answer on name expansions for the "Bank of Singapore" case.

## Sarcasm, jokes and questions

**Sarcastic expansions of a bank's name: "DBS - Dumbest Bank of
Singapore". Negative toward DBS, and not about OCBC?**
- Assumed: yes; NER wrongly adds OCBC (it reads "Bank of Singapore", OCBC's
  private bank). Are there other common ones? None of the guesses Claude
  tried, such as "Damn Bloody Slow", occur in this corpus.
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Yes: negative toward the bank whose initials are being mocked, and not about OCBC. Joke expansions of initials are a recorded Singapore habit (a folklore archive lists "Pay and Pay" for a political party and "Pay Until Bankrupt" for a utilities board), but that record has none for the three banks, and no reliable page was found for "Dumbest Bank of Singapore", "Damn Bloody Slow" or "Use Other Banks"; so the web does not show which are common, and the two the proposal found in the corpus remain the only evidence. The drafted proposal is kept.

  **Sources.** [Singaporean Joke Acronyms (USC Digital Folklore Archives)](https://folklore.usc.edu/?p=8795); [DBS Bank (Wikipedia)](https://en.wikipedia.org/wiki/DBS_Bank); [Bank of Singapore | Asia's global private bank](https://bankofsingapore.com).

  **Confidence.** High on the reading. Low on "are there other common ones": no source was found, so that part is not settled.

  **What it changes.** `preprocess/bank_ner.py`: the `bank\s+of\s+singapore` line of `RESOLUTION` gives OCBC for any phrase ending in those words. Checked on 11 October 2026 with made-up sentences: "DBS - Dumbest Bank of Singapore" returns DBS and OCBC, and "The Development Bank of Singapore was founded in 1968." returns OCBC alone, although that was DBS's own name until 2003. A line that resolves "development bank of singapore" to DBS, placed above it, would fix the second case; the first needs a rule for expansions. Both are for the team to approve, since they change which sentences count for a bank.

**Contrarian jokes: "Jialat if auntie say buy dbs means gone case liao"
(when the aunties buy, it's the top). Negative about the stock?**
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Yes, negative about the stock. The joke is a local telling of an old market saying, that when people with no market background start giving stock tips everyone who might buy has already bought and the top is near (the "shoeshine boy" signal); contrarian investing rests on the same idea, that "widespread optimism can result in unjustifiably high valuations". The two Singlish words fit: jialat means in trouble and gone case means doomed, so the sentence says that if the aunties are telling people to buy DBS, the stock is finished. No Singapore page was found that records the "auntie" version by name. The drafted proposal is kept.

  **Sources.** [Don't Be A (Knee) Jerk (SentimenTrader)](https://sentimentrader.com/blog/dont-be-a-knee-jerk); [Contrarian investing (Wikipedia)](https://en.wikipedia.org/wiki/Contrarian_investing); [Singlish vocabulary (Wikipedia)](https://en.wikipedia.org/wiki/Singlish_vocabulary).

  **Confidence.** Medium to high. The saying and both words are sourced; that this sentence is that joke is a reading, though a hard one to read any other way.

  **What it changes.** An example for the `investor_stock_sentiment` row of `docs/annotation-guideline.md`. No label moves (no such row is in train and dev).

**Sarcasm marked "/s" (7) or not marked at all. Should annotators flag
sarcasm, so the models' errors on it can be counted?**
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Recommended yes; this is a judgment for the team, not a fact. "/s" is a tone indicator that marks sarcasm, used because writing lacks the voice and face that carry it in speech, and most sarcasm carries no mark at all. Research treats spotting it as a hard problem of its own: in the SemEval-2018 shared task the best system reached an F1 of 0.71 at telling ironic tweets from plain ones. With only 7 marked sentences in the corpus, a yes-or-no flag filled in by annotators is the only way to count the models' errors on sarcasm. The drafted proposal is kept.

  **Sources.** [Tone indicator (Wikipedia)](https://en.wikipedia.org/wiki/Tone_indicator); [SemEval-2018 Task 3: Irony Detection in English Tweets (ACL Anthology)](https://aclanthology.org/S18-1005/).

  **Confidence.** Medium. The case for measuring is sourced; whether an extra column is worth the annotators' time is the team's call.

  **What it changes.** If adopted: one optional column on the labelling sheet and a line in `docs/annotation-guideline.md`. If not, the report should say that errors on sarcasm were not measured.

  **Validated (2026-10-11).** The sources hold; the flag is not worth adding as written. The corpus has 7 marked sentences in 45,844 and none of the 1,676 labelled rows outside the test split carries the mark, and people no longer label the sheets, so the column would stay empty. Cheaper and honest: the report says errors on sarcasm were not measured. If a figure is wanted later, the Opus rater can be asked to flag sarcasm in a pass of its own. Details: [local-context-validation](evidence/local-context-validation-2026-10-11.md).

**A question is not evidence: "How is the fundamental/current state of
DBS?" Neutral, and never quoted as a supporting quote?**
- Matters for: the chatbot. When evidence search ranks by the question's
  wording, it returns other people's questions (`chatbot-eval-build`,
  search-mode replay).
- Team answer:

  **Answer (researched on the web, 2026-10-11).** Agreed. A standard reference on sentiment analysis notes that many forum posts are "questions and answers with no opinions" and lists questions among text that carries no opinion, and Financial PhraseBank told annotators to use "only the information explicitly available in the given sentence". So a question is neutral unless its wording states a view (a question that presumes the bank is unsafe carries doubt), and the chatbot should not quote a question as support. People already label this way: 45 of the 52 train and dev rows ending in a question mark are neutral. The drafted proposal is kept.

  **Sources.** [Sentiment Analysis and Subjectivity (chapter of the Handbook of Natural Language Processing)](https://www.cs.uic.edu/~liub/FBS/NLP-handbook-Liub-final.pdf); [Financial PhraseBank (dataset card, Hugging Face)](https://huggingface.co/datasets/takala/financial_phrasebank).

  **Confidence.** High on neutral by default. Medium on "never quoted": that is a product choice.

  **What it changes.** No label rule: the 10 October 2026 rule already keeps a question about a product neutral. For the chatbot, a filter in the evidence search (`chatbot/retrieval.py`) that leaves out sentences ending in a question mark; no such filter was found there on 11 October 2026.

## What Claude Code assumed in its own analysis

These are judgements made while writing the evidence, recorded so a person
can check them.

**Customer rates read as NIM.** In the top-up sheet, Claude read 16 of the 19 Reddit rows the LLM
called NIM as customer rates (retail banking), and 3 of 23 news and earnings
rows likewise. Opus agreed (19 of 42 to retail). No person has checked.
(`labelling-topup-2026-10-01.md`)

**Answer (researched on the web, 2026-10-11).** The reading is right in principle: net interest margin is the bank's own measure of what it earns on loans over what it pays for funds, while the rate on UOB One or OCBC 360 is a term of a savings account that the bank's own notice revises for customers. See the first question of the banking products section. The web cannot check the 19 individual rows; a person still has to.

**Sources.** [Net interest margin (Wikipedia)](https://en.wikipedia.org/wiki/Net_interest_margin); [Revision of UOB One Account Interest Rates (UOB notice, effective 1 September 2025)](https://www.uob.com.sg/assets/web-resources/personal/pdf/save/everyday-accounts/revision-of-interest-rates-for-uob-one-account-202508.pdf).

**Confidence.** High on the principle. The row-by-row reading remains unchecked by a person.

**What it changes.** Nothing new.

**On-topic quotes in the replay.** In the search-mode replay, Claude judged how many harness-found
quotes were on the asked topic: about 10 of 33 when ranked by the question,
about 19 of 33 when ranked by the aspect's name, most of the latter report
boilerplate. A subjective count. (`chatbot-eval-build-2026-10-01.md`)

**Answer (researched on the web, 2026-10-11).** Not a question the web can answer: it is a count of this project's own search results, and only a second person reading the same 33 quotes can check it. No source was looked for.

**Sources.** None.

**Confidence.** Not settled.

**What it changes.** Nothing.

**Report boilerplate.** Report boilerplate is not evidence of sentiment: "These
Forward-Looking Statements are statements regarding ...", footnotes such as
"1/ Wealth Management income comprises ...". Assumed neutral and not worth
quoting. Should they be removed from the corpus, as PDF debris was
considered (`preprocessing-dry-run-2026-10-01.md`)?

**Answer (researched on the web, 2026-10-11).** Recommended: keep such sentences out of the sentiment evidence, either removed in preprocessing or marked so that the index and the chatbot skip them; this is a recommendation for the team. The web evidence is that a forward-looking statements notice is a legal "safe harbor" disclaimer, included so that a company can speak about the future without being held to it, and so it says nothing about how the bank is doing. Footnotes that define a term ("Wealth Management income comprises ...") are the same kind of text.

**Sources.** [Forward-looking statement (Wikipedia)](https://en.wikipedia.org/wiki/Forward-looking_statement).

**Confidence.** Medium. One source, and it describes United States law; the Singapore banks' wording follows the same form, but no Singapore source was opened.

**What it changes.** A preprocessing step if the team wants one. Removing rows from `data/plp.db` needs the team's approval, so build and test it on a copy first.

**Validated (2026-10-11).** Holds, with a narrower fix. The source describes United States law, as the answer says. In the corpus about 188 sentences are disclaimers (26) or footnotes that define a term (162), 0.41% of the total, and the model scores 50 of them positive or negative. That is too few to move the index; the harm is in the chatbot's evidence, where such a line can be quoted. Filter them at evidence search first, and read the 188 before filtering anything, because the word patterns used to count them are rough. Details: [local-context-validation](evidence/local-context-validation-2026-10-11.md).

**Product descriptions.** A product description is neutral unless it judges: "UOB One gives
4% on $100k" neutral, "UOB One is the best leh" positive. This is the
neutral boundary where people, Opus and the fine-tuned model disagree most
(`error-analysis-2026-10-01.md`: most of the model's errors are Reddit
descriptions of retail products called positive or negative).

**Answer (decided by the team on 2026-10-10, recorded with web sources on 2026-10-11).** The boundary moved. A retail product's feature now carries sentiment directed at the bank: a feature clearly good for the customer is positive and one clearly bad is negative, while a bare mention, a question, a how-to or terms with both good and bad sides stay neutral. So "UOB One gives 4% on $100k" is no longer neutral by default (a high rate is good for the customer), and "UOB One is the best leh" stays positive as a judgment. The banks' own pages show why these sentences are so common: the accounts are sold on the rate and its conditions.

**Sources.** [Revision of UOB One Account Interest Rates (UOB notice, effective 1 September 2025)](https://www.uob.com.sg/assets/web-resources/personal/pdf/save/everyday-accounts/revision-of-interest-rates-for-uob-one-account-202508.pdf); [OCBC 360 Account | High Interest Savings Account | Salary Crediting](https://www.ocbc.com/personal-banking/deposits/360-savings-account).

**Confidence.** High. It is the team's decision; the web sources only illustrate it.

**What it changes.** Already written into `docs/annotation-guideline.md` ("Two rules decided on 2026-10-10"). Labels made before that date followed the older reading.

**A "buy" with 0.9% upside.** Analyst consensus: "buy" with an implied upside of 0.9% was reported
as given. Whether a local reader would call that a buy is not a question
the system answers.

**Answer (researched on the web, 2026-10-11).** A reader who knows broker ratings would not take it as a buy. Brokers that publish their scales tie "buy" to an expected total return over 12 months of more than about 15% (20% at one broker) and put anything from about flat up to 10% or 15% under "hold", so a consensus "buy" beside an implied upside of 0.9% usually means the price has caught up with targets that have not been revised. Recommended: keep reporting both figures as given, and do not let the system describe the pair as a bullish view; this is a recommendation for the team.

**Sources.** [Broker Recommendations Explained (FNArena)](https://fnarena.com/broker-recommendations-explained).

**Confidence.** Medium. One source, and its examples are brokers covering Australian shares; the rating definitions of the Singapore brokers were searched for and not found on an open page.

**What it changes.** Nothing in labels or code unless the team wants the wording changed where the consensus is shown.

**Validated (2026-10-11).** Holds, with the thresholds corrected from the page cited (the first wording said 10% to 15%). The case is real in the stored data: DBS is rated "buy" with an implied upside of +0.9%, OCBC "buy" with -0.9% (its average target is below the price), UOB "hold" with +1.9%. The chatbot already reports both figures as given and called neither a bullish view in six recent answers, so nothing needs changing; one of those answers did misdescribe the analysts ("17 analysts who have rated the bank as 'buy' or 'strong buy'"). Details: [local-context-validation](evidence/local-context-validation-2026-10-11.md).

**Opus as the NER reference.** The NER gold-sheet reference: Opus's reading was taken as a
stand-in for a person's. It agrees with NER on 200 of 201 sentences, but it
was given the same rules NER encodes, so it can't test the rules (the DBS Vickers and subsidiaries questions).

**Answer (researched on the web, 2026-10-11).** The web cannot test this either, but the facts behind the rules that NER encodes were checked in this round and hold: DBS Vickers, POSB, Bank of Singapore and Great Eastern belong to their parents, and UOB Kay Hian is a separate listed broker (see those questions above). The same check found two places where the rules are incomplete: app names used alone (PayLah, digibank, TMRW) resolve to no bank, and "Development Bank of Singapore" resolves to OCBC.

**Sources.** [DBS Vickers Online Trading](https://www.dbsvickers.com/vickers/default.page); [UOB-Kay Hian Holdings Limited Annual Report 2024 (SGX)](https://links.sgx.com/1.0.0/corporate-announcements/R3CRJY2XHBYM2N9L/839897_UOBKHHL%20Annual%20Report%202024.pdf); [DBS Bank (Wikipedia)](https://en.wikipedia.org/wiki/DBS_Bank).

**Confidence.** High on the ownership facts. The point of this item, that Opus cannot test rules it was given, stands.

**What it changes.** `preprocess/bank_ner.py`, if the team approves the two fixes described under the subsidiaries question and the name expansions question.

---

*Counts: `data/plp.db` on 2026-10-02, case-insensitive word matches over
`sentences.text`. Examples are quoted from the corpus. Sources for model
behaviour: `data/aspect_llm/llama3.1_8b.96efe244.jsonl` (llama's cached answers),
`data/labeled/candidates.csv` (people, base FinBERT),
`data/labeled/llm_rater/` (Opus).*
