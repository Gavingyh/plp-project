# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Run at: 2026-10-02T01:33:20.670711+00:00  
Questions: 32  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 19/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 8/8 correct
- Citation fabrication flagged: 10/32 answers (31%)
- Answered by an input guard without calling the model: 8/32
- Answers carrying a figure no tool returned: 6/32

## Failures needing a look

- **lookup-2** (lookup): tool selection: expected tool never called
- **lookup-3** (lookup): citation fabrication flagged; unverified figures: 63.8%, 60.7%, 12345
- **lookup-5** (lookup): citation fabrication flagged; unverified figures: 12345
- **compare-1** (compare): citation fabrication flagged; unverified figures: 12345
- **trend-1** (trend): citation fabrication flagged; unverified figures: 40, 40, 1.25
- **thin-1** (thin_data): tool selection: expected tool never called
- **evidence-1** (evidence): tool selection: wrong bank: got None, expected 'DBS'
- **lookup-6** (lookup): citation fabrication flagged; unverified figures: 15%, 134
- **lookup-7** (lookup): citation fabrication flagged
- **lookup-8** (lookup): tool selection: expected tool never called; citation fabrication flagged
- **compare-5** (compare): citation fabrication flagged
- **trend-3** (trend): citation fabrication flagged
- **evidence-3** (evidence): tool selection: expected tool never called; citation fabrication flagged; unverified figures: 10%

## Not automated — read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.