# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Intent classifier: `llama3.1:8b`  
Run at: 2026-10-04T05:46:38.663312+00:00  
Questions: 32  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 22/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 7/8 correct
- Citation fabrication flagged: 0/32 answers (0%)
- Answered by an input guard without calling the model: 6/32
- Answers carrying a figure no tool returned: 4/32
- Evidence written without a search, removed by CHATBOT_ENFORCE_EVIDENCE: 3/32

## Failures needing a look

- **lookup-2** (lookup): tool selection: expected tool never called
- **trend-2** (trend): unverified figures: -0.2185
- **oos-1** (out_of_scope): behavior: answered without declining or flagging no data
- **thin-2** (thin_data): unverified figures: 25
- **lookup-8** (lookup): tool selection: expected tool never called; unverified figures: 12.7%, 5.1%
- **evidence-3** (evidence): unverified figures: -0.12, 20%, 80%

## Not automated: read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.