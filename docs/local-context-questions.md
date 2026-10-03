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

**Mortgage repricing (FHR, SORA, "fixed for 2Y") is retail banking too?**
- Occurs: SORA 96; FHR 15 (DBS's Fixed Deposit Home Rate, assumed).
- Assumed: retail banking; a customer comparing package rates is sentiment
  toward the bank as a lender, not toward its margin.
- Team answer:

**OCBC's "Premier Dividend+" and "Dividend+" are deposit accounts, not
the bank's dividend. Right?**
- Occurs: 52, e.g. "OCBC already nerfed their dividend+ from 3.7% to 3.3%".
- Assumed by Claude, confirmed by Opus on the top-up sheet (5 rows moved from
  dividend policy to retail banking). An embedding or keyword method will
  read them as dividend policy.
- Team answer:

**Where do priority and private banking products belong: DBS Treasures,
OCBC Premier, Bank of Singapore, the DBS Insignia card?**
- Occurs: Treasures 231; Premier 206; Insignia 15; Bank of Singapore (NER
  stratum, 20 in the gold sheet).
- Assumed: unresolved. This is the wealth-versus-retail boundary that
  explains 63 of Opus's aspect disagreements with the human labels; the
  guideline draws it loosely.
- Answer goes into: `docs/annotation-guideline.md`, before the top-up round.
- Team answer:

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
- Team answer:

**Subsidiaries and apps count as the parent: POSB, PayLah! and digibank
as DBS; Great Eastern and Bank of Singapore as OCBC. Right?**
- Occurs: POSB 535; PayLah 161; digibank 52.
- Assumed: yes (PLAN section 7). Great Eastern is an insurer OCBC controls;
  counting its news as OCBC moves OCBC's index.
- Team answer:

**Tickers and market names: D05, O39 and U11 are the three banks on SGX;
the STI is the index they are in. Anything else a local reader would
recognise that the models don't?**
- Occurs: D05/O39/U11 130; STI 174; SGX 233; CDP (with brokers) common.
- Assumed: tickers resolve to the bank (`preprocess/bank_ner.py`).
- Team answer:

**A bank's economists forecasting the economy ("UOB revises up
Vietnam's 2026 GDP growth forecast to 8.5%", "Malaysian SMEs face rising
costs ..., OCBC warns"): is that macro sentiment about the bank, or not
about the bank?**
- Assumed by Opus: not about the bank (25 of the 52 top-up rows it called
  macro). If people agree, macro ends near 49 labelled rows, well short of
  80.
- Matters for: whether the macro aspect can be trained and evaluated at all.
- Team answer:

**Comparisons with brokers and robo-advisers (IBKR, moomoo, Tiger,
Endowus, Syfe, StashAway): when is "IBKR is cheaper than DBS Vickers"
sentiment about the bank?**
- Occurs: IBKR 796; moomoo or Tiger 278; Endowus, Syfe or StashAway 341.
- Assumed: about the bank when the bank's product is compared unfavourably
  (negative, retail or wealth); not about the bank when it is only the
  funding account.
- Team answer:

**Products that compete with bank deposits (SSB, T-bills, CPF, SRS):
"T-bills beat UOB One now" is negative for UOB?**
- Occurs: SSB 217; T-bills 179; CPF 268; SRS 259.
- Assumed: negative for the bank's product when it's the comparison point,
  otherwise not about the bank.
- Team answer:

**Scams and outages: an impersonation scam the bank didn't cause ("Scam
call impersonating DBS"), against a failure that is the bank's ("DBS went
down again"). Both negative retail banking sentiment?**
- Occurs: scam 212; phishing 35; outage or "down again" 100.
- Assumed: the guideline (version 2) files scams and outages under retail
  banking. Whether an impersonation scam is sentiment *toward the bank* is
  not settled.
- Team answer:

**MAS rules and notices ("Is this part of some new MAS guideline or
just UOB being extra cautious?"): which aspect?**
- Occurs: MAS 282.
- Assumed: capital and liquidity for prudential rules, retail banking for
  customer-facing rules, other for boilerplate.
- Team answer:

## Singlish and local expressions

**Particles (lah, leh, lor, meh, liao, sia) carry tone, not sentiment.
Agreed?**
- Occurs: lah 23 (plus 161 "PayLah", the DBS app, which a model may
  confuse); leh 16; lor 30; meh 9; liao 21; sia 21 lowercase (plus 75 "SIA",
  Singapore Airlines).
- Assumed: tone only. "uob one have meh?" is a doubtful question; "Then just
  go for uob lor" is a resigned recommendation.
- Team answer:

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

**What do these mean? Claude could not tell.**
- "Not chio no mood to invest liao, heng dbs give me xmm this time." What is
  *xmm*, and is the sentence positive about DBS?
- "Lobang Sis says cannot use DBS Woman's to smash that 4mpd": is *Lobang
  Sis* a deals page or person whose posts are a known source?
- "Pet10003 / Pet1003, your favourite DBS uncle" (9 sentences): a known
  Reddit persona? Should one poster's long posts count like everyone
  else's?
- Team answer:

## Internet and investing slang

**"nerf" and "buff" are gaming words for a product made worse or better.
Agreed, and always about the product?**
- Occurs: nerf 154; buff 10. See the savings-account rate-cut question (first in the banking
  products section) for what llama did with them.
- Team answer:

**Do "lol", "lmao", "😂", "tbh", "sigh" change a sentence's sentiment?**
- Occurs: lol 169; lmao 14; tbh 36; imo 56; iirc 62.
- Assumed: they soften or mark sarcasm but don't flip it. "Don't use DBS lol
  hahah it's down again" is negative; "where else did u think DBS fund the
  accelerated miles accrual ..., lol" was labelled neutral by people and
  negative by Opus.
- Team answer:

**Investing stance words: DCA (150), "diamond hands", "to the moon",
"stonks", FOMO, YOLO. Is "Monthly DCA dbs stock." positive investor
sentiment, or neutral description?**
- Assumed: a plan to keep buying is mildly positive about the stock; the
  guideline doesn't say.
- Team answer:

**"FIRE" means financial independence, retire early, except when it
means fire insurance. Any other local acronym with two readings?**
- Occurs: 9 "FIRE" in capitals, 6 "fire insurance".
- Team answer:

## Sarcasm, jokes and questions

**Sarcastic expansions of a bank's name: "DBS - Dumbest Bank of
Singapore". Negative toward DBS, and not about OCBC?**
- Assumed: yes; NER wrongly adds OCBC (it reads "Bank of Singapore", OCBC's
  private bank). Are there other common ones? None of the guesses Claude
  tried, such as "Damn Bloody Slow", occur in this corpus.
- Team answer:

**Contrarian jokes: "Jialat if auntie say buy dbs means gone case liao"
(when the aunties buy, it's the top). Negative about the stock?**
- Team answer:

**Sarcasm marked "/s" (7) or not marked at all. Should annotators flag
sarcasm, so the models' errors on it can be counted?**
- Team answer:

**A question is not evidence: "How is the fundamental/current state of
DBS?" Neutral, and never quoted as a supporting quote?**
- Matters for: the chatbot. When evidence search ranks by the question's
  wording, it returns other people's questions (`chatbot-eval-build`,
  search-mode replay).
- Team answer:

## What Claude Code assumed in its own analysis

These are judgements made while writing the evidence, recorded so a person
can check them.

**Customer rates read as NIM.** In the top-up sheet, Claude read 16 of the 19 Reddit rows the LLM
called NIM as customer rates (retail banking), and 3 of 23 news and earnings
rows likewise. Opus agreed (19 of 42 to retail). No person has checked.
(`labelling-topup-2026-10-01.md`)

**On-topic quotes in the replay.** In the search-mode replay, Claude judged how many harness-found
quotes were on the asked topic: about 10 of 33 when ranked by the question,
about 19 of 33 when ranked by the aspect's name, most of the latter report
boilerplate. A subjective count. (`chatbot-eval-build-2026-10-01.md`)

**Report boilerplate.** Report boilerplate is not evidence of sentiment: "These
Forward-Looking Statements are statements regarding ...", footnotes such as
"1/ Wealth Management income comprises ...". Assumed neutral and not worth
quoting. Should they be removed from the corpus, as PDF debris was
considered (`preprocessing-dry-run-2026-10-01.md`)?

**Product descriptions.** A product description is neutral unless it judges: "UOB One gives
4% on $100k" neutral, "UOB One is the best leh" positive. This is the
neutral boundary where people, Opus and the fine-tuned model disagree most
(`error-analysis-2026-10-01.md`: most of the model's errors are Reddit
descriptions of retail products called positive or negative).

**A "buy" with 0.9% upside.** Analyst consensus: "buy" with an implied upside of 0.9% was reported
as given. Whether a local reader would call that a buy is not a question
the system answers.

**Opus as the NER reference.** The NER gold-sheet reference: Opus's reading was taken as a
stand-in for a person's. It agrees with NER on 200 of 201 sentences, but it
was given the same rules NER encodes, so it can't test the rules (the DBS Vickers and subsidiaries questions).

---

*Counts: `data/plp.db` on 2026-10-02, case-insensitive word matches over
`sentences.text`. Examples are quoted from the corpus. Sources for model
behaviour: `data/aspect_llm/llama3.1_8b.96efe244.jsonl` (llama's cached answers),
`data/labeled/candidates.csv` (people, base FinBERT),
`data/labeled/claude/` (Opus).*
