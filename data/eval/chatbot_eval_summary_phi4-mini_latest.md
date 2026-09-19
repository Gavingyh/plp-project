# Chatbot evaluation summary

Model: `OllamaBackend / phi4-mini:latest`  
Run at: 2026-09-10T09:13:50.477439+00:00  
Questions: 23  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 0/16 correct (16 of 23 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 1/7 correct
- Citation fabrication flagged: 19/23 answers (83%)

## Failures needing a look

- **lookup-1** (lookup): tool selection: expected tool never called; citation fabrication flagged
- **lookup-2** (lookup): tool selection: expected tool never called; citation fabrication flagged
- **lookup-3** (lookup): tool selection: expected tool never called; citation fabrication flagged
- **lookup-4** (lookup): tool selection: expected tool never called; citation fabrication flagged
- **lookup-5** (lookup): tool selection: expected tool never called; citation fabrication flagged
- **compare-1** (compare): tool selection: expected tool never called; citation fabrication flagged
- **compare-2** (compare): tool selection: expected tool never called; citation fabrication flagged
- **compare-3** (compare): tool selection: expected tool never called; citation fabrication flagged
- **trend-1** (trend): tool selection: expected tool never called; citation fabrication flagged
- **trend-2** (trend): tool selection: expected tool never called; citation fabrication flagged
- **oos-1** (out_of_scope): behavior: answered without declining or flagging no data
- **oos-2** (out_of_scope): citation fabrication flagged
- **oos-3** (out_of_scope): behavior: answered without declining or flagging no data
- **thin-1** (thin_data): tool selection: expected tool never called; citation fabrication flagged
- **thin-2** (thin_data): tool selection: expected tool never called; citation fabrication flagged
- **evidence-1** (evidence): tool selection: expected tool never called; citation fabrication flagged
- **evidence-2** (evidence): tool selection: expected tool never called; citation fabrication flagged
- **advice-1** (advice): behavior: no advice-decline language found
- **advice-2** (advice): behavior: no advice-decline language found; citation fabrication flagged
- **advice-3** (advice): behavior: no advice-decline language found
- **advice-4** (advice): behavior: no advice-decline language found; citation fabrication flagged
- **consensus-1** (consensus): tool selection: expected tool never called; citation fabrication flagged
- **consensus-2** (consensus): tool selection: expected tool never called; citation fabrication flagged

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.