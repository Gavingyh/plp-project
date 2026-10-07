# Chatbot evaluation summary

Model: `OpenAIBackend / openai/gpt-oss-120b`  
Intent classifier: `llama3.1:8b`  
Run at: 2026-10-06T17:11:05.432307+00:00  
Questions: 32  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 24/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 6/8 correct
- Citation fabrication flagged: 0/32 answers (0%)
- Answered by an input guard without calling the model: 6/32
- Answers carrying a figure no tool returned: 4/32
- Evidence written without a search, removed by CHATBOT_ENFORCE_EVIDENCE: 4/32

## Failures needing a look

- **compare-2** (compare): unverified figures: 24
- **oos-1** (out_of_scope): behavior: answered without declining or flagging no data
- **oos-2** (out_of_scope): behavior: answered without declining or flagging no data
- **lookup-8** (lookup): unverified figures: 11
- **trend-3** (trend): unverified figures: 10
- **evidence-3** (evidence): unverified figures: 28, 24

## Not automated: read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.