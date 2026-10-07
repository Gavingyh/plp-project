# Chatbot evaluation summary

Model: `OpenAIBackend / openai/gpt-oss-120b`  
Intent classifier: `llama3.1:8b`  
Run at: 2026-10-06T17:11:09.845230+00:00  
Questions: 29  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 3/3 correct (3 of 29 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 0/1 correct
- Citation fabrication flagged: 0/29 answers (0%)
- Answered by an input guard without calling the model: 22/29
- Answers carrying a figure no tool returned: 1/29

## Failures needing a look

- **mixed-1** (mixed): behavior: didn't say it can't help with the unrelated part; unverified figures: 49,700

## Not automated: read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.