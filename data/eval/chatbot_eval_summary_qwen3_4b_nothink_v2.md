# Chatbot evaluation summary

Model: `OllamaBackend / qwen3:4b`  
Run at: 2026-10-02T02:40:53.722878+00:00  
Questions: 32  
Errors (backend/network failures): 22

## Automated checks

- Tool selection: 2/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 8/8 correct
- Citation fabrication flagged: 2/32 answers (6%)
- Answered by an input guard without calling the model: 8/32
- Answers carrying a figure no tool returned: 0/32

## Failures needing a look

- **lookup-1** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-2** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-3** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-4** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-5** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **compare-1** (compare): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **compare-2** (compare): citation fabrication flagged
- **compare-3** (compare): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **trend-1** (trend): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **trend-2** (trend): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **thin-1** (thin_data): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **thin-2** (thin_data): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **evidence-1** (evidence): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **evidence-2** (evidence): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **consensus-1** (consensus): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **consensus-2** (consensus): citation fabrication flagged
- **lookup-6** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-7** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-8** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-9** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **compare-4** (compare): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **compare-5** (compare): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **trend-3** (trend): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **evidence-3** (evidence): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.