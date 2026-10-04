# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Run at: 2026-10-02T00:56:25.059988+00:00  
Questions: 32  
Errors (backend/network failures): 1

## Automated checks

- Tool selection: 20/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 8/8 correct
- Citation fabrication flagged: 0/32 answers (0%)
- Answered by an input guard without calling the model: 8/32
- Answers carrying a figure no tool returned: 1/32
- Evidence written without a search, removed by CHATBOT_ENFORCE_EVIDENCE: 10/32

## Failures needing a look

- **thin-1** (thin_data): tool selection: expected tool never called
- **evidence-1** (evidence): tool selection: wrong bank: got None, expected 'DBS'
- **lookup-8** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **evidence-3** (evidence): tool selection: expected tool never called; unverified figures: 70.5%

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.