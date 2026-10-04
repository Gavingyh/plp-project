# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Run at: 2026-10-01T15:20:50.251985+00:00  
Questions: 32  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 20/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 8/8 correct
- Citation fabrication flagged: 11/32 answers (34%)
- Answered by an input guard without calling the model: 8/32
- Answers carrying a figure no tool returned: 11/32

## Failures needing a look

- **lookup-1** (lookup): citation fabrication flagged; unverified figures: 40%
- **lookup-2** (lookup): tool selection: expected tool never called; citation fabrication flagged; unverified figures: 12345, 67890
- **lookup-5** (lookup): citation fabrication flagged; unverified figures: 10, 12
- **trend-1** (trend): citation fabrication flagged; unverified figures: 12345, 67890
- **thin-1** (thin_data): tool selection: expected tool never called
- **evidence-1** (evidence): tool selection: wrong bank: got None, expected 'DBS'
- **evidence-2** (evidence): unverified figures: 0.58
- **consensus-1** (consensus): citation fabrication flagged; unverified figures: 80
- **lookup-6** (lookup): citation fabrication flagged
- **lookup-8** (lookup): citation fabrication flagged; unverified figures: 14.4%, 12345, 83.4%, 67890
- **lookup-9** (lookup): citation fabrication flagged; unverified figures: 14%, 1.43
- **compare-4** (compare): citation fabrication flagged; unverified figures: 1.4%, 12.40, 12345, 0.8%, 25.50, 67890
- **compare-5** (compare): citation fabrication flagged; unverified figures: 123456, 789012, 345678
- **evidence-3** (evidence): tool selection: expected tool never called; citation fabrication flagged; unverified figures: 15%, 12345, 67890

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.