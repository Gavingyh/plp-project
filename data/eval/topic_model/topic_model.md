# Topic models against the human aspect labels

Fitted on 45,844 sentences; compared on 1,277 human-labelled sentences. Chance is the level a shuffled labelling gives.

| method | topics | mean coherence | NMI (chance) | ARI (chance) | purity (chance) |
|---|---|---|---|---|---|
| NMF | 11 | 0.247 | 0.268 (0.019) | 0.116 (0.000) | 0.486 (0.373) |
| LDA | 11 | 0.161 | 0.264 (0.019) | 0.122 (-0.000) | 0.507 (0.373) |

### NMF, 11 topics

| topic | top words | coherence | corpus sentences | commonest human aspect (share) |
|---|---|---|---|---|
| 0 | income, net, non, fee, trading, book, commercial, treasury | 0.406 | 2,146 | income_profit_results (0.39, n=84) |
| 1 | account, savings, multiplier, open, salary, multi, currency, stash | 0.067 | 3,278 | retail_banking_sentiment (0.88, n=59) |
| 2 | card, credit, debit, use, spending, lady, pay, miles | 0.195 | 3,334 | retail_banking_sentiment (0.94, n=87) |
| 3 | usd, transfer, ibkr, sgd, currency, multi, deposit, free | 0.292 | 2,734 | retail_banking_sentiment (0.86, n=73) |
| 4 | year, ago, half, previous, compared, growth, years, fixed | 0.183 | 1,979 | income_profit_results (0.27, n=67) |
| 5 | just, buy, use, like, vickers, stocks, shares, money | 0.103 | 10,033 | retail_banking_sentiment (0.45, n=216) |
| 6 | million, allowances, total, higher, basis, points, specific, loans | 0.339 | 2,213 | asset_quality (0.41, n=86) |
| 7 | wealth, management, fees, banking, growth, loan, related, new | 0.279 | 7,954 | wealth_business (0.23, n=234) |
| 8 | quarter, ratio, dividend, share, capital, cents, return, npl | 0.340 | 4,706 | capital_liquidity (0.18, n=153) |
| 9 | billion, profit, rose, expenses, sgd, net, grew, increased | 0.310 | 1,874 | income_profit_results (0.48, n=71) |
| 10 | spend, cashback, month, salary, miles, cards, bonus, citi | 0.205 | 5,593 | retail_banking_sentiment (0.86, n=147) |

### LDA, 11 topics

| topic | top words | coherence | corpus sentences | commonest human aspect (share) |
|---|---|---|---|---|
| 0 | income, net, million, billion, profit, total, quarter, year | 0.322 | 7,879 | income_profit_results (0.40, n=307) |
| 1 | like, gold, money, shares, buy, long, invest, term | 0.069 | 5,102 | retail_banking_sentiment (0.40, n=120) |
| 2 | card, credit, miles, cards, citi, visa, use, spend | 0.216 | 4,486 | retail_banking_sentiment (0.95, n=107) |
| 3 | usd, account, transfer, ibkr, sgd, fee, currency, fees | 0.211 | 3,660 | retail_banking_sentiment (0.84, n=95) |
| 4 | said, ceo, grew, group, financial, customers, gupta, tan | 0.102 | 3,337 | other (0.29, n=77) |
| 5 | singapore, banking, asia, services, global, malaysia, digital, loan | 0.121 | 2,668 | other (0.36, n=87) |
| 6 | wealth, management, customer, fees, growth, banking, loan, trade | 0.240 | 2,871 | wealth_business (0.28, n=95) |
| 7 | account, savings, just, multiplier, currently, cash, rates, salary | 0.120 | 5,494 | retail_banking_sentiment (0.71, n=111) |
| 8 | buy, vickers, stock, just, years, cash, stocks, time | -0.002 | 3,858 | retail_banking_sentiment (0.33, n=91) |
| 9 | card, cashback, spend, month, credit, salary, minimum, hit | 0.232 | 3,701 | retail_banking_sentiment (0.87, n=98) |
| 10 | loans, year, rate, rates, basis, points, billion, china | 0.144 | 2,788 | asset_quality (0.21, n=89) |
