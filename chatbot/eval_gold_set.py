"""
Gold-set questions for evaluating the chatbot, covering the categories the
grounding rules in chatbot/prompts.py are meant to handle correctly:
straightforward lookups, comparisons, trends, out-of-scope questions, thin
or zero-data questions, evidence requests, and advice-seeking questions the
chatbot must decline.

Each entry states what a correct answer looks like, so a run can be checked
automatically where that is possible (which tool should have been called,
whether the answer should decline advice) and flagged for human judgement
where it is not (whether a stated number is actually correct, whether cited
evidence is relevant).

Real aspect names, matching config/aspects.yaml.

Two frozen sets. GOLD_SET (v1, 23 questions) is unchanged since 26 Sep so
runs stay comparable; it only covers the proposal's four aspects. GOLD_SET_V2
(2026-10-01) adds nine questions on the aspects the ten-aspect taxonomy
introduced and one more uncovered bank, for 32 in all. MULTI_TURN holds
conversations whose later turns depend on earlier ones ("and OCBC?").
"""

ASPECTS = ["dividend_policy", "asset_quality", "net_interest_margin", "management_guidance"]  # v1's four
BANKS = ["DBS", "OCBC", "UOB"]

GOLD_SET = [
    # --- Single-bank, single-aspect lookup ---
    {"id": "lookup-1", "category": "lookup", "question": "What is the sentiment for DBS on dividend policy?",
     "expected_tool": "get_sentiment", "expected_bank": "DBS", "expected_aspect": "dividend_policy"},
    {"id": "lookup-2", "category": "lookup", "question": "How is OCBC's asset quality being discussed?",
     "expected_tool": "get_sentiment", "expected_bank": "OCBC", "expected_aspect": "asset_quality"},
    {"id": "lookup-3", "category": "lookup", "question": "Tell me about UOB's net interest margin sentiment.",
     "expected_tool": "get_sentiment", "expected_bank": "UOB", "expected_aspect": "net_interest_margin"},
    {"id": "lookup-4", "category": "lookup", "question": "What's the overall sentiment on DBS right now?",
     "expected_tool": "get_sentiment", "expected_bank": "DBS", "expected_aspect": None},
    {"id": "lookup-5", "category": "lookup", "question": "How does the market feel about DBS's management guidance?",
     "expected_tool": "get_sentiment", "expected_bank": "DBS", "expected_aspect": "management_guidance"},

    # --- Cross-bank comparison ---
    {"id": "compare-1", "category": "compare", "question": "Compare DBS, OCBC and UOB on dividend policy.",
     "expected_tool": "compare_banks", "expected_aspect": "dividend_policy"},
    {"id": "compare-2", "category": "compare", "question": "Which of the three banks has the best asset quality sentiment?",
     "expected_tool": "compare_banks", "expected_aspect": "asset_quality"},
    {"id": "compare-3", "category": "compare", "question": "How does UOB compare to DBS overall?",
     "expected_tool": "compare_banks", "expected_aspect": None},

    # --- Trend ---
    {"id": "trend-1", "category": "trend", "question": "Has sentiment on DBS's dividend policy improved recently?",
     "expected_tool": "get_trend", "expected_bank": "DBS", "expected_aspect": "dividend_policy"},
    {"id": "trend-2", "category": "trend", "question": "Is UOB's asset quality sentiment getting worse?",
     "expected_tool": "get_trend", "expected_bank": "UOB", "expected_aspect": "asset_quality"},

    # --- Out of scope: a bank the system does not cover ---
    {"id": "oos-1", "category": "out_of_scope",
     "question": "What is the sentiment on Standard Chartered's dividend policy?",
     "expected_behavior": "decline_or_no_data"},
    {"id": "oos-2", "category": "out_of_scope",
     "question": "How does the market feel about HSBC right now?",
     "expected_behavior": "decline_or_no_data"},
    {"id": "oos-3", "category": "out_of_scope",
     "question": "What's the weather like in Singapore today?",
     "expected_behavior": "decline_or_no_data"},

    # --- Thin/zero data: real aspects, but combinations unlikely to have volume ---
    {"id": "thin-1", "category": "thin_data",
     "question": "What is UOB's sentiment on net interest margin in the last 7 days?",
     "expected_tool": "get_sentiment", "expected_bank": "UOB", "expected_aspect": "net_interest_margin"},
    {"id": "thin-2", "category": "thin_data",
     "question": "How is OCBC's management guidance trending this week?",
     "expected_tool": "get_trend", "expected_bank": "OCBC", "expected_aspect": "management_guidance"},

    # --- Evidence requests ---
    {"id": "evidence-1", "category": "evidence",
     "question": "Show me evidence of what people are saying about DBS's dividend.",
     "expected_tool": "search_evidence", "expected_bank": "DBS"},
    {"id": "evidence-2", "category": "evidence",
     "question": "What specific complaints exist about UOB's asset quality?",
     "expected_tool": "search_evidence", "expected_bank": "UOB"},

    # --- Advice-seeking: must decline, per chatbot/prompts.py rule 5 ---
    {"id": "advice-1", "category": "advice", "question": "Should I buy DBS stock?",
     "expected_behavior": "decline_advice"},
    {"id": "advice-2", "category": "advice", "question": "Is now a good time to sell my UOB shares?",
     "expected_behavior": "decline_advice"},
    {"id": "advice-3", "category": "advice", "question": "Which bank should I invest in?",
     "expected_behavior": "decline_advice"},
    {"id": "advice-4", "category": "advice", "question": "Will DBS's share price go up next quarter?",
     "expected_behavior": "decline_advice"},

    # --- Analyst consensus ---
    {"id": "consensus-1", "category": "consensus", "question": "What do analysts think of DBS?",
     "expected_tool": "get_analyst_consensus", "expected_bank": "DBS"},
    {"id": "consensus-2", "category": "consensus", "question": "What's the average price target for OCBC?",
     "expected_tool": "get_analyst_consensus", "expected_bank": "OCBC"},
]

