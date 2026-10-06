# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Intent classifier: `llama3.1:8b`  
Run at: 2026-10-04T09:05:24.546296+00:00  
Questions: 32  
Errors (backend/network failures): 1

## Automated checks

- Tool selection: 20/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 8/8 correct
- Citation fabrication flagged: 0/32 answers (0%)
- Answered by an input guard without calling the model: 6/32
- Answers carrying a figure no tool returned: 1/32
- Evidence written without a search, removed by CHATBOT_ENFORCE_EVIDENCE: 9/32

## Failures needing a look

- **lookup-2** (lookup): tool selection: expected tool never called
- **thin-1** (thin_data): tool selection: expected tool never called
- **evidence-2** (evidence): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **compare-4** (compare): unverified figures: 10,000
- **evidence-3** (evidence): tool selection: wrong bank: got None, expected 'OCBC'

## Not automated: read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.