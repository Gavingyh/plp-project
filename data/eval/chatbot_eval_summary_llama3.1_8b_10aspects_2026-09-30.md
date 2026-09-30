# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Run at: 2026-09-30T19:02:59.617613+00:00  
Questions: 23  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 13/16 correct (16 of 23 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 7/7 correct
- Citation fabrication flagged: 4/23 answers (17%)
- Answered by an input guard without calling the model: 7/23
- Answers carrying a figure no tool returned: 3/23

## Failures needing a look

- **lookup-2** (lookup): tool selection: expected tool never called; citation fabrication flagged
- **lookup-5** (lookup): citation fabrication flagged; unverified figures: 7%
- **compare-1** (compare): citation fabrication flagged; unverified figures: 40%, 12345, 4.5%, 67890
- **trend-1** (trend): citation fabrication flagged; unverified figures: 12345, 67890
- **thin-1** (thin_data): tool selection: expected tool never called
- **evidence-1** (evidence): tool selection: wrong bank: got None, expected 'DBS'

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.