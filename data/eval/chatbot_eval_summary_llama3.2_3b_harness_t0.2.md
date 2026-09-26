# Chatbot evaluation summary

Model: `OllamaBackend / llama3.2:3b`  
Run at: 2026-09-26T02:54:15.169152+00:00  
Questions: 23  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 13/16 correct (16 of 23 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 6/7 correct
- Citation fabrication flagged: 10/23 answers (43%)
- Answered by an input guard without calling the model: 6/23
- Answers carrying a figure no tool returned: 10/23

## Failures needing a look

- **lookup-1** (lookup): citation fabrication flagged; unverified figures: 123456, 3.5%, 987654
- **lookup-2** (lookup): tool selection: expected tool never called; unverified figures: 24
- **lookup-3** (lookup): citation fabrication flagged
- **lookup-5** (lookup): citation fabrication flagged; unverified figures: 123456, 789012
- **compare-1** (compare): citation fabrication flagged; unverified figures: 123456, 10, 234567, 1967, 345678
- **trend-1** (trend): citation fabrication flagged; unverified figures: 123456, 789012
- **trend-2** (trend): tool selection: expected tool never called; citation fabrication flagged
- **oos-3** (out_of_scope): behavior: answered without declining or flagging no data
- **thin-1** (thin_data): tool selection: expected tool never called; citation fabrication flagged; unverified figures: 12345, 67890
- **thin-2** (thin_data): citation fabrication flagged; unverified figures: 12345
- **evidence-1** (evidence): unverified figures: 4400, 0.54, 0.81, 26
- **consensus-1** (consensus): citation fabrication flagged; unverified figures: 25
- **consensus-2** (consensus): citation fabrication flagged; unverified figures: 10, 12345

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.