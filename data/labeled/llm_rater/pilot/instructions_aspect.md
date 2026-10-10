# Rater instructions, pass 1: aspect

You are labelling sentences about Singapore's three listed banks (DBS, OCBC,
UOB) for an investor-sentiment study. The text below is the project's
annotation guideline (`docs/annotation-guideline.md`, version 2), quoted, plus
the output format.

## Rules for this task

- Read only `input_aspect.csv` and this file. Do not open any other file in
  the repository: other files hold human or model labels for these sentences.
- Judge each sentence yourself. Do not write code to classify, and do not call
  any model, API or search.
- Every row gets an answer.

## From the guideline

Each row is one sentence. For each one:

1. **Is it about the bank?** If the bank is named only in passing ("I banked
   in via DBS PayNow" in a thread about something else), or the name refers
   to something else entirely (UOB Kay Hian the broker, Aston Martin DBS),
   set `not_about_bank`. (For this task, still choose the best aspect, so
   the answer can be compared with people who had no such option.)
2. **Choose one aspect**: the one the sentence is mainly about, from the ten
   below or `other`. If it touches two, choose the one its sentiment is about.

| aspect | covers | not here |
|---|---|---|
| `asset_quality` | non-performing loans, allowances and provisions, credit costs, exposure to troubled borrowers or sectors | scams against customers (`retail_banking_sentiment`) |
| `capital_liquidity` | CET1 and capital ratios, leverage, LCR/NSFR, Basel rules, capital instruments and bond issuance | dividends and buybacks (`dividend_policy`) |
| `dividend_policy` | dividends paid or expected, DPS, payout ratio, ex-dividend dates, dividend yield, capital returned to shareholders | interest a customer earns on deposits (`retail_banking_sentiment`) |
| `net_interest_margin` | NIM and net interest income, loan and deposit growth as a driver of them, the effect of rate moves on the bank's earnings | rates offered to customers (`retail_banking_sentiment`) |
| `management_guidance` | forward-looking statements by the bank: targets, outlook, guidance raised or cut, strategy, earnings-call answers | results already reported (`income_profit_results`) |
| `income_profit_results` | reported income and profit: total income, net profit, fee and trading income | results that are specifically NIM, asset quality or wealth (those aspects) |
| `wealth_business` | wealth management and private or premier banking: AUM, wealth fee income, wealth targets | retail savings products (`retail_banking_sentiment`) |
| `investor_stock_sentiment` | the stock itself: buy, sell or hold views, share price and valuation, target prices, returns against alternatives | the bank's own results (`income_profit_results`) |
| `retail_banking_sentiment` | products and service as customers experience them: cards, cashback, savings accounts, fees, app outages, scams, rejected applications | — |
| `macro_market_environment` | GDP, rate cuts and hikes, geopolitics and trade, the macro outlook as it affects the banks | — |
| `other` | appointments and pay, awards, M&A and partnerships, CSR, careers, regulatory boilerplate, anything else | — |

## Output

Write `rater_aspect.jsonl` in the same folder: one line per input row, in
input order, exactly

{"sentence_id": "<id>", "aspect": "<one key from the table>", "not_about_bank": true|false}

No other fields, no commentary lines.
