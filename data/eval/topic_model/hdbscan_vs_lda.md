# HDBSCAN and LDA against the human aspect labels

HDBSCAN clusters UMAP-reduced FinBERT embeddings of 43,331 of the 45,844 sentences in the database (the embedding cache is not up to date for the rest), compared on 1,277 human-labelled sentences. Chance is the level a shuffled labelling gives. No setting was chosen using the human labels.

| method | groups | sentences left as noise | mean coherence | NMI (chance) | ARI (chance) | purity (chance) |
|---|---|---|---|---|---|---|
| LDA, 11 topics | 11 | 0% | 0.161 | 0.264 (0.019) | 0.122 (-0.000) | 0.507 (0.373) |
| HDBSCAN, min cluster 10 (noise as one group) | 345 | 63% | -0.132 | 0.274 (0.173) | 0.051 (0.002) | 0.543 (0.443) |
| HDBSCAN, min cluster 100 (noise as one group) | 27 | 59% | 0.203 | 0.253 (0.050) | 0.086 (0.001) | 0.522 (0.378) |
| HDBSCAN, min cluster 200 (noise as one group) | 5 | 11% | 0.183 | 0.103 (0.014) | 0.078 (0.001) | 0.413 (0.374) |

Clustered sentences only (noise left out):

| min cluster size | labelled sentences covered | NMI (chance) | ARI (chance) | purity (chance) |
|---|---|---|---|---|
| 10 | 485 of 1277 | 0.466 (0.312) | 0.110 (-0.001) | 0.757 (0.525) |
| 100 | 598 of 1277 | 0.409 (0.086) | 0.219 (0.000) | 0.624 (0.326) |
| 200 | 1147 of 1277 | 0.113 (0.014) | 0.062 (0.001) | 0.434 (0.390) |

### HDBSCAN, min cluster size 10: largest clusters

| cluster | sentences | top words | coherence | commonest human aspect (share) |
|---|---|---|---|---|
| 290 | 1,234 | bad, fraudulent, called, worst, told, blocked, scam, police | -0.197 | retail_banking_sentiment (0.73, n=67) |
| 209 | 701 | fixed, years, months, cash, eir, current, vwra, cpf | 0.061 | retail_banking_sentiment (0.69, n=16) |
| 199 | 653 | fell, declined, lower, previous, million, quarter, decreased, decline | 0.294 | income_profit_results (0.48, n=23) |
| 124 | 590 | does, did, buy, what's, ask, instead, work, curious | -0.106 | retail_banking_sentiment (0.78, n=9) |
| 342 | 462 | strong, structural, growing, position, opportunities, continue, franchise, flows | 0.220 | management_guidance (0.39, n=28) |
| 148 | 325 | usd, transfer, multi, free, currency, open, account, send | 0.253 | retail_banking_sentiment (1.00, n=7) |
| 316 | 301 | started, applied, opened, approved, years, signed, got, happened | -0.165 | retail_banking_sentiment (0.43, n=7) |
| 236 | 247 | better, good, decent, rates, pretty, imo, quite, exchange | -0.080 | retail_banking_sentiment (1.00, n=5) |
| 14 | 197 | laundering, claim, court, lawsuit, scams, phishing, scam, jail | -0.316 | other (0.50, n=6) |
| 220 | 196 | beats, hits, estimates, record, profit, rises, posts, jumps | -0.116 | dividend_policy (0.25, n=4) |
| 265 | 196 | currently, savings, sitting, account, emergency, salary, credited, i'm | 0.156 | retail_banking_sentiment (1.00, n=3) |
| 308 | 183 | stake, acquire, indonesia, allianzgi, acquires, allianz, commonwealth, arm | -0.337 | management_guidance (0.60, n=5) |
| 306 | 173 | spend, salary, earn, month, min, monthly, credit, grabpay | 0.156 | retail_banking_sentiment (1.00, n=2) |
| 284 | 171 | travel, online, contactless, shopping, dining, visa, miles, spend | 0.325 | retail_banking_sentiment (1.00, n=5) |
| 205 | 166 | yoy, qoq, core, record, nim, nii, npl, profit | 0.336 | income_profit_results (0.71, n=7) |

### HDBSCAN, min cluster size 100: largest clusters

| cluster | sentences | top words | coherence | commonest human aspect (share) |
|---|---|---|---|---|
| 3 | 2,303 | singapore, launches, digital, asia, banking, new, launch, malaysia | 0.151 | other (0.53, n=87) |
| 10 | 1,962 | rose, income, billion, net, grew, higher, million, increased | 0.327 | income_profit_results (0.64, n=84) |
| 23 | 1,935 | spend, miles, card, cashback, month, spending, better, bonus | 0.203 | retail_banking_sentiment (0.91, n=54) |
| 16 | 1,647 | growth, strong, wealth, continue, management, opportunities, customers, business | 0.254 | management_guidance (0.44, n=63) |
| 24 | 1,389 | card, account, got, just, bad, called, like, fraudulent | 0.057 | retail_banking_sentiment (0.76, n=74) |
| 20 | 984 | account, usd, transfer, app, use, open, ibkr, multi | 0.205 | retail_banking_sentiment (0.90, n=20) |
| 11 | 747 | lower, fell, declined, million, income, quarter, net, billion | 0.346 | income_profit_results (0.47, n=34) |
| 6 | 695 | net, assets, income, equity, non, allowances, amortisation, loans | 0.418 | income_profit_results (0.53, n=19) |
| 21 | 662 | does, did, buy, know, account, just, instead, work | 0.060 | retail_banking_sentiment (0.67, n=12) |
| 17 | 616 | rates, rate, year, billion, piyush, gupta, cuts, quarter | 0.124 | management_guidance (0.31, n=35) |
| 22 | 587 | fixed, years, sgd, cash, months, usd, eir, month | 0.031 | retail_banking_sentiment (0.54, n=13) |
| 19 | 506 | account, custodian, endowus, use, currently, held, using, card | 0.078 | retail_banking_sentiment (0.82, n=11) |
| 25 | 464 | account, started, years, opened, ago, got, open, card | 0.068 | retail_banking_sentiment (0.70, n=10) |
| 2 | 417 | ceo, appoints, head, names, tan, chairman, chief, india | 0.246 | other (0.57, n=7) |
| 4 | 412 | services, disruption, claim, laundering, outage, restored, court, linked | -0.383 | retail_banking_sentiment (0.54, n=13) |

### HDBSCAN, min cluster size 200: largest clusters

| cluster | sentences | top words | coherence | commonest human aspect (share) |
|---|---|---|---|---|
| 4 | 34,889 | account, card, income, year, billion, just, net, credit | 0.024 | retail_banking_sentiment (0.42, n=1032) |
| 1 | 2,034 | singapore, launches, banking, digital, new, asia, wealth, launch | 0.137 | other (0.53, n=78) |
| 3 | 1,042 | net, income, assets, loans, non, equity, total, allowances | 0.364 | income_profit_results (0.39, n=26) |
| 2 | 390 | ceo, appoints, head, names, tan, chairman, chief, new | 0.207 | other (0.57, n=7) |
| 0 | 344 | financial, statements, group, audit, information, consolidated, report, statement | 0.183 | other (1.00, n=4) |
