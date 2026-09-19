# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Run at: 2026-09-10T09:58:37.582550+00:00  
Questions: 23  
Errors (backend/network failures): 3

## Automated checks

- Tool selection: 12/16 correct (16 of 23 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 3/7 correct
- Citation fabrication flagged: 3/23 answers (13%)

## Failures needing a look

- **lookup-1** (lookup): citation fabrication flagged
- **lookup-2** (lookup): tool selection: expected tool never called
- **trend-1** (trend): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **oos-3** (out_of_scope): behavior: answered without declining or flagging no data
- **thin-1** (thin_data): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **evidence-2** (evidence): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **advice-1** (advice): behavior: no advice-decline language found; citation fabrication flagged
- **advice-2** (advice): behavior: no advice-decline language found; citation fabrication flagged
- **advice-3** (advice): behavior: no advice-decline language found

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.