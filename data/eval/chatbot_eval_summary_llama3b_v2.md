# Chatbot evaluation summary

Model: `OllamaBackend / llama3.2:3b`  
Run at: 2026-10-01T15:46:08.390218+00:00  
Questions: 32  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 18/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 8/8 correct
- Citation fabrication flagged: 15/32 answers (47%)
- Answered by an input guard without calling the model: 8/32
- Answers carrying a figure no tool returned: 12/32

## Failures needing a look

- **lookup-1** (lookup): citation fabrication flagged; unverified figures: 12345, 67890
- **lookup-2** (lookup): tool selection: expected tool never called
- **lookup-3** (lookup): citation fabrication flagged; unverified figures: 12345, 67890
- **lookup-5** (lookup): citation fabrication flagged
- **compare-1** (compare): citation fabrication flagged; unverified figures: 40%, 1967
- **compare-2** (compare): citation fabrication flagged; unverified figures: 12345, 67890, 34567, 52,332
- **compare-3** (compare): citation fabrication flagged
- **trend-1** (trend): tool selection: expected tool never called
- **trend-2** (trend): tool selection: expected tool never called
- **thin-1** (thin_data): tool selection: expected tool never called; citation fabrication flagged; unverified figures: 123456, 789012
- **thin-2** (thin_data): citation fabrication flagged
- **consensus-1** (consensus): citation fabrication flagged; unverified figures: 12345
- **consensus-2** (consensus): citation fabrication flagged; unverified figures: 12345
- **lookup-6** (lookup): citation fabrication flagged; unverified figures: 123456, 789012
- **lookup-7** (lookup): citation fabrication flagged
- **lookup-8** (lookup): tool selection: expected tool never called; citation fabrication flagged; unverified figures: 15%
- **lookup-9** (lookup): citation fabrication flagged; unverified figures: 8.59, 7.73, 9.14, 123456, 24.1%, 23.4%, 789012
- **compare-4** (compare): citation fabrication flagged; unverified figures: 12345, 50%, 67890, 4.5%, 34567
- **trend-3** (trend): tool selection: expected tool never called; unverified figures: -0.04, -0.05, -0.07

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.