# --- v2 additions (2026-10-01): the aspects added on 30 Sep, and one more uncovered bank ---
V2_ADDITIONS = [
    {"id": "lookup-6", "category": "lookup", "question": "How do people feel about OCBC's wealth management business?",
     "expected_tool": "get_sentiment", "expected_bank": "OCBC", "expected_aspect": "wealth_business"},
    {"id": "lookup-7", "category": "lookup", "question": "What's the sentiment on UOB's cards and retail banking service?",
     "expected_tool": "get_sentiment", "expected_bank": "UOB", "expected_aspect": "retail_banking_sentiment"},
    {"id": "lookup-8", "category": "lookup", "question": "How is DBS's capital and liquidity position being discussed?",
     "expected_tool": "get_sentiment", "expected_bank": "DBS", "expected_aspect": "capital_liquidity"},
    {"id": "lookup-9", "category": "lookup", "question": "What's the sentiment on OCBC's reported profits?",
     "expected_tool": "get_sentiment", "expected_bank": "OCBC", "expected_aspect": "income_profit_results"},
    {"id": "compare-4", "category": "compare", "question": "Compare how investors feel about the three banks' shares.",
     "expected_tool": "compare_banks", "expected_aspect": "investor_stock_sentiment"},
    {"id": "compare-5", "category": "compare", "question": "Compare the banks on how the macro environment is discussed.",
     "expected_tool": "compare_banks", "expected_aspect": "macro_market_environment"},
    {"id": "trend-3", "category": "trend", "question": "Is sentiment on UOB's retail banking improving?",
     "expected_tool": "get_trend", "expected_bank": "UOB", "expected_aspect": "retail_banking_sentiment"},
    {"id": "evidence-3", "category": "evidence", "question": "Show me what people say about OCBC's wealth business.",
     "expected_tool": "search_evidence", "expected_bank": "OCBC"},
    {"id": "oos-4", "category": "out_of_scope", "question": "What's the sentiment on Maybank's dividend?",
     "expected_behavior": "decline_or_no_data"},
]

GOLD_SET_V2 = GOLD_SET + V2_ADDITIONS

# Conversations: each turn is checked like a single question, but asked within
# one Conversation, so a turn that omits the bank or aspect must carry it over.
MULTI_TURN = [
    {"id": "mt-1", "turns": [
        {"question": "What is the sentiment on DBS's dividend policy?",
         "expected_tool": "get_sentiment", "expected_bank": "DBS", "expected_aspect": "dividend_policy"},
        {"question": "And OCBC?",
         "expected_tool": "get_sentiment", "expected_bank": "OCBC", "expected_aspect": "dividend_policy"},
    ]},
    {"id": "mt-2", "turns": [
        {"question": "How is UOB doing overall?",
         "expected_tool": "get_sentiment", "expected_bank": "UOB", "expected_aspect": None},
        {"question": "What about its asset quality?",
         "expected_tool": "get_sentiment", "expected_bank": "UOB", "expected_aspect": "asset_quality"},
        {"question": "Has that improved lately?",
         "expected_tool": "get_trend", "expected_bank": "UOB", "expected_aspect": "asset_quality"},
    ]},
    {"id": "mt-3", "turns": [
        {"question": "Compare the three banks on net interest margin.",
         "expected_tool": "compare_banks", "expected_aspect": "net_interest_margin"},
        {"question": "Show me some evidence for DBS on that.",
         "expected_tool": "search_evidence", "expected_bank": "DBS"},
    ]},
    {"id": "mt-4", "turns": [
        {"question": "What do analysts think of OCBC?",
         "expected_tool": "get_analyst_consensus", "expected_bank": "OCBC"},
        {"question": "So should I buy it?", "expected_behavior": "decline_advice"},
    ]},
]

_ADVICE_DECLINE_MARKERS = (
    "not financial advice", "not investment advice", "can't advise", "cannot advise",
    "can't tell you whether", "cannot tell you whether", "not able to advise",
    "consult a financial", "do not provide investment advice", "not provide financial advice",
    "i can't recommend", "i cannot recommend", "unable to recommend", "not in a position to advise",
)

_NO_DATA_MARKERS = (
    "no data", "not covered", "don't have data", "do not have data", "only cover",
    "only covers", "not available", "outside the scope", "out of scope", "not something i track",
    # the off-topic reply of chatbot/guards.py's scope guard, added when the checker
    # was found not to recognise it (2026-09-26)
    "outside what i can help with",
    "don't track", "do not track", "cannot answer", "can't answer",
)


def looks_like_advice_decline(answer: str) -> bool:
    low = answer.lower()
    return any(m in low for m in _ADVICE_DECLINE_MARKERS)


def looks_like_no_data_response(answer: str) -> bool:
    low = answer.lower()
    return any(m in low for m in _NO_DATA_MARKERS)
