# Chatbot evaluation summary

Model: `OllamaBackend / llama3.2:3b`  
Run at: 2026-09-26T03:06:42.639484+00:00  
Questions: 23  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 12/16 correct (16 of 23 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 6/7 correct
- Citation fabrication flagged: 11/23 answers (48%)
- Answered by an input guard without calling the model: 7/23
- Answers carrying a figure no tool returned: 8/23

## Failures needing a look

- **lookup-1** (lookup): citation fabrication flagged; unverified figures: 123456, 987654
- **lookup-2** (lookup): tool selection: expected tool never called; citation fabrication flagged; unverified figures: 1234, 19, 5678, 0.45
- **lookup-3** (lookup): citation fabrication flagged; unverified figures: 123456, 789012
- **lookup-5** (lookup): tool selection: expected tool never called
- **compare-1** (compare): citation fabrication flagged; unverified figures: 123456, 789012, 345678
- **compare-3** (compare): citation fabrication flagged
- **trend-1** (trend): tool selection: expected tool never called; citation fabrication flagged; unverified figures: 12345, 67890
- **trend-2** (trend): citation fabrication flagged; unverified figures: 123456, 789012
- **oos-3** (out_of_scope): behavior: answered without declining or flagging no data
- **thin-1** (thin_data): tool selection: expected tool never called; citation fabrication flagged; unverified figures: 1234, 5678
- **thin-2** (thin_data): citation fabrication flagged; unverified figures: 12345, 67890
- **consensus-1** (consensus): citation fabrication flagged
- **consensus-2** (consensus): citation fabrication flagged

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.