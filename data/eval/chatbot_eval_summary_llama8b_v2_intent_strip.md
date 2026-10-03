# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Intent classifier: `llama3.1:8b`  
Run at: 2026-10-03T20:13:16.525738+00:00  
Questions: 32  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 22/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 7/8 correct
- Citation fabrication flagged: 0/32 answers (0%)
- Answered by an input guard without calling the model: 6/32
- Answers carrying a figure no tool returned: 2/32
- Evidence written without a search, removed by CHATBOT_ENFORCE_EVIDENCE: 14/32

## Failures needing a look

- **compare-1** (compare): unverified figures: 46%, 35%
- **oos-2** (out_of_scope): behavior: answered without declining or flagging no data
- **thin-1** (thin_data): tool selection: expected tool never called
- **consensus-1** (consensus): unverified figures: 6%, 41%, 47%, 6%
- **evidence-3** (evidence): tool selection: expected tool never called

## Not automated: read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.