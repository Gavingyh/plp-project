# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Intent classifier: `llama3.1:8b`  
Run at: 2026-10-06T17:10:47.720818+00:00  
Questions: 32  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 23/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 7/8 correct
- Citation fabrication flagged: 0/32 answers (0%)
- Answered by an input guard without calling the model: 6/32
- Answers carrying a figure no tool returned: 2/32
- Evidence written without a search, removed by CHATBOT_ENFORCE_EVIDENCE: 2/32

## Failures needing a look

- **lookup-2** (lookup): unverified figures: 4.4%
- **trend-2** (trend): unverified figures: +0.006
- **oos-1** (out_of_scope): behavior: answered without declining or flagging no data
- **thin-1** (thin_data): tool selection: expected tool never called

## Not automated: read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.