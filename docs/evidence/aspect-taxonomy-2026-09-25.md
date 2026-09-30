# From 338 clusters to a 10-aspect taxonomy

How the aspect taxonomy in `config/aspects.yaml` was derived (DESIGN
decision 21). Done by the text-analytics workstream on 2026-09-25; recorded
here on 2026-09-30 from the team's working files.

## Method

1. **Discovery.** `python -m aspects.discover` (FinBERT embeddings, UMAP,
   HDBSCAN, `min_cluster_size=10`) on the 42,690-sentence corpus of the
   2026-09-24 snapshot: **338 clusters, 27,949 noise points (65%)**. Output:
   [aspect-discovery-2026-09-25.raw.txt](aspect-discovery-2026-09-25.raw.txt)
   (email addresses in the sample sentences are redacted).
2. **Cluster labelling.** Every cluster was given one label from its top
   TF-IDF terms and sample sentences, in two passes. The team's working
   notes record that an AI assistant (Claude, in a chat session) drafted
   both passes from the raw output, with the teammate directing the
   revisions. The first pass used the proposal's aspects plus new labels
   for clusters that didn't fit; the second merged and promoted labels as
   described below. Per-cluster labels:
   [aspect-cluster-labels-2026-09-25.csv](aspect-cluster-labels-2026-09-25.csv)
   (sample sentences left out; they are in the raw output).
3. **Seed terms.** Each aspect's seeds in `config/aspects.yaml` are full
   sentences taken from its clusters, spread across banks and sub-topics,
   because a short phrase embeds differently from the sentences it is
   compared with.

## Result

Of the 14,741 clustered sentences:

| label | kind | clusters | sentences | share |
|---|---|---|---|---|
| retail_banking_sentiment | new | 113 | 5,386 | 36.5% |
| investor_stock_sentiment | new | 48 | 1,638 | 11.1% |
| income_profit_results | new | 27 | 1,575 | 10.7% |
| management_guidance | proposal, broadened | 21 | 1,066 | 7.2% |
| net_interest_margin | proposal, broadened | 20 | 949 | 6.4% |
| asset_quality | proposal, broadened | 19 | 746 | 5.1% |
| capital_liquidity | proposal, broadened | 12 | 296 | 2.0% |
| dividend_policy | proposal, broadened | 10 | 286 | 1.9% |
| wealth_business | new | 8 | 268 | 1.8% |
| macro_market_environment | new | 3 | 89 | 0.6% |
| corporate_news_governance | not an aspect | 45 | 2,172 | 14.7% |
| noise_boilerplate | not an aspect | 12 | 270 | 1.8% |

The ten aspects cover 83.4% of clustered sentences. The two non-aspect
buckets fall to `other`. HDBSCAN noise, 65% of the corpus, is untouched by
labelling: it is a clustering question.

"Proposal, broadened" counts capital and liquidity among the proposal's
aspects, as the labelling pass did; the September proposal's four were
dividend policy, asset quality, NIM and management guidance.

## Definitions

- **asset_quality**: NPL/NPA, allowances, credit costs, allowance coverage, credit-risk exposure.
- **capital_liquidity**: CET1/CAR, leverage ratio, LCR/NSFR, Basel III/IV, capital instruments, bond issuance.
- **dividend_policy**: dividends declared or paid, DPS, payout ratio, ex-dividend dates, dividend yield, and Reddit dividend-income arithmetic.
- **management_guidance**: outlook and forward guidance, earnings-call Q&A, executive commentary on strategy, risk and regulation.
- **net_interest_margin**: NIM, net interest income, loan and deposit growth as a NIM driver, repricing effects. Absorbs the first pass's separate loan/deposit-growth label.
- **income_profit_results**: total income, net profit, fee and trading income: income-statement reporting not specific to NIM, asset quality or wealth.
- **investor_stock_sentiment**: retail-investor talk about the stock itself: buy, sell or hold, share price and target prices, returns against alternatives.
- **retail_banking_sentiment**: consumer products and service: cards, cashback, savings accounts, fees, app outages, scams, rejected applications. An indirect signal, through the retail franchise and the bank's reputation.
- **wealth_business**: wealth management and private or premier banking: AUM, wealth fee income, wealth growth targets.
- **macro_market_environment**: GDP, rate moves, geopolitics and trade, macro outlook as it affects the banks.
- **other**: everything else, including corporate news and governance (appointments, pay, awards, M&A, CSR, careers, regulatory boilerplate) and extraction noise.

## What changed between the two labelling passes

1. The proposal's aspects were broadened to clusters whose own terms
   matched their vocabulary. NIM gained most (13 to 20 clusters), partly by
   absorbing loan and deposit growth.
2. `wealth_business` became an aspect: 268 sentences, the size of dividend
   policy or capital, and a revenue driver all three banks report.
3. Nine non-aspect labels were consolidated into two.
4. Retail-banking and retail-investor content, which the first pass had
   counted as non-aspect (all non-aspect labels then covered 62% of
   clustered sentences), became the two largest aspects. `investor_stock_sentiment` is retail investor
   sentiment in the most literal sense.

## Known limits

- **The similarity floor wasn't re-tuned.** 0.65 was calibrated in
  September for four aspects. With these ten and sentence-length seeds,
  seed-centroid assignment matches most sentences to most aspects: on the
  2026-09-30 corpus, 281,744 pairs for 44,345 sentences (6.4 aspects per
  sentence), and only 4% fall to `other`.
- **Seed-centroid assignment disagrees with people.** In the 2026-09-27
  labelling round annotators changed the assigned aspect on 1,119 of 1,300
  candidate rows (86%). Per-aspect scores from the centroids are therefore
  weak; the LLM classifier (DESIGN decision 16) is the planned fix, and the
  human aspect labels are now its evaluation set.
- The cluster labels were drafted by an AI assistant and not checked by a
  second person. Record this in the report's GenAI disclosure.
