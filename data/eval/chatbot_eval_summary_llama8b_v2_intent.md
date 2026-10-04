# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Intent classifier: `llama3.1:8b`  
Run at: 2026-10-03T19:28:41.861771+00:00  
Questions: 32  
Errors (backend/network failures): 1

## Automated checks

- Tool selection: 21/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 7/8 correct
- Citation fabrication flagged: 12/32 answers (38%)
- Answered by an input guard without calling the model: 6/32
- Answers carrying a figure no tool returned: 5/32

## Failures needing a look

- **lookup-2** (lookup): citation fabrication flagged
- **lookup-3** (lookup): citation fabrication flagged
- **lookup-5** (lookup): citation fabrication flagged
- **compare-1** (compare): error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=120); tool selection: expected tool never called
- **trend-1** (trend): citation fabrication flagged; unverified figures: 12345
- **oos-2** (out_of_scope): behavior: answered without declining or flagging no data
- **thin-1** (thin_data): tool selection: expected tool never called
- **evidence-1** (evidence): citation fabrication flagged
- **consensus-1** (consensus): citation fabrication flagged; unverified figures: 6%, 41%, 47%, 6%
- **lookup-6** (lookup): citation fabrication flagged
- **lookup-7** (lookup): citation fabrication flagged; unverified figures: 12345
- **lookup-8** (lookup): citation fabrication flagged; unverified figures: 14.4%, 123, 83.6%, 125
- **compare-4** (compare): citation fabrication flagged; unverified figures: 12345, 67890, 34567
- **compare-5** (compare): citation fabrication flagged
- **trend-3** (trend): citation fabrication flagged
- **evidence-3** (evidence): tool selection: expected tool never called

## Not automated: read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.