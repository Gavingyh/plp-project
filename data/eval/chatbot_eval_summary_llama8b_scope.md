# Chatbot evaluation summary

Model: `OllamaBackend / llama3.1:8b`  
Intent classifier: `llama3.1:8b`  
Run at: 2026-10-03T19:44:41.606297+00:00  
Questions: 29  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 3/3 correct (3 of 29 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 0/1 correct
- Citation fabrication flagged: 3/29 answers (10%)
- Answered by an input guard without calling the model: 22/29
- Answers carrying a figure no tool returned: 2/29

## Failures needing a look

- **mixed-1** (mixed): behavior: didn't say it can't help with the unrelated part
- **ctrl-4** (control): citation fabrication flagged; unverified figures: 50%, 12345, 67890
- **ctrl-5** (control): citation fabrication flagged
- **ctrl-6** (control): citation fabrication flagged; unverified figures: 12345, 67890

## Not automated: read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.