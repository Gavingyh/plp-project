# Chatbot evaluation summary

Model: `OpenAIBackend / gpt-6-luna`  
Intent classifier: `llama3.1:8b`  
Run at: 2026-10-24T10:05:23.777328+00:00  
Rechecked on 2026-10-25 from each stored answer: flags on the answer shown filled in for 0, refusal check changed for 0  
Questions: 32  
Errors (backend/network failures): 0

## Automated checks

- Tool selection: 23/24 correct (24 of 32 questions had an expected tool to check)
- Behavior (advice decline / no-data acknowledgement): 8/8 correct
- Citation fabrication flagged, in the model's first draft: 0/32 answers (0%)
- The same, in the answer shown: 0/32
- Answered by an input guard without calling the model: 6/32
- Answers carrying a figure no tool returned, in the model's first draft: 1/32
- The same, in the answer shown: 0/32

## Failures needing a look

- **compare-3** (compare): tool selection: expected tool never called; unverified figures: 24 (first draft only; the answer shown passes)

## Not automated: read the full transcript for these

Whether stated numbers are correct, and whether cited evidence is actually relevant to the question. See the results `.jsonl` beside this file for the full transcript, including every tool call and its raw result alongside the model's final answer.