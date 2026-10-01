# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Run at: 2026-10-01T14:14:55.318945+00:00  
Questions: 32  
Errors (backend/network failures): 6

## Automated checks

- Tool selection: 14/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 8/8 correct
- Citation fabrication flagged: 8/32 answers (25%)
- Answered by an input guard without calling the model: 8/32
- Answers carrying a figure no tool returned: 6/32

## Failures needing a look

- **lookup-1** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-2** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-5** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **compare-1** (compare): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **trend-1** (trend): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **thin-1** (thin_data): tool selection: expected tool never called
- **evidence-1** (evidence): tool selection: wrong bank: got None, expected 'DBS'; unverified figures: 0.97
- **evidence-2** (evidence): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **consensus-1** (consensus): citation fabrication flagged
- **lookup-7** (lookup): citation fabrication flagged; unverified figures: 12345, 67890
- **lookup-8** (lookup): tool selection: expected tool never called; citation fabrication flagged
- **lookup-9** (lookup): citation fabrication flagged; unverified figures: 15%, 12345
- **compare-4** (compare): citation fabrication flagged
- **compare-5** (compare): citation fabrication flagged; unverified figures: 4099
- **trend-3** (trend): citation fabrication flagged; unverified figures: 12345, 67890
- **evidence-3** (evidence): tool selection: expected tool never called; citation fabrication flagged; unverified figures: 12345, 67890

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.