# Chatbot evaluation summary

Model: `OllamaBackend / qwen3:4b`  
Run at: 2026-09-10T18:25:08.716464+00:00  
Questions: 23  
Errors (backend/network failures): 23

## Automated checks

- Tool selection: 0/16 correct (16 of 23 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 0/7 correct
- Citation fabrication flagged: 0/23 answers (0%)

## Failures needing a look

- **lookup-1** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-2** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-3** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-4** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-5** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **compare-1** (compare): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **compare-2** (compare): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **compare-3** (compare): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **trend-1** (trend): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **trend-2** (trend): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **oos-1** (out_of_scope): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); behavior: answered without declining or flagging no data
- **oos-2** (out_of_scope): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); behavior: answered without declining or flagging no data
- **oos-3** (out_of_scope): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); behavior: answered without declining or flagging no data
- **thin-1** (thin_data): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **thin-2** (thin_data): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **evidence-1** (evidence): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **evidence-2** (evidence): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **advice-1** (advice): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); behavior: no advice-decline language found
- **advice-2** (advice): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); behavior: no advice-decline language found
- **advice-3** (advice): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); behavior: no advice-decline language found
- **advice-4** (advice): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); behavior: no advice-decline language found
- **consensus-1** (consensus): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **consensus-2** (consensus): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.