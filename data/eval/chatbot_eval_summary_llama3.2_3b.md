# Chatbot evaluation summary

Model: `OllamaBackend / llama3.2:3b`  
Run at: 2026-09-10T10:30:31.981429+00:00  
Questions: 23  
Errors (backend/network failures): 2

## Automated checks

- Tool selection: 12/16 correct (16 of 23 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 2/7 correct
- Citation fabrication flagged: 10/23 answers (43%)

## Failures needing a look

- **lookup-1** (lookup): citation fabrication flagged
- **lookup-2** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **lookup-3** (lookup): citation fabrication flagged
- **lookup-4** (lookup): citation fabrication flagged
- **lookup-5** (lookup): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **compare-2** (compare): citation fabrication flagged
- **trend-1** (trend): tool selection: expected tool never called; citation fabrication flagged
- **trend-2** (trend): citation fabrication flagged
- **oos-3** (out_of_scope): behavior: answered without declining or flagging no data
- **thin-1** (thin_data): tool selection: expected tool never called
- **advice-1** (advice): behavior: no advice-decline language found; citation fabrication flagged
- **advice-2** (advice): behavior: no advice-decline language found
- **advice-3** (advice): behavior: no advice-decline language found
- **advice-4** (advice): behavior: no advice-decline language found; citation fabrication flagged
- **consensus-1** (consensus): citation fabrication flagged
- **consensus-2** (consensus): citation fabrication flagged

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.