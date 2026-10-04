# Chatbot evaluation summary

Model: `OllamaBackend / llama3.2:3b`  
Run at: 2026-10-02T01:08:38.343287+00:00  
Questions: 32  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 18/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 8/8 correct
- Citation fabrication flagged: 2/32 answers (6%)
- Answered by an input guard without calling the model: 8/32
- Answers carrying a figure no tool returned: 3/32
- Evidence written without a search, removed by CHATBOT_ENFORCE_EVIDENCE: 16/32

## Failures needing a look

- **lookup-2** (lookup): tool selection: expected tool never called
- **compare-2** (compare): unverified figures: 1,762
- **trend-1** (trend): tool selection: expected tool never called
- **trend-2** (trend): tool selection: expected tool never called; unverified figures: -0.43
- **thin-1** (thin_data): tool selection: expected tool never called
- **consensus-1** (consensus): citation fabrication flagged
- **consensus-2** (consensus): citation fabrication flagged
- **lookup-8** (lookup): tool selection: expected tool never called
- **compare-4** (compare): unverified figures: 73.5%, 72.6%, 4.7%, 14.7%, 81.5%, 3.8%
- **trend-3** (trend): tool selection: expected tool never called

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